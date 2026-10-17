import json
import os
import sqlite3
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
import cctv_log_analyzer as ui
from scripts.case_workspace import create_workspace, workspace_for_database, audit


def test_workspaces_are_unique_and_do_not_overwrite_other_images(tmp_path):
    case = tmp_path / 'Case A'
    first = create_workspace(case, r'F:\Disk1\same.E01', 'TVT', '1.01')
    second = create_workspace(case, r'F:\Disk2\same.E01', 'TVT', '1.01')
    repeated = create_workspace(case, r'F:\Disk1\same.E01', 'TVT', '1.01')
    assert len({first, second, repeated}) == 3
    audit(first, 'example', detail='ONLY_FIRST_IMAGE')
    assert 'ONLY_FIRST_IMAGE' not in (second / 'workspace.log').read_text(encoding='utf-8')
    assert json.loads((case / 'case.json').read_text())['format'] == 'cctv-log-analyzer-case'
    for root in (first, second, repeated):
        assert (root / 'databases').is_dir()
        assert (root / 'reports').is_dir()
        assert workspace_for_database(root / 'databases' / 'logs.db') == root
    assert workspace_for_database(tmp_path / 'old-flat-output.db') is None


def test_extraction_writes_its_own_audit_and_manifest(tmp_path, monkeypatch):
    root = create_workspace(tmp_path / 'Case', 'test.img', 'TVT', '1.01')
    class Engine:
        def __init__(self, _source): pass
        def extract_logs(self, **options):
            options['progress_callback'](10, 10, 1)
            return [{'timestamp': '2026-01-01', 'time_unix': 1, 'user': 'admin',
                     'category': 'CONFIGURATION', 'description': 'config',
                     'raw_payload': 'mlogtype:config;', 'offset': 17}]
        def save_to_sqlite(self, records, output, cancelled=None):
            connection = sqlite3.connect(output)
            connection.execute('CREATE TABLE tvt_logs(id INTEGER)')
            connection.commit()
            connection.close()
    monkeypatch.setattr(ui, 'TVTEngine', Engine)
    thread = ui.ExtractionThread('test.img', str(root / 'databases'), 'TVT', str(root))
    completed = []
    thread.finished_signal.connect(lambda *result: completed.append(result))
    thread.run()
    assert completed[0][0]
    manifest = json.loads((root / 'workspace.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'completed'
    assert Path(manifest['database']).parent == root / 'databases'
    log = (root / 'workspace.log').read_text(encoding='utf-8')
    assert '[STARTED]' in log and '[PROGRESS]' in log and '[COMPLETED]' in log


def test_failed_extraction_records_error_and_traceback(tmp_path):
    root = create_workspace(tmp_path / 'Case', 'test.img', 'UNKNOWN', '1.01')
    thread = ui.ExtractionThread('test.img', str(root / 'databases'), 'UNKNOWN', str(root))
    completed = []
    thread.finished_signal.connect(lambda *result: completed.append(result))
    thread.run()
    assert not completed[0][0]
    assert json.loads((root / 'workspace.json').read_text())['status'] == 'failed'
    log = (root / 'workspace.log').read_text()
    assert '[ERROR]' in log and '[TRACEBACK]' in log


def test_viewer_routes_reports_and_reopens_correct_workspace(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    root = create_workspace(tmp_path / 'Case', 'test.img', 'TVT', '1.01')
    database = root / 'databases' / 'logs.db'
    connection = sqlite3.connect(database)
    connection.execute('CREATE TABLE logs(message TEXT)')
    connection.commit()
    connection.close()
    viewer = ui.CCTVLogAnalyzerWindow()
    monkeypatch.setattr(viewer.settings, 'set', lambda *_: None)
    monkeypatch.setattr(viewer, 'load_image_path', lambda _: None)
    viewer.detected_brand = 'TVT'
    try:
        viewer.open_recent(SimpleNamespace(image_path='test.img', database_path=str(database), table_name='logs'))
        assert viewer.workspace_dir == str(root)
        assert viewer.case_folder == str(tmp_path / 'Case')
        assert Path(viewer._report_destination('html')).parent == root / 'reports'
        assert viewer.workspace_button.isEnabled()
        viewer.append_log('[INFO] workspace resumed')
        assert 'workspace resumed' in (root / 'workspace.log').read_text()
    finally:
        viewer.close()
        app.processEvents()


def test_case_on_physical_evidence_disk_is_rejected_before_creation(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    viewer = ui.CCTVLogAnalyzerWindow()
    viewer.image_path = r'\\.\PhysicalDrive3'
    letter = os.path.splitdrive(str(tmp_path))[0][:1].upper()
    monkeypatch.setattr(ui, 'drive_volume_letters', lambda _: {letter})
    try:
        import pytest
        with pytest.raises(ValueError, match='evidence disk'):
            viewer._validate_case_location(str(tmp_path / 'DoNotCreate'))
        assert not (tmp_path / 'DoNotCreate').exists()
    finally:
        viewer.close()
        app.processEvents()


def test_entropy_result_is_preserved_in_workspace_on_close(tmp_path):
    from scripts.entropy_dialog import EntropyDialog, EntropyWorker
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'unknown.img'
    source.write_bytes(bytes(2048))
    root = create_workspace(tmp_path / 'Case', str(source), 'UNKNOWN', '1.01')
    worker = EntropyWorker(str(source), 0, None, 1024)
    result = []
    worker.result.connect(lambda *values: result.append(values))
    worker.run()
    dialog = EntropyDialog(str(source), lambda _: None, results_dir=str(root / 'databases'))
    dialog.show_results(*result[0])
    preserved = Path(dialog.saved_results[0])
    dialog.reject()
    assert preserved.parent == root / 'databases'
    assert preserved.is_file()
    assert not Path(result[0][0]).exists()
    app.processEvents()
