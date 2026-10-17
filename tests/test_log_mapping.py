import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import scripts.forensic_engine as fe
import scripts.carving_utils as cu

class TestLogMapping(unittest.TestCase):

    def test_major_minor_composite_resolution(self):
        # 1. Alarm Motion Detection
        res_alarm = fe.resolve_log_type(1, 3)
        self.assertEqual(res_alarm["major_name"], "Alarm")
        self.assertEqual(res_alarm["minor_macro"], "MINOR_MOTDET_START")
        self.assertIn("Motion", res_alarm["minor_name"])

        # 2. Operation Power On
        res_pwr = fe.resolve_log_type(3, 65)
        self.assertEqual(res_pwr["major_name"], "Operation")
        self.assertEqual(res_pwr["minor_macro"], "MINOR_START_DVR")
        self.assertIn("Power On", res_pwr["minor_name"])

        # 3. Information S.M.A.R.T.
        res_smart = fe.resolve_log_type(4, 162)
        self.assertEqual(res_smart["major_name"], "Information")
        self.assertEqual(res_smart["minor_macro"], "MINOR_SMART_INFO")

    def test_minor_collision_different_majors(self):
        """
        Verify that the same minor numeric value (65 / 0x41) resolves to completely different events
        under different major types, proving the composite key (major, minor) is necessary.
        """
        # Minor 65 in Alarm -> MINOR_SMART_OBJECT_REMOVAL_END
        alarm_65 = fe.resolve_log_type("Alarm", 65)
        self.assertEqual(alarm_65["minor_macro"], "MINOR_SMART_OBJECT_REMOVAL_END")

        # Minor 65 in Operation -> MINOR_START_DVR (Power On)
        op_65 = fe.resolve_log_type("Operation", 65)
        self.assertEqual(op_65["minor_macro"], "MINOR_START_DVR")

        # Minor 65 in Exception -> MINOR_RECORD_OVERFLOW
        exc_65 = fe.resolve_log_type("Exception", 65)
        self.assertEqual(exc_65["minor_macro"], "MINOR_RECORD_OVERFLOW")

        # Confirm they are all distinct
        self.assertNotEqual(alarm_65["minor_macro"], op_65["minor_macro"])
        self.assertNotEqual(op_65["minor_macro"], exc_65["minor_macro"])

    def test_unknown_major_minor_preservation(self):
        """
        Verify that unmapped or unknown types preserve their raw numeric/hex values verbatim.
        """
        res_unk_min = fe.resolve_log_type(3, 0xbeef)
        self.assertEqual(res_unk_min["major_name"], "Operation")
        self.assertEqual(res_unk_min["minor_id"], 0xbeef)
        self.assertEqual(res_unk_min["minor_hex"], "0xbeef")
        self.assertIn("0xbeef", res_unk_min["minor_name"])
        self.assertEqual(res_unk_min["status"], "Unknown Type")

        res_unk_maj = fe.resolve_log_type(99, 1)
        self.assertEqual(res_unk_maj["major_id"], 99)
        self.assertEqual(res_unk_maj["major_hex"], "0x0063")

    def test_regression_existing_supported_types(self):
        """
        Verify backwards compatibility with existing carving_utils.get_MinorType()
        """
        self.assertEqual(cu.get_MinorType("Operation", "4100"), "Power On")
        self.assertEqual(cu.get_MinorType("Operation", "5000"), "Local: Login")
        self.assertEqual(cu.get_MinorType("Alarm", "0300"), "Start Motion Detection")
        self.assertEqual(cu.get_MinorType("Exception", "2200"), "Illegal Login")
        self.assertEqual(cu.get_MinorType("Information", "a100"), "HDD Information")

    def test_newly_discovered_types(self):
        """
        Verify that newly added SDK types from evidence image resolve accurately.
        """
        # 0x44 -> Reboot DVR
        reboot = fe.resolve_log_type(3, 68)
        self.assertEqual(reboot["minor_macro"], "MINOR_REBOOT_DVR")

        # 0x54 -> Playback by time
        playback = fe.resolve_log_type(3, 84)
        self.assertEqual(playback["minor_macro"], "MINOR_LOCAL_PLAYBYTIME")

        # 0x5b -> Backup/Export video files
        export_rec = fe.resolve_log_type(3, 91)
        self.assertEqual(export_rec["minor_macro"], "MINOR_LOCAL_RECFILE_OUTPUT")

        # 0xb8 in Info -> Client Service Logout
        client_logout = fe.resolve_log_type(4, 184)
        self.assertEqual(client_logout["minor_macro"], "MINOR_CLIENT_LOGOUT")

if __name__ == '__main__':
    unittest.main()
