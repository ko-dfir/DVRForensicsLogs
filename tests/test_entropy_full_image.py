import os
import sqlite3
from contextlib import closing
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer
from scripts.entropy_dialog import EntropyWorker, EntropyDialog
from scripts.entropy_scan import interpret_window


def test_full_scan_covers_tail_and_paginates_candidates(tmp_path):
    app = QApplication.instance() or QApplication([])
    image = tmp_path / 'unknown.img'
    # Candidate content occurs at the very end, beyond the first 200 result rows.
    data = bytes(1024) * 255 + b'user login action test\n' * 8
    image.write_bytes(data)
    worker = EntropyWorker(str(image), 0, None, 1024)
    results, errors, progress = [], [], []
    worker.result.connect(lambda path, summary, cancelled: results.append((path, summary, cancelled)))
    worker.failed.connect(errors.append)
    worker.progress.connect(lambda done, total: progress.append((done, total)))
    worker.run()
    assert not errors
    path, summary, cancelled = results[0]
    dialog = EntropyDialog(str(image), lambda _: None)
    try:
        assert dialog.scope.currentData() == 'all'
        assert not dialog.start_edit.isEnabled()
        assert summary['processed'] == summary['requested'] == len(data)
        assert not cancelled
        assert progress[-1] == (len(data), len(data))
        dialog.show_results(path, summary, cancelled)
        assert dialog.table.rowCount() == 200
        dialog.change_page(1)
        assert dialog.table.rowCount() == 56
        dialog.result_filter.setCurrentIndex(1)
        assert dialog.table.rowCount() == 1
        assert dialog.table.item(0, 6).text() == str(255 * 1024)
        assert 'readable text' in dialog.table.item(0, 5).text()
        dialog.scope.setCurrentIndex(1)
        assert dialog.start_edit.isEnabled()
    finally:
        dialog.reject()
        app.processEvents()
    assert not Path(path).exists()


def test_cancelled_full_scan_retains_partial_coverage(tmp_path, monkeypatch):
    from scripts import entropy_dialog
    original = entropy_dialog.iter_entropy_profile
    image = tmp_path / 'unknown.img'
    image.write_bytes(bytes(4096))
    worker = EntropyWorker(str(image), 0, None, 1024)
    interrupted = [False]
    monkeypatch.setattr(worker, 'isInterruptionRequested', lambda: interrupted[0])
    def interrupt_after_first(*args, **kwargs):
        for row in original(*args, **kwargs):
            yield row
            interrupted[0] = True
    monkeypatch.setattr(entropy_dialog, 'iter_entropy_profile', interrupt_after_first)
    results = []
    worker.result.connect(lambda path, summary, cancelled: results.append((path, summary, cancelled)))
    worker.run()
    path, summary, cancelled = results[0]
    try:
        assert cancelled
        assert summary['processed'] == 1024
        assert summary['requested'] == 4096
        with closing(sqlite3.connect(path)) as conn:
            assert conn.execute('SELECT count(*) FROM windows').fetchone()[0] == 1
    finally:
        Path(path).unlink()


def test_zero_and_high_entropy_are_not_log_detections():
    for item in ({'zero_ratio': 1, 'printable_ratio': 0, 'entropy': 0},
                 {'zero_ratio': 0.004, 'printable_ratio': 0.38, 'entropy': 8}):
        description, candidate = interpret_window(item)
        assert not candidate
        assert 'log found' not in description


def test_dialog_cancels_running_thread_and_keeps_partial_results(tmp_path):
    app = QApplication.instance() or QApplication([])
    image = tmp_path / 'unknown.img'
    image.write_bytes(bytes(16 * 1024**2))
    dialog = EntropyDialog(str(image), lambda _: None)
    dialog.start_scan()
    loop = QEventLoop()
    dialog.worker.finished.connect(loop.quit)
    QTimer.singleShot(0, dialog.reject)
    QTimer.singleShot(10000, loop.quit)
    loop.exec()
    try:
        assert dialog.worker.wait(1000)
        app.processEvents()
        assert 'Cancelled' in dialog.status.text()
        assert dialog.database
        path = dialog.database
    finally:
        dialog.worker.requestInterruption()
        dialog.worker.wait()
        dialog.reject()
    assert not Path(path).exists()
