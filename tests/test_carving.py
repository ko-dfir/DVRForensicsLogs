import unittest
import sys
import os
import struct
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import scripts.forensic_engine as fe

def create_synthetic_rats_record(flag=0x14, timestamp=1577836800, maj=3, min_t=65, user=b"test_admin", payload_tail=b""):
    """
    Creates a valid synthetic RATS binary record with no sensitive evidence data.
    Header format:
      b'RATS' (4 bytes)
      flag: 4 bytes uint32 LE
      ts:   4 bytes uint32 LE
      maj:  2 bytes uint16 LE
      min:  2 bytes uint16 LE
      payload: 32 bytes (16 bytes user padded + 16 bytes) + payload_tail
    """
    header = struct.pack('<4sIIHH', b'RATS', flag, timestamp, maj, min_t)
    padded_user = user.ljust(16, b'\x00')
    rest_payload = (b'\x00' * 16) + payload_tail
    # Pad to total length of 96 bytes (standard minimum)
    total_data = header + padded_user + rest_payload
    if len(total_data) < 96:
        total_data += b'\x00' * (96 - len(total_data))
    return total_data


class TestCarving(unittest.TestCase):

    def setUp(self):
        # Create a temporary file with synthetic records at known offsets
        self.temp_file = tempfile.NamedTemporaryFile(delete=False)
        
        # 1. Write 1024 bytes of padding (like file header)
        self.temp_file.write(b'\x00' * 1024)
        self.record1_offset = 1024
        
        # Record 1: Synthetic Power On (Maj=3, Min=65)
        rec1 = create_synthetic_rats_record(
            flag=0x14,
            timestamp=1600000000,
            maj=3,
            min_t=65,
            user=b"synth_user1"
        )
        self.temp_file.write(rec1)
        self.record2_offset = self.record1_offset + len(rec1)
        
        # Record 2: Synthetic Motion Detection Start (Maj=1, Min=3) on Camera 5
        cam_payload = bytes([5]) + (b'\x00' * 15)
        rec2 = create_synthetic_rats_record(
            flag=0x14,
            timestamp=1600000100,
            maj=1,
            min_t=3,
            user=b"",
            payload_tail=cam_payload
        )
        self.temp_file.write(rec2)
        self.record3_offset = self.record2_offset + len(rec2)
        
        # Record 3: Synthetic Video Backup Export (Maj=3, Min=91)
        rec3 = create_synthetic_rats_record(
            flag=0x14,
            timestamp=1600000200,
            maj=3,
            min_t=91,
            user=b"synth_operator"
        )
        self.temp_file.write(rec3)
        self.end_offset = self.record3_offset + len(rec3)
        
        # Trailing bytes / random non-RATS garbage
        self.temp_file.write(b'GARBAGE_BYTES_NO_MAGIC' * 10)
        self.temp_file.close()

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_bounded_stream_parsing_and_absolute_offsets(self):
        """
        Verify that iter_stream_records correctly identifies synthetic records
        and accurately calculates their absolute file offsets.
        """
        records = list(fe.iter_stream_records(
            self.temp_file.name,
            start_offset=0,
            end_offset=self.end_offset + 500,
            region_name="TestSynthetic"
        ))

        self.assertEqual(len(records), 3)

        # Verify Record 1
        r1 = records[0]
        self.assertEqual(r1["offset"], self.record1_offset)
        self.assertEqual(r1["major_name"], "Operation")
        self.assertEqual(r1["minor_id"], 65)
        self.assertEqual(r1["macro"], "MINOR_START_DVR")
        self.assertEqual(r1["user"], "synth_user1")

        # Verify Record 2
        r2 = records[1]
        self.assertEqual(r2["offset"], self.record2_offset)
        self.assertEqual(r2["major_name"], "Alarm")
        self.assertEqual(r2["minor_id"], 3)
        self.assertEqual(r2["macro"], "MINOR_MOTDET_START")

        # Verify Record 3
        r3 = records[2]
        self.assertEqual(r3["offset"], self.record3_offset)
        self.assertEqual(r3["major_name"], "Operation")
        self.assertEqual(r3["minor_id"], 91)
        self.assertEqual(r3["macro"], "MINOR_LOCAL_RECFILE_OUTPUT")
        self.assertEqual(r3["user"], "synth_operator")

    def test_detect_image_structure_synthetic_raw(self):
        """
        Verify that detect_image_structure handles unstructured files gracefully
        without throwing exceptions or defaulting to hardcoded offsets.
        """
        st = fe.detect_image_structure(self.temp_file.name)
        self.assertFalse(st["fs_found"])
        self.assertIn("Not Detected", st["fs_signature"])
        self.assertGreater(len(st["scan_regions"]), 0)
        # Verify that carving across detected scan regions finds our 3 synthetic records
        reg_name, s_off, e_off = st["scan_regions"][0]
        records = list(fe.iter_stream_records(self.temp_file.name, s_off, e_off, reg_name))
        self.assertEqual(len(records), 3)

    def test_dynamic_device_fingerprint_no_fake_data(self):
        """
        Verify that extract_device_fingerprint does NOT return fake/hardcoded DVR serials
        when analyzing an image that lacks Hikvision hardware headers.
        """
        st = fe.detect_image_structure(self.temp_file.name)
        fp = fe.extract_device_fingerprint(self.temp_file.name, st)
        self.assertEqual(fp["model"], "Not Detected")
        self.assertEqual(fp["serial"], "Not Detected")
        self.assertEqual(fp["hdd_model"], "Not Detected")

if __name__ == '__main__':
    unittest.main()

