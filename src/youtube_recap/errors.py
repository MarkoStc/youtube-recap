"""Exception types raised by youtube-recap."""

from __future__ import annotations


class YouTubeRecapError(Exception):
    """Base class for all errors this package raises on purpose."""


class InvalidInputError(YouTubeRecapError, ValueError):
    """A tool argument is malformed (empty query, bad video id, ...)."""


class TranscriptUnavailableError(YouTubeRecapError):
    """The video has no transcript we can use (disabled, missing language, private, ...)."""

    def __init__(self, video_id: str, reason: str) -> None:
        super().__init__(f"no transcript for {video_id}: {reason}")
        self.video_id = video_id
        self.reason = reason


class YouTubeUnavailableError(YouTubeRecapError):
    """YouTube could not be reached or kept failing after all retries."""
