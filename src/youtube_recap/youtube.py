"""Adapters around yt-dlp (search) and youtube-transcript-api (captions).

The service depends on the two Protocols below, not on these classes, so tests and other
backends can swap them out. The adapters own the network concerns: timeouts, which errors
are worth retrying, and translating library exceptions into ``youtube_recap.errors``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any, Protocol

import requests
import yt_dlp
from youtube_transcript_api import (
    YouTubeRequestFailed,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)
from yt_dlp.utils import DownloadError

from youtube_recap.errors import TranscriptUnavailableError, YouTubeUnavailableError
from youtube_recap.models import Transcript, Video
from youtube_recap.retry import RetryPolicy

logger = logging.getLogger(__name__)

# Failures that may succeed on a later try: dropped connections, timeouts, HTTP 429/5xx.
_TRANSIENT_TRANSCRIPT_ERRORS: tuple[type[BaseException], ...] = (
    requests.ConnectionError,
    requests.Timeout,
    YouTubeRequestFailed,
)


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
        ydl_factory: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        self._retry = retry
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
        with self._ydl_factory(dict(self._options)) as ydl:
            info: dict[str, Any] | None = ydl.extract_info(url, download=False)
            return info


class TimeoutSession(requests.Session):
    """A requests Session that applies a default timeout to every request."""

    def __init__(self, timeout_seconds: float) -> None:
        super().__init__()
        self._timeout = timeout_seconds

    def request(self, *args: Any, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self._timeout)
        return super().request(*args, **kwargs)


class YouTubeTranscriptSource:
    """Fetches captions with youtube-transcript-api."""

    def __init__(
        self,
        retry: RetryPolicy,
        timeout_seconds: float,
        api: YouTubeTranscriptApi | None = None,
    ) -> None:
        self._retry = retry
        self._api = api or YouTubeTranscriptApi(http_client=TimeoutSession(timeout_seconds))

    def fetch(self, video_id: str, languages: Sequence[str]) -> Transcript:
        try:
            fetched = self._retry.call(
                lambda: self._api.fetch(video_id, languages=languages),
                retry_on=_TRANSIENT_TRANSCRIPT_ERRORS,
                description=f"transcript {video_id}",
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise YouTubeUnavailableError(f"transcript {video_id}: {exc!r}") from exc
        except YouTubeTranscriptApiException as exc:
            raise TranscriptUnavailableError(video_id, type(exc).__name__) from exc
        logger.info("transcript %s lang=%s", video_id, fetched.language_code)
        return Transcript(
            video_id=video_id,
            language_code=fetched.language_code,
            text=" ".join(snippet.text for snippet in fetched),
            is_generated=fetched.is_generated,
        )
