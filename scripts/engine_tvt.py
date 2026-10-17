import struct
import re
import sqlite3
import json
from scripts.tvt_sdk_types import describe_action, payload_fields
from contextlib import closing
from scripts.cancellation import check_cancelled
from datetime import datetime, timezone
from scripts.image_io import open_image
from scripts.tvt_log_fields import payload_mlogtype, ensure_tvt_mlogtype

# TVT Action ID mapping reverse-engineered from SDK & payloads
TVT_ACTION_MAP = {
    2: "Local Login (IPv4)",
    17: "Live View / Playback (Channel Opened)",
    28: "Cloud / P2P Mobile App Login (IPv6)",
    64: "Configuration Changed",
    120: "NAT Server Connect",
    121: "NAT Server Disconnect / Redirect Failed",
    126: "NAT Server Offline",
}

# General log category definitions based on SDK Enums
TVT_LOG_CATEGORY_MAP = {
    "alarm": "ALARM_EVENT",
    "operation": "USER_ACTION",
    "config": "CONFIGURATION",
    "exception": "SYSTEM_ERROR"
}

class TVTEngine:
    def __init__(self, image_path):
        self.image_path = image_path
        self.is_e01 = image_path.lower().endswith('.e01')

    def _open_image(self):
        return open_image(self.image_path)

    def _parse_payload(self, payload):
        """
        Parses the raw mlogtype payload and returns a human-readable event category and description.
        Example: mlogtype:operation;action:2;ip:15.161.54.149
        """
        # Cleanup garbage bytes at the end
        clean_payload = re.sub(r'[^\x20-\x7E]+', '', payload).strip()
        
        category = "UNKNOWN"
        description = "Unknown Event"
        
        # Extract major log type
        type_match = re.search(r'mlogtype:([^;#]+)', clean_payload)
        if type_match:
            raw_type = type_match.group(1).lower()
            category = TVT_LOG_CATEGORY_MAP.get(raw_type, raw_type.upper())
            
            if raw_type == "alarm":
                description = "Motion / Sensor Alarm Triggered"
        
        # Extract action code
        action_text, _, _ = describe_action(clean_payload, TVT_ACTION_MAP)
        if action_text:
            description = action_text
            
        # Extract IP if present
        ip_match = re.search(r'ip:([^;]+)', clean_payload)
        if ip_match:
            description += f" [IP: {ip_match.group(1)}]"
            
        # Extract NAT info if present
        nat_match = re.search(r'nat-info:([^;]+)', clean_payload)
        if nat_match:
            description += f" [NAT: {nat_match.group(1)}]"
            
        # Extract Channels if present
        ch_match = re.search(r'channels:([^;]+)', clean_payload)
        if ch_match:
            description += f" [Channel Ref: {ch_match.group(1)}]"
            
        return category, description, clean_payload

    def extract_logs(self, limit_bytes=1100*1024*1024, start_offset=0,
                     progress_callback=None, cancelled=None):
        """Extracts TVT specific mlogtype variables from the raw headless disk."""
        f = self._open_image()
        chunk_size = 16 * 1024 * 1024
        # Maximum payload is 4096 bytes; retain enough context across chunks.
        overlap = 4096 + 256
        target = b'mlogtype:'
        
        records = []
        try:
            check_cancelled(cancelled)
            current_offset = max(0, start_offset)
            f.seek(current_offset)
            tail = b''
            last_record_offset = -1
            
            while current_offset < limit_bytes:
                check_cancelled(cancelled)
                buf = f.read(min(chunk_size, limit_bytes - current_offset))
                if not buf:
                    break
                    
                data = tail + buf
                data_offset = current_offset - len(tail)
                pos = 0
                
                while True:
                    check_cancelled(cancelled)
                    idx = data.find(target, pos)
                    if idx == -1:
                        break
                    absolute_offset = data_offset + idx
                    if absolute_offset <= last_record_offset:
                        pos = idx + len(target)
                        continue

                    # The two bytes directly before mlogtype are the exact
                    # payload length. This is safer than looking for NUL: many
                    # TVT config/exception records are not NUL terminated.
                    if idx < 2:
                        pos = idx + len(target)
                        continue
                    payload_length = struct.unpack('<H', data[idx-2:idx])[0]
                    if not (len(target) <= payload_length <= 4096):
                        pos = idx + len(target)
                        continue
                    end_idx = idx + payload_length
                    if end_idx > len(data):
                        # The overlap will present the complete record in the
                        # next iteration.
                        break
                    payload = data[idx:end_idx].decode('utf-8', 'replace')

                    # Each TVT record begins AA AB. The epoch is a fixed field
                    # at marker+16, not an arbitrary plausible 4-byte window.
                    marker = data.rfind(b'\xaa\xab', max(0, idx-256), idx)
                    dt_str = "unknown"
                    ts_val_final = 0
                    if marker >= 0 and marker + 20 <= idx:
                        ts_val = struct.unpack('<I', data[marker+16:marker+20])[0]
                        if 1420070400 <= ts_val <= 1893456000:
                            try:
                                dt = datetime.fromtimestamp(ts_val, timezone.utc)
                                dt_str = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
                                ts_val_final = ts_val
                            except (OverflowError, OSError, ValueError):
                                pass

                    # Operation/config records store a one-byte username
                    # length followed by the username immediately before the
                    # two-byte payload length.
                    username = "unknown"
                    user_end = idx - 2
                    for user_length in range(1, min(32, user_end) + 1):
                        length_pos = user_end - user_length - 1
                        if data[length_pos] != user_length:
                            continue
                        raw_user = data[length_pos + 1:user_end]
                        if raw_user and all(0x20 <= char < 0x7f for char in raw_user):
                            username = raw_user.decode('utf-8', 'replace')
                            break
                        
                    category, description, clean_payload = self._parse_payload(payload)
                        
                    records.append({
                        "timestamp": dt_str,
                        "time_unix": ts_val_final,
                        "user": username,
                        "category": category,
                        "description": description,
                        "raw_payload": clean_payload,
                        "mlogtype": payload_mlogtype(clean_payload),
                        "action_code": payload_fields(clean_payload).get('action', ''),
                        "sdk_macro": describe_action(clean_payload, TVT_ACTION_MAP)[1],
                        "interpretation_source": describe_action(clean_payload, TVT_ACTION_MAP)[2],
                        "payload_fields": json.dumps(payload_fields(clean_payload), ensure_ascii=False),
                        "offset": absolute_offset,
                        "raw_record_offset": data_offset + (marker if marker >= 0 else idx - 2),
                        "raw_record_hex": data[marker if marker >= 0 else idx - 2:end_idx].hex(),
                    })

                    last_record_offset = absolute_offset
                    pos = end_idx

                tail = data[-overlap:]
                current_offset += len(buf)
                if progress_callback:
                    progress_callback(
                        current_offset - start_offset,
                        max(1, limit_bytes - start_offset),
                        len(records),
                    )
                
        finally:
            f.close()
            
        return records

    def save_to_sqlite(self, records, out_db_path, cancelled=None):
        """Saves the extracted TVT records to a structured SQLite database."""
        with closing(sqlite3.connect(out_db_path)) as conn, conn:
            self._save_records(conn, records, cancelled)
        print(f"[*] TVT Logs successfully saved to SQLite Database: {out_db_path}")

    @staticmethod
    def _save_records(conn, records, cancelled):
        check_cancelled(cancelled)
        c = conn.cursor()
        
        # Create schema for TVT logs with English translation columns
        c.execute('''
            CREATE TABLE IF NOT EXISTS tvt_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                time_unix INTEGER,
                username TEXT,
                event_category TEXT,
                event_description TEXT,
                raw_payload TEXT,
                source_offset INTEGER
            )
        ''')
        columns = {row[1] for row in c.execute('PRAGMA table_info(tvt_logs)')}
        ensure_tvt_mlogtype(conn)
        if 'source_offset' not in columns:
            c.execute('ALTER TABLE tvt_logs ADD COLUMN source_offset INTEGER DEFAULT 0')
        for name, kind in (('raw_record_offset', 'INTEGER'), ('raw_record_hex', 'TEXT')):
            if name not in columns:
                c.execute(f'ALTER TABLE tvt_logs ADD COLUMN {name} {kind}')
        for name in ('action_code', 'sdk_macro', 'interpretation_source', 'payload_fields'):
            if name not in columns:
                c.execute(f'ALTER TABLE tvt_logs ADD COLUMN {name} TEXT')
        # Re-running the same case must not duplicate all previously carved
        # entries in the deterministic output database.
        c.execute('DELETE FROM tvt_logs')
        
        # Insert records
        for r in records:
            check_cancelled(cancelled)
            c.execute('''
                INSERT INTO tvt_logs (timestamp, time_unix, username, event_category, event_description, raw_payload, source_offset, raw_record_offset, raw_record_hex, mlogtype)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (r['timestamp'], r['time_unix'], r['user'], r['category'],
                  r['description'], r['raw_payload'], r.get('offset', 0),
                  r.get('raw_record_offset'), r.get('raw_record_hex', ''),
                  r.get('mlogtype') or payload_mlogtype(r.get('raw_payload'))))
            payload = r.get('raw_payload', '')
            _, macro, source = describe_action(payload, TVT_ACTION_MAP)
            c.execute('UPDATE tvt_logs SET action_code=?, sdk_macro=?, interpretation_source=?, payload_fields=? WHERE id=?',
                      (payload_fields(payload).get('action', ''), macro, source,
                       json.dumps(payload_fields(payload), ensure_ascii=False), c.lastrowid))
            
        check_cancelled(cancelled)
