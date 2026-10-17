"""Table header with a debounced filter input embedded in every column."""

from PySide6.QtCore import QSize, QTimer, Signal, Slot
from PySide6.QtWidgets import QHeaderView, QLineEdit


class ColumnFilterHeader(QHeaderView):
    filtersChanged = Signal()

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self._editors = []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(350)
        self._timer.timeout.connect(self._emit_filters_changed)
        self.sectionResized.connect(self._section_geometry_changed)
        self.sectionMoved.connect(self._section_geometry_changed)
        self.geometriesChanged.connect(self._position_editors)
        self.setMinimumHeight(62)

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(hint.width(), max(62, hint.height() + 30))

    def set_columns(self, columns):
        for editor in self._editors:
            editor.deleteLater()
        self._editors = []
        for column in columns:
            editor = QLineEdit(self.viewport())
            editor.setObjectName("ColumnFilter")
            editor.setPlaceholderText("Filter…")
            editor.setToolTip(f"Filter {column}")
            editor.textChanged.connect(self._schedule_filters_changed)
            editor.returnPressed.connect(self._emit_filters_changed)
            editor.show()
            self._editors.append(editor)
        QTimer.singleShot(0, self._position_editors)

    def filters(self):
        model = self.model()
        result = {}
        if model is None:
            return result
        for logical, editor in enumerate(self._editors):
            value = editor.text().strip()
            if value:
                result[str(model.headerData(logical, self.orientation()))] = value
        return result

    @Slot()
    def _emit_filters_changed(self):
        self._timer.stop()
        self.filtersChanged.emit()

    @Slot(str)
    def _schedule_filters_changed(self, _text):
        self._timer.start()

    @Slot(int, int, int)
    def _section_geometry_changed(self, _logical, _old, _new):
        self._position_editors()

    def clear_filters(self):
        self._timer.stop()
        for editor in self._editors:
            editor.blockSignals(True)
            editor.clear()
            editor.blockSignals(False)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_editors()

    @Slot()
    def _position_editors(self):
        height = 25
        y = max(30, self.height() - height - 4)
        for logical, editor in enumerate(self._editors):
            x = self.sectionViewportPosition(logical) + 3
            width = max(30, self.sectionSize(logical) - 6)
            editor.setGeometry(x, y, width, height)
            editor.setVisible(x + width > 0 and x < self.viewport().width())
