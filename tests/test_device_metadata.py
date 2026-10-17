import os

from scripts.device_metadata import (
    acquisition_metadata, dahua_database_metadata, tvt_filesystem_metadata,
    tvt_log_metadata,
)


def test_acquisition_and_vendor_metadata(tmp_path):
    image = tmp_path / "TVT1.001"
    data = bytearray(2 * 1024 * 1024)
    data[1024 * 1024:1024 * 1024 + 4] = b"SHFL"
    image.write_bytes(data)
    (tmp_path / "TVT1.001.txt").write_text(
        "Drive Model: WDC TEST\nDrive Serial Number: SERIAL123\n"
        "MD5 checksum: 0123456789abcdef0123456789abcdef\n",
        encoding="utf-8")
    acquisition = acquisition_metadata(image)
    assert acquisition["Disk model"][0] == "WDC TEST"
    assert acquisition["Disk serial"][0] == "SERIAL123"

    layout = tvt_filesystem_metadata(image)
    assert layout["Partition table"][0].startswith("None")
    assert layout["Filesystem"][0].startswith("Raw/headless")

    dahua = dahua_database_metadata([
        tmp_path / "ABC123_log.db", tmp_path / "IoTDataBase.db"])
    assert dahua["Recorder serial"][0] == "ABC123"
    assert dahua["Extracted databases"][0] == "2"


def test_tvt_log_summary():
    rows = [{
        "time_unix": 1700000000,
        "user": "admin",
        "category": "USER_ACTION",
        "raw_payload": "mlogtype:operation;action:2;ip:192.0.2.4;channels:{1}",
    }]
    metadata = tvt_log_metadata(rows)
    assert metadata["Recovered logs"][0] == "1"
    assert metadata["Distinct users"][0] == "1"
    assert metadata["Distinct IPs"][0] == "1"
    assert metadata["Action codes"][0] == "2"
