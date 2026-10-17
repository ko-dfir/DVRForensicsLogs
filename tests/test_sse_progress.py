import pytest

from scripts.sse_progress import decode_sse, encode_sse


def test_sse_round_trip():
    frame = encode_sse("progress", progress=42, phase="scan", bytes_done=10)
    event, data = decode_sse(frame)
    assert event == "progress"
    assert data == {"progress": 42, "phase": "scan", "bytes_done": 10}


def test_sse_rejects_non_object_data():
    with pytest.raises(ValueError):
        decode_sse("event: progress\ndata: []\n\n")
