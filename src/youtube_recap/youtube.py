"""Adapters around yt-dlp (search) and youtube-transcript-api (captions).

The service depends on the two Protocols below, not on these classes, so tests and other
backends can swap them out. The adapters own the network concerns: timeouts, which errors
are worth retrying, and translating library exceptions into ``youtube_recap.errors``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any, Literal, Protocol

import requests
import yt_dlp
from youtube_transcript_api import (
    FetchedTranscript,
    NoTranscriptFound,
    YouTubeRequestFailed,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)
from yt_dlp.utils import DownloadError

from youtube_recap.errors import TranscriptUnavailableError, YouTubeUnavailableError
from youtube_recap.models import Transcript, Video
from youtube_recap.ratelimit import NoRateLimit
from youtube_recap.retry import RetryPolicy

logger = logging.getLogger(__name__)

# Failures that may succeed on a later try: dropped connections, timeouts, HTTP 429/5xx.
_TRANSIENT_TRANSCRIPT_ERRORS: tuple[type[BaseException], ...] = (
    requests.ConnectionError,
    requests.Timeout,
    YouTubeRequestFailed,
)


class Limiter(Protocol):
    def acquire(self) -> float:
        """Block until one more request is allowed; return the seconds waited."""
        ...


class VideoSearcher(Protocol):
    def search(self, query: str, limit: int) -> list[Video]:
        """Return up to ``limit`` results for ``query`` in YouTube's own order."""
        ...


class TranscriptSource(Protocol):
    def fetch(self, video_id: str, languages: Sequence[str]) -> Transcript:
        """Return the transcript in the first available language, or raise
        :class:`TranscriptUnavailableError`."""
        ...


class YtDlpSearcher:
    """Searches YouTube with yt-dlp's ``ytsearchN:`` extractor."""

    # Flat extraction skips per-video page loads: fast, and still carries
    # id/title/view_count/channel/duration for ranking.
    _BASE_OPTIONS: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
    }

    def __init__(
        self,
        retry: RetryPolicy,
        timeout_seconds: float,
        limiter: Limiter | None = None,
        ydl_factory: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self._retry = retry
        self._limiter = limiter or NoRateLimit()
        self._options = {**self._BASE_OPTIONS, "socket_timeout": timeout_seconds}
        self._ydl_factory = ydl_factory or yt_dlp.YoutubeDL

    def search(self, query: str, limit: int) -> list[Video]:
        try:
            info = self._retry.call(
                lambda: self._extract(f"ytsearch{limit}:{query}"),
                retry_on=(DownloadError,),
                description=f"search {query!r}",
            )
        except DownloadError as exc:
            raise YouTubeUnavailableError(f"search failed: {exc}") from exc
        entries = (info or {}).get("entries") or []
        videos = [v for v in (Video.from_yt_dlp(e) for e in entries) if v is not None]
        logger.info("search %r limit=%d -> %d results", query, limit, len(videos))
        return videos

    def _extract(self, url: str) -> dict[str, Any] | None:
        self._limiter.acquire()
        with self._ydl_factory(dict(self._options)) as ydl:
            info: dict[str, Any] | None = ydl.extract_info(url, download=False)
            return info


class YouTubeHttpSession(requests.Session):
    """A requests Session with a default timeout and a rate limit on every request."""

    def __init__(self, timeout_seconds: float, limiter: Limiter | None = None) -> None:
        super().__init__()
        self._timeout = timeout_seconds
        self._limiter = limiter or NoRateLimit()

    def request(self, *args: Any, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        self._limiter.acquire()
        return super().request(*args, **kwargs)


FallbackMode = Literal["translate", "original", "none"]


class YouTubeTranscriptSource:
    """Fetches captions with youtube-transcript-api.

    Tries the requested languages in order (manually created captions before generated
    ones). If none exist, ``fallback`` decides what happens:

    - ``translate``: use YouTube's machine translation of an existing transcript into the
      first requested language; if no transcript can be translated, use ``original``.
    - ``original``: return the first available transcript in its own language.
    - ``none``: report the transcript as unavailable.
    """

    def __init__(
        self,
        retry: RetryPolicy,
        timeout_seconds: float,
        limiter: Limiter | None = None,
        fallback: FallbackMode = "translate",
        api: YouTubeTranscriptApi | None = None,
    ) -> None:
        self._retry = retry
        self._fallback = fallback
        session = YouTubeHttpSession(timeout_seconds, limiter)
        self._api = api or YouTubeTranscriptApi(http_client=session)

    def fetch(self, video_id: str, languages: Sequence[str]) -> Transcript:
        try:
            fetched, translated_from = self._retry.call(
                lambda: self._fetch_with_fallback(video_id, languages),
                retry_on=_TRANSIENT_TRANSCRIPT_ERRORS,
                description=f"transcript {video_id}",
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise YouTubeUnavailableError(f"transcript {video_id}: {exc!r}") from exc
        except YouTubeTranscriptApiException as exc:
            raise TranscriptUnavailableError(video_id, type(exc).__name__) from exc
        logger.info(
            "transcript %s lang=%s translated_from=%s",
            video_id,
            fetched.language_code,
            translated_from,
        )
        return Transcript(
            video_id=video_id,
            language_code=fetched.language_code,
            text=" ".join(snippet.text for snippet in fetched),
            is_generated=fetched.is_generated,
            translated_from=translated_from,
        )

    def _fetch_with_fallback(
        self, video_id: str, languages: Sequence[str]
    ) -> tuple[FetchedTranscript, str | None]:
        """Return the fetched transcript and, if translated, the source language code."""
        available = self._api.list(video_id)
        try:
            return available.find_transcript(languages).fetch(), None
        except NoTranscriptFound:
            if self._fallback == "none":
                raise
            transcripts = list(available)
            if not transcripts:
                raise
        if self._fallback == "translate":
            target = languages[0]
            for transcript in transcripts:
                codes = {t.language_code for t in transcript.translation_languages}
                if transcript.is_translatable and target in codes:
                    translated = transcript.translate(target).fetch()
                    return translated, transcript.language_code
        return transcripts[0].fetch(), None
