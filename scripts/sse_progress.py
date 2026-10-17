"""Small Server-Sent Events codec used by worker-to-UI progress streams."""

from __future__ import annotations

import json


def encode_sse(event: str, **data) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


def decode_sse(frame: str) -> tuple[str, dict]:
    event = "message"
    data_lines = []
    for line in frame.splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    payload = json.loads("\n".join(data_lines) or "{}")
    if not isinstance(payload, dict):
        raise ValueError("SSE data must be a JSON object")
    return event, payload
