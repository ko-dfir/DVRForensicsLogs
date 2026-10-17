"""Unified random-access readers for raw, split-raw, and EWF evidence."""

from __future__ import annotations

import bisect
import os
import re
from pathlib import Path

from scripts.e01_native import E01File
from scripts.physical_drive import PhysicalDriveReader, is_physical_drive


class SegmentedRawFile:
    """Expose sequential .001/.002 raw segments as one seekable image."""

    def __init__(self, filename):
        first = Path(filename)
        match = re.match(r"^(.*)\.(\d{3})$", str(first), re.IGNORECASE)
        if not match:
            raise ValueError(f"Not a numbered raw segment: {filename}")
        stem, number = match.groups()
        paths = []
        index = int(number)
        while True:
            candidate = Path(f"{stem}.{index:03d}")
            if not candidate.is_file():
                break
            paths.append(candidate)
            index += 1
        if not paths:
            raise FileNotFoundError(filename)
        self.paths = paths
        self._sizes = [path.stat().st_size for path in paths]
        self._ends = []
        total = 0
        for size in self._sizes:
            total += size
            self._ends.append(total)
        self.size = total
        self.pos = 0
        self._handle = None
        self._segment = -1

    def _select(self, index):
        if index != self._segment:
            if self._handle:
                self._handle.close()
            self._handle = self.paths[index].open("rb")
            self._segment = index

    def read(self, size=-1):
        if size < 0:
            size = self.size - self.pos
        remaining = min(size, self.size - self.pos)
        chunks = []
        while remaining > 0:
            index = bisect.bisect_right(self._ends, self.pos)
            if index >= len(self.paths):
                break
            segment_start = 0 if index == 0 else self._ends[index - 1]
            self._select(index)
            self._handle.seek(self.pos - segment_start)
            block = self._handle.read(min(remaining, self._ends[index] - self.pos))
            if not block:
                break
            chunks.append(block)
            self.pos += len(block)
            remaining -= len(block)
        return b"".join(chunks)

    def seek(self, offset, whence=os.SEEK_SET):
        if whence == os.SEEK_CUR:
            offset += self.pos
        elif whence == os.SEEK_END:
            offset += self.size
        self.pos = max(0, min(int(offset), self.size))
        return self.pos

    def tell(self):
        return self.pos

    def close(self):
        if self._handle:
            self._handle.close()
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def open_image(image_path):
    lower = str(image_path).lower()
    if is_physical_drive(image_path):
        return PhysicalDriveReader(str(image_path))
    if lower.endswith((".e01", ".ex01")):
        return E01File(image_path)
    if re.search(r"\.\d{3}$", lower):
        return SegmentedRawFile(image_path)
    return open(image_path, "rb")
