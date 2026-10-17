import os
import sqlite3
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from PySide6.QtGui import QFontDatabase
import scripts.app_settings as settings
import cctv_log_analyzer as ui


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    # The Windows offscreen plugin does not always enumerate installed fonts.
    for name in ('segoeui.ttf', 'consola.ttf'):
        font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / name
        if font.is_file():
            QFontDatabase.addApplicationFont(str(font))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(settings, 'QSettings', lambda *_: QSettings(str(tmp_path / 'settings.ini'), QSettings.Format.IniFormat))
    database = tmp_path / 'hik.db'
    conn = sqlite3.connect(database)
    conn.execute('CREATE TABLE hikvision_logs(id INTEGER PRIMARY KEY, timestamp TEXT, time_unix INTEGER, '
                 'major_type TEXT, minor_type TEXT, minor_code TEXT, sdk_macro TEXT, username TEXT, '
                 'channel TEXT, ip TEXT, details TEXT, offset INTEGER, raw_record_hex TEXT, region TEXT, status TEXT)')
    records = [(index, '2026-10-01 08:00:00', 1790841600, 'Operation', 'Local: Backup/Export Video Files',
                '0x005b', 'MINOR_LOCAL_RECFILE_OUTPUT', 'demo', '1', '192.0.2.1', 'Video exported',
                index * 128, '52415453', 'Declared Active Ring-Buffer' if index % 2 else 'Alternative Residual Region',
                'Mapped') for index in range(1, 406)]
    records += [(406, '2026-10-02 08:00:00', 1790928000, 'Alarm', 'Start Motion Detection',
                 '0x0002', 'MINOR_START_MOTION', 'viewer', '2', '', 'motion', 50000, '000102', '', 'Mapped'),
                (407, '2026-10-02 08:05:00', 1790928300, 'Information', 'Start Record',
                 '0x00a3', 'MINOR_REC_START', 'viewer', '2', '', 'Recording', 50128, '', '', 'Mapped')]
    conn.executemany('INSERT INTO hikvision_logs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', records)
    conn.commit()
    conn.close()
    viewer = ui.CCTVLogAnalyzerWindow()
    viewer.current_db, viewer.current_table = str(database), 'hikvision_logs'
    viewer.setup_table_columns()
    viewer.populate_table()
    yield viewer
    viewer.close()
    app.processEvents()


def test_main_workbench_has_enabled_investigation_tabs(workbench):
    viewer = workbench
    assert [viewer.tabs.tabText(viewer.tabs.indexOf(v)) for v in viewer.hik_views] == [
        'Security Audit', 'Camera / Motion', 'Log Statistics']
    assert all(viewer.tabs.isTabEnabled(viewer.tabs.indexOf(v)) for v in viewer.hik_views)


def test_audit_queries_all_pages_and_global_search(workbench):
    audit = workbench.hik_views[0]
    audit.refresh()
    assert audit.total == 405 and len(audit.rows) == 200
    audit.move(1)
    assert audit.page == 2 and audit.rows[0]['id'] == 201
    audit.move(1)
    assert len(audit.rows) == 5 and audit.rows[-1]['id'] == 405
    workbench.filter_text.setText('viewer')
    workbench.reset_and_populate()
    audit.reset()
    assert audit.total == 0


def test_camera_filters_and_shared_date_scope(workbench):
    view = workbench.hik_views[1]
    view.refresh()
    assert view.total == 2
    view.selector.setCurrentIndex(1)
    assert view.total == 1 and view.rows[0]['id'] == 406
    view.selector.setCurrentIndex(2)
    assert view.total == 1 and view.rows[0]['id'] == 407
    view.channel.setCurrentIndex(view.channel.findData('1'))
    assert view.total == 0
    view.channel.setCurrentIndex(0)
    workbench.date_to.setDate(workbench.date_from.date())
    workbench.date_enabled.setChecked(True)
    view.reset()
    assert view.total == 0


def test_statistics_have_global_counts_and_regions(workbench):
    stats = workbench.hik_views[2]
    stats.refresh()
    assert stats.total == 3
    top = stats.rows[0]
    assert top['total'] == 405 and top['declared'] == 203 and top['residual'] == 202
    assert sum(row['total'] for row in stats.rows) == 407
    stats.search.setText('motion')
    stats.reset()
    assert stats.total == 1 and stats.rows[0]['total'] == 1


def test_statistics_drilldown_and_inspector_identity(workbench, monkeypatch):
    audit, _, stats = workbench.hik_views
    audit.refresh()
    audit.move(1)
    selected = []
    monkeypatch.setattr(workbench, 'show_record_values', lambda values, *args: selected.append(values))
    audit.open_record(0, 0)
    assert selected[0]['id'] == 201 and selected[0]['offset'] == 201 * 128
    stats.refresh()
    stats.open_record(0, 0)
    assert workbench.total_rows == 405
    assert workbench.tabs.currentWidget() is workbench.tab_search


def test_views_clear_when_switching_brand_or_table(workbench):
    audit = workbench.hik_views[0]
    audit.refresh()
    workbench.current_table = 'dahua_logs'
    workbench._sync_investigation_views()
    assert audit.total == 0 and audit.table.rowCount() == 0
    assert all(not workbench.tabs.isTabEnabled(workbench.tabs.indexOf(view)) for view in workbench.hik_views)


def test_older_hikvision_database_does_not_invent_region_or_status(workbench):
    with sqlite3.connect(workbench.current_db) as conn:
        conn.execute('ALTER TABLE hikvision_logs DROP COLUMN region')
        conn.execute('ALTER TABLE hikvision_logs DROP COLUMN status')
    workbench.setup_table_columns()
    stats = workbench.hik_views[2]
    stats.refresh()
    assert stats.rows[0]['other / not stored'] == 405
    assert stats.rows[0]['status'] == ''


def test_cancel_button_stops_running_worker_and_reenables_ui(workbench, tmp_path, monkeypatch):
    import threading
    import time
    from scripts.cancellation import check_cancelled
    from scripts.case_workspace import initialize_case
    started = threading.Event()
    class SlowEngine:
        def __init__(self, source):
            pass
        def extract_logs(self, *, cancelled, **_options):
            started.set()
            while not cancelled():
                time.sleep(0.001)
            check_cancelled(cancelled)
    monkeypatch.setattr(ui, 'TVTEngine', SlowEngine)
    viewer = workbench
    viewer.case_folder = str(initialize_case(tmp_path / 'Case'))
    viewer.image_path, viewer.detected_brand = 'synthetic.img', 'TVT'
    viewer.action_carve_data()
    thread = viewer.extraction_thread
    try:
        assert started.wait(2)
        assert not viewer.btn_cancel.isHidden()
        viewer.btn_cancel.click()
        assert thread.wait(2000)
        QApplication.instance().processEvents()
        assert 'Cancelled' in viewer.progress_bar.format()
        assert viewer.btn_cancel.isHidden()
        assert viewer.btn_carve.isEnabled()
    finally:
        thread.requestInterruption()
        assert thread.wait(2000)


def test_render_investigation_tabs_in_both_themes(workbench, tmp_path):
    viewer = workbench
    viewer.resize(1440, 900)
    viewer.show()
    for theme in ('dark', 'light'):
        viewer.settings.set('theme', theme)
        viewer.apply_settings()
        for view in viewer.hik_views:
            viewer.tabs.setCurrentWidget(view)
            QApplication.instance().processEvents()
            image = viewer.grab()
            assert not image.isNull()
            assert image.save(str(tmp_path / f'{theme}-{view.mode}.png'))
