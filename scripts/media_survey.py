"""Whole-address-space entropy survey with adaptive metadata expansion."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone

from scripts.entropy_scan import shannon_entropy


SIGNATURES = {
    "icatch_hour": b"HOUR_",
    "sqlite": b"SQLite format 3\x00",
    "xml": b"<?xml",
    "json_object": b'{"',
    "log_ascii": b"log",
    "event_ascii": b"event",
    "alarm_ascii": b"alarm",
    "user_ascii": b"user",
    "login_ascii": b"login",
    "config_ascii": b"config",
    "shfl": b"SHFL",
    "ext_superblock": b"\x53\xef",
    "xfs": b"XFSB",
}


def _metrics(data):
    size = max(1, len(data))
    zero_ratio = data.count(0) / size
    printable = sum(1 for value in data if value in (9, 10, 13) or 32 <= value < 127) / size
    lowered = data.lower()
    hits = {
        name: lowered.count(value) if name.endswith("_ascii") else data.count(value)
        for name, value in SIGNATURES.items()
        if (lowered.count(value) if name.endswith("_ascii") else data.count(value))
    }
    return {
        "entropy": round(shannon_entropy(data), 4),
        "zero_ratio": round(zero_ratio, 5),
        "printable_ratio": round(printable, 5),
        "signatures": hits,
    }


def _merge_offsets(offsets, radius, media_size):
    ranges = []
    for offset in sorted(set(offsets)):
        start = max(0, offset - radius)
        end = min(media_size, offset + radius)
        if ranges and start <= ranges[-1][1]:
            ranges[-1][1] = max(ranges[-1][1], end)
        else:
            ranges.append([start, end])
    return ranges


def survey(path, stride=128 * 1024 * 1024, sample_size=64 * 1024,
           offsets=(0, 4 * 1024 * 1024, 16 * 1024 * 1024, 64 * 1024 * 1024),
           progress_callback=None):
    media_size = os.path.getsize(path)
    samples = []
    candidate_rows = []
    planned = ((media_size + stride - 1) // stride) * len(offsets)
    completed = 0
    with open(path, "rb", buffering=8 * 1024 * 1024) as source:
        base = 0
        while base < media_size:
            for relative in offsets:
                absolute = base + relative
                if absolute >= media_size:
                    completed += 1
                    continue
                source.seek(absolute)
                data = source.read(min(sample_size, media_size - absolute))
                metrics = _metrics(data)
                row = {"offset": absolute, "size": len(data), **metrics}
                samples.append(row)
                strong_signature = any(
                    name in metrics["signatures"] for name in
                    ("icatch_hour", "sqlite", "xml", "xfs"))
                if (metrics["entropy"] < 6.5 or metrics["zero_ratio"] > 0.20
                        or metrics["printable_ratio"] > 0.85 or strong_signature):
                    candidate_rows.append(row)
                completed += 1
                if progress_callback and completed % 256 == 0:
                    progress_callback(completed, planned, absolute)
            base += stride

        # Always include disk boundaries and the validated initial metadata area.
        # Deep-read the strongest signatures and the 64 lowest-entropy
        # candidates. This bounds adaptive I/O even on large zero/unallocated
        # areas while preserving the most structured regions.
        strong_names = {"icatch_hour", "sqlite", "xml", "xfs"}
        strong_offsets = [
            row["offset"] for row in candidate_rows
            if strong_names.intersection(row["signatures"])
        ]
        entropy_offsets = [
            row["offset"] for row in sorted(
                candidate_rows, key=lambda item: item["entropy"])
            [:64]
        ]
        candidates = strong_offsets + entropy_offsets
        candidates.extend((0, 4 * 1024 * 1024, max(0, media_size - 64 * 1024 * 1024)))
        deep_ranges = _merge_offsets(candidates, 8 * 1024 * 1024, media_size)
        deep_findings = []
        for start, end in deep_ranges:
            source.seek(start)
            data = source.read(end - start)
            metrics = _metrics(data)
            strings = []
            for match in re.finditer(rb"[ -~]{8,}", data):
                value = match.group().decode("ascii", "replace")
                if any(term in value.lower() for term in
                       ("hour_", "log", "event", "alarm", "user", "login", "config")):
                    strings.append({"offset": start + match.start(), "value": value[:240]})
                    if len(strings) >= 200:
                        break
            deep_findings.append({
                "start": start, "end": end, "size": end - start,
                **metrics, "relevant_strings": strings,
            })
    return {
        "image": os.path.abspath(path),
        "media_size": media_size,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "method": {
            "stride": stride, "sample_size": sample_size,
            "relative_offsets": list(offsets),
            "deep_radius": 8 * 1024 * 1024,
        },
        "samples": samples,
        "candidate_count": len(candidate_rows),
        "deep_candidate_count": len(set(candidates)),
        "deep_findings": deep_findings,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument("--output", required=True)
    parser.add_argument("--stride-mib", type=int, default=128)
    args = parser.parse_args()

    def progress(done, total, offset):
        print(f"{done}/{total} ({done * 100 / max(1, total):.1f}%) offset=0x{offset:x}", flush=True)

    result = survey(
        args.image, stride=args.stride_mib * 1024 * 1024,
        progress_callback=progress)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as report:
        json.dump(result, report, indent=2)
    print(args.output, flush=True)


if __name__ == "__main__":
    main()
