"""Windows physical-disk discovery and strictly read-only random access."""

from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass


_DRIVE_PATTERN = re.compile(r"^\\\\\.\\PhysicalDrive([0-9]+)$", re.IGNORECASE)
_ERROR_CANCELLED = 1223


def is_physical_drive(path: str) -> bool:
    return bool(_DRIVE_PATTERN.fullmatch(str(path)))


def is_running_as_admin() -> bool:
    """True when this process holds an elevated (Administrator) token."""
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def relaunch_command() -> tuple[str, str]:
    """Executable and parameter string that start this application again."""
    if "__compiled__" in globals() or getattr(sys, "frozen", False):
        # Nuitka/frozen builds: argv[0] is the application executable itself.
        return os.path.abspath(sys.argv[0]), subprocess.list2cmdline(sys.argv[1:])
    return sys.executable, subprocess.list2cmdline(
        [os.path.abspath(sys.argv[0]), *sys.argv[1:]])


def relaunch_as_admin() -> bool:
    """Start a new elevated instance through the Windows UAC prompt.

    Returns False when the user declines the prompt; raises OSError for any
    other failure. The caller is responsible for closing this instance.
    """
    if os.name != "nt":
        raise OSError("Elevation is only supported on Windows")
    executable, parameters = relaunch_command()
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteW.argtypes = [
        ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
        ctypes.c_wchar_p, ctypes.c_int,
    ]
    shell32.ShellExecuteW.restype = ctypes.c_void_p
    result = shell32.ShellExecuteW(None, "runas", executable, parameters or None,
                                   os.getcwd(), 1)
    if (result or 0) > 32:
        return True
    error = ctypes.get_last_error()
    if error == _ERROR_CANCELLED:
        return False
    raise ctypes.WinError(error)


@dataclass(frozen=True)
class PhysicalDrive:
    path: str
    model: str
    serial: str
    size: int

    @property
    def label(self) -> str:
        size_gib = self.size / (1024 ** 3)
        return f"{self.path} — {self.model} — {size_gib:.1f} GiB — S/N {self.serial or 'N/A'}"


def _run_powershell(command: str) -> str:
    """Run a read-only PowerShell query and return its trimmed output.

    CREATE_NO_WINDOW keeps PowerShell from opening a console window, which
    would otherwise flash on screen from the windowed (console-less) app.
    """
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=20, check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return result.stdout.strip()


def list_physical_drives() -> list[PhysicalDrive]:
    """Query Windows disk inventory; no disk contents are read or modified."""
    if os.name != "nt":
        return []
    command = (
        "Get-CimInstance Win32_DiskDrive | "
        "Select-Object Index,Model,SerialNumber,Size,DeviceID | ConvertTo-Json -Compress"
    )
    payload = _run_powershell(command)
    if not payload:
        return []
    entries = json.loads(payload)
    if isinstance(entries, dict):
        entries = [entries]
    drives = []
    for entry in entries:
        path = str(entry.get("DeviceID") or "")
        if is_physical_drive(path):
            drives.append(PhysicalDrive(
                path=path,
                model=str(entry.get("Model") or "Unknown model").strip(),
                serial=str(entry.get("SerialNumber") or "").strip(),
                size=int(entry.get("Size") or 0),
            ))
    return sorted(drives, key=lambda drive: int(_DRIVE_PATTERN.fullmatch(drive.path)[1]))


def drive_volume_letters(path: str) -> set[str]:
    """Return mounted drive letters backed by this physical disk."""
    match = _DRIVE_PATTERN.fullmatch(path)
    if os.name != "nt" or not match:
        raise ValueError("Expected a Windows physical drive")
    command = (f"Get-Partition -DiskNumber {int(match[1])} | "
               "Where-Object DriveLetter | Select-Object -ExpandProperty DriveLetter | "
               "ConvertTo-Json -Compress")
    payload = _run_powershell(command)
    if not payload:
        return set()
    letters = json.loads(payload)
    if isinstance(letters, str):
        letters = [letters]
    return {str(letter).upper() for letter in letters if letter}


class PhysicalDriveReader:
    """Seek/read interface backed by a GENERIC_READ Windows device handle."""

    def __init__(self, path: str):
        if os.name != "nt" or not is_physical_drive(path):
            raise ValueError("Expected a Windows \\\\.\\PhysicalDriveN path")
        import msvcrt

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
        ]
        kernel32.CreateFileW.restype = ctypes.c_void_p
        kernel32.DeviceIoControl.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
            ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_void_p,
        ]
        kernel32.DeviceIoControl.restype = ctypes.c_int
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_int

        # GENERIC_READ only; share reads/writes so a mounted disk remains usable.
        handle = kernel32.CreateFileW(path, 0x80000000, 0x3, None, 3, 0x80, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        length = ctypes.c_int64()
        returned = ctypes.c_uint32()
        try:
            if not kernel32.DeviceIoControl(
                handle, 0x7405C, None, 0, ctypes.byref(length),
                ctypes.sizeof(length), ctypes.byref(returned), None,
            ):
                raise ctypes.WinError(ctypes.get_last_error())
            if length.value <= 0:
                raise OSError("Physical drive returned an invalid size")
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            kernel32.CloseHandle(handle)
            raise
        self._file = os.fdopen(fd, "rb", buffering=0)
        self.size = length.value

    def read(self, size=-1):
        if size < 0:
            size = max(0, self.size - self.tell())
        return self._file.read(size)

    def seek(self, offset, whence=os.SEEK_SET):
        return self._file.seek(offset, whence)

    def tell(self):
        return self._file.tell()

    def close(self):
        self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
