import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

import cctv_log_analyzer as ui


def test_dropdown_and_calendar_popups_have_theme_specific_colors():
    dark = ui.application_stylesheet("dark", "Segoe UI", 13)
    light = ui.application_stylesheet("light", "Segoe UI", 13)
    for sheet in (dark, light):
        assert "QComboBox QAbstractItemView" in sheet
        assert "QCalendarWidget QAbstractItemView" in sheet
        assert "QMenu::item:selected" in sheet
    assert "background: #1f242e; color: #e6e9f0" in dark
    assert "background: #f0f2f6; color: #171a21" in light
    assert "QMenu::item:selected { color: #171a21; }" in light


def test_dropdown_and_spinbox_arrows_have_images_in_both_themes():
    from pathlib import Path
    build = (Path(ui.__file__).parent / "build.bat").read_text(encoding="utf-8")
    for theme in ("dark", "light"):
        sheet = ui.application_stylesheet(theme, "Segoe UI", 13)
        for subcontrol in ("QComboBox::down-arrow", "QSpinBox::up-arrow",
                           "QSpinBox::up-button", "QSpinBox::down-button",
                           "QScrollBar:horizontal", "QScrollBar::add-page"):
            assert subcontrol in sheet, (theme, subcontrol)
        for direction in ("up", "down"):
            icon = ui.resource_path("assets", f"arrow-{direction}-{theme}.svg")
            assert icon.is_file()
            assert icon.as_posix() in sheet
            assert f"assets\\arrow-{direction}-{theme}.svg" in build  # bundled in the exe
        assert "QCheckBox::indicator:checked" in sheet
        assert "QCheckBox::indicator:disabled" in sheet
        assert ui.resource_path("assets", "check.svg").as_posix() in sheet
        assert "image: none" not in sheet  # disabled controls keep their arrows
    assert "assets\\check.svg" in build


def test_clear_recent_requires_confirmation_and_refreshes_sidebar(monkeypatch):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.recents, "recent", lambda limit: [])
    monkeypatch.setattr(ui.recents, "registered_exports", lambda: [])
    cleared = []
    monkeypatch.setattr(ui.recents, "clear", lambda: cleared.append(True) or 3)
    viewer = ui.CCTVLogAnalyzerWindow()
    try:
        monkeypatch.setattr(viewer, "_choose_recent_cleanup", lambda exports: None)
        viewer.clear_recent_history()
        assert not cleared
        monkeypatch.setattr(viewer, "_choose_recent_cleanup", lambda exports: False)
        viewer.clear_recent_history()
        assert cleared == [True]
        assert viewer.recent_list.item(0).text() == "No recent evidence"
        assert "3 recent" in viewer.statusBar().currentMessage()
    finally:
        viewer.close()
        application.processEvents()


def test_clear_recent_with_exports_calls_exact_file_cleanup(monkeypatch):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.recents, "recent", lambda limit: [])
    monkeypatch.setattr(ui.recents, "registered_exports", lambda: [SimpleNamespace(path="C:\\report.html")])
    operations = []
    monkeypatch.setattr(ui.recents, "delete_registered_exports",
                        lambda: operations.append("files") or 1)
    monkeypatch.setattr(ui.recents, "clear", lambda: operations.append("history") or 2)
    viewer = ui.CCTVLogAnalyzerWindow()
    try:
        monkeypatch.setattr(viewer, "_choose_recent_cleanup", lambda exports: True)
        viewer.clear_recent_history()
        assert operations == ["files", "history"]
    finally:
        viewer.close()
        application.processEvents()
