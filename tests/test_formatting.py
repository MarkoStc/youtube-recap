from __future__ import annotations

import pytest

from tests.conftest import HIGH, LOW, UNKNOWN
from youtube_recap import formatting
from youtube_recap.models import RecapItem, Transcript


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(None, "unknown"), (0.0, "0:00"), (65.0, "1:05"), (3725.0, "1:02:05")],
)
def test_format_duration(seconds: float | None, expected: str) -> None:
    assert formatting.format_duration(seconds) == expected


def test_format_views() -> None:
    assert formatting.format_views(1234567) == "1,234,567"
    assert formatting.format_views(None) == "unknown"


def test_video_list_lines() -> None:
    out = formatting.format_video_list("q", [HIGH, UNKNOWN])
    assert "- High\n  id=bbbbbbbbbbb | views=5,000 | channel=U2 | duration=1:02:05" in out
    assert "views=unknown | channel=unknown | duration=unknown" in out
    assert "https://youtu.be/bbbbbbbbbbb" in out


def test_empty_results_message() -> None:
    assert formatting.format_video_list("x", []) == "No results for 'x'."
    assert formatting.format_recap("x", []) == "No results for 'x'."


def test_recap_blocks_and_placeholder() -> None:
    items = [
        RecapItem(LOW, Transcript(LOW.id, "en", "hello", is_generated=False)),
        RecapItem(UNKNOWN, None, unavailable_reason="TranscriptsDisabled"),
    ]
    out = formatting.format_recap("q", items)
    first, second = out.split(formatting.RECAP_SEPARATOR)
    assert first == "## Low\nhttps://youtu.be/aaaaaaaaaaa | views=10 | channel=C1\n\nhello"
    assert second.endswith("[transcript unavailable: ccccccccccc: TranscriptsDisabled]")
