import math
import tempfile
import os

from scripts.entropy_scan import shannon_entropy
from scripts.media_survey import survey


def test_entropy_distinguishes_structured_zeroes_from_balanced_bytes():
    assert shannon_entropy(b"\x00" * 4096) == 0.0
    balanced = bytes(range(256)) * 16
    assert math.isclose(shannon_entropy(balanced), 8.0)


def test_media_survey_covers_full_address_range_and_ranks_candidates():
    with tempfile.NamedTemporaryFile(delete=False) as image:
        image.write(b"\x00" * 4096 + bytes(range(256)) * 32)
        path = image.name
    try:
        result = survey(
            path, stride=4096, sample_size=512,
            offsets=(0,), progress_callback=None)
        assert result["media_size"] == 12288
        assert len(result["samples"]) == 3
        assert result["candidate_count"] >= 1
        assert result["deep_findings"]
    finally:
        os.remove(path)
