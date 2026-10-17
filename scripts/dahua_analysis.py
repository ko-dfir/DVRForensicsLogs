"""Normalize and interpret Dahua SQLite artefacts without changing originals."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing
from scripts.cancellation import check_cancelled


MODE_LABELS = {
    "Log_Ugm": "Account",
    "Log_Event": "Alarm/Event",
    "Log_Config": "Configuration",
    "Log_Recctrl": "Record mode",
    "Log_RecOpr": "Recording operation",
    "LOG_RemoteInfo": "Remote information",
}

EVENTS = {
    "Log_Login": ("Account", "Login", "User logged in through the local interface."),
    "Log_NetLogin": ("Account", "Network login", "A network login was recorded; the source address may be the recorder itself."),
    "Log_Logout": ("Account", "Logout", "User logged out."),
    "Log_UserUnauth": ("Security", "Illegal login", "Authentication failed because invalid credentials were supplied."),
    "Log_AddUser": ("Account", "Add user", "A user account was created."),
    "Log_DelUser": ("Account", "Delete user", "A user account was deleted."),
    "Log_ModUser": ("Account", "Modify user", "A user's permissions or account settings were modified."),
    "Log_AddGroup": ("Account", "Add group", "A user group was created."),
    "LossStart": ("Video", "Video loss started", "The recorder reported loss of a camera video signal; the cause is not established by this log."),
    "LossEnd": ("Video", "Video loss ended", "The lost camera signal was restored."),
    "BlindStart": ("Video", "Video tampering started", "The recorder reported a video-blind condition; the cause is not established by this log."),
    "BlindEnd": ("Video", "Video tampering ended", "The camera view returned from a tampered state."),
    "NetAbortStart": ("Network", "Camera offline", "An enrolled IP camera disconnected from the recorder."),
    "NetAbortEnd": ("Network", "Camera online", "An enrolled IP camera reconnected to the recorder."),
    "InlAlmStart": ("Intelligent", "AI alarm", "An intelligent rule fired; inspect the payload and AI databases for face, human, vehicle, or tripwire context."),
    "Log_SaveConfig": ("Configuration", "Save configuration", "The recorder logged a configuration save; repeated identical entries do not prove repeated human changes."),
    "Log_AutoRec": ("Record mode", "Automatic recording", "Recording follows the configured schedule."),
    "Log_ManualRec": ("Record mode", "Manual recording", "Continuous manual recording was enabled."),
    "Log_ManualStop": ("Record mode", "Recording disabled", "Manual recording was stopped or recording was disabled."),
    "Log_RecStart": ("Recording", "Recording started", "A recording operation started."),
    "Log_RecStop": ("Recording", "Recording stopped", "A recording operation stopped."),
    "Log_RecSearch": ("Playback", "Recording search", "The user searched recorded video."),
    "Log_RecBack": ("Playback", "Recording backup", "Recorded video was exported or backed up."),
    "Log_RecFast": ("Playback", "Fast playback", "Recorded video was played at increased speed."),
    "Log_RecPause": ("Playback", "Playback paused", "Playback of recorded video was paused."),
    "TempHigh": ("Hardware", "High temperature", "The recorder reported a high-temperature alarm."),
}

CODE_FALLBACKS = {
    "appEventVideoBlind": ("Video", "Video tampering", "The camera view was obstructed or redirected."),
    "appEventVideoLoss": ("Video", "Video loss", "The recorder lost a camera video signal."),
    "appEventNetDisconnect": ("Network", "Network disconnected", "A network connection was interrupted."),
    "com.TemperatureAlarm": ("Hardware", "Temperature alarm", "The recorder reported a temperature alarm."),
}

# On-disk JSON vocabulary; not asserted to be the live NetSDK LOG_ITEM layout.
FIELD_LABELS = {
    'Log_Code': 'Original device event identifier',
    'EventAction': 'Original event state; Log_EventStart/Log_EventEnd indicate start/end',
    'Log_UserName': 'Recorded account name', 'LoginUser': 'Recorded acting/login account',
    'Log_IP_Address': 'Recorded source address; not independently verified',
    'LoginIPAddr': 'Recorded login address; not independently verified',
    'Log_FailReason': 'Device-provided authentication failure reason',
    'Name': 'Configuration setting name', 'Log_Name': 'Original log/setting name',
    'Group': 'Configuration group', 'SubName': 'Configuration subsetting',
    'User': 'Recorded user/target account; interpret in event context',
    'IP': 'Recorded source field; not proof of an external connection',
    'Log_LinkRec': 'Linked recording references, retained in stored order',
    'Log_LinkRecTime': 'Linked-recording time text',
    'Log_Time': 'Device log time text', 'sys.StartTime': 'Device start time text',
    'com.EndTime': 'Device end time text; may differ from row timep',
    'StartTime': 'Original start time text', 'EndTime': 'Original end time text',
    'Detail': 'Setting IDs/values; value-array old/new ordering is not established',
    'Authority': 'Permission changes with explicit Old/New flags when present',
    'ReserveType': 'Reserved type value; numeric meaning is not established',
}


def explain_payload_fields(payload, mode):
    """Expose every JSON key, including unknowns, without losing its value."""
    if not isinstance(payload, dict):
        return '[]'
    result = []
    for field, value in payload.items():
        meaning = FIELD_LABELS.get(field, 'Original field; semantic meaning not established')
        if field == 'Log_Index':
            meaning = ('Device camera/channel index; original numbering retained' if mode == 'Log_Event'
                       else 'Configuration/event index; not assumed to be a camera')
        result.append({'field': field, 'value': value, 'meaning': meaning})
    return json.dumps(result, ensure_ascii=False, indent=2)


def _quoted(value):
    return '"' + str(value).replace('"', '""') + '"'


def _lookup(connection, table):
    try:
        return dict(connection.execute(
            f"SELECT id, name FROM {_quoted(table)}").fetchall())
    except sqlite3.DatabaseError:
        return {}


def _device_time(payload):
    if not isinstance(payload, dict):
        return "", None
    for key in ("sys.StartTime", "com.EndTime", "Log_Time", "Log_LinkRecTime", "StartTime", "EndTime"):
        value = payload.get(key)
        if value:
            try:
                return str(value), datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return str(value), None
    return "", None


def _timestamps(epoch, payload):
    try:
        utc_value = datetime.fromtimestamp(int(epoch), timezone.utc)
        utc_text = utc_value.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError, OSError, OverflowError):
        return "", "", ""
    device_text, device_value = _device_time(payload)
    offset_text = ""
    if device_value:
        delta_seconds = (device_value - utc_value.replace(tzinfo=None)).total_seconds()
        minutes = round(delta_seconds / 900) * 15
        # A stale event-end field must not be interpreted as a one-minute UTC offset.
        if -14 * 60 <= minutes <= 14 * 60 and abs(delta_seconds - minutes * 60) <= 5:
            sign = "+" if minutes >= 0 else "-"
            absolute = abs(minutes)
            offset_text = f"UTC{sign}{absolute // 60:02d}:{absolute % 60:02d} (inferred)"
    return utc_text, device_text, offset_text


def _interpret(mode, operation, payload):
    if not isinstance(payload, dict):
        payload = {}
    code = str(payload.get("Log_Code") or "")
    category, event, explanation = EVENTS.get(
        operation, CODE_FALLBACKS.get(code, (
            MODE_LABELS.get(mode, mode or "Unknown"),
            operation or code or "Unknown event",
            "Unmapped Dahua event; the original identifiers and JSON are preserved.",
        )))
    details = []
    if operation == "Log_SaveConfig":
        for key, label in (("Name", "Setting"), ("Log_Name", "Log name"),
                           ("Group", "Group field"), ("User", "Recorded user"),
                           ("IP", "Source field"), ("SubName", "Subsetting")):
            if payload.get(key):
                details.append(f"{label}: {payload[key]}")
        if payload.get("Log_Index") is not None:
            details.append(f"Setting index: {payload['Log_Index']} (meaning unverified)")
        for item in payload.get("Detail", []) if isinstance(payload.get("Detail"), list) else []:
            if isinstance(item, dict) and item.get("ID"):
                values = item.get("Value")
                details.append(f"{item['ID']}: {values!r} (stored order; old/new unverified)")
    elif operation in ("Log_NetLogin", "Log_Logout", "Log_UserUnauth"):
        actor = payload.get("Log_UserName") or payload.get("LoginUser")
        address = payload.get("Log_IP_Address") or payload.get("LoginIPAddr")
        if actor:
            details.append(f"Account: {actor}")
        if address:
            details.append(f"Recorded address: {address}")
        if payload.get("Log_FailReason"):
            details.append(f"Device reason: {payload['Log_FailReason']}")
    elif operation in ("Log_AddUser", "Log_DelUser", "Log_ModUser"):
        target = payload.get("User") or payload.get("Log_UserName")
        if target:
            details.append(f"Target account: {target}")
        if payload.get("LoginUser"):
            details.append(f"Acting account: {payload['LoginUser']}")
        authority = payload.get("Authority")
        if isinstance(authority, dict):
            for group, changes in authority.items():
                if isinstance(changes, list):
                    enabled = sum(isinstance(v, dict) and v.get("Old") is False and v.get("New") is True for v in changes)
                    disabled = sum(isinstance(v, dict) and v.get("Old") is True and v.get("New") is False for v in changes)
                    details.append(f"{group} permissions: {enabled} enabled, {disabled} disabled")
    elif mode == "Log_Event":
        if payload.get("Log_Code"):
            details.append(f"Device code: {payload['Log_Code']}")
        if payload.get("Log_Index") is not None:
            details.append(f"Camera channel: {payload['Log_Index']}")
        if payload.get("Log_LinkRec") is not None:
            details.append(f"Linked recording indexes: {payload['Log_LinkRec']!r}")
        if payload.get("ReserveType") is not None:
            details.append(f"ReserveType: {payload['ReserveType']} (numeric meaning unverified)")
    if details:
        explanation = explanation.rstrip(".") + ". " + "; ".join(details).rstrip(".") + "."
    action_value = str(payload.get("EventAction") or "")
    if action_value == "Log_EventStart":
        action = "Start"
    elif action_value == "Log_EventEnd":
        action = "End"
    else:
        action = action_value
    # Configuration records also contain Log_Index, but there it is not a camera.
    channel = payload.get("Log_Index") if mode == "Log_Event" else None
    return category, event, action, explanation, channel, code


def build_analysis_database(database_paths, output_path, progress_callback=None, cancelled=None):
    """Inventory every SQLite DB and normalize all compatible Dahua log rows."""
    check_cancelled(cancelled)
    # Connections must close on cancellation so Windows releases all files.
    with closing(sqlite3.connect(str(output_path))) as output, output:
        return _build_analysis_database(database_paths, str(output_path), output,
                                        progress_callback, cancelled)


def _build_analysis_database(database_paths, output_path, output, progress_callback, cancelled):
    output.executescript("""
        DROP TABLE IF EXISTS dahua_databases;
        DROP TABLE IF EXISTS dahua_logs;
        CREATE TABLE dahua_databases (
            id INTEGER PRIMARY KEY, source_database TEXT, size_bytes INTEGER,
            status TEXT, tables TEXT, row_counts TEXT
        );
        CREATE TABLE dahua_logs (
            id INTEGER PRIMARY KEY,
            timestamp TEXT, timestamp_device TEXT, timezone_offset TEXT,
            time_unix INTEGER, category TEXT, event TEXT, action TEXT,
            explanation TEXT, username TEXT, channel TEXT,
            mode_code TEXT, operation_code TEXT, log_code TEXT,
            source_database TEXT, source_row_id INTEGER, raw_json TEXT
            , actor_account TEXT, source_ip TEXT, config_target TEXT, field_explanations TEXT
        );
        CREATE INDEX dahua_logs_time ON dahua_logs(time_unix);
        CREATE INDEX dahua_logs_event ON dahua_logs(event);
        CREATE INDEX dahua_logs_source ON dahua_logs(source_database);
    """)
    paths = [str(path) for path in database_paths]
    total = max(1, len(paths))
    inserted = 0
    for index, path in enumerate(paths, 1):
        check_cancelled(cancelled)
        source = None
        status, tables_json, counts_json = "ok", "[]", "{}"
        try:
            source = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
            source.set_progress_handler(lambda: int(bool(cancelled and cancelled())), 1000)
            tables = [row[0] for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            counts = {}
            for table in tables:
                check_cancelled(cancelled)
                try:
                    counts[table] = source.execute(
                        f"SELECT count(*) FROM {_quoted(table)}").fetchone()[0]
                except sqlite3.DatabaseError as exc:
                    check_cancelled(cancelled)
                    counts[table] = f"unreadable: {exc}"
                    status = "partial: one or more tables are malformed"
            tables_json = json.dumps(tables, ensure_ascii=False)
            counts_json = json.dumps(counts, ensure_ascii=False)
            if "log" in tables:
                users = _lookup(source, "user")
                operations = _lookup(source, "operate")
                modes = _lookup(source, "mode")
                for row_id, epoch, raw, oid, mid, uid in source.execute(
                        "SELECT id, timep, data, oid, mid, uid FROM log"):
                    check_cancelled(cancelled)
                    try:
                        payload = json.loads(raw) if raw else {}
                        if not isinstance(payload, dict):
                            payload = {}
                    except (json.JSONDecodeError, TypeError):
                        payload = {}
                    operation = operations.get(oid, "")
                    mode = modes.get(mid, "")
                    utc_text, device_text, offset = _timestamps(epoch, payload)
                    category, event, action, explanation, channel, code = _interpret(
                        mode, operation, payload)
                    output.execute("""
                        INSERT INTO dahua_logs (
                            timestamp, timestamp_device, timezone_offset, time_unix,
                            category, event, action, explanation, username, channel,
                            mode_code, operation_code, log_code, source_database,
                          source_row_id, raw_json, actor_account, source_ip, config_target, field_explanations
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (utc_text, device_text, offset, epoch, category, event,
                          action, explanation, users.get(uid, ""), '' if channel is None else str(channel),
                          mode, operation, code, os.path.basename(path), row_id, raw or "",
                          str(payload.get('LoginUser') or payload.get('Log_UserName') or payload.get('User') or ''),
                          str(payload.get('Log_IP_Address') or payload.get('LoginIPAddr') or payload.get('IP') or ''),
                          str(payload.get('Name') or payload.get('Log_Name') or '') if operation == 'Log_SaveConfig' else '',
                          explain_payload_fields(payload, mode)))
                    inserted += 1
        except sqlite3.DatabaseError as exc:
            check_cancelled(cancelled)
            status = f"unreadable: {exc}"
        finally:
            if source is not None:
                source.close()
        output.execute("""
            INSERT INTO dahua_databases
                (source_database, size_bytes, status, tables, row_counts)
            VALUES (?, ?, ?, ?, ?)
        """, (os.path.basename(path), os.path.getsize(path), status, tables_json, counts_json))
        check_cancelled(cancelled)
        if progress_callback:
            progress_callback(index, total, os.path.basename(path), inserted)
    check_cancelled(cancelled)
    return {"database": output_path, "databases": len(paths), "logs": inserted}
