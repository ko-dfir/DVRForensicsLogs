import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

import cctv_log_analyzer as ui


@pytest.fixture
def viewer_factory(monkeypatch):
    application = QApplication.instance() or QApplication([])
    monkeypatch.setattr(ui.recents, "recent", lambda _limit: [])
    viewers = []

    def make(admin):
        monkeypatch.setattr(ui, "is_running_as_admin", lambda: admin)
        viewer = ui.CCTVLogAnalyzerWindow()
        viewers.append(viewer)
        return viewer

    yield application, make
    for viewer in viewers:
        viewer.close()
    application.processEvents()


def click_dialog_button(application, text):
    def click():
        dialog = application.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        next(button for button in dialog.buttons() if button.text() == text).click()
    QTimer.singleShot(0, click)


def test_admin_badge_reflects_elevation(viewer_factory):
    _application, make = viewer_factory
    assert make(admin=True).admin_lbl.isHidden() is False
    assert make(admin=False).admin_lbl.isHidden() is True


def test_cancel_stops_before_listing_drives(viewer_factory, monkeypatch):
    application, make = viewer_factory
    viewer = make(admin=False)
    listed = []
    monkeypatch.setattr(ui, "list_physical_drives", lambda: listed.append(True) or [])
    click_dialog_button(application, "Cancel")
    viewer.action_load_drive()
    assert listed == []


def test_continue_anyway_lists_drives(viewer_factory, monkeypatch):
    application, make = viewer_factory
    viewer = make(admin=False)
    listed = []
    monkeypatch.setattr(ui, "list_physical_drives", lambda: listed.append(True) or [])
    monkeypatch.setattr(ui.QMessageBox, "information", lambda *args, **kwargs: None)
    click_dialog_button(application, "Continue anyway")
    viewer.action_load_drive()
    assert listed == [True]


def test_restart_relaunches_and_closes(viewer_factory, monkeypatch):
    application, make = viewer_factory
    viewer = make(admin=False)
    viewer.show()
    relaunched = []
    monkeypatch.setattr(ui, "relaunch_as_admin", lambda: relaunched.append(True) or True)
    monkeypatch.setattr(ui, "list_physical_drives", lambda: pytest.fail("must not list drives"))
    click_dialog_button(application, "Restart as Administrator")
    viewer.action_load_drive()
    assert relaunched == [True]
    assert not viewer.isVisible()


def test_declined_uac_keeps_app_open(viewer_factory, monkeypatch):
    application, make = viewer_factory
    viewer = make(admin=False)
    viewer.show()
    notices = []
    monkeypatch.setattr(ui, "relaunch_as_admin", lambda: False)
    monkeypatch.setattr(ui.QMessageBox, "information",
                        lambda _parent, title, _text: notices.append(title))
    click_dialog_button(application, "Restart as Administrator")
    viewer.action_load_drive()
    assert notices == ["Restart cancelled"]
    assert viewer.isVisible()


def test_admin_skips_prompt(viewer_factory, monkeypatch):
    _application, make = viewer_factory
    viewer = make(admin=True)
    listed = []
    monkeypatch.setattr(ui, "list_physical_drives", lambda: listed.append(True) or [])
    monkeypatch.setattr(ui.QMessageBox, "information", lambda *args, **kwargs: None)
    viewer.action_load_drive()
    assert listed == [True]
