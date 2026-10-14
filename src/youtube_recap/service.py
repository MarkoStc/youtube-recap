"""Business logic: ranking, limits, truncation. No MCP and no formatting here."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import replace

from youtube_recap.config import AppConfig
from youtube_recap.errors import (
    InvalidInputError,
    TranscriptUnavailableError,
    YouTubeUnavailableError,
)
from youtube_recap.models import RecapItem, Transcript, Video
from youtube_recap.youtube import TranscriptSource, VideoSearcher

logger = logging.getLogger(__name__)

# YouTube video ids are 11 characters from the URL-safe base64 alphabet.
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


def validate_query(query: str) -> str:
    stripped = query.strip()
    if not stripped:
        raise InvalidInputError("query must not be empty")
    return stripped


def validate_video_id(video_id: str) -> str:
    stripped = video_id.strip()
    if not _VIDEO_ID.fullmatch(stripped):
        raise InvalidInputError(f"not a YouTube video id: {video_id!r} (expected 11 characters)")
    return stripped


def _clamp(value: int | None, default: int, upper: int) -> int:
    """Use ``default`` when ``value`` is None, then keep the result within 1..``upper``."""
    return max(1, min(default if value is None else value, upper))


class RecapService:
    """Searches, ranks by views and collects transcripts, within the configured limits."""

    def __init__(
        self, config: AppConfig, searcher: VideoSearcher, transcripts: TranscriptSource
    ) -> None:
        self._config = config
        self._searcher = searcher
        self._transcripts = transcripts

    @property
    def config(self) -> AppConfig:
        return self._config

    def search(self, query: str, max_results: int | None = None) -> list[Video]:
        """Return search results sorted by view count, most-viewed first (unknown counts last)."""
        limit = _clamp(
            max_results, self._config.search.default_results, self._config.search.max_results
        )
        return self._ranked(validate_query(query), limit)

    def transcript(self, video_id: str, languages: Sequence[str] | None = None) -> Transcript:
        """Return the full transcript, or raise :class:`TranscriptUnavailableError`."""
        return self._transcripts.fetch(
            validate_video_id(video_id), languages or self._config.transcripts.languages
        )

    def recap(
        self, query: str, num_videos: int | None = None, search_pool: int | None = None
    ) -> list[RecapItem]:
        """Search ``search_pool`` results, keep the ``num_videos`` most viewed, and attach
        each one's transcript, cut to the configured length."""
        recap_cfg = self._config.recap
        count = _clamp(num_videos, recap_cfg.default_videos, recap_cfg.max_videos)
        pool = _clamp(search_pool, recap_cfg.default_search_pool, self._config.search.max_results)
        videos = self._ranked(validate_query(query), max(pool, count))[:count]
        return [self._recap_item(v) for v in videos]

    def _ranked(self, query: str, limit: int) -> list[Video]:
        videos = self._searcher.search(query, limit)
        return sorted(videos, key=lambda v: v.view_count or 0, reverse=True)

    def _recap_item(self, video: Video) -> RecapItem:
        try:
            transcript = self.transcript(video.id)
        except TranscriptUnavailableError as exc:
            return RecapItem(video=video, transcript=None, unavailable_reason=exc.reason)
        except YouTubeUnavailableError as exc:
            # One unreachable video should not fail the whole recap.
            logger.warning("recap: skipping %s: %s", video.id, exc)
            return RecapItem(video=video, transcript=None, unavailable_reason="network error")
        limit = self._config.recap.max_transcript_chars
        if len(transcript.text) <= limit:
            return RecapItem(video=video, transcript=transcript)
        cut = replace(transcript, text=transcript.text[:limit])
        return RecapItem(video=video, transcript=cut, truncated=True)
