"""Shared fakes: tests never touch the network.

``FakeSearcher`` and ``FakeTranscripts`` implement the service's Protocols directly.
``FakeYoutubeDL`` and ``FakeTranscriptApi`` stand in for the third-party libraries, to test
the adapters in ``youtube_recap.youtube``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest

from youtube_recap.config import AppConfig, load_config
from youtube_recap.errors import TranscriptUnavailableError
from youtube_recap.models import Transcript, Video
from youtube_recap.service import RecapService

LOW = Video("aaaaaaaaaaa", "Low", "C1", 10, 65.0)
HIGH = Video("bbbbbbbbbbb", "High", "U2", 5000, 3725.0)
UNKNOWN = Video("ccccccccccc", "Unknown views", "unknown", None, None)


@dataclass
class FakeSearcher:
    videos: list[Video] = field(default_factory=lambda: [LOW, HIGH, UNKNOWN])
    calls: list[tuple[str, int]] = field(default_factory=list)

    def search(self, query: str, limit: int) -> list[Video]:
        self.calls.append((query, limit))
        return self.videos[:limit]


@dataclass
class FakeTranscripts:
    texts: dict[str, str] = field(
        default_factory=lambda: {LOW.id: "hello world", HIGH.id: "x" * 9000}
    )
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def fetch(self, video_id: str, languages: Sequence[str]) -> Transcript:
        self.calls.append((video_id, tuple(languages)))
        if video_id not in self.texts:
            raise TranscriptUnavailableError(video_id, "TranscriptsDisabled")
        return Transcript(video_id, languages[0], self.texts[video_id], is_generated=False)


@pytest.fixture
def config() -> AppConfig:
    return load_config()


@pytest.fixture
def searcher() -> FakeSearcher:
    return FakeSearcher()


@pytest.fixture
def transcripts() -> FakeTranscripts:
    return FakeTranscripts()


@pytest.fixture
def service(
    config: AppConfig, searcher: FakeSearcher, transcripts: FakeTranscripts
) -> RecapService:
    return RecapService(config, searcher, transcripts)


class FakeYoutubeDL:
    """Stands in for ``yt_dlp.YoutubeDL``; records the URL it was asked to extract."""

    def __init__(self, entries: list[dict[str, Any]] | None) -> None:
        self.entries = entries
        self.urls: list[str] = []
        self.options: dict[str, Any] = {}
        self.error: Exception | None = None

    def __call__(self, options: dict[str, Any]) -> FakeYoutubeDL:
        self.options = options
        return self

    def __enter__(self) -> FakeYoutubeDL:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any] | None:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return None if self.entries is None else {"entries": self.entries}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
