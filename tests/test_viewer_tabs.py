import os
import sys
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
import scripts.forensic_engine as fe
import scripts.carving_utils as cu
from hikvision_forensic_viewer import ForensicViewerWindow

app = QApplication.instance()
if app is None:
    app = QApplication(sys.argv)


class TestViewerTabs(unittest.TestCase):
    def setUp(self):
        self.window = ForensicViewerWindow()
        # Synthetic mock records (no PII, fully synthetic)
        self.mock_records = [
            {
                "number": 1,
                "time_utc": "2026-01-01 10:00:00",
                "timestamp": 1767261600,
                "major_id": 3,
                "major_hex": "0x0003",
                "major_name": "Operation",
                "major_macro": "MAJOR_OPERATION",
                "minor_id": 91,
                "minor_hex": "0x005b",
                "minor_name": "Local: Backup/Export Video Files",
                "macro": "MINOR_LOCAL_RECFILE_OUTPUT",
                "channel": 2,
                "user": "admin",
                "ip": "127.0.0.1",
                "details": "Channel 2 (Camera 02) Video Exported to External Media",
                "offset": 41472,
                "region": "Alternative Residual Region",
                "status": "Fully Parsed",
                "raw_payload_hex": "00" * 136
            },
            {
                "number": 2,
                "time_utc": "2026-01-01 10:05:00",
                "timestamp": 1767261900,
                "major_id": 3,
                "major_hex": "0x0003",
                "major_name": "Operation",
                "major_macro": "MAJOR_OPERATION",
                "minor_id": 84,
                "minor_hex": "0x0054",
                "minor_name": "Local: Playback by Time",
                "macro": "MINOR_LOCAL_PLAYBYTIME",
                "channel": 1,
                "user": "admin",
                "ip": "127.0.0.1",
                "details": "Channel 1 Playback Started",
                "offset": 41608,
                "region": "Alternative Residual Region",
                "status": "Fully Parsed",
                "raw_payload_hex": "00" * 136
            },
            {
                "number": 3,
                "time_utc": "2026-01-01 10:10:00",
                "timestamp": 1767262200,
                "major_id": 2,
                "major_hex": "0x0002",
                "major_name": "Exception",
                "major_macro": "MAJOR_EXCEPTION",
                "minor_id": 34,
                "minor_hex": "0x0022",
                "minor_name": "Illegal Login",
                "macro": "MINOR_ILLEGAL_ACCESS",
                "channel": 0,
                "user": "anonymous",
                "ip": "192.168.1.100",
                "details": "Authentication Failed - Invalid Credentials",
                "offset": 41744,
                "region": "Alternative Residual Region",
                "status": "Fully Parsed",
                "raw_payload_hex": "00" * 136
            },
            {
                "number": 4,
                "time_utc": "2026-01-01 10:15:00",
                "timestamp": 1767262500,
                "major_id": 1,
                "major_hex": "0x0001",
                "major_name": "Alarm",
                "major_macro": "MAJOR_ALARM",
                "minor_id": 3,
                "minor_hex": "0x0003",
                "minor_name": "Start Motion Detection",
                "macro": "MINOR_MOTDET_START",
                "channel": 3,
                "user": "",
                "ip": "",
                "details": "Motion Grid Triggered on Channel 3",
                "offset": 41880,
                "region": "Declared Active Ring-Buffer",
                "status": "Fully Parsed",
                "raw_payload_hex": "00" * 136
            },
            {
                "number": 5,
                "time_utc": "2026-01-01 10:20:00",
                "timestamp": 1767262800,
                "major_id": 4,
                "major_hex": "0x0004",
                "major_name": "Information",
                "major_macro": "MAJOR_INFORMATION",
                "minor_id": 163,
                "minor_hex": "0x00a3",
                "minor_name": "Start Record",
                "macro": "MINOR_REC_START",
                "channel": 3,
                "user": "",
                "ip": "",
                "details": "Channel 3 Recording Started (Motion/Alarm Trigger, Main Stream)",
                "offset": 42016,
                "region": "Declared Active Ring-Buffer",
                "status": "Fully Parsed",
                "raw_payload_hex": "00" * 136
            },
            {
                "number": 6,
                "time_utc": "2026-01-01 10:25:00",
                "timestamp": 1767263100,
                "major_id": 4,
                "major_hex": "0x0004",
                "major_name": "Information",
                "major_macro": "MAJOR_INFORMATION",
                "minor_id": 164,
                "minor_hex": "0x00a4",
                "minor_name": "Stop Record",
                "macro": "MINOR_REC_STOP",
                "channel": 3,
                "user": "",
                "ip": "",
                "details": "Channel 3 Recording Stopped",
                "offset": 42152,
                "region": "Declared Active Ring-Buffer",
                "status": "Fully Parsed",
                "raw_payload_hex": "00" * 136
            },
            {
                "number": 7,
                "time_utc": "2026-01-01 10:30:00",
                "timestamp": 1767263400,
                "major_id": 3,
                "major_hex": "0x0003",
                "major_name": "Operation",
                "major_macro": "MAJOR_OPERATION",
                "minor_id": 68,
                "minor_hex": "0x0044",
                "minor_name": "Local: Reboot DVR",
                "macro": "MINOR_REBOOT_DVR",
                "channel": 0,
                "user": "admin",
                "ip": "",
                "details": "DVR System Reboot Initiated",
                "offset": 42288,
                "region": "Alternative Residual Region",
                "status": "Fully Parsed",
                "raw_payload_hex": "00" * 136
            }
        ]

    def tearDown(self):
        self.window.close()

    def test_no_partially_parsed_in_db_or_code(self):
        """Verify that zero records or types in JSON or Python have 'partially parsed'."""
        db = fe.get_log_db()
        for maj_k, maj_v in db.get("major_types", {}).items():
            for min_k, min_v in maj_v.get("minors", {}).items():
                st = min_v.get("status", "")
                self.assertNotIn("partially", st.lower(), f"Found partially parsed in JSON {maj_k}:{min_k}")
                self.assertNotIn("not parsed", st.lower(), f"Found not parsed in JSON {maj_k}:{min_k}")

        for maj, minors in cu.minor_type_dict.items():
            for mkey, mval in minors.items():
                if isinstance(mval, list) and len(mval) > 1:
                    st = mval[1]
                    self.assertNotIn("partially", st.lower(), f"Found partially parsed in cu.minor_type_dict: {maj}:{mkey}")
                    self.assertNotIn("not parsed", st.lower(), f"Found not parsed in cu.minor_type_dict: {maj}:{mkey}")

    def test_on_carving_finished_populates_all_tabs(self):
        """Verify that passing carved records properly updates all 5 tabs without crashing."""
        self.window.on_records_chunk_received(self.mock_records)
        self.window.on_carving_finished(len(self.mock_records))

        # Check Tab 1 (Logs)
        self.assertEqual(self.window.table_logs.rowCount(), len(self.mock_records))
        self.assertIn("Records: 7", self.window.lbl_record_count.text())

        # Check Tab 2 (Exfiltration & Security)
        self.assertGreater(self.window.table_exfil.rowCount(), 0)
        self.assertIn("Video File Exports (1)", self.window.btn_filter_exfil.text())
        self.assertIn("Video Playbacks (1)", self.window.btn_filter_playback.text())
        self.assertIn("Illegal Logins (1)", self.window.btn_filter_illegal.text())
        self.assertIn("Reboots / Power (1)", self.window.btn_filter_reboots.text())
        self.assertIn("All Security Events", self.window.btn_filter_all_sec.text())

        # Check Tab 3 (Camera & Motion)
        self.assertGreater(self.window.table_cam.rowCount(), 0)
        # Verify combo options include Camera 1, 2, 3
        cam_items = [self.window.combo_cam_select.itemText(i) for i in range(self.window.combo_cam_select.count())]
        self.assertIn("All Active Cameras", cam_items)
        self.assertIn("Camera 1", cam_items)
        self.assertIn("Camera 2", cam_items)
        self.assertIn("Camera 3", cam_items)

        # Check Tab 4 (Stats)
        self.assertGreater(self.window.table_stats.rowCount(), 0)
        self.assertIn("Distinct Types:", self.window.lbl_stats_summary.text())

    def test_exfil_tab_filters_and_inspector(self):
        """Verify dynamic filtering on Tab 2 and inspector population."""
        self.window.on_records_chunk_received(self.mock_records)
        self.window.on_carving_finished(len(self.mock_records))

        # Click Export filter
        self.window.quick_filter("Export")
        self.assertEqual(self.window.table_exfil.rowCount(), 1)
        self.assertIn("Backup/Export", self.window.table_exfil.item(0, 2).text())
        self.assertIn("Exported to External Media", self.window.txt_exfil_inspector.toPlainText())
        self.assertNotIn("partially parsed", self.window.txt_exfil_inspector.toPlainText().lower())

        # Click Playback filter
        self.window.quick_filter("Playback")
        self.assertEqual(self.window.table_exfil.rowCount(), 1)
        self.assertIn("Playback", self.window.table_exfil.item(0, 2).text())
        self.assertIn("Playback Started", self.window.txt_exfil_inspector.toPlainText())

        # Click Illegal filter
        self.window.quick_filter("Illegal")
        self.assertEqual(self.window.table_exfil.rowCount(), 1)
        self.assertIn("Illegal Login", self.window.table_exfil.item(0, 2).text())
        self.assertIn("Authentication Failed", self.window.txt_exfil_inspector.toPlainText())

    def test_camera_tab_filtering_and_inspector(self):
        """Verify camera tab filtering by camera channel and event type, ensuring 'All Active Cameras' works."""
        self.window.on_records_chunk_received(self.mock_records)
        self.window.on_carving_finished(len(self.mock_records))

        # 1. Default "All Active Cameras" should NOT be empty (bug fix check)
        self.window.combo_cam_select.setCurrentText("All Active Cameras")
        self.window.combo_cam_event_type.setCurrentText("All Camera Events")
        self.window.populate_camera_tab()
        # Records 4 (Motion, ch 3), 5 (Rec Start, ch 3), 6 (Rec Stop, ch 3)
        self.assertEqual(self.window.table_cam.rowCount(), 3)
        self.assertIn("Camera 03", self.window.txt_cam_inspector.toPlainText())

        # 2. Filter by Motion Detection Only
        self.window.combo_cam_event_type.setCurrentText("Motion Detection Only")
        self.window.populate_camera_tab()
        self.assertEqual(self.window.table_cam.rowCount(), 1)
        self.assertEqual(self.window.table_cam.item(0, 3).text(), "Start Motion Detection")

        # 3. Filter by Video Recording Only
        self.window.combo_cam_event_type.setCurrentText("Video Recording Only")
        self.window.populate_camera_tab()
        self.assertEqual(self.window.table_cam.rowCount(), 2)

    def test_stats_tab_filter_and_double_click(self):
        """Verify searching stats and double-clicking to jump to All Logs explorer."""
        self.window.on_records_chunk_received(self.mock_records)
        self.window.on_carving_finished(len(self.mock_records))

        # Filter stats by "Motion"
        self.window.edit_stats_filter.setText("Motion")
        visible_rows = [r for r in range(self.window.table_stats.rowCount()) if not self.window.table_stats.isRowHidden(r)]
        self.assertEqual(len(visible_rows), 1)

        # Clear filter
        self.window.edit_stats_filter.setText("")

        # Double click the first row
        self.window.on_stat_row_double_clicked(0, 3)
        # Should switch to Tab 1 (Logs) and set search text
        self.assertEqual(self.window.tabs.currentWidget(), self.window.tab_logs)
        self.assertTrue(len(self.window.edit_filter.text()) > 0)


if __name__ == '__main__':
    unittest.main()
