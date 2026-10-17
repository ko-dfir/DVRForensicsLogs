"""Original TVT log fields and upgrades of derived extraction databases."""

import re


def payload_mlogtype(payload):
    match = re.search(r'(?:^|[;#\s])mlogtype:([^;#\s]+)', str(payload or ''), re.IGNORECASE)
    return match.group(1) if match else ''


def ensure_tvt_mlogtype(connection):
    """Add the raw type to our extracted database, never to the source image."""
    columns = {row[1] for row in connection.execute('PRAGMA table_info(tvt_logs)')}
    if not columns or 'mlogtype' in columns or 'raw_payload' not in columns:
        return
    connection.execute('ALTER TABLE tvt_logs ADD COLUMN mlogtype TEXT')
    connection.create_function('tvt_payload_type', 1, payload_mlogtype)
    connection.execute('UPDATE tvt_logs SET mlogtype = tvt_payload_type(raw_payload)')
    connection.commit()
