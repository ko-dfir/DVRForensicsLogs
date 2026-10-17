import json
from types import SimpleNamespace

from scripts import physical_drive
from scripts.image_io import open_image


def test_physical_drive_paths_are_strict():
    assert physical_drive.is_physical_drive(r"\\.\PhysicalDrive0")
    assert physical_drive.is_physical_drive(r"\\.\PHYSICALDRIVE12")
    assert not physical_drive.is_physical_drive(r"\\.\C:")
    assert not physical_drive.is_physical_drive(r"\\.\PhysicalDrive0\anything")


def test_windows_inventory_parses_single_disk(monkeypatch):
    monkeypatch.setattr(physical_drive, "os", SimpleNamespace(name="nt"))
    payload = {"DeviceID": r"\\.\PHYSICALDRIVE2", "Model": "Example disk",
               "SerialNumber": "ABC123", "Size": "1073741824"}
    monkeypatch.setattr(physical_drive.subprocess, "run",
                        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload)))
    drives = physical_drive.list_physical_drives()
    assert len(drives) == 1
    assert drives[0].size == 1073741824
    assert "ABC123" in drives[0].label


def test_open_image_routes_physical_path(monkeypatch):
    marker = object()
    monkeypatch.setattr("scripts.image_io.PhysicalDriveReader", lambda path: marker)
    assert open_image(r"\\.\PhysicalDrive3") is marker


def test_relaunch_command_from_source(monkeypatch):
    monkeypatch.delattr(physical_drive.sys, "frozen", raising=False)
    monkeypatch.setattr(physical_drive.sys, "executable", r"C:\Python\python.exe")
    monkeypatch.setattr(physical_drive.sys, "argv", [r"C:\app dir\cctv_log_analyzer.py", "--flag"])
    executable, parameters = physical_drive.relaunch_command()
    assert executable == r"C:\Python\python.exe"
    assert parameters == r'"C:\app dir\cctv_log_analyzer.py" --flag'


def test_relaunch_command_from_frozen_executable(monkeypatch):
    monkeypatch.setattr(physical_drive.sys, "frozen", True, raising=False)
    monkeypatch.setattr(physical_drive.sys, "argv", [r"C:\Programs\DVR\CCTVLogAnalyzer.exe"])
    executable, parameters = physical_drive.relaunch_command()
    assert executable == r"C:\Programs\DVR\CCTVLogAnalyzer.exe"
    assert parameters == ""


def test_admin_check_is_false_off_windows(monkeypatch):
    monkeypatch.setattr(physical_drive, "os", SimpleNamespace(name="posix"))
    assert physical_drive.is_running_as_admin() is False


def test_disk_volume_letters(monkeypatch):
    monkeypatch.setattr(physical_drive, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(physical_drive.subprocess, "run",
                        lambda *args, **kwargs: SimpleNamespace(stdout='["C","D"]'))
    assert physical_drive.drive_volume_letters(r"\\.\PhysicalDrive0") == {"C", "D"}
