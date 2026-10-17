"""Read-only entropy survey with complete byte coverage and paged results."""

import os
import sqlite3
import tempfile
import time
import shutil
import uuid
from contextlib import closing
from pathlib import Path

from PySide6.QtCore import QThread, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QProgressBar, QTableWidget, QTableWidgetItem, QMessageBox, QHeaderView,
)
from scripts.image_io import open_image
from scripts.entropy_scan import iter_entropy_profile, interpret_window


def human_size(value):
    value = float(value)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB':
            return f'{value:.1f} {unit}'
        value /= 1024


class EntropyWorker(QThread):
    progress = Signal(object, object)
    result = Signal(str, dict, bool)
    failed = Signal(str)

    def __init__(self, path, start, length, window, parent=None):
        super().__init__(parent)
        self.path, self.start_byte, self.length, self.window = path, start, length, window

    def run(self):
        database = None
        try:
            with open_image(self.path) as source:
                size = getattr(source, 'size', None)
                if size is None:
                    source.seek(0, 2)
                    size = source.tell()
                if self.start_byte < 0 or self.start_byte >= size:
                    raise ValueError('Start offset is beyond the evidence size or the image is empty.')
                length = size - self.start_byte if self.length is None else min(self.length, size - self.start_byte)
                fd, database = tempfile.mkstemp(prefix='dvr-entropy-', suffix='.sqlite')
                os.close(fd)
                summary = dict(start=self.start_byte, requested=length, processed=0,
                               windows=0, candidates=0, zeros=0, high=0, elapsed=0)
                started = last_event = time.monotonic()
                self.progress.emit(0, length)
                with closing(sqlite3.connect(database)) as conn, conn:
                    conn.execute('CREATE TABLE windows (offset INTEGER PRIMARY KEY, size INTEGER, entropy REAL, '
                                 'printable_ratio REAL, zero_ratio REAL, interpretation TEXT, candidate INTEGER)')
                    for item in iter_entropy_profile(source, self.start_byte, length, self.window,
                                                     cancelled=self.isInterruptionRequested):
                        interpretation, candidate = interpret_window(item)
                        conn.execute('INSERT INTO windows VALUES (?, ?, ?, ?, ?, ?, ?)',
                                     (item['offset'], item['size'], item['entropy'], item['printable_ratio'],
                                      item['zero_ratio'], interpretation, int(candidate)))
                        summary['processed'] += item['size']
                        summary['windows'] += 1
                        summary['candidates'] += int(candidate)
                        summary['zeros'] += int(item['zero_ratio'] >= 0.98)
                        summary['high'] += int(item['entropy'] >= 7.5)
                        now = time.monotonic()
                        if now - last_event >= 0.3:
                            self.progress.emit(summary['processed'], length)
                            last_event = now
                        if summary['windows'] % 1000 == 0:
                            conn.commit()
                    conn.execute('CREATE INDEX candidate_windows ON windows(candidate, offset)')
                summary['elapsed'] = time.monotonic() - started
                self.progress.emit(summary['processed'], length)
                cancelled = self.isInterruptionRequested()
                if not cancelled and summary['processed'] != length:
                    raise OSError('Evidence ended before the requested range was read; scan is incomplete.')
            self.result.emit(database, summary, cancelled)
        except Exception as exc:
            if database:
                Path(database).unlink(missing_ok=True)
            self.failed.emit(str(exc))


