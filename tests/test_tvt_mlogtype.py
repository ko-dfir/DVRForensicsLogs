import json
import os
import sqlite3
from contextlib import closing

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from cctv_log_analyzer import CCTVLogAnalyzerWindow
from scripts.dvr_extractor import export_to_html, export_to_csv
from scripts.tvt_log_fields import ensure_tvt_mlogtype, payload_mlogtype


def legacy_database(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('CREATE TABLE tvt_logs(event_category TEXT, raw_payload TEXT)')
        conn.executemany('INSERT INTO tvt_logs VALUES (?, ?)',
                         [('USER_ACTION', 'mlogtype:operation;action:2')] * 120 +
                         [('CONFIGURATION', 'mlogtype:config;action:64'),
                          ('ALARM_EVENT', 'mlogtype:alarm;channels:1'),
                          ('SYSTEM_ERROR', 'mlogtype:exception;action:999')])


def test_mlogtype_migration_is_idempotent_and_keeps_raw_values(tmp_path):
    path = tmp_path / 'tvt.db'
    legacy_database(path)
    with closing(sqlite3.connect(path)) as conn:
        ensure_tvt_mlogtype(conn)
        ensure_tvt_mlogtype(conn)
        assert conn.execute('SELECT count(*) FROM tvt_logs').fetchone()[0] == 123
        assert dict(conn.execute('SELECT mlogtype, count(*) FROM tvt_logs GROUP BY mlogtype')) == {
            'operation': 120, 'config': 1, 'alarm': 1, 'exception': 1}
    assert payload_mlogtype('mlogtype:custom_type;action:1') == 'custom_type'


def test_viewer_mlogtype_filter_applies_across_pages_and_exports(tmp_path):
    app = QApplication.instance() or QApplication([])
    path = tmp_path / 'tvt.db'
    legacy_database(path)
    viewer = CCTVLogAnalyzerWindow()
    try:
        viewer.current_db, viewer.current_table = str(path), 'tvt_logs'
        viewer.setup_table_columns()
        assert 'mlogtype' in viewer.columns
        assert viewer.mlogtype_selector.count() == 5
        viewer.page_size.setCurrentIndex(viewer.page_size.findData(50))
        viewer.mlogtype_selector.setCurrentIndex(viewer.mlogtype_selector.findData('operation'))
        assert viewer.total_rows == 120
        viewer.go_next_page()
        assert viewer.current_page == 2
        where, params = viewer._where_clause()
        csv = tmp_path / 'filtered.csv'
        html = tmp_path / 'filtered.html'
        export_to_csv(path, 'tvt_logs', csv, where, params)
        export_to_html(path, 'tvt_logs', html, where, params,
                       report_context={'page_size': 50})
        assert len(csv.read_text(encoding='utf-8-sig').splitlines()) == 121
        assert 'mlogtype:config' not in csv.read_text(encoding='utf-8-sig')
        assert 'operation' in viewer._export_context()['metadata']['Active filters']
        viewer.clear_filters()
        assert viewer.total_rows == 123
    finally:
        viewer.close()
        app.processEvents()


def test_report_has_independent_global_mlogtype_selector_for_legacy_db(tmp_path):
    path = tmp_path / 'tvt.db'
    legacy_database(path)
    report = tmp_path / 'report.html'
    export_to_html(path, 'tvt_logs', report, report_context={'page_size': 50})
    index_text = (tmp_path / 'report_index.js').read_text(encoding='utf-8')
    index = json.loads(index_text.removeprefix('window.REPORT_INDEX=').strip().removesuffix(';'))
    assert len(index) == 123
    for page in (report, tmp_path / 'report_page_0003.html'):
        document = page.read_text(encoding='utf-8')
        assert "id='report-mlogtype'" in document
        assert "<option value='config'>config</option>" in document
        assert 'entry[3][reportMlogtypeIndex] === mlogtype' in document
        assert "url.searchParams.set('mlogtype', mlogtype)" in document
    assert 'config' in index[120][3]
