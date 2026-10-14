"""Domain objects passed between the YouTube clients, the service and the formatters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Video:
    """One search result with the metadata used for ranking and display."""

    id: str
    title: str
    channel: str
    view_count: int | None
    duration_seconds: float | None

    @property
    def url(self) -> str:
        return f"https://youtu.be/{self.id}"

    @classmethod
    def from_yt_dlp(cls, entry: Mapping[str, Any]) -> Video | None:
        """Build a Video from a flat yt-dlp entry; return None when the entry has no id."""
        video_id = entry.get("id")
        if not video_id:
            return None
        views = entry.get("view_count")
        duration = entry.get("duration")
        return cls(
            id=str(video_id),
            title=str(entry.get("title") or "Untitled"),
            channel=str(entry.get("channel") or entry.get("uploader") or "unknown"),
            view_count=views if isinstance(views, int) else None,
            duration_seconds=float(duration) if isinstance(duration, int | float) else None,
        )


@dataclass(frozen=True, slots=True)
class Transcript:
    """Plain text of one video's captions."""

    video_id: str
    language_code: str
    text: str
    is_generated: bool


@dataclass(frozen=True, slots=True)
class RecapItem:
    """One video in a recap: its transcript (possibly cut), or why there is none."""

    video: Video
    transcript: Transcript | None
    unavailable_reason: str | None = None
    truncated: bool = False
