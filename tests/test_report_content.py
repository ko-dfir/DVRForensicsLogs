import json
import os
import sqlite3
from pathlib import Path
from contextlib import closing

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from cctv_log_analyzer import CCTVLogAnalyzerWindow
from scripts.dvr_extractor import export_to_html
from scripts.report_options import ReportOptionsDialog
from scripts.app_settings import AppSettings


def make_database(path):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('CREATE TABLE logs (category TEXT, explanation TEXT, raw_payload TEXT)')
        conn.executemany('INSERT INTO logs VALUES (?, ?, ?)',
                         [('User', f'Event {i:03}', 'EXCLUDED_SECRET') for i in range(105)] +
                         [('System', 'Power on', 'EXCLUDED_SECRET')])


def test_export_contains_only_selected_fields_in_pages_and_search_index(tmp_path):
    db, output = tmp_path / 'logs.db', tmp_path / 'report.html'
    make_database(db)
    files = export_to_html(db, 'logs', output, ' WHERE category = ?', ['User'],
                           report_context={'columns': ['explanation'], 'page_size': 50})
    for file in files:
        text = Path(file).read_text(encoding='utf-8')
        assert 'EXCLUDED_SECRET' not in text
        assert 'raw_payload' not in text
        assert "id='report-category'" not in text
    text = (tmp_path / 'report_index.js').read_text(encoding='utf-8')
    entries = json.loads(text.removeprefix('window.REPORT_INDEX=').strip().removesuffix(';'))
    assert len(entries) == 105
    assert all(len(entry[3]) == 1 for entry in entries)


@pytest.mark.parametrize('columns', [[], ['nonexistent'], ['category', 'category']])
def test_invalid_report_fields_rejected(tmp_path, columns):
    db = tmp_path / 'logs.db'
    make_database(db)
    with pytest.raises(ValueError):
        export_to_html(db, 'logs', tmp_path / 'report.html', report_context={'columns': columns})


def test_record_scope_uses_stable_ids_after_table_sort(tmp_path):
    app = QApplication.instance() or QApplication([])
    db = tmp_path / 'logs.db'
    make_database(db)
    viewer = CCTVLogAnalyzerWindow()
    try:
        viewer.current_db, viewer.current_table = str(db), 'logs'
        viewer.setup_table_columns()
        viewer.page_size.setCurrentIndex(viewer.page_size.findData(50))
        viewer.category_selector.setCurrentIndex(viewer.category_selector.findData('User'))
        viewer.table.sortItems(1, Qt.SortOrder.DescendingOrder)
        expected = viewer.table.item(0, 1).text()
        viewer.table.selectRow(0)
        selected = viewer._report_rowids(True)
        page = viewer._report_rowids(False)
        with closing(sqlite3.connect(db)) as conn:
            where, params = viewer._report_scope('selected', selected, page)
            assert conn.execute('SELECT explanation FROM logs' + where, params).fetchall() == [(expected,)]
            where, params = viewer._report_scope('page', selected, page)
            assert conn.execute('SELECT COUNT(*) FROM logs' + where, params).fetchone()[0] == 50
            where, params = viewer._report_scope('filtered', selected, page)
            assert conn.execute('SELECT COUNT(*) FROM logs' + where, params).fetchone()[0] == 105
            where, params = viewer._report_scope('all', selected, page)
            assert conn.execute('SELECT COUNT(*) FROM logs' + where, params).fetchone()[0] == 106
        dialog = ReportOptionsDialog(viewer.columns, AppSettings(), {'filtered': 105, 'all': 106, 'selected': 1, 'page': 50})
        dialog.select_preset('summary')
        assert 'raw_payload' not in dialog.selected_columns()
        assert 'explanation' in dialog.selected_columns()
        assert dialog.scope.currentData() == 'filtered'
        dialog.close()
    finally:
        viewer.close()
        app.processEvents()


@pytest.mark.parametrize('table,type_column,config', [
    ('tvt_logs', 'mlogtype', 'config'),
    ('dahua_logs', 'category', 'Configuration'),
    ('hikvision_logs', 'minor_type', 'Configuration Changed'),
])
def test_export_chooses_log_records_independently_of_columns(tmp_path, table, type_column, config):
    app = QApplication.instance() or QApplication([])
    db = tmp_path / 'logs.db'
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute(f'CREATE TABLE {table} ({type_column} TEXT, explanation TEXT)')
        conn.executemany(f'INSERT INTO {table} VALUES (?, ?)',
                         [('operation', 'LOGIN_MUST_NOT_BE_EXPORTED')] * 100 +
                         [(config, f'Configuration event {i}') for i in range(5)])
    viewer = CCTVLogAnalyzerWindow()
    try:
        viewer.current_db, viewer.current_table = str(db), table
        viewer.setup_table_columns()
        selected, page = [], []
        dialog = ReportOptionsDialog(viewer.columns, AppSettings(), {'filtered': 105, 'all': 105},
            log_type_columns=[type_column],
            type_provider=lambda scope, col: viewer._report_type_counts(scope, selected, page, col),
            count_provider=lambda scope, col, values: viewer._report_record_count(scope, selected, page, col, values))
        assert dialog.export_count == 105
        dialog.check_log_types(False)
        assert dialog.export_count == 0
        for i in range(dialog.log_types.count()):
            item = dialog.log_types.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == config:
                item.setCheckState(Qt.CheckState.Checked)
        assert dialog.export_count == 5
        assert '5 records will be exported' in dialog.record_count_label.text()
        where, params = viewer._report_scope('all', [], [], type_column, dialog.selected_log_types())
        report = tmp_path / 'config.html'
        export_to_html(db, table, report, where, params, report_context={'columns': ['explanation']})
        text = (tmp_path / 'config_index.js').read_text(encoding='utf-8')
        assert 'LOGIN_MUST_NOT_BE_EXPORTED' not in text
        entries = json.loads(text.removeprefix('window.REPORT_INDEX=').strip().removesuffix(';'))
        assert len(entries) == 5
        dialog.close()
    finally:
        viewer.close()
        app.processEvents()
