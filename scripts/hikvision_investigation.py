"""SQL-backed Hikvision investigation views for the main PySide6 workbench."""

import sqlite3
from contextlib import closing
from pathlib import Path
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit,
)
from scripts.table_rows import CELL_ALIGNMENT, cell_summary, cell_tooltip, fit_rows

AUDIT_GROUPS = {
    'Video exports / backups': ('export', 'backup', 'recfile_output'),
    'Playback': ('playback', 'playbytime', 'playbyfile'),
    'Illegal access': ('illegal', 'unlawful', 'invalid'),
    'Reboots / power': ('reboot', 'shutdown', 'power', 'abnormal'),
    'Configuration': ('config', 'parameter', 'time sync', 'initialize hdd'),
}


class HikvisionInvestigation(QWidget):
    page_size = 200

    def __init__(self, owner, mode):
        super().__init__(owner)
        self.owner, self.mode = owner, mode
        self.page, self.total = 1, 0
        self.database = ''
        self.rows = []
        self.fields = []
        layout = QVBoxLayout(self)
        note = QLabel('Hikvision only · shares the Log Database global/column/date filters. '
                      'Groups are investigation aids, not proof of intent. Double-click for full details/hex.')
        note.setWordWrap(True)
        layout.addWidget(note)
        bar = QHBoxLayout()
        self.selector = QComboBox()
        self.selector.addItems(['All security events', *AUDIT_GROUPS] if mode == 'audit' else
                               ['All camera events', 'Motion / tampering / VCA', 'Recording'])
        self.selector.setVisible(mode != 'stats')
        self.channel = QComboBox()
        self.channel.addItem('All channels', None)
        self.channel.setVisible(mode == 'camera')
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search these events/types across every page…')
        self.search.returnPressed.connect(self.reset)
        self.selector.currentIndexChanged.connect(self.reset)
        self.channel.currentIndexChanged.connect(self.reset)
        refresh = QPushButton('Apply / Refresh')
        refresh.clicked.connect(self.reset)
        for widget in (self.selector, self.channel, self.search, refresh):
            bar.addWidget(widget)
        layout.addLayout(bar)
        self.table = QTableWidget()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellClicked.connect(self.inspect)
        self.table.cellDoubleClicked.connect(self.open_record)
        layout.addWidget(self.table, 1)
        self.inspector = QPlainTextEdit()
        self.inspector.setReadOnly(True)
        self.inspector.setMaximumHeight(145)
        self.inspector.setVisible(mode != 'stats')
        layout.addWidget(self.inspector)
        footer = QHBoxLayout()
        self.previous = QPushButton('Previous')
        self.next = QPushButton('Next')
        self.previous.clicked.connect(self.previous_page)
        self.next.clicked.connect(self.next_page)
        self.summary = QLabel('Load Hikvision logs to use this view.')
        for widget in (self.previous, self.next, self.summary):
            footer.addWidget(widget)
        footer.addStretch()
        layout.addLayout(footer)

    def reset(self, *_):
        self.page = 1
        self.refresh()

    def move(self, step):
        self.page = max(1, self.page + step)
        self.refresh()

    @Slot()
    def previous_page(self):
        self.move(-1)

    @Slot()
    def next_page(self):
        self.move(1)

    def clear(self):
        self.rows = []
        self.total = 0
        self.table.setRowCount(0)
        self.inspector.clear()
        self.previous.setEnabled(False)
        self.next.setEnabled(False)
        self.summary.setText('Select the Hikvision logs dataset to use this view.')

    def refresh(self):
        owner = self.owner
        if not owner.current_db or owner.current_table != 'hikvision_logs':
            self.clear()
            return
        if self.database != owner.current_db:
            self.database = owner.current_db
            self.page = 1
            self.search.clear()
            self.selector.setCurrentIndex(0)
        try:
            with closing(sqlite3.connect(f'file:{Path(owner.current_db).as_posix()}?mode=ro', uri=True)) as conn:
                self._query(conn)
        except sqlite3.Error as exc:
            self.clear()
            self.summary.setText('Cannot read investigation view: ' + str(exc))

    def _query(self, conn):
        owner = self.owner
        self.fields = [row[1] for row in conn.execute('PRAGMA table_info(hikvision_logs)')]
        def col(name):
            return 'COALESCE(CAST("' + name + '" AS TEXT), \'\')' if name in self.fields else "''"
        words = 'lower(' + " || ' ' || ".join(col(name) for name in
                    ('minor_type', 'details', 'sdk_macro')) + ')'
        def matches(tokens):
            return '(' + ' OR '.join(f"{words} LIKE '%{token}%'" for token in tokens) + ')'
        where, params = owner._where_clause()
        predicates = [where[7:]] if where else []
        if self.mode == 'audit':
            group = self.selector.currentText()
            if group in AUDIT_GROUPS:
                predicates.append(matches(AUDIT_GROUPS[group]))
            else:
                predicates.append('(' + matches(tuple(t for values in AUDIT_GROUPS.values() for t in values))
                                  + f" OR {col('major_type')} = 'Exception')")
        elif self.mode == 'camera':
            chosen = self.channel.currentData()
            self.channel.blockSignals(True)
            self.channel.clear()
            self.channel.addItem('All channels', None)
            channels = conn.execute(f'SELECT DISTINCT {col("channel")} FROM hikvision_logs{where} '
                                    f'ORDER BY {col("channel")}', params).fetchall()
            for (channel,) in channels:
                if channel not in ('', '0'):
                    self.channel.addItem('Camera ' + str(channel), str(channel))
            self.channel.setCurrentIndex(max(0, self.channel.findData(chosen)))
            self.channel.blockSignals(False)
            if self.channel.currentData() is not None:
                predicates.append(f'{col("channel")} = ?')
                params.append(self.channel.currentData())
            selection = self.selector.currentIndex()
            motion = matches(('motion', 'tampering', 'vca'))
            recording = matches(('record',))
            predicates.append(motion if selection == 1 else recording if selection == 2 else
                              f'({motion} OR {recording} OR {col("major_type")} = \'Alarm\')')
        text = self.search.text().strip()
        if text:
            predicates.append(f"({words} LIKE ? OR lower({col('major_type')}) LIKE ? OR lower({col('minor_code')}) LIKE ?)")
            params.extend(['%' + text.lower() + '%'] * 3)
        clause = ' WHERE ' + ' AND '.join(predicates) if predicates else ''
        if self.mode == 'stats':
            groups = ['major_type', 'minor_code', 'sdk_macro', 'minor_type', 'status']
            group_sql = ', '.join(col(name) for name in groups)
            region = col('region')
            query = (f'SELECT {group_sql}, '
                     f"SUM(CASE WHEN {region} LIKE '%Declared%' THEN 1 ELSE 0 END), "
                     f"SUM(CASE WHEN {region} LIKE '%Alternative%' THEN 1 ELSE 0 END), "
                     f"SUM(CASE WHEN {region} = '' OR ({region} NOT LIKE '%Declared%' AND {region} NOT LIKE '%Alternative%') THEN 1 ELSE 0 END), "
                     f'COUNT(*) FROM hikvision_logs{clause} GROUP BY {group_sql}')
            self.total = conn.execute('SELECT COUNT(*) FROM (' + query + ')', params).fetchone()[0]
            columns = [*groups, 'declared', 'residual', 'other / not stored', 'total']
            order = ' ORDER BY 9 DESC, 1, 2, 3, 4, 5'
        else:
            columns = [name for name in ('timestamp', 'minor_type', 'username', 'channel', 'ip', 'details', 'offset', 'region') if name in self.fields]
            query = f'SELECT _rowid_, * FROM hikvision_logs{clause}'
            self.total = conn.execute(f'SELECT COUNT(*) FROM hikvision_logs{clause}', params).fetchone()[0]
            order = ' ORDER BY ' + ('time_unix, ' if 'time_unix' in self.fields else '') + '_rowid_'
        pages = max(1, (self.total + self.page_size - 1) // self.page_size)
        self.page = min(self.page, pages)
        fetched = conn.execute(query + order + ' LIMIT ? OFFSET ?',
                               [*params, self.page_size, (self.page - 1) * self.page_size]).fetchall()
        self.rows = [dict(zip(columns, row)) if self.mode == 'stats' else
                     dict(zip(self.fields, row[1:])) for row in fetched]
        self.table.setSortingEnabled(False)
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(self.rows))
        for row, values in enumerate(self.rows):
            for index, field in enumerate(columns):
                value = values.get(field)
                text = '' if value is None else str(value)
                item = QTableWidgetItem(cell_summary(text))
                item.setToolTip(cell_tooltip(text))
                item.setTextAlignment(CELL_ALIGNMENT)
                self.table.setItem(row, index, item)
        # Stable SQL ordering preserves row-to-inspector identity; no local sorting.
        self.table.resizeColumnsToContents()
        for index in range(len(columns)):
            self.table.setColumnWidth(index, min(420, max(100, self.table.columnWidth(index))))
        fit_rows(self.table)
        self.previous.setEnabled(self.page > 1)
        self.next.setEnabled(self.page < pages)
        extra = 'types' if self.mode == 'stats' else 'events'
        count = conn.execute(f'SELECT COUNT(*) FROM hikvision_logs{where}', owner._where_clause()[1]).fetchone()[0]
        self.summary.setText(f'{self.total:,} matching {extra} · page {self.page:,}/{pages:,} · {count:,} records in global scope')
        self.inspector.clear()
        if self.rows:
            self.inspect(0, 0)

    def inspect(self, row, _column):
        if 0 <= row < len(self.rows):
            self.inspector.setPlainText('\n\n'.join(f'{key}\n{value}' for key, value in self.rows[row].items()))

    def open_record(self, row, _column):
        if not 0 <= row < len(self.rows):
            return
        values = self.rows[row]
        if self.mode == 'stats':
            self.owner.filter_header.clear_filters()
            for field in ('major_type', 'minor_type', 'minor_code', 'sdk_macro'):
                if field in self.owner.columns and values.get(field):
                    self.owner.filter_header._editors[self.owner.columns.index(field)].setText(str(values[field]))
            self.owner.reset_and_populate()
            self.owner.tabs.setCurrentWidget(self.owner.tab_search)
        else:
            self.owner.show_record_values(values, 'hikvision_logs', 'Investigation record')
