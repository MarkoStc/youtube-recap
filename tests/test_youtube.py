"""Tests for the yt-dlp and youtube-transcript-api adapters, with the libraries faked."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, cast

import pytest
import requests
from youtube_transcript_api import (
    FetchedTranscript,
    FetchedTranscriptSnippet,
    NoTranscriptFound,
    TranscriptsDisabled,
)
from yt_dlp.utils import DownloadError

from tests.conftest import FakeYoutubeDL
from youtube_recap.errors import TranscriptUnavailableError, YouTubeUnavailableError
from youtube_recap.retry import RetryPolicy
from youtube_recap.youtube import (
    FallbackMode,
    YouTubeHttpSession,
    YouTubeTranscriptSource,
    YtDlpSearcher,
)

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


@dataclass
class FakeLang:
    language_code: str


@dataclass
class FakeTranscript:
    """Duck-typed ``youtube_transcript_api.Transcript``."""

    language_code: str
    texts: list[str] = field(default_factory=lambda: ["text"])
    translatable_to: list[str] = field(default_factory=list)

    @property
    def is_translatable(self) -> bool:
        return bool(self.translatable_to)

    @property
    def translation_languages(self) -> list[FakeLang]:
        return [FakeLang(c) for c in self.translatable_to]

    def translate(self, code: str) -> FakeTranscript:
        return FakeTranscript(code, [f"{t} ({code})" for t in self.texts])

    def fetch(self) -> FetchedTranscript:
        return _fetched(self.texts, self.language_code)


class FakeList:
    def __init__(self, transcripts: list[FakeTranscript]) -> None:
        self.transcripts = transcripts

    def __iter__(self) -> Iterator[FakeTranscript]:
        return iter(self.transcripts)

    def find_transcript(self, languages: Iterable[str]) -> FakeTranscript:
        for code in languages:
            for t in self.transcripts:
                if t.language_code == code:
                    return t
        raise NoTranscriptFound("vid", list(languages), "transcript list")


class FakeApi:
    """Duck-typed ``YouTubeTranscriptApi``: each ``list`` call returns the next result."""

    def __init__(self, *results: FakeList | Exception) -> None:
        self.results = list(results)
        self.calls: list[str] = []

    def list(self, video_id: str) -> FakeList:
        self.calls.append(video_id)
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
        language="whatever",
        language_code=language_code,
        is_generated=True,
    )


def _source(retry: RetryPolicy, api: FakeApi, fallback: FallbackMode = "translate") -> Any:
    return YouTubeTranscriptSource(retry, TIMEOUT, fallback=fallback, api=cast(Any, api))


def test_transcript_source_prefers_requested_languages_in_order(retry: RetryPolicy) -> None:
    listing = FakeList([FakeTranscript("en", ["hi"]), FakeTranscript("de", ["hallo", "welt"])])
    transcript = _source(retry, FakeApi(listing)).fetch("vid", ["de", "en"])
    assert transcript.text == "hallo welt"
    assert transcript.language_code == "de"
    assert transcript.translated_from is None
    assert transcript.is_generated is True


def test_fallback_translate_uses_machine_translation(retry: RetryPolicy) -> None:
    listing = FakeList([FakeTranscript("de", ["hallo"], translatable_to=["en", "fr"])])
    transcript = _source(retry, FakeApi(listing)).fetch("vid", ["en"])
    assert transcript.text == "hallo (en)"
    assert transcript.language_code == "en"
    assert transcript.translated_from == "de"


def test_fallback_translate_falls_back_to_original(retry: RetryPolicy) -> None:
    listing = FakeList([FakeTranscript("de", ["hallo"], translatable_to=["fr"])])
    transcript = _source(retry, FakeApi(listing)).fetch("vid", ["en"])
    assert transcript.language_code == "de"
    assert transcript.translated_from is None


def test_fallback_original_skips_translation(retry: RetryPolicy) -> None:
    listing = FakeList([FakeTranscript("de", ["hallo"], translatable_to=["en"])])
    transcript = _source(retry, FakeApi(listing), "original").fetch("vid", ["en"])
    assert transcript.text == "hallo"
    assert transcript.translated_from is None


def test_fallback_none_reports_unavailable(retry: RetryPolicy) -> None:
    listing = FakeList([FakeTranscript("de")])
    with pytest.raises(TranscriptUnavailableError, match="NoTranscriptFound"):
        _source(retry, FakeApi(listing), "none").fetch("vid", ["en"])


def test_empty_transcript_list_is_unavailable(retry: RetryPolicy) -> None:
    with pytest.raises(TranscriptUnavailableError, match="NoTranscriptFound"):
        _source(retry, FakeApi(FakeList([]))).fetch("vid", ["en"])


def test_transcript_source_wraps_library_errors_without_retry(retry: RetryPolicy) -> None:
    api = FakeApi(TranscriptsDisabled("vid"))
    with pytest.raises(TranscriptUnavailableError) as info:
        _source(retry, api).fetch("vid", ["en"])
    assert info.value.reason == "TranscriptsDisabled"
    assert api.calls == ["vid"]


def test_transcript_source_retries_timeouts(retry: RetryPolicy) -> None:
    api = FakeApi(requests.Timeout("slow"), FakeList([FakeTranscript("en", ["ok"])]))
    assert _source(retry, api).fetch("vid", ["en"]).text == "ok"
    assert len(api.calls) == 2


def test_transcript_source_gives_up_on_repeated_connection_errors(retry: RetryPolicy) -> None:
    api = FakeApi(requests.ConnectionError("a"), requests.ConnectionError("b"))
    with pytest.raises(YouTubeUnavailableError):
        _source(retry, api).fetch("vid", ["en"])


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
