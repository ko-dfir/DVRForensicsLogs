import struct

from scripts.dvr_extractor import detect_brand_details
from scripts.image_io import SegmentedRawFile


def _split_image(tmp_path):
    image = bytearray(8192)
    image[510:512] = b"\x55\xaa"
    image[512:520] = b"EFI PART"
    image[512 + 72:512 + 80] = struct.pack("<Q", 2)
    image[512 + 80:512 + 84] = struct.pack("<I", 1)
    image[512 + 84:512 + 88] = struct.pack("<I", 128)
    entry = 1024
    image[entry:entry + 16] = b"\x01" + b"\x00" * 15
    image[entry + 32:entry + 40] = struct.pack("<Q", 8)
    image[entry + 40:entry + 48] = struct.pack("<Q", 15)
    image[entry + 56:entry + 66] = "Linux".encode("utf-16le")
    image[4096:4100] = b"XFSB"
    first = tmp_path / "evidence.001"
    first.write_bytes(image[:3000])
    (tmp_path / "evidence.002").write_bytes(image[3000:])
    return first, bytes(image)


def test_segmented_raw_random_access_across_boundary(tmp_path):
    first, image = _split_image(tmp_path)
    with SegmentedRawFile(first) as reader:
        assert reader.size == len(image)
        reader.seek(2996)
        assert reader.read(12) == image[2996:3008]


def test_dahua_detection_reads_xfs_from_later_raw_segment(tmp_path):
    first, _image = _split_image(tmp_path)
    result = detect_brand_details(str(first))
    assert result["brand"] == "DAHUA"
    assert result["confidence"] == "HIGH"
