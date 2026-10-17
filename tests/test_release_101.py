import io
import os
import sqlite3
import struct
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QPlainTextEdit
from cctv_log_analyzer import CCTVLogAnalyzerWindow
from scripts.table_rows import cell_summary
from scripts.engine_tvt import TVTEngine
from scripts.engine_hikvision import HikvisionEngine
from scripts.entropy_scan import entropy_profile
from scripts.entropy_dialog import EntropyWorker


def test_entropy_limits_progress_and_cancellation(tmp_path):
    data = b'\x00' * 1024 + bytes(range(256)) * 4
    progress = []
    rows = entropy_profile(io.BytesIO(data), 0, len(data), 1024,
                           lambda done, total: progress.append((done, total)),
                           lambda: bool(progress))
    assert len(rows) == 1
    assert rows[0]['zero_ratio'] == 1
    assert progress == [(1024, 2048)]
    image = tmp_path / 'unknown.img'
    image.write_bytes(data)
    worker = EntropyWorker(str(image), 1024, 4096, 1024)
    result = []
    worker.result.connect(lambda path, summary, cancelled: result.append((path, summary)))
    worker.run()
    path, summary = result[0]
    try:
        connection = sqlite3.connect(path)
        rows = connection.execute('SELECT offset, entropy FROM windows').fetchall()
        connection.close()
        assert rows == [(1024, 8.0)]  # clipped to end of evidence
        assert summary['processed'] == summary['requested'] == 1024
    finally:
        Path(path).unlink()


def test_tvt_raw_hex_preserves_binary_header_and_offset(tmp_path):
    payload = b'mlogtype:operation;action:2;ip:127.0.0.1'
    header = b'\xaa\xab' + bytes(14) + struct.pack('<I', 1600000000)
    record = header + b'\x05admin' + struct.pack('<H', len(payload)) + payload
    image = tmp_path / 'tvt.img'
    image.write_bytes(bytes(64) + record)
    engine = TVTEngine(str(image))
    rows = engine.extract_logs(limit_bytes=image.stat().st_size)
    database = tmp_path / 'tvt.db'
    engine.save_to_sqlite(rows, database)
    with sqlite3.connect(database) as conn:
        offset, raw_start, raw_hex = conn.execute(
            'SELECT source_offset, raw_record_offset, raw_record_hex FROM tvt_logs').fetchone()
    assert raw_start == 64
    assert offset == 64 + len(record) - len(payload)
    assert bytes.fromhex(raw_hex) == record


def test_hikvision_database_preserves_raw_hex(tmp_path):
    record = struct.pack('<4sIIHH', b'RATS', 0x14, 1600000000, 3, 65) + bytes(112)
    image = tmp_path / 'hik.img'
    image.write_bytes(bytes(64) + record)
    database = tmp_path / 'hik.db'
    HikvisionEngine(str(image)).carve_to_sqlite(
        str(database), limit_bytes=image.stat().st_size,
        structure={'scan_regions': [('test', 0, image.stat().st_size)]})
    with sqlite3.connect(database) as conn:
        offset, raw_hex = conn.execute('SELECT offset, raw_record_hex FROM hikvision_logs').fetchone()
    assert offset == 64
    assert bytes.fromhex(raw_hex) == record


def test_source_database_filter_global_and_export_context(tmp_path):
    app = QApplication.instance() or QApplication([])
    database = tmp_path / 'dahua.db'
    explanation = 'Complete explanation with many details. ' * 20
    with sqlite3.connect(database) as conn:
        conn.execute('CREATE TABLE dahua_logs(source_database TEXT, explanation TEXT)')
        conn.executemany('INSERT INTO dahua_logs VALUES (?, ?)',
                         [('A.db', explanation)] * 125 + [('B.db', 'Second database')])
    viewer = CCTVLogAnalyzerWindow()
    try:
        viewer.current_db, viewer.current_table = str(database), 'dahua_logs'
        viewer.setup_table_columns()
        viewer.page_size.setCurrentIndex(viewer.page_size.findData(50))
        viewer.database_selector.setCurrentIndex(viewer.database_selector.findData('A.db'))
        assert viewer.total_rows == 125
        viewer.go_next_page()
        assert viewer.current_page == 2
        # Rows show a summary; the full explanation is kept for record details.
        assert viewer.table.item(0, 1).text() == cell_summary(explanation)
        assert viewer.table.item(0, 1).data(Qt.ItemDataRole.UserRole) == explanation
        assert viewer._where_clause()[1] == ['A.db']
        assert 'A.db' in viewer._export_context()['metadata']['Active filters']
        viewer.clear_filters()
        assert viewer.total_rows == 126
    finally:
        viewer.close()
        app.processEvents()


def test_inspector_hex_keeps_zero_header_offset(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    database = tmp_path / 'tvt.db'
    with sqlite3.connect(database) as conn:
        conn.execute('CREATE TABLE tvt_logs(source_offset INTEGER, raw_record_offset INTEGER, raw_record_hex TEXT)')
        conn.execute("INSERT INTO tvt_logs VALUES (20, 0, 'aaab0001')")
    viewer = CCTVLogAnalyzerWindow()
    try:
        viewer.current_db, viewer.current_table = str(database), 'tvt_logs'
        viewer.setup_table_columns()
        viewer.populate_table()
        captured = []
        def inspect(dialog):
            captured.extend(widget.toPlainText() for widget in dialog.findChildren(QPlainTextEdit))
        monkeypatch.setattr(QDialog, 'exec', inspect)
        viewer.open_record_details(0, 0)
        assert any('0000000000000000  aa ab 00 01' in value for value in captured)
    finally:
        viewer.close()
        app.processEvents()
