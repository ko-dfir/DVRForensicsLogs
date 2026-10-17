"""Appearance and history settings for the PySide6 workbench."""

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QCheckBox,
)

class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        heading = QLabel("Appearance, Reports & History")
        heading.setObjectName("SectionTitle")
        root.addWidget(heading)
        form = QFormLayout()

        self.theme = QComboBox()
        self.theme.addItem("System (follow Windows)", "system")
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Light", "light")
        self.theme.setCurrentIndex(max(0, self.theme.findData(settings.get("theme"))))
        form.addRow("Theme", self.theme)

        self.family = QComboBox()
        families = QFontDatabase.families()
        preferred = ["Segoe UI", "Segoe UI Variable Text", "Inter", "Verdana", "Consolas"]
        ordered = [name for name in preferred if name in families]
        ordered.extend(name for name in families if name not in ordered)
        self.family.addItems(ordered)
        self.family.setCurrentText(settings.font()[0])
        form.addRow("Font", self.family)

        self.font_size = QSpinBox()
        self.font_size.setRange(9, 22)
        self.font_size.setSuffix(" px")
        self.font_size.setValue(settings.font()[1])
        form.addRow("Font size", self.font_size)

        self.recent_limit = QSpinBox()
        self.recent_limit.setRange(3, 30)
        self.recent_limit.setValue(int(settings.get("recent_limit")))
        form.addRow("Recent evidence", self.recent_limit)

        report_heading = QLabel("HTML REPORT")
        report_heading.setObjectName("StatusMuted")
        form.addRow(report_heading)
        self.report_title = QLineEdit(str(settings.get("report_title") or ""))
        form.addRow("Report title", self.report_title)
        self.report_page_size = QSpinBox()
        self.report_page_size.setRange(10, 1000)
        self.report_page_size.setSingleStep(25)
        self.report_page_size.setValue(int(settings.get("report_page_size")))
        form.addRow("Rows per HTML file", self.report_page_size)
        self.report_show_metadata = QCheckBox("Include evidence and filter summary")
        self.report_show_metadata.setChecked(bool(settings.get("report_show_metadata")))
        form.addRow("Metadata", self.report_show_metadata)

        logo_row = QHBoxLayout()
        self.report_logo = QLineEdit(str(settings.get("report_logo") or ""))
        self.report_logo.setPlaceholderText("Optional PNG/JPG logo for HTML reports")
        browse_logo = QPushButton("Browse…")
        browse_logo.clicked.connect(self._browse_logo)
        logo_row.addWidget(self.report_logo, 1)
        logo_row.addWidget(browse_logo)
        form.addRow("Report logo", logo_row)
        root.addLayout(form)

        self.preview = QLabel("The quick brown fox · 439,930 forensic records")
        self.preview.setWordWrap(True)
        root.addWidget(self.preview)
        self.family.currentTextChanged.connect(self._preview)
        self.font_size.valueChanged.connect(self._preview)
        self._preview()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _preview(self):
        self.preview.setFont(QFont(self.family.currentText(), self.font_size.value()))

    def _browse_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select report logo", self.report_logo.text(),
            "Images (*.png *.jpg *.jpeg *.gif *.svg);;All files (*.*)")
        if path:
            self.report_logo.setText(path)

    def _save(self):
        self.settings.set("theme", self.theme.currentData())
        self.settings.set("font_family", self.family.currentText())
        self.settings.set("font_size", self.font_size.value())
        self.settings.set("recent_limit", self.recent_limit.value())
        self.settings.set("report_logo", self.report_logo.text().strip())
        self.settings.set("report_title", self.report_title.text().strip()
                          or "CCTV Log Analyzer Report")
        self.settings.set("report_page_size", self.report_page_size.value())
        self.settings.set("report_show_metadata", self.report_show_metadata.isChecked())
        self.accept()
