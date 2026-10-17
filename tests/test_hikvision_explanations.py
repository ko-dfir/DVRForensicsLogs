from scripts.engine_hikvision import explain_log_record, parse_record_details, resolve_log_type
import sqlite3

from scripts.engine_hikvision import HikvisionEngine


def test_known_sdk_code_explained_without_claiming_disk_layout_is_official():
    resolved = resolve_log_type(3, 65)
    explanation = explain_log_record({
        "major_name": resolved["major_name"],
        "minor_name": resolved["minor_name"],
        "major_id": 3,
        "minor_id": 65,
        "macro": resolved["minor_macro"],
        "status": resolved["status"],
        "channel": "2",
        "user": "admin",
        "ip": "192.0.2.1",
    })
    assert "MINOR_START_DVR" in explanation
    assert "0x0003/0x0041" in explanation
    assert "Channel 2" in explanation
    assert "User admin" in explanation
    assert "IP 192.0.2.1" in explanation
    assert "reverse engineering, not the SDK guide" in explanation


def test_unknown_code_is_not_presented_as_sdk_defined():
    explanation = explain_log_record({
        "major_name": "Operation",
        "minor_name": "Unknown Minor (0xbeef)",
        "major_id": 3,
        "minor_id": 0xbeef,
        "macro": None,
        "status": "Unknown Type",
    })
    assert "no verified SDK label" in explanation
    assert "0x0003/0xbeef" in explanation


def test_existing_hikvision_database_gains_explanation_columns(tmp_path):
    image = tmp_path / "empty.001"
    image.write_bytes(b"\x00" * 512)
    database = tmp_path / "logs.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE hikvision_logs (id INTEGER PRIMARY KEY, "
                           "timestamp TEXT, time_unix INTEGER, major_type TEXT, "
                           "minor_type TEXT, channel TEXT, username TEXT, ip TEXT, "
                           "details TEXT, offset INTEGER)")
    HikvisionEngine(str(image)).carve_to_sqlite(
        str(database), limit_bytes=512,
        structure={"file_size": 512, "scan_regions": [("test", 0, 512)]})
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(hikvision_logs)")}
    assert {"major_code", "minor_code", "sdk_macro", "interpretation_source",
            "explanation"} <= columns


def test_playback_does_not_invent_camera_when_raw_channel_absent():
    # Two matching DVR XML entries show Channel No.=0 for this payload shape.
    payload = bytes.fromhex(
        "61646d696e000000000000000000000000000000000000000000000000000000"
        "00000000000000000000590000000c000000010000000700000002000000")
    channel, user, ip, details = parse_record_details(3, 0x54, payload)
    assert channel == ""
    assert user == "admin"
    assert "Camera 1" not in details
