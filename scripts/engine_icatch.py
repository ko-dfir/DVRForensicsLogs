"""Read-only parser for the validated iCatch hourly recording index."""

from datetime import datetime, timezone
import os
import re
import sqlite3
import struct

from scripts.image_io import open_image


INDEX_SCAN_SIZE = 16 * 1024 * 1024
INDEX_RECORD_SIZE = 0x144
HOUR_PATTERN = re.compile(rb"HOUR_[0-9]{5}:[0-2][0-9]\x00")


def validated_hour_entries(data, base_offset=0):
    """Return entries only when key, epoch and record cadence agree."""
    candidates = []
    for match in HOUR_PATTERN.finditer(data):
        if match.start() + 0x38 > len(data):
            continue
        epoch = struct.unpack_from("<I", data, match.start() + 0x34)[0]
        try:
            stamp = datetime.fromtimestamp(epoch, timezone.utc)
        except (OverflowError, OSError, ValueError):
            continue
        if not (2015 <= stamp.year <= 2035):
            continue
        key = match.group()[:-1].decode("ascii")
        hour = int(key[-2:])
        if hour > 23 or stamp.hour != hour:
            continue
        candidates.append({
            "index_key": key,
            "timestamp": stamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "time_unix": epoch,
            "source_offset": base_offset + match.start(),
            "record_offset": base_offset + match.start() - 0x20,
        })
    if len(candidates) < 3:
        return []
    validated = []
    for index, entry in enumerate(candidates):
        if index == 0:
            validated.append(entry)
            continue
        previous = candidates[index - 1]
        offset_delta = entry["record_offset"] - previous["record_offset"]
        time_delta = entry["time_unix"] - previous["time_unix"]
        if offset_delta == INDEX_RECORD_SIZE and time_delta == 3600:
            validated.append(entry)
        elif len(validated) < 3:
            validated = [entry]
    return validated if len(validated) >= 3 else []


def detect_icatch_structure(data):
    entries = validated_hour_entries(data)
    if not entries:
        return None
    return {
        "entries": len(entries),
        "first": entries[0]["timestamp"],
        "last": entries[-1]["timestamp"],
        "offset": entries[0]["record_offset"],
    }


class ICatchEngine:
    def __init__(self, image_path):
        self.image_path = image_path

    def extract_timeline(self, progress_callback=None):
        with open_image(self.image_path) as image:
            image.seek(0)
            data = image.read(INDEX_SCAN_SIZE)
            if progress_callback:
                progress_callback(len(data), INDEX_SCAN_SIZE, 0)
            entries = validated_hour_entries(data)
            if not entries:
                raise RuntimeError("No validated iCatch HOUR index records were found.")
            profiles = entropy_profile_from_bytes(data)
            for entry in entries:
                region = entry["source_offset"] // (1024 * 1024)
                entry["region_entropy"] = profiles.get(region)
                entry["record_size"] = INDEX_RECORD_SIZE
            if progress_callback:
                progress_callback(INDEX_SCAN_SIZE, INDEX_SCAN_SIZE, len(entries))
            return entries

    def save_to_sqlite(self, records, output_path):
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        connection = sqlite3.connect(output_path)
        try:
            connection.execute("DROP TABLE IF EXISTS icatch_timeline")
            connection.execute("""
                CREATE TABLE icatch_timeline (
                    id INTEGER PRIMARY KEY,
                    timestamp TEXT,
                    time_unix INTEGER,
                    index_key TEXT,
                    source_offset INTEGER,
                    record_offset INTEGER,
                    record_size INTEGER,
                    region_entropy REAL
                )
            """)
            connection.executemany("""
                INSERT INTO icatch_timeline (
                    timestamp, time_unix, index_key, source_offset,
                    record_offset, record_size, region_entropy
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [(
                row["timestamp"], row["time_unix"], row["index_key"],
                row["source_offset"], row["record_offset"], row["record_size"],
                row["region_entropy"],
            ) for row in records])
            connection.execute(
                "CREATE INDEX icatch_timeline_time ON icatch_timeline(time_unix)")
            connection.commit()
        finally:
            connection.close()


def entropy_profile_from_bytes(data, window_size=1024 * 1024):
    """Map MiB window number to entropy without another evidence read."""
    from scripts.entropy_scan import shannon_entropy
    return {
        offset // window_size: round(shannon_entropy(data[offset:offset + window_size]), 4)
        for offset in range(0, len(data), window_size)
    }
