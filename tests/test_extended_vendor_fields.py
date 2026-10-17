import json
import re
import sqlite3
from pathlib import Path
from scripts.tvt_sdk_types import SDK_TYPES, SDK_BY_CODE, describe_action
from scripts.engine_tvt import TVTEngine, TVT_ACTION_MAP
from scripts.dahua_analysis import explain_payload_fields, build_analysis_database


def test_tvt_sdk_mapping_matches_vendor_header():
    header = Path('scratchpad/tvt_headers/dvrdvstypedef.h')
    if not header.exists():
        # This source header is reference material, not a runtime dependency.
        return
    text = header.read_text(encoding='utf-8')
    enum = text.split('typedef enum _n9000_log_type', 1)[1].split('}N9000_LOG_TYPE', 1)[0]
    symbols = re.findall(r'^\s*(LOG_\w+)\s*(?:=\s*0x100)?\s*,', enum, re.MULTILINE)
    assert symbols == [macro for macro, _ in SDK_TYPES]
    assert SDK_BY_CODE[256][0] == 'LOG_ALARM_MOTION'
    assert len(symbols) == 38


def test_tvt_raw_action_namespace_remains_separate():
    assert describe_action('mlogtype:operation;action:256', TVT_ACTION_MAP)[0] == 'Action ID: 256'
    text, macro, source = describe_action('mlogtype:alarm;action:999;sdk_log_type:0x100', TVT_ACTION_MAP)
    assert (text, macro) == ('Motion detection alarm', 'LOG_ALARM_MOTION')
    assert 'explicitly' in source
    text, macro, _ = describe_action('mlogtype:operation;action:LOG_OPERATE_FORMAT_HD', TVT_ACTION_MAP)
    assert (text, macro) == ('Disk formatting', 'LOG_OPERATE_FORMAT_HD')
    assert 'Action: custom' == describe_action('action:custom', TVT_ACTION_MAP)[0]
    assert describe_action('action:DD_LOG_TYPE_BACKUP_FAIL', TVT_ACTION_MAP)[0] == 'Backup failed'


def test_tvt_extra_fields_persist_without_dropping_unknown_values(tmp_path):
    payload = 'mlogtype:operation;action:LOG_OPERATE_AUDIO_TALK;custom:retained;ip:2001:db8::1'
    category, text, raw = TVTEngine('unused.img')._parse_payload(payload)
    row = dict(timestamp='2026-01-01', time_unix=1, user='demo', category=category,
               description=text, raw_payload=raw)
    database = tmp_path / 'tvt.db'
    TVTEngine('unused.img').save_to_sqlite([row], database)
    with sqlite3.connect(database) as conn:
        action, macro, fields = conn.execute('SELECT action_code, sdk_macro, payload_fields FROM tvt_logs').fetchone()
    assert action == macro == 'LOG_OPERATE_AUDIO_TALK'
    assert json.loads(fields)['ip'] == '2001:db8::1'
    assert json.loads(fields)['custom'] == 'retained'


def test_dahua_every_json_key_has_value_and_explanation():
    data = dict(Log_Index=0, Authority={'Monitor': [{'Old': False, 'New': True}]}, custom={'x': [1, 2]})
    rows = json.loads(explain_payload_fields(data, 'Log_Config'))
    assert {row['field']: row['value'] for row in rows} == data
    assert 'not assumed to be a camera' in rows[0]['meaning']
    assert 'not established' in rows[-1]['meaning']


def test_dahua_enriched_columns_and_channel_zero(tmp_path):
    path = tmp_path / 'demo.db'
    with sqlite3.connect(path) as conn:
        conn.executescript("CREATE TABLE mode(id, name); INSERT INTO mode VALUES(1, 'Log_Event');"
                           "CREATE TABLE log(id, timep, data, oid, mid, uid);")
        conn.execute('INSERT INTO log VALUES(1, 1, ?, 1, 1, 1)',
                     (json.dumps(dict(Log_Index=0, LoginUser='demo', LoginIPAddr='192.0.2.1', custom=42)),))
    output = tmp_path / 'analysis.db'
    build_analysis_database([path], output)
    with sqlite3.connect(output) as conn:
        channel, account, ip, fields = conn.execute('SELECT channel, actor_account, source_ip, field_explanations FROM dahua_logs').fetchone()
    assert (channel, account, ip) == ('0', 'demo', '192.0.2.1')
    assert 'custom' in fields
