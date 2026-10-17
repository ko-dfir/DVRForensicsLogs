import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

import cctv_log_analyzer as viewer_module


def test_dahua_scope_warning_is_visible_and_resets_for_other_brand(tmp_path, monkeypatch):
    application = QApplication.instance() or QApplication([])
    evidence = tmp_path / "disk.001"
    evidence.write_bytes(b"\x00" * 512)
    monkeypatch.setattr(viewer_module.recents, "remember", lambda *args: None)
    monkeypatch.setattr(viewer_module.CCTVLogAnalyzerWindow, "refresh_recent_list", lambda self: None)
    brand = {"value": "DAHUA"}
    monkeypatch.setattr(viewer_module, "detect_brand_details", lambda _: {
        "brand": brand["value"], "reason": "test", "confidence": "HIGH"})
    viewer = viewer_module.CCTVLogAnalyzerWindow()
    try:
        # A synthetic pytest path must never replace the user's saved chooser path.
        monkeypatch.setattr(viewer.settings, "set", lambda *_args: None)
        viewer.load_image_path(str(evidence))
        assert "incomplete" in viewer.log_availability_lbl.text()
        assert "absence of an event" in viewer.log_availability_lbl.toolTip()
        assert "Log coverage" in viewer.metadata
        brand["value"] = "HIKVISION"
        viewer.load_image_path(str(evidence))
        assert viewer.log_availability_lbl.text() == ""
        assert viewer.log_availability_lbl.toolTip() == ""
    finally:
        viewer.close()
        application.processEvents()
