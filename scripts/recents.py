"""Recent evidence history stored in a private AppData SQLite database."""

from __future__ import annotations

import contextlib
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from scripts.physical_drive import is_physical_drive, list_physical_drives

APP_DIR_NAME = "CCTVLogAnalyzer"


def app_data_dir() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    path = base / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return app_data_dir() / "recents.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS recents (
    image_path TEXT PRIMARY KEY,
    brand TEXT NOT NULL DEFAULT 'UNKNOWN',
    database_path TEXT NOT NULL DEFAULT '',
    table_name TEXT NOT NULL DEFAULT '',
    opened REAL NOT NULL,
    times INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS recents_opened ON recents(opened DESC);
CREATE TABLE IF NOT EXISTS exports (
    path TEXT PRIMARY KEY,
    image_path TEXT NOT NULL,
    kind TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    modified_ns INTEGER NOT NULL,
    device_id INTEGER NOT NULL,
    file_id INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class RecentEvidence:
    image_path: str
    brand: str
    database_path: str
    table_name: str
    opened: float
    times: int

    @property
    def exists(self):
        try:
            if is_physical_drive(self.image_path):
                return any(drive.path.lower() == self.image_path.lower()
                           for drive in list_physical_drives())
            return Path(self.image_path).is_file()
        except Exception:
            return False


@dataclass(frozen=True)
class ExportArtifact:
    path: str
    image_path: str
    kind: str
    size_bytes: int
    modified_ns: int
    device_id: int
    file_id: int


@contextlib.contextmanager
def _open():
    connection = sqlite3.connect(db_path(), timeout=5.0)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.executescript(_SCHEMA)
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    with _open():
        pass
    return db_path()


def remember(image_path, brand="UNKNOWN", database_path="", table_name=""):
    with _open() as connection:
        connection.execute(
            "INSERT INTO recents(image_path, brand, database_path, table_name, opened) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(image_path) DO UPDATE SET "
            "brand=excluded.brand, "
            "database_path=CASE WHEN excluded.database_path != '' "
            "THEN excluded.database_path ELSE recents.database_path END, "
            "table_name=CASE WHEN excluded.table_name != '' "
            "THEN excluded.table_name ELSE recents.table_name END, "
            "opened=excluded.opened, times=times+1",
            (str(image_path), brand, str(database_path or ""), table_name, time.time()),
        )


def recent(limit=10):
    with _open() as connection:
        rows = connection.execute(
            "SELECT image_path, brand, database_path, table_name, opened, times "
            "FROM recents ORDER BY opened DESC LIMIT ?", (int(limit),)
        ).fetchall()
    return [RecentEvidence(*row) for row in rows]


def remember_export(image_path, export_path, kind):
    """Register an exact app-created file after a successful export."""
    source = (str(image_path) if is_physical_drive(image_path)
              else str(Path(image_path).resolve(strict=False)))
    path = Path(export_path)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Export is not a regular file: {path}")
    resolved = path.resolve(strict=True)
    if str(resolved).lower() == source.lower() or resolved == db_path().resolve(strict=False):
        raise ValueError("An evidence source or the history database cannot be registered as an export")
    stat = resolved.stat()
    with _open() as connection:
        connection.execute(
            "INSERT INTO exports(path, image_path, kind, size_bytes, modified_ns, device_id, file_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(path) DO UPDATE SET "
            "image_path=excluded.image_path, kind=excluded.kind, "
            "size_bytes=excluded.size_bytes, modified_ns=excluded.modified_ns, "
            "device_id=excluded.device_id, file_id=excluded.file_id",
            (str(resolved), source, str(kind), stat.st_size, stat.st_mtime_ns,
             stat.st_dev, stat.st_ino),
        )


def registered_exports():
    with _open() as connection:
        rows = connection.execute(
            "SELECT path, image_path, kind, size_bytes, modified_ns, device_id, file_id "
            "FROM exports ORDER BY path COLLATE NOCASE").fetchall()
    return [ExportArtifact(*row) for row in rows]


def delete_registered_exports():
    """Delete only registered, unchanged files; never recurse into a directory."""
    removed = 0
    with _open() as connection:
        rows = connection.execute(
            "SELECT path, image_path, kind, size_bytes, modified_ns, device_id, file_id "
            "FROM exports").fetchall()
        for artifact in map(lambda row: ExportArtifact(*row), rows):
            path = Path(artifact.path)
            if path.is_symlink():
                raise ValueError(f"Export became a symbolic link: {path}")
            if not path.exists():
                connection.execute("DELETE FROM exports WHERE path=?", (artifact.path,))
                continue
            if not path.is_file() or path.resolve() == db_path().resolve(strict=False):
                raise ValueError(f"Unsafe export target: {path}")
            if str(path.resolve()).lower() == artifact.image_path.lower():
                raise ValueError(f"Export points to evidence source: {path}")
            stat = path.stat()
            identity = (stat.st_size, stat.st_mtime_ns, stat.st_dev, stat.st_ino)
            expected = (artifact.size_bytes, artifact.modified_ns,
                        artifact.device_id, artifact.file_id)
            if identity != expected:
                raise ValueError(f"Export changed since registration: {path}")
            path.unlink()
            connection.execute("DELETE FROM exports WHERE path=?", (artifact.path,))
            removed += 1
    return removed


def clear():
    with _open() as connection:
        count = connection.execute("SELECT count(*) FROM recents").fetchone()[0]
        connection.execute("DELETE FROM recents")
        connection.execute("DELETE FROM exports")
    return count

