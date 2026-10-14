"""Tests for the three MCP tools against fake YouTube backends (see conftest.py)."""

from __future__ import annotations

from tests.conftest import FakeYoutubeDL
from youtube_recap import server


def test_search_ranks_by_views_most_viewed_first() -> None:
    out = server.search_videos("q", 3)
    assert out.index("High") < out.index("Low") < out.index("Unknown views")
    assert FakeYoutubeDL.calls == ["ytsearch3:q"]


def test_search_formats_metadata() -> None:
    out = server.search_videos("q", 3)
    assert "views=5,000" in out
    assert "channel=U2" in out  # falls back to uploader
    assert "duration=1:02:05" in out
    assert "duration=1:05" in out
    assert "views=unknown | channel=unknown | duration=unknown" in out
    assert "https://youtu.be/bbbbbbbbbbb" in out


def test_search_no_results() -> None:
    FakeYoutubeDL.entries = []
    assert server.search_videos("nothing", 5) == "No results for 'nothing'."


def test_search_drops_entries_without_id() -> None:
    FakeYoutubeDL.entries = [{"title": "No id", "view_count": 99}, *FakeYoutubeDL.entries]
    out = server.search_videos("q", 4)
    assert "No id" not in out
    assert "id=None" not in out


def test_get_transcript_joins_snippets() -> None:
    assert server.get_transcript("aaaaaaaaaaa") == "hello world"


def test_get_transcript_missing_returns_placeholder() -> None:
    out = server.get_transcript("zzzzzzzzzzz")
    assert out.startswith("[transcript unavailable:")


def test_recap_keeps_top_videos_and_truncates() -> None:
    out = server.recap("q", num_videos=2, search_pool=3)
    assert out.startswith("## High")
    assert "## Low" in out
    assert "Unknown views" not in out
    high_block = out.split("---")[0]
    assert high_block.count("x") == server.config.recap.max_transcript_chars
    assert FakeYoutubeDL.calls == ["ytsearch3:q"]


def test_recap_search_pool_never_smaller_than_num_videos() -> None:
    server.recap("q", num_videos=3, search_pool=1)
    assert FakeYoutubeDL.calls == ["ytsearch3:q"]


def test_recap_negative_count_is_clamped_to_one() -> None:
    out = server.recap("q", num_videos=-1)
    assert out.count("## ") == 1


def test_search_count_is_capped_by_config() -> None:
    server.search_videos("q", 10_000)
    assert FakeYoutubeDL.calls == [f"ytsearch{server.config.search.max_results}:q"]
