"""Single-source application version metadata from version.json."""

from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path


def bundle_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return bundle_root().joinpath(*parts)


@lru_cache(maxsize=1)
def version_info() -> dict:
    path = resource_path("version.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot read application version metadata: {path}: {exc}") from exc
    if not isinstance(data.get("version"), str) or not data["version"].strip():
        raise RuntimeError("version.json must contain a non-empty string 'version'.")
    return data


def get_version() -> str:
    return version_info()["version"].strip()


def windows_version_tuple() -> tuple[int, int, int, int]:
    explicit = version_info().get('windows_version')
    if explicit is not None and not isinstance(explicit, str):
        raise RuntimeError('windows_version must be a dotted numeric string.')
    raw = (explicit if explicit is not None else get_version().split('-', 1)[0]).split('.')
    if explicit is not None and len(raw) != 4:
        raise RuntimeError('windows_version must have exactly four numeric components.')
    if len(raw) > 4 or not all(part.isdigit() for part in raw):
        raise RuntimeError(f"Version '{get_version()}' cannot be used as a Windows version.")
    value = tuple(int(part) for part in [*raw, *("0" for _ in range(4 - len(raw)))])
    if any(part > 65535 for part in value):
        raise RuntimeError('Windows version components must be in the range 0..65535.')
    return value
