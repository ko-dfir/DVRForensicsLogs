"""Per-export choices of HTML report records, fields and presentation."""

from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QSpinBox, QCheckBox, QListWidget, QListWidgetItem,
    QPushButton, QDialogButtonBox, QFileDialog, QMessageBox, QTabWidget, QWidget,
)


class ReportOptionsDialog(QDialog):
    def __init__(self, columns, settings, counts, parent=None, *,
                 log_type_columns=(), type_provider=None, count_provider=None):
        super().__init__(parent)
        self.type_provider, self.count_provider = type_provider, count_provider
        self.setWindowTitle('Choose HTML report content')
        self.resize(640, 650)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.scope = QComboBox()
        for key, label in (('filtered', 'All matching the current filters'),
                           ('selected', 'Selected rows'), ('page', 'Current results page'),
                           ('all', 'Entire dataset — ignore current filters')):
            self.scope.addItem(f'{label} ({counts.get(key, 0):,} records)', key)
            if not counts.get(key, 0):
                self.scope.model().item(self.scope.count() - 1).setEnabled(False)
        form.addRow('Records to include', self.scope)
        hint = QLabel('Filtered records use the main window search, dates, column filters, '
                      'category, source database and TVT mlogtype. Selected rows and current page '
                      'refer to the rows currently displayed.')
        hint.setWordWrap(True)
        form.addRow(hint)
        self.title = QLineEdit(str(settings.get('report_title') or 'CCTV Log Analyzer Report'))
        form.addRow('Report title', self.title)
        self.page_size = QSpinBox()
        self.page_size.setRange(10, 1000)
        self.page_size.setValue(int(settings.get('report_page_size')))
        form.addRow('Rows per HTML file', self.page_size)
        self.metadata = QCheckBox('Include evidence and filter summary')
        self.metadata.setChecked(bool(settings.get('report_show_metadata')))
        form.addRow('Metadata', self.metadata)
        logo_row = QHBoxLayout()
        self.logo = QLineEdit(str(settings.get('report_logo') or ''))
        browse = QPushButton('Browse…')
        browse.clicked.connect(self.browse_logo)
        logo_row.addWidget(self.logo)
        logo_row.addWidget(browse)
        form.addRow('Logo (optional)', logo_row)
        layout.addLayout(form)
        tabs = QTabWidget()
        record_tab = QWidget()
        record_layout = QVBoxLayout(record_tab)
        type_note = QLabel('Choose the log types that will actually be exported. For example, select only '
                           'config in TVT mlogtype. You may check several types. This narrows the record scope above.')
        type_note.setWordWrap(True)
        record_layout.addWidget(type_note)
        self.type_column = QComboBox()
        self.type_column.addItems(log_type_columns)
        record_layout.addWidget(self.type_column)
        self.log_types = QListWidget()
        record_layout.addWidget(self.log_types, 1)
        type_buttons = QHBoxLayout()
        for label, handler in (('All log types', self.check_all_log_types),
                               ('Clear log types', self.clear_log_types)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            type_buttons.addWidget(button)
        record_layout.addLayout(type_buttons)
        tabs.addTab(record_tab, 'Records / log types')
        field_tab = QWidget()
        field_layout = QVBoxLayout(field_tab)
        note = QLabel('Choose which fields will be written to the report and its search index. '
                      'Category and mlogtype controls are available when their columns are included. '
                      'Search always covers all exported pages.')
        note.setWordWrap(True)
        field_layout.addWidget(note)
        presets = QHBoxLayout()
        for label, handler in (('All fields', self.select_all_fields),
                               ('Investigation summary', self.select_summary_fields),
                               ('Clear fields', self.clear_fields)):
            button = QPushButton(label)
            button.clicked.connect(handler)
            presets.addWidget(button)
        field_layout.addLayout(presets)
        self.fields = QListWidget()
        for column in columns:
            item = QListWidgetItem(column)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.fields.addItem(item)
        field_layout.addWidget(self.fields, 1)
        self.selection_label = QLabel()
        field_layout.addWidget(self.selection_label)
        self.fields.itemChanged.connect(self.update_selection_label)
        self.update_selection_label()
        tabs.addTab(field_tab, 'Columns')
        layout.addWidget(tabs, 1)
        self.record_count_label = QLabel()
        layout.addWidget(self.record_count_label)
        self.type_column.setEnabled(bool(log_type_columns))
        self.log_types.itemChanged.connect(self.update_record_count)
        self.type_column.currentTextChanged.connect(self.load_log_types)
        self.scope.currentIndexChanged.connect(self.load_log_types)
        self.load_log_types()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Continue to save…')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @Slot()
    def check_all_log_types(self):
        self.check_log_types(True)

    @Slot()
    def clear_log_types(self):
        self.check_log_types(False)

    @Slot()
    def select_all_fields(self):
        self.select_preset('all')

    @Slot()
    def select_summary_fields(self):
        self.select_preset('summary')

    @Slot()
    def clear_fields(self):
        self.select_preset('none')

    def load_log_types(self):
        # Retain checked types when changing record scope, where possible.
        previous_column = getattr(self, '_loaded_type_column', None)
        previous = self.selected_log_types()
        column = self.type_column.currentText()
        rows = self.type_provider(self.scope.currentData(), column) if self.type_provider and column else []
        self.log_types.blockSignals(True)
        self.log_types.clear()
        for value, count in rows:
            label = '(missing)' if value is None else str(value) or '(empty)'
            item = QListWidgetItem(f'{label} — {count:,} records')
            item.setData(Qt.ItemDataRole.UserRole, value)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = previous is None or previous_column != column or value in previous
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.log_types.addItem(item)
        self.log_types.blockSignals(False)
        self._loaded_type_column = column
        self.update_record_count()

    def selected_log_types(self):
        # None means no additional restriction, including absent/empty types.
        values = [self.log_types.item(i).data(Qt.ItemDataRole.UserRole)
                  for i in range(self.log_types.count())
                  if self.log_types.item(i).checkState() == Qt.CheckState.Checked]
        return None if len(values) == self.log_types.count() else values

    def check_log_types(self, checked):
        self.log_types.blockSignals(True)
        for i in range(self.log_types.count()):
            self.log_types.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.log_types.blockSignals(False)
        self.update_record_count()

    def update_record_count(self):
        self.export_count = (self.count_provider(self.scope.currentData(), self.type_column.currentText(),
                                                self.selected_log_types()) if self.count_provider else None)
        self.record_count_label.setText(f'{self.export_count:,} records will be exported'
                                       if self.export_count is not None else '')

    def selected_columns(self):
        return [self.fields.item(i).text() for i in range(self.fields.count())
                if self.fields.item(i).checkState() == Qt.CheckState.Checked]

    def update_selection_label(self):
        self.selection_label.setText(f'{len(self.selected_columns())} of {self.fields.count()} fields selected')

    def select_preset(self, preset):
        summary = {'timestamp', 'time_utc', 'username', 'ip', 'channel', 'category',
                   'event_category', 'major_type', 'minor_type', 'mlogtype', 'event',
                   'action', 'explanation', 'event_description', 'source_database',
                   'source_offset', 'offset'}
        for i in range(self.fields.count()):
            item = self.fields.item(i)
            checked = preset == 'all' or (preset == 'summary' and item.text() in summary)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def browse_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Select report logo', self.logo.text(),
                                             'Images (*.png *.jpg *.jpeg *.gif *.svg)')
        if path:
            self.logo.setText(path)

    def accept(self):
        if self.export_count == 0:
            QMessageBox.warning(self, 'Report records', 'No records match these log types and scope.')
            return
        if not self.selected_columns():
            QMessageBox.warning(self, 'Report fields', 'Select at least one field for the report.')
            return
        if not self.scope.model().item(self.scope.currentIndex()).isEnabled():
            QMessageBox.warning(self, 'Report records', 'There are no records in this scope.')
            return
        super().accept()

    def report_context(self):
        return {'columns': self.selected_columns(), 'title': self.title.text().strip() or 'CCTV Log Analyzer Report',
                'page_size': self.page_size.value(), 'show_metadata': self.metadata.isChecked()}
