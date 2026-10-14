"""Adapters around yt-dlp (search) and youtube-transcript-api (captions).

The service depends on the two Protocols below, not on these classes, so tests and other
backends can swap them out.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Protocol

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi, YouTubeTranscriptApiException

from youtube_recap.errors import TranscriptUnavailableError
from youtube_recap.models import Transcript, Video


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

    def __init__(self, ydl_factory: Callable[[dict[str, Any]], Any] | None = None) -> None:
        self._ydl_factory = ydl_factory or yt_dlp.YoutubeDL

    def search(self, query: str, limit: int) -> list[Video]:
        with self._ydl_factory(dict(self._BASE_OPTIONS)) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
        entries = (info or {}).get("entries") or []
        videos = (Video.from_yt_dlp(e) for e in entries)
        return [v for v in videos if v is not None]


class YouTubeTranscriptSource:
    """Fetches captions with youtube-transcript-api."""

    def __init__(self, api: YouTubeTranscriptApi | None = None) -> None:
        self._api = api or YouTubeTranscriptApi()

    def fetch(self, video_id: str, languages: Sequence[str]) -> Transcript:
        try:
            fetched = self._api.fetch(video_id, languages=languages)
        except YouTubeTranscriptApiException as exc:
            raise TranscriptUnavailableError(video_id, type(exc).__name__) from exc
        return Transcript(
            video_id=video_id,
            language_code=fetched.language_code,
            text=" ".join(snippet.text for snippet in fetched),
            is_generated=fetched.is_generated,
        )