class EntropyDialog(QDialog):
    PAGE_SIZE = 200

    def __init__(self, path, log_callback, parent=None, *, results_dir=None):
        super().__init__(parent)
        self.path, self.log_callback, self.worker = path, log_callback, None
        self.database, self.page = None, 0
        self.results_dir, self.persistent = results_dir, False
        self.outcome, self.last_summary, self.saved_results = 'not_started', {}, []
        self.setWindowTitle('Find regions to investigate — entropy survey')
        self.resize(1080, 720)
        layout = QVBoxLayout(self)
        note = QLabel(
            'What does this do? Reads the image in blocks and measures how varied the bytes are (0–8). '
            'It helps locate readable or structured areas worth inspecting for metadata or logs. '
            'It does not extract logs or determine that an image has no logs.\n'
            'Entire image reads every byte, including the end of the disk; it can take hours on large images. '
            'Selected region examines only the range you enter. Evidence is opened read-only.')
        note.setWordWrap(True)
        layout.addWidget(note)
        controls = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.addItem('Entire image — read every byte', 'all')
        self.scope.addItem('Selected region', 'region')
        self.scope.currentIndexChanged.connect(self.scope_changed)
        self.start_edit, self.length_edit = QLineEdit('0'), QLineEdit('256')
        self.window = QComboBox()
        for label, value in (('64 KiB — finer detail', 65536), ('1 MiB — recommended', 1024**2),
                             ('4 MiB', 4*1024**2), ('16 MiB', 16*1024**2)):
            self.window.addItem(label, value)
        self.window.setCurrentIndex(1)
        self.window.setToolTip('Every byte is read. Smaller blocks reveal smaller regions; large blocks can hide small logs inside video data.')
        controls.addWidget(self.scope)
        controls.addWidget(QLabel('Start (MiB)'))
        controls.addWidget(self.start_edit)
        controls.addWidget(QLabel('Length (MiB)'))
        controls.addWidget(self.length_edit)
        controls.addWidget(QLabel('Block size'))
        controls.addWidget(self.window)
        layout.addLayout(controls)
        self.run_button = QPushButton('Scan entire image')
        self.run_button.clicked.connect(self.start_scan)
        layout.addWidget(self.run_button)
        self.progress = QProgressBar()
        layout.addWidget(self.progress)
        self.status = QLabel('Ready. Choose the scope and press Scan.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.summary_label = QLabel(
            'Reading the results: mostly zeros = little content; readable or repetitive bytes = inspect further; '
            'high byte diversity = possibly compressed video or encrypted data. These are clues, not identifications.')
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        pager = QHBoxLayout()
        self.result_filter = QComboBox()
        self.result_filter.addItems(['All scanned blocks', 'Candidates for manual inspection'])
        self.result_filter.currentIndexChanged.connect(self.reset_page)
        self.previous, self.next = QPushButton('Previous'), QPushButton('Next')
        self.previous.clicked.connect(self.previous_page)
        self.next.clicked.connect(self.next_page)
        self.page_label = QLabel('No results')
        for widget in (self.result_filter, self.previous, self.next, self.page_label):
            pager.addWidget(widget)
        pager.addStretch()
        layout.addLayout(pager)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ['Offset (hex)', 'Bytes', 'Entropy (0–8)', 'Readable text %', 'Zero bytes %', 'Interpretation', 'Offset (bytes)'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(0, 150)
        self.table.setColumnWidth(5, 380)
        layout.addWidget(self.table)
        footer = QLabel('Offsets are absolute bytes in the logical evidence stream, not positions in the compressed E01 file. '
                        'Results are paged from a temporary database; memory does not grow with the image size.')
        footer.setWordWrap(True)
        layout.addWidget(footer)
        self.close_button = QPushButton('Close')
        self.close_button.clicked.connect(self.reject)
        layout.addWidget(self.close_button)
        self.scope_changed()
        self.reset_page()

    def scope_changed(self):
        region = self.scope.currentData() == 'region'
        self.start_edit.setEnabled(region)
        self.length_edit.setEnabled(region)
        self.run_button.setText('Scan selected region' if region else 'Scan entire image')

    def clear_database(self):
        if self.database:
            if not self.persistent:
                Path(self.database).unlink(missing_ok=True)
            self.database = None
            self.persistent = False

    def start_scan(self):
        start, length = 0, None
        if self.scope.currentData() == 'region':
            try:
                start = int(self.start_edit.text()) * 1024**2
                length = int(self.length_edit.text()) * 1024**2
                if start < 0 or length <= 0:
                    raise ValueError()
            except ValueError:
                QMessageBox.warning(self, 'Scan range', 'Enter a non-negative start and a positive length in MiB.')
                return
        self.clear_database()
        self.outcome = 'running'
        self.reset_page()
        for widget in (self.run_button, self.scope, self.window, self.start_edit, self.length_edit):
            widget.setEnabled(False)
        self.close_button.setText('Cancel scan')
        self.progress.setRange(0, 0)
        self.status.setText('Opening evidence…')
        self.summary_label.setText('Scan in progress. Results will remain available if you cancel.')
        scope = 'entire image (every byte)' if length is None else f'{human_size(length)} from byte {start}'
        self.log_callback(f'[ENTROPY] Read-only scan: {scope}; block={human_size(self.window.currentData())}; source={self.path}')
        self.started = time.monotonic()
        self.worker = EntropyWorker(self.path, start, length, self.window.currentData(), self)
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(self.show_results)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(self.scan_finished)
        self.worker.start()

    def update_progress(self, done, total):
        self.progress.setRange(0, 10000)
        percent = done * 100 / max(1, total)
        self.progress.setValue(int(percent * 100))
        self.progress.setFormat(f'{percent:.2f}% — {human_size(done)} / {human_size(total)}')
        elapsed = time.monotonic() - self.started
        speed = done / max(0.001, elapsed)
        eta = f'{(total - done) / speed / 60:.1f} min remaining (estimate)' if speed else 'Calculating speed…'
        self.status.setText(f'{human_size(speed)}/s · {eta}')

    def show_results(self, database, summary, cancelled):
        if self.results_dir:
            destination = Path(self.results_dir) / f'entropy-{uuid.uuid4().hex[:12]}.sqlite'
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(database, destination)
                Path(database).unlink()
            except OSError as exc:
                self.log_callback(f'[ENTROPY ERROR] Could not preserve results: {exc}')
            else:
                database = str(destination)
                self.persistent = True
                self.saved_results.append(database)
                self.log_callback(f'[ENTROPY] Results saved: {database}')
        self.database = database
        self.outcome = 'cancelled' if cancelled else 'completed'
        self.last_summary = summary
        complete = not cancelled and summary['processed'] == summary['requested']
        state = 'Completed' if complete else 'Cancelled — partial coverage'
        self.status.setText(f"{state}: read {human_size(summary['processed'])} of {human_size(summary['requested'])}; "
                            f"{summary['windows']:,} blocks in {summary['elapsed'] / 60:.1f} minutes.")
        self.summary_label.setText(
            f"{summary['candidates']:,} candidate blocks for manual inspection; {summary['zeros']:,} mostly zero blocks; "
            f"{summary['high']:,} high-diversity blocks. Candidate means a heuristic clue, not a recovered log. "
            'Zero candidates does not establish that there are no logs; a smaller block size may reveal smaller regions.')
        self.reset_page()
        self.log_callback(f"[ENTROPY] {state}: bytes={summary['processed']}/{summary['requested']}; "
                          f"windows={summary['windows']}; candidate_windows={summary['candidates']}")

    def reset_page(self):
        self.page = 0
        self.show_page()

    def change_page(self, delta):
        self.page = max(0, self.page + delta)
        self.show_page()

    @Slot()
    def previous_page(self):
        self.change_page(-1)

    @Slot()
    def next_page(self):
        self.change_page(1)

    def show_page(self):
        rows, count = [], 0
        if self.database:
            where = ' WHERE candidate = 1' if self.result_filter.currentIndex() == 1 else ''
            with closing(sqlite3.connect(self.database)) as conn:
                count = conn.execute('SELECT COUNT(*) FROM windows' + where).fetchone()[0]
                rows = conn.execute('SELECT * FROM windows' + where + ' ORDER BY offset LIMIT ? OFFSET ?',
                                    (self.PAGE_SIZE, self.page * self.PAGE_SIZE)).fetchall()
        self.table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            offset, size, entropy, printable, zeros, interpretation, _candidate = item
            values = [f'0x{offset:X}', str(size), f'{entropy:.4f}', f'{100*printable:.2f}',
                      f'{100*zeros:.2f}', interpretation, str(offset)]
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setToolTip(value)
                self.table.setItem(row, col, cell)
        self.table.resizeRowsToContents()
        self.previous.setEnabled(self.page > 0)
        self.next.setEnabled((self.page + 1) * self.PAGE_SIZE < count)
        self.page_label.setText(f'Page {self.page + 1} of {max(1, (count + self.PAGE_SIZE - 1) // self.PAGE_SIZE)} · {count:,} blocks')

    def show_error(self, message):
        self.outcome = 'failed'
        self.status.setText(f'Failed: {message}')
        self.log_callback(f'[ENTROPY ERROR] {message}')

    def scan_finished(self):
        self.progress.setRange(0, 10000)
        for widget in (self.run_button, self.scope, self.window):
            widget.setEnabled(True)
        self.scope_changed()
        self.close_button.setText('Close')

    def done(self, result):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.status.setText('Cancelling after the current block… Partial results will be shown.')
            return
        self.clear_database()
        super().done(result)

    def reject(self):
        self.done(QDialog.DialogCode.Rejected)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.done(QDialog.DialogCode.Rejected)
            event.ignore()
            return
        self.clear_database()
        super().closeEvent(event)
