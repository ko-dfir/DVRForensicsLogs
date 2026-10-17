import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

import cctv_log_analyzer as ui
import scripts.app_settings as app_settings
from scripts.settings_dialog import SettingsDialog


class FakeSettings:
    def __init__(self, **values):
        self.values = dict(app_settings.DEFAULTS, **values)

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def font(self):
        return "Segoe UI", 13


def fake_application(scheme):
    hints = SimpleNamespace(colorScheme=lambda: scheme)
    return SimpleNamespace(styleHints=lambda: hints)


def test_system_theme_follows_windows_colour_scheme(monkeypatch):
    for scheme, expected in ((Qt.ColorScheme.Light, "light"),
                             (Qt.ColorScheme.Dark, "dark"),
                             (Qt.ColorScheme.Unknown, "dark")):
        monkeypatch.setattr(app_settings.QGuiApplication, "instance",
                            lambda scheme=scheme: fake_application(scheme))
        assert app_settings.system_theme() == expected
    assert app_settings.resolve_theme("light") == "light"
    assert app_settings.resolve_theme("dark") == "dark"


def test_system_is_the_default_and_uses_the_resolved_stylesheet(monkeypatch):
    assert app_settings.DEFAULTS["theme"] == "system"
    for resolved in ("light", "dark"):
        monkeypatch.setattr(app_settings, "system_theme", lambda resolved=resolved: resolved)
        assert (ui.application_stylesheet("system", "Segoe UI", 13)
                == ui.application_stylesheet(resolved, "Segoe UI", 13))


def test_viewer_switches_live_only_when_following_system(monkeypatch):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.recents, "recent", lambda _limit: [])
    viewer = ui.CCTVLogAnalyzerWindow()
    try:
        fake = FakeSettings(theme="system")
        viewer.settings = fake
        monkeypatch.setattr(app_settings, "system_theme", lambda: "light")
        viewer._system_colour_scheme_changed(Qt.ColorScheme.Light)
        assert viewer.styleSheet() == ui.application_stylesheet("light", "Segoe UI", 13)
        monkeypatch.setattr(app_settings, "system_theme", lambda: "dark")
        viewer._system_colour_scheme_changed(Qt.ColorScheme.Dark)
        assert viewer.styleSheet() == ui.application_stylesheet("dark", "Segoe UI", 13)
        fake.values["theme"] = "light"  # an explicit choice is not overridden
        viewer.apply_settings()
        viewer._system_colour_scheme_changed(Qt.ColorScheme.Dark)
        assert viewer.styleSheet() == ui.application_stylesheet("light", "Segoe UI", 13)
    finally:
        viewer.close()
        application.processEvents()


def test_settings_dialog_offers_and_saves_system(monkeypatch):
    QApplication.instance() or QApplication([])
    fake = FakeSettings()
    dialog = SettingsDialog(fake)
    assert [dialog.theme.itemData(i) for i in range(dialog.theme.count())] == ["system", "dark", "light"]
    assert dialog.theme.currentData() == "system"
    dialog.theme.setCurrentIndex(dialog.theme.findData("dark"))
    dialog._save()
    assert fake.values["theme"] == "dark"
    assert SettingsDialog(fake).theme.currentData() == "dark"
