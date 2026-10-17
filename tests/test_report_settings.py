import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from scripts.app_settings import AppSettings, DEFAULTS
from scripts.settings_dialog import SettingsDialog


class MemorySettings:
    def __init__(self):
        self.values = dict(DEFAULTS)

    def get(self, key):
        return self.values[key]

    def set(self, key, value):
        self.values[key] = value

    def font(self):
        return self.values["font_family"], self.values["font_size"]


def test_report_preferences_are_saved_from_settings_dialog():
    application = QApplication.instance() or QApplication([])
    settings = MemorySettings()
    dialog = SettingsDialog(settings)
    try:
        dialog.report_title.setText("Blue case report")
        dialog.report_page_size.setValue(75)
        dialog.report_show_metadata.setChecked(False)
        dialog._save()
        assert settings.get("report_title") == "Blue case report"
        assert settings.get("report_page_size") == 75
        assert settings.get("report_show_metadata") is False
    finally:
        dialog.close()
        application.processEvents()


def test_qsettings_boolean_strings_are_not_treated_as_true_integers():
    class StoredValues:
        def value(self, key, default):
            return "false" if key == "report_show_metadata" else default

    settings = AppSettings.__new__(AppSettings)
    settings._settings = StoredValues()
    assert settings.get("report_show_metadata") is False
