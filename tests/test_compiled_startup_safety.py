"""Source regressions for the reported compiled signal-connection crash.

These tests do not compile or establish that a Nuitka executable works.
"""

import ast
import os
from pathlib import Path
import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTableWidget, QPushButton
from PySide6.QtTest import QSignalSpy, QTest
from scripts.filter_header import ColumnFilterHeader
from scripts.report_options import ReportOptionsDialog
from scripts.entropy_dialog import EntropyDialog
from scripts.app_settings import DEFAULTS

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('source', [
    'cctv_log_analyzer.py', 'scripts/filter_header.py', 'scripts/entropy_dialog.py',
    'scripts/hikvision_investigation.py', 'scripts/report_options.py',
])
def test_no_lambda_is_connected_to_a_qt_signal(source):
    tree = ast.parse((ROOT / source).read_text(encoding='utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'connect':
            assert not any(isinstance(argument, ast.Lambda) for argument in node.args), (source, node.lineno)


def test_header_slots_resize_move_and_debounce_after_many_connections(qt_app):
    table = QTableWidget(1, 3)
    # Repeated connections exercise the complete class, not a lambda micro-test.
    headers = [ColumnFilterHeader(Qt.Orientation.Horizontal, table) for _ in range(24)]
    header = headers[-1]
    table.setHorizontalHeader(header)
    table.setHorizontalHeaderLabels(['one', 'two', 'three'])
    header.set_columns(['one', 'two', 'three'])
    try:
        meta = header.metaObject()
        for signature in ('_section_geometry_changed(int,int,int)', '_schedule_filters_changed(QString)',
                          '_emit_filters_changed()', '_position_editors()'):
            assert meta.indexOfSlot(signature) >= 0
        spy = QSignalSpy(header.filtersChanged)
        header.resizeSection(0, 220)
        header.moveSection(0, 1)
        qt_app.processEvents()
        assert header._editors[0].x() == header.sectionViewportPosition(0) + 3
        header._editors[0].setText('needle')
        QTest.qWait(450)
        assert spy.count() == 1 and header.filters() == {'one': 'needle'}
        header._editors[0].setText('new')
        header._editors[0].returnPressed.emit()
        QTest.qWait(450)
        assert spy.count() == 2  # Enter stops the pending debounce, no second emission.
    finally:
        table.close()


def test_report_buttons_keep_their_own_preset_and_checkbox_values(qt_app):
    dialog = ReportOptionsDialog(['timestamp', 'raw_json'], DEFAULTS,
                                {'filtered': 2, 'selected': 0, 'page': 2, 'all': 2},
                                log_type_columns=['category'],
                                type_provider=lambda *_: [('config', 1), ('login', 1)])
    buttons = {button.text(): button for button in dialog.findChildren(QPushButton)}
    try:
        buttons['Clear fields'].clicked[bool].emit(True)
        assert dialog.selected_columns() == []
        buttons['Investigation summary'].clicked[bool].emit(False)
        assert dialog.selected_columns() == ['timestamp']
        buttons['All fields'].click()
        assert dialog.selected_columns() == ['timestamp', 'raw_json']
        buttons['Clear log types'].click()
        assert dialog.selected_log_types() == []
        buttons['All log types'].click()
        assert dialog.selected_log_types() is None
    finally:
        dialog.close()


def test_entropy_pager_buttons_have_bound_slots(qt_app, monkeypatch):
    dialog = EntropyDialog('not-opened.img', lambda *_: None)
    steps = []
    monkeypatch.setattr(dialog, 'change_page', steps.append)
    try:
        dialog.previous.setEnabled(True)
        dialog.next.setEnabled(True)
        dialog.next.click()
        dialog.previous.click()
        assert steps == [1, -1]
    finally:
        dialog.close()


def test_build_pins_preflights_and_does_not_assume_runtime_success():
    script = (ROOT / 'build.bat').read_text(encoding='utf-8')
    assert 'set "VENV_DIR=%CCTV_BUILD_VENV%"' in script
    assert '%LOCALAPPDATA%\\CCTVBuild\\venv' in script
    assert '--exe-only' in script
    assert script.index('Inno Setup was not found') < script.index(' -m nuitka ')
    assert '--file-version=%WINDOWS_VERSION%' in script
    assert '--product-version=%WINDOWS_VERSION%' in script
    assert 'compilation success is not runtime validation' in script
    assert 'nuitka==4.2.2' in (ROOT / 'requirements-build.txt').read_text()
    assert 'PySide6==6.11.2' in (ROOT / 'requirements.txt').read_text()


def test_explicit_windows_version_and_bounds(monkeypatch):
    from scripts import versioning
    monkeypatch.setattr(versioning, 'version_info', lambda: dict(version='1.01', windows_version='1.0.1.101'))
    assert versioning.get_version() == '1.01'
    assert versioning.windows_version_tuple() == (1, 0, 1, 101)
    for invalid in ('1.01', '1.2.3.65536', '-1.2.3.4', '1.x.3.4'):
        monkeypatch.setattr(versioning, 'version_info', lambda: dict(version='1.01', windows_version=invalid))
        with pytest.raises(RuntimeError):
            versioning.windows_version_tuple()


def test_native_fault_log_keeps_a_real_descriptor_alive(tmp_path, monkeypatch):
    from scripts import logging_config
    enabled = []
    monkeypatch.setattr(logging_config, '_NATIVE_FAULT_STREAM', None)
    monkeypatch.setattr(logging_config, 'log_dir', lambda: tmp_path)
    monkeypatch.setattr(logging_config.faulthandler, 'enable', lambda **options: enabled.append(options))
    logging_config.enable_native_fault_log()
    stream = logging_config._NATIVE_FAULT_STREAM
    try:
        assert not stream.closed and stream.fileno() >= 0
        assert Path(stream.name) == tmp_path / 'native-crash.log'
        assert enabled == [{'file': stream, 'all_threads': True}]
        logging_config.enable_native_fault_log()
        assert len(enabled) == 1
    finally:
        stream.close()
