"""Tests for the yt-dlp and youtube-transcript-api adapters, with the libraries faked."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from youtube_transcript_api import FetchedTranscript, FetchedTranscriptSnippet, TranscriptsDisabled

from tests.conftest import FakeYoutubeDL
from youtube_recap.errors import TranscriptUnavailableError
from youtube_recap.youtube import YouTubeTranscriptSource, YtDlpSearcher


def test_searcher_builds_ytsearch_url_and_flat_options() -> None:
    fake = FakeYoutubeDL([{"id": "a", "title": "A"}, {"title": "no id"}])
    videos = YtDlpSearcher(fake).search("cats", 2)
    assert fake.urls == ["ytsearch2:cats"]
    assert fake.options["extract_flat"] is True
    assert [v.id for v in videos] == ["a"]


def test_searcher_handles_empty_info() -> None:
    assert YtDlpSearcher(FakeYoutubeDL(None)).search("q", 3) == []


class FakeApi:
    def __init__(self, result: FetchedTranscript | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, list[str]]] = []

    def fetch(self, video_id: str, languages: Iterable[str] = ("en",)) -> FetchedTranscript:
        self.calls.append((video_id, list(languages)))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _fetched(texts: list[str], language_code: str = "en") -> FetchedTranscript:
    snippets = [
        FetchedTranscriptSnippet(text=t, start=float(i), duration=1.0) for i, t in enumerate(texts)
    ]
    return FetchedTranscript(
        snippets=snippets,
        video_id="vid",
        language="English",
        language_code=language_code,
        is_generated=True,
    )


def test_transcript_source_joins_snippets() -> None:
    api = FakeApi(_fetched(["hello", "world"], "de"))
    transcript = YouTubeTranscriptSource(api).fetch("vid", ["de", "en"])  # type: ignore[arg-type]
    assert transcript.text == "hello world"
    assert transcript.language_code == "de"
    assert transcript.is_generated is True
    assert api.calls == [("vid", ["de", "en"])]


def test_transcript_source_wraps_library_errors() -> None:
    api: Any = FakeApi(TranscriptsDisabled("vid"))
    with pytest.raises(TranscriptUnavailableError) as info:
        YouTubeTranscriptSource(api).fetch("vid", ["en"])
    assert info.value.reason == "TranscriptsDisabled"
    assert info.value.video_id == "vid"
