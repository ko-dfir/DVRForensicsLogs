"""Case folders and independent per-extraction workspaces with audit trails."""

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_AUDIT_LOCK = threading.RLock()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def initialize_case(folder):
    root = Path(folder).resolve()
    root.mkdir(parents=True, exist_ok=True)
    marker = root / 'case.json'
    if not marker.exists():
        with marker.open('x', encoding='utf-8') as stream:
            json.dump({'format': 'cctv-log-analyzer-case', 'name': root.name,
                       'created_utc': utc_now()}, stream, indent=2)
    else:
        data = json.loads(marker.read_text(encoding='utf-8'))
        if data.get('format') != 'cctv-log-analyzer-case':
            raise ValueError('This folder contains an unrelated case.json. Choose another case folder.')
    return root


def create_workspace(folder, source, brand, version, metadata=None):
    case = initialize_case(folder)
    source_name = str(source).replace('\\', '/').rsplit('/', 1)[-1]
    label = re.sub(r'[^\w.-]+', '_', source_name).strip('._')[:80] or 'evidence'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    root = case / 'workspaces' / f'{label}_{stamp}_{uuid.uuid4().hex[:10]}'
    root.mkdir(parents=True, exist_ok=False)
    (root / 'databases').mkdir()
    (root / 'reports').mkdir()
    manifest = {'format': 'cctv-log-analyzer-workspace', 'source': str(source),
                'brand': brand, 'app_version': version, 'created_utc': utc_now(),
                'status': 'prepared', 'metadata': metadata or {}}
    with (root / 'workspace.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
    audit(root, 'workspace_created', source=str(source), brand=brand, app_version=version)
    return root


def audit(folder, event, **details):
    if not folder:
        return
    with _AUDIT_LOCK:
        with (Path(folder) / 'workspace.log').open('a', encoding='utf-8') as stream:
            stream.write(f'{utc_now()} [{event.upper()}] ' +
                         json.dumps(details, ensure_ascii=False, default=str) + '\n')


def update_workspace(folder, **changes):
    if not folder:
        return
    with _AUDIT_LOCK:
        path = Path(folder) / 'workspace.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data.update(changes, updated_utc=utc_now())
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)


def workspace_for_database(database):
    path = Path(database).resolve()
    root = path.parent.parent
    marker = root / 'workspace.json'
    if path.parent.name != 'databases' or not marker.is_file():
        return None
    data = json.loads(marker.read_text(encoding='utf-8'))
    return root if data.get('format') == 'cctv-log-analyzer-workspace' else None
