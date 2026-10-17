import json
import sqlite3

from scripts.dahua_analysis import _interpret, _timestamps, build_analysis_database


def test_dahua_timestamp_and_event_interpretation(tmp_path):
    source_path = tmp_path / "serial_log.db"
    source = sqlite3.connect(source_path)
    source.executescript("""
        CREATE TABLE user (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE operate (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE mode (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE log (id INTEGER PRIMARY KEY, timep INTEGER, data TEXT,
                          oid INTEGER, mid INTEGER, uid INTEGER);
        INSERT INTO user VALUES (1, 'admin');
        INSERT INTO operate VALUES (1, 'BlindStart');
        INSERT INTO mode VALUES (1, 'Log_Event');
    """)
    payload = {
        "EventAction": "Log_EventStart",
        "Log_Code": "appEventVideoBlind",
        "Log_Index": 2,
        "sys.StartTime": "2025-10-03 00:18:53",
    }
    source.execute("INSERT INTO log VALUES (?, ?, ?, ?, ?, ?)",
                   (7, 1759450733, json.dumps(payload), 1, 1, 1))
    source.commit()
    source.close()

    output_path = tmp_path / "analysis.db"
    result = build_analysis_database([source_path], output_path)
    assert result == {"database": str(output_path), "databases": 1, "logs": 1}

    analysis = sqlite3.connect(output_path)
    row = analysis.execute("""
        SELECT timestamp, timestamp_device, timezone_offset, category, event,
               action, username, channel, operation_code, source_database
        FROM dahua_logs
    """).fetchone()
    inventory = analysis.execute(
        "SELECT status, tables, source_database FROM dahua_databases").fetchone()
    analysis.close()
    assert row == (
        "2025-10-03 00:18:53 UTC", "2025-10-03 00:18:53",
        "UTC+00:00 (inferred)", "Video", "Video tampering started",
        "Start", "admin", "2", "BlindStart", "serial_log.db",
    )
    assert inventory[0] == "ok"
    assert "log" in inventory[1]
    assert inventory[2] == "serial_log.db"


def test_exported_dahua_configuration_index_is_not_a_camera():
    category, event, _, _, channel, _ = _interpret(
        "Log_Config", "Log_SaveConfig", {"Log_Index": 3, "Group": "user"})
    assert (category, event, channel) == ("Configuration", "Save configuration", None)


def test_exported_dahua_end_time_does_not_create_false_timezone():
    # Observed in the exported DB: LossEnd.timep is 60 s after com.EndTime.
    assert _timestamps(1774973557, {"com.EndTime": "2026-03-31 16:11:37"}) == (
        "2026-03-31 16:12:37 UTC", "2026-03-31 16:11:37", "")


def test_exported_dahua_logout_uses_explicit_log_time():
    assert _timestamps(1774973762, {"Log_Time": "2026-03-31 16:16:02"}) == (
        "2026-03-31 16:16:02 UTC", "2026-03-31 16:16:02",
        "UTC+00:00 (inferred)")


def test_exported_dahua_field_explanations_keep_uncertainty():
    *_, config_text, channel, _ = _interpret("Log_Config", "Log_SaveConfig", {
        "Name": "VideoInDenoise", "Log_Index": 3,
        "Detail": [{"ID": "2DDenoise", "Value": [50, 90]}],
    })
    assert "VideoInDenoise" in config_text
    assert "2DDenoise: [50, 90]" in config_text
    assert "old/new unverified" in config_text
    assert channel is None

    *_, user_text, _, _ = _interpret("Log_Ugm", "Log_ModUser", {
        "User": "target", "LoginUser": "admin",
        "Authority": {"Monitor": [{"Old": False, "New": True}]},
    })
    assert "Target account: target" in user_text
    assert "Acting account: admin" in user_text
    assert "Monitor permissions: 1 enabled" in user_text
