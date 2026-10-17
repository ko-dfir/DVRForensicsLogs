import pytest

from scripts import recents


def test_registered_export_deleted_without_touching_source(tmp_path, monkeypatch):
    monkeypatch.setattr(recents, "db_path", lambda: tmp_path / "recents.db")
    image = tmp_path / "source.001"
    image.write_bytes(b"evidence")
    report = tmp_path / "report.html"
    report.write_text("report", encoding="utf-8")
    recents.remember(str(image), "TVT")
    recents.remember_export(str(image), str(report), "HTML report")
    assert [item.path for item in recents.registered_exports()] == [str(report)]
    assert recents.delete_registered_exports() == 1
    assert not report.exists()
    assert image.read_bytes() == b"evidence"
    assert recents.clear() == 1


def test_changed_export_is_not_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(recents, "db_path", lambda: tmp_path / "recents.db")
    image = tmp_path / "source.001"
    image.write_bytes(b"evidence")
    report = tmp_path / "report.csv"
    report.write_text("original", encoding="utf-8")
    recents.remember_export(str(image), str(report), "CSV report")
    report.write_text("changed content", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        recents.delete_registered_exports()
    assert report.read_text(encoding="utf-8") == "changed content"


def test_source_image_cannot_be_registered_as_export(tmp_path, monkeypatch):
    monkeypatch.setattr(recents, "db_path", lambda: tmp_path / "recents.db")
    image = tmp_path / "source.001"
    image.write_bytes(b"evidence")
    with pytest.raises(ValueError, match="evidence source"):
        recents.remember_export(str(image), str(image), "bad")
