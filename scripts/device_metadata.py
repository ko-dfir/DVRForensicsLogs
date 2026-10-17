"""Vendor-neutral evidence metadata helpers for the desktop UI."""

from __future__ import annotations

import os
import re
from pathlib import Path

from scripts.image_io import open_image


def acquisition_metadata(image_path):
    """Read FTK-style sidecar metadata, preserving its acquisition provenance."""
    path = Path(str(image_path) + ".txt")
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "Disk model": r"Drive Model:\s*(.+)",
        "Disk serial": r"Drive Serial Number:\s*(.+)",
        "Disk interface": r"Drive Interface Type:\s*(.+)",
        "Sector count": r"Sector count:\s*([\d.]+)",
        "Source size": r"Source data size:\s*(.+)",
        "MD5": r"MD5 checksum:\s*([0-9a-fA-F]{32})",
        "SHA1": r"SHA1 checksum:\s*([0-9a-fA-F]{40})",
        "Acquired": r"Acquisition started:\s*(.+)",
    }
    values = {}
    for label, pattern in patterns.items():
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            values[label] = (match.group(1).strip(), "Acquisition sidecar")
    return values


def tvt_filesystem_metadata(image_path):
    """Describe the validated headless TVT layout using bounded sampling."""
    values = {
        "Filesystem": ("Raw/headless proprietary TVT layout", "On-disk structure"),
        "Partition table": ("None (no MBR/GPT)", "Sector 0 inspection"),
        "Log storage": ("Proprietary mlogtype records near 850–1100 MiB", "Validated carving region"),
    }
    with open_image(image_path) as image:
        known_size = getattr(image, "size", None)
        size = int(known_size if known_size is not None else os.path.getsize(image_path))
        image.seek(0)
        boot = image.read(1024)
        has_partition_table = boot[510:512] == b"\x55\xaa" or boot[512:520] == b"EFI PART"
        values["Image capacity"] = (f"{size / (1024 ** 3):.2f} GiB", "Evidence image")
        values["Partition table"] = (
            "Present" if has_partition_table else "None (no MBR/GPT)",
            "Sector 0 inspection")
        hits = 0
        samples = 0
        for fraction in (0.10, 0.25, 0.50, 0.75, 0.90):
            image.seek(int(size * fraction) // 512 * 512)
            samples += 1
            if b"SHFL" in image.read(1024 * 1024):
                hits += 1
        values["Video ring signature"] = (
            f"SHFL found in {hits}/{samples} disk samples",
            "Bounded on-disk sampling")
    return values


def dahua_database_metadata(paths):
    serials = []
    for path in paths:
        match = re.match(r"(.+)_log\.db$", os.path.basename(path), re.IGNORECASE)
        if match:
            serials.append(match.group(1))
    values = {
        "Extracted databases": (str(len(paths)), "XFS recursive extraction"),
    }
    if serials:
        values["Recorder serial"] = (", ".join(sorted(set(serials))), "Dahua log database filename")
    return values


def tvt_log_metadata(records):
    epochs = [row.get("time_unix", 0) for row in records if row.get("time_unix", 0)]
    users = sorted({row.get("user") for row in records if row.get("user") not in (None, "", "unknown")})
    ips, channels, categories, actions = set(), set(), set(), set()
    for row in records:
        raw = row.get("raw_payload", "")
        categories.add(row.get("category", "UNKNOWN"))
        ip = re.search(r"(?:^|;)ip:([^;]+)", raw)
        channel = re.search(r"(?:^|;)channels:([^;]+)", raw)
        action = re.search(r"(?:^|;)action:(\d+)", raw)
        if ip:
            ips.add(ip.group(1))
        if channel:
            channels.add(channel.group(1))
        if action:
            actions.add(action.group(1))
    values = {
        "Recovered logs": (f"{len(records):,}", "TVT mlogtype carving"),
        "Log categories": (", ".join(sorted(categories)), "Parsed TVT records"),
        "Distinct users": (str(len(users)), "Parsed TVT records"),
        "Distinct IPs": (str(len(ips)), "Parsed TVT records"),
        "Referenced channels": (str(len(channels)), "Parsed TVT records"),
        "Action codes": (", ".join(sorted(actions, key=int)), "Parsed TVT records"),
    }
    if epochs:
        from datetime import datetime, timezone
        values["Log range (UTC)"] = (
            f"{datetime.fromtimestamp(min(epochs), timezone.utc):%Y-%m-%d %H:%M:%S} — "
            f"{datetime.fromtimestamp(max(epochs), timezone.utc):%Y-%m-%d %H:%M:%S}",
            "Parsed Unix timestamps")
    return values


def icatch_timeline_metadata(records):
    epochs = [row["time_unix"] for row in records]
    entropies = [row["region_entropy"] for row in records
                 if row.get("region_entropy") is not None]
    values = {
        "Filesystem": ("Proprietary/headless iCatch recording layout", "On-disk structure"),
        "Recovered hourly indexes": (f"{len(records):,}", "Validated fixed-size HOUR records"),
        "Index record size": ("324 bytes (0x144)", "Observed record cadence"),
    }
    if epochs:
        from datetime import datetime, timezone
        values["Recording index range (UTC)"] = (
            f"{datetime.fromtimestamp(min(epochs), timezone.utc):%Y-%m-%d %H:%M:%S} — "
            f"{datetime.fromtimestamp(max(epochs), timezone.utc):%Y-%m-%d %H:%M:%S}",
            "Validated embedded Unix timestamps")
    if entropies:
        values["Index-region entropy"] = (
            f"{min(entropies):.3f}–{max(entropies):.3f} bits/byte",
            "1 MiB Shannon entropy windows")
    return values
