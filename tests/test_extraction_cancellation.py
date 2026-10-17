import json
import sqlite3
import struct
from types import SimpleNamespace
import pytest

from scripts.cancellation import ExtractionCancelled
from scripts.engine_tvt import TVTEngine
from scripts.engine_hikvision import HikvisionEngine, iter_stream_records
from scripts.engine_dahua import DahuaEngine
from scripts.dahua_analysis import build_analysis_database
from scripts.case_workspace import create_workspace


def test_tvt_cancel_before_read_and_during_record_parse(tmp_path):
    image = tmp_path / 'tvt.img'
    payload = b'mlogtype:operation;action:2'
    image.write_bytes(b'\xaa\xab' + bytes(14) + struct.pack('<I', 1600000000)
                      + b'\x05admin' + struct.pack('<H', len(payload)) + payload)
    calls = [0]
    def cancel():
        calls[0] += 1
        return calls[0] >= 3
    with pytest.raises(ExtractionCancelled):
        TVTEngine(str(image)).extract_logs(limit_bytes=image.stat().st_size, cancelled=cancel)
    with pytest.raises(ExtractionCancelled):
        TVTEngine(str(image)).extract_logs(cancelled=lambda: True)
    image.rename(tmp_path / 'closed.img')  # Windows handle must have closed.


def test_tvt_cancel_write_rolls_back_previous_complete_records(tmp_path):
    engine = TVTEngine('unused.img')
    path = tmp_path / 'tvt.db'
    row = dict(timestamp='2026-01-01', time_unix=1, user='demo', category='USER_ACTION',
               description='login', raw_payload='mlogtype:operation;action:2')
    engine.save_to_sqlite([row], path)
    calls = [0]
    def cancel():
        calls[0] += 1
        return calls[0] >= 3
    with pytest.raises(ExtractionCancelled):
        engine.save_to_sqlite([row, row], path, cancelled=cancel)
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM tvt_logs').fetchone()[0] == 1


def test_hikvision_cancel_during_scan_closes_and_rolls_back(tmp_path):
    image = tmp_path / 'hik.img'
    record = struct.pack('<4sIIHH', b'RATS', 0x14, 1600000000, 3, 65) + bytes(112)
    image.write_bytes(record * 3)
    calls = [0]
    def cancel():
        calls[0] += 1
        return calls[0] >= 5
    database = tmp_path / 'hik.db'
    with pytest.raises(ExtractionCancelled):
        HikvisionEngine(str(image)).carve_to_sqlite(database, limit_bytes=384,
            structure={'scan_regions': [('test', 0, 384)]}, cancelled=cancel)
    with sqlite3.connect(database) as conn:
        assert conn.execute('SELECT COUNT(*) FROM hikvision_logs').fetchone()[0] == 0
    image.rename(tmp_path / 'closed.img')
    with pytest.raises(ExtractionCancelled):
        list(iter_stream_records(str(tmp_path / 'closed.img'), 0, 384, cancelled=lambda: True))


def test_dahua_walk_cancel_is_not_swallowed():
    root = SimpleNamespace(dirlist=lambda: {'demo.db': SimpleNamespace(filetype=0x8000)})
    with pytest.raises(ExtractionCancelled):
        list(DahuaEngine._walk_regular_files(root, cancelled=lambda: True))


def test_dahua_cancelled_file_is_partial_and_closed(tmp_path, monkeypatch):
    import io
    import scripts.engine_dahua as dahua
    source = io.BytesIO(b'data' * 32)
    inode = SimpleNamespace(size=128, filetype=0x8000, open=lambda: source)
    root = SimpleNamespace(dirlist=lambda: {'log.db': inode})
    monkeypatch.setattr(dahua, 'xfs', SimpleNamespace(XFS=lambda _: SimpleNamespace(get=lambda _: root)))
    monkeypatch.setattr(dahua, 'DISSECT_XFS_AVAILABLE', True)
    cancelled = [False]
    with pytest.raises(ExtractionCancelled):
        DahuaEngine('unused.img').extract_xfs_native(0, tmp_path,
            image_handle=io.BytesIO(bytes(512)), cancelled=lambda: cancelled[0],
            progress_callback=lambda *_: cancelled.__setitem__(0, True))
    assert source.closed
    assert not (tmp_path / 'Dahua_Databases/log.db').exists()
    assert (tmp_path / 'Dahua_Databases/log.db.partial').read_bytes() == b'data' * 32


def test_dahua_normalization_cancel_does_not_commit_rows(tmp_path):
    source = tmp_path / 'source.db'
    with sqlite3.connect(source) as conn:
        conn.executescript('CREATE TABLE log(id, timep, data, oid, mid, uid);')
        conn.executemany('INSERT INTO log VALUES (?, 1, "{}", 1, 1, 1)', [(i,) for i in range(100)])
    conn.close()
    calls = [0]
    def cancel():
        calls[0] += 1
        return calls[0] >= 8
    output = tmp_path / 'analysis.db'
    with pytest.raises(ExtractionCancelled):
        build_analysis_database([source], output, cancelled=cancel)
    with sqlite3.connect(output) as conn:
        assert conn.execute('SELECT COUNT(*) FROM dahua_logs').fetchone()[0] == 0
    source.rename(tmp_path / 'closed.db')


@pytest.mark.parametrize('brand', ['TVT', 'HIKVISION', 'DAHUA'])
def test_worker_marks_cancellation_not_failure_or_success(tmp_path, monkeypatch, brand):
    import cctv_log_analyzer as ui
    root = create_workspace(tmp_path / 'Case', 'demo.img', brand, '1.01')
    worker = ui.ExtractionThread('demo.img', str(root / 'databases'), brand, str(root))
    calls = [0]
    def cancelled():
        calls[0] += 1
        return calls[0] > 1
    monkeypatch.setattr(worker, 'isInterruptionRequested', cancelled)
    stopped, completed = [], []
    worker.cancelled_signal.connect(stopped.append)
    worker.finished_signal.connect(lambda *args: completed.append(args))
    worker.run()
    assert stopped and not completed
    assert json.loads((root / 'workspace.json').read_text())['status'] == 'cancelled'
    log = (root / 'workspace.log').read_text()
    assert '[CANCELLED]' in log and '[COMPLETED]' not in log and '[ERROR]' not in log
