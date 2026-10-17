import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

import cctv_log_analyzer as ui


def test_open_image_prefers_latest_existing_recent_folder(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    evidence = tmp_path / "disk.001"
    evidence.write_bytes(b"evidence")
    monkeypatch.setattr(ui.recents, "recent", lambda _limit: [
        SimpleNamespace(image_path=str(evidence), exists=True, brand="TVT")])
    viewer = ui.CCTVLogAnalyzerWindow()
    try:
        original_get = viewer.settings.get
        chosen = tmp_path / "chosen"
        chosen.mkdir()
        monkeypatch.setattr(viewer.settings, "get", lambda key:
                            str(chosen) if key == "last_open_dir"
                            else original_get(key))
        assert viewer._preferred_image_directory() == str(chosen)
        monkeypatch.setattr(viewer.settings, "get", lambda key:
                            str(tmp_path / "missing") if key == "last_open_dir"
                            else original_get(key))
        assert viewer._preferred_image_directory() == str(tmp_path)
    finally:
        viewer.close()
        application.processEvents()


def test_completion_dialog_can_open_results_folder(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.recents, "recent", lambda _limit: [])
    opened = []
    monkeypatch.setattr(ui.QDesktopServices, "openUrl", lambda url: opened.append(url.toLocalFile()) or True)
    viewer = ui.CCTVLogAnalyzerWindow()
    database = tmp_path / "Extracted_Logs_TVT.db"

    def click_open_folder():
        dialog = application.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        next(button for button in dialog.buttons() if button.text() == "Open Folder").click()

    try:
        QTimer.singleShot(0, click_open_folder)
        viewer._show_extraction_complete(str(database))
        assert [os.path.normpath(path) for path in opened] == [str(Path(tmp_path))]
    finally:
        viewer.close()
        application.processEvents()
