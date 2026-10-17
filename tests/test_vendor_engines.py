import os
import struct
import tempfile
import unittest

from scripts.engine_dahua import OffsetFile
from scripts.engine_tvt import TVTEngine
from scripts.engine_icatch import ICatchEngine


class TestVendorEngines(unittest.TestCase):
    def test_icatch_extracts_only_valid_hourly_index_records(self):
        image_data = bytearray(0x144 * 3 + 0x80)
        base_epoch = 1750377600
        for index in range(3):
            record = index * 0x144
            key = f"HOUR_20259:{index:02d}".encode() + b"\x00"
            image_data[record + 0x20:record + 0x20 + len(key)] = key
            image_data[record + 0x54:record + 0x58] = struct.pack(
                "<I", base_epoch + index * 3600)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as image:
            image.write(image_data)
            path = image.name
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        rows = ICatchEngine(path).extract_timeline()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["record_size"], 0x144)
        self.assertEqual(rows[-1]["timestamp"], "2025-06-20 02:00:00 UTC")

    def test_dahua_partition_view_tracks_position_for_raw_images(self):
        with tempfile.NamedTemporaryFile(delete=False) as image:
            image.write(b"prefix" + b"XFSB" + b"payload")
            path = image.name
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        with open(path, "rb") as raw:
            view = OffsetFile(raw, 6)
            self.assertEqual(view.read(4), b"XFSB")
            self.assertEqual(view.tell(), 4)
            view.seek(0)
            self.assertEqual(view.tell(), 0)
            self.assertEqual(view.read(), b"XFSBpayload")

    def test_tvt_uses_structured_timestamp_length_and_username(self):
        timestamp = 1745074191
        payload = b"mlogtype:operation;action:28;ip:192.0.2.1"
        prefix = bytearray(b"\xaa\xab" + b"\x00" * 46)
        prefix[16:20] = struct.pack("<I", timestamp)
        username = b"admin"
        record = bytes(prefix) + bytes([len(username)]) + username
        record += struct.pack("<H", len(payload)) + payload
        with tempfile.NamedTemporaryFile(delete=False, suffix=".img") as image:
            image.write(record)
            path = image.name
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))

        rows = TVTEngine(path).extract_logs(limit_bytes=len(record))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["time_unix"], timestamp)
        self.assertEqual(rows[0]["user"], "admin")
        self.assertEqual(rows[0]["raw_payload"], payload.decode())
        self.assertEqual(rows[0]["offset"], len(prefix) + 1 + len(username) + 2)


if __name__ == "__main__":
    unittest.main()
