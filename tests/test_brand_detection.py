import os
import struct
import tempfile
import unittest

from scripts.dvr_extractor import detect_brand_details


class TestBrandDetection(unittest.TestCase):
    def _image(self, data):
        handle = tempfile.NamedTemporaryFile(delete=False, suffix=".img")
        handle.write(data)
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.remove(handle.name))
        return handle.name

    def test_hikvision_filesystem_signature(self):
        path = self._image(b"\x00" * 528 + b"HIKVISION@HANGZHOU" + b"\x00" * 512)
        result = detect_brand_details(path)
        self.assertEqual(result["brand"], "HIKVISION")
        self.assertEqual(result["confidence"], "HIGH")

    def test_hikvision_standalone_log_signatures(self):
        path = self._image(b"RATS" + b"\x00" * 132 + b"RATS" + b"\x00" * 132
                           + b"RATS" + b"\x00" * 132)
        self.assertEqual(detect_brand_details(path)["brand"], "HIKVISION")

    def test_dahua_requires_gpt_partition_with_xfs(self):
        image = bytearray(8192)
        image[512:520] = b"EFI PART"
        image[512 + 72:512 + 80] = struct.pack("<Q", 2)
        image[512 + 80:512 + 84] = struct.pack("<I", 1)
        image[512 + 84:512 + 88] = struct.pack("<I", 128)
        entry = 1024
        image[entry:entry + 16] = b"\x01" + b"\x00" * 15
        image[entry + 32:entry + 40] = struct.pack("<Q", 8)
        image[entry + 40:entry + 48] = struct.pack("<Q", 15)
        name = "msftdata".encode("utf-16le")
        image[entry + 56:entry + 56 + len(name)] = name
        image[8 * 512:8 * 512 + 4] = b"XFSB"
        self.assertEqual(detect_brand_details(self._image(image))["brand"], "DAHUA")

    def test_tvt_payload_signature(self):
        path = self._image(b"\x00" * 256 + b"mlogtype:operation;action:2;\x00")
        self.assertEqual(detect_brand_details(path)["brand"], "TVT")

    def test_icatch_requires_fixed_hourly_index_cadence(self):
        image = bytearray(0x144 * 3 + 0x80)
        base_epoch = 1750377600
        for index in range(3):
            record = index * 0x144
            key = f"HOUR_20259:{index:02d}".encode("ascii") + b"\x00"
            image[record + 0x20:record + 0x20 + len(key)] = key
            image[record + 0x54:record + 0x58] = struct.pack(
                "<I", base_epoch + index * 3600)
        result = detect_brand_details(self._image(image))
        self.assertEqual(result["brand"], "ICATCH")
        self.assertIn("fixed-cadence HOUR", result["reason"])

    def test_unsigned_image_is_unknown_not_tvt(self):
        result = detect_brand_details(self._image(b"\x00" * 8192))
        self.assertEqual(result["brand"], "UNKNOWN")
        self.assertEqual(result["confidence"], "NONE")


if __name__ == "__main__":
    unittest.main()
