"""Tests for the yt-dlp and youtube-transcript-api adapters, with the libraries faked."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
import requests
from youtube_transcript_api import (
    FetchedTranscript,
    FetchedTranscriptSnippet,
    TranscriptsDisabled,
)
from yt_dlp.utils import DownloadError

from tests.conftest import FakeYoutubeDL
from youtube_recap.errors import TranscriptUnavailableError, YouTubeUnavailableError
from youtube_recap.retry import RetryPolicy
from youtube_recap.youtube import YouTubeHttpSession, YouTubeTranscriptSource, YtDlpSearcher

TIMEOUT = 5.0


@pytest.fixture
def retry() -> RetryPolicy:
    return RetryPolicy(
        attempts=2, initial_backoff=0, max_backoff=0, multiplier=1, sleep=lambda _: None
    )


def test_searcher_builds_ytsearch_url_and_options(retry: RetryPolicy) -> None:
    fake = FakeYoutubeDL([{"id": "a", "title": "A"}, {"title": "no id"}])
    videos = YtDlpSearcher(retry, TIMEOUT, ydl_factory=fake).search("cats", 2)
    assert fake.urls == ["ytsearch2:cats"]
    assert fake.options["extract_flat"] is True
    assert fake.options["socket_timeout"] == TIMEOUT
    assert [v.id for v in videos] == ["a"]


def test_searcher_handles_empty_info(retry: RetryPolicy) -> None:
    assert YtDlpSearcher(retry, TIMEOUT, ydl_factory=FakeYoutubeDL(None)).search("q", 3) == []


def test_searcher_retries_then_raises_unavailable(retry: RetryPolicy) -> None:
    fake = FakeYoutubeDL([])
    fake.error = DownloadError("network down")
    with pytest.raises(YouTubeUnavailableError, match="network down"):
        YtDlpSearcher(retry, TIMEOUT, ydl_factory=fake).search("q", 1)
    assert len(fake.urls) == retry.attempts


class FakeApi:
    def __init__(self, *results: FetchedTranscript | Exception) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, list[str]]] = []

    def fetch(self, video_id: str, languages: Iterable[str] = ("en",)) -> FetchedTranscript:
        self.calls.append((video_id, list(languages)))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


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


def test_transcript_source_joins_snippets(retry: RetryPolicy) -> None:
    api: Any = FakeApi(_fetched(["hello", "world"], "de"))
    transcript = YouTubeTranscriptSource(retry, TIMEOUT, api=api).fetch("vid", ["de", "en"])
    assert transcript.text == "hello world"
    assert transcript.language_code == "de"
    assert transcript.is_generated is True
    assert api.calls == [("vid", ["de", "en"])]


def test_transcript_source_wraps_library_errors_without_retry(retry: RetryPolicy) -> None:
    api: Any = FakeApi(TranscriptsDisabled("vid"))
    with pytest.raises(TranscriptUnavailableError) as info:
        YouTubeTranscriptSource(retry, TIMEOUT, api=api).fetch("vid", ["en"])
    assert info.value.reason == "TranscriptsDisabled"
    assert len(api.calls) == 1


def test_transcript_source_retries_timeouts(retry: RetryPolicy) -> None:
    api: Any = FakeApi(requests.Timeout("slow"), _fetched(["ok"]))
    assert YouTubeTranscriptSource(retry, TIMEOUT, api=api).fetch("vid", ["en"]).text == "ok"
    assert len(api.calls) == 2


def test_transcript_source_gives_up_on_repeated_connection_errors(retry: RetryPolicy) -> None:
    api: Any = FakeApi(requests.ConnectionError("a"), requests.ConnectionError("b"))
    with pytest.raises(YouTubeUnavailableError):
        YouTubeTranscriptSource(retry, TIMEOUT, api=api).fetch("vid", ["en"])


def test_http_session_sets_default_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_request(self: requests.Session, *args: Any, **kwargs: Any) -> str:
        seen.update(kwargs)
        return "response"

    monkeypatch.setattr(requests.Session, "request", fake_request)
    YouTubeHttpSession(3.0).get("https://example.invalid")
    assert seen["timeout"] == 3.0
    YouTubeHttpSession(3.0).get("https://example.invalid", timeout=1)
    assert seen["timeout"] == 1


class CountingLimiter:
    def __init__(self) -> None:
        self.count = 0

    def acquire(self) -> float:
        self.count += 1
        return 0.0


def test_searcher_acquires_limiter_per_attempt(retry: RetryPolicy) -> None:
    fake = FakeYoutubeDL([])
    fake.error = DownloadError("down")
    limiter = CountingLimiter()
    with pytest.raises(YouTubeUnavailableError):
        YtDlpSearcher(retry, TIMEOUT, limiter, ydl_factory=fake).search("q", 1)
    assert limiter.count == retry.attempts


def test_http_session_acquires_limiter_per_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(requests.Session, "request", lambda self, *a, **k: "response")
    limiter = CountingLimiter()
    session = YouTubeHttpSession(3.0, limiter)
    session.get("https://example.invalid")
    session.post("https://example.invalid")
    assert limiter.count == 2
