"""Shared fixtures: fake yt-dlp and transcript API so tests never touch the network."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import yt_dlp

from youtube_recap import server

ENTRIES: list[dict[str, Any]] = [
    {"id": "aaaaaaaaaaa", "title": "Low", "view_count": 10, "channel": "C1", "duration": 65},
    {"id": "bbbbbbbbbbb", "title": "High", "view_count": 5000, "uploader": "U2", "duration": 3725},
    {"id": "ccccccccccc", "title": "Unknown views", "view_count": None, "duration": None},
]


class FakeYoutubeDL:
    """Stands in for ``yt_dlp.YoutubeDL``; records the search string it was given."""

    calls: list[str] = []
    entries: list[dict[str, Any]] = ENTRIES

    def __init__(self, opts: dict[str, Any]) -> None:
        self.opts = opts

    def __enter__(self) -> FakeYoutubeDL:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = False) -> dict[str, Any]:
        FakeYoutubeDL.calls.append(url)
        limit = int(url.removeprefix("ytsearch").split(":", 1)[0])
        return {"entries": [dict(e) for e in self.entries[:limit]]}


class FakeSnippet:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeTranscriptApi:
    """Stands in for ``YouTubeTranscriptApi``; transcripts keyed by video id."""

    transcripts: dict[str, list[str]] = {}

    def fetch(self, video_id: str, languages: list[str]) -> list[FakeSnippet]:
        if video_id not in self.transcripts:
            raise RuntimeError(f"no transcript for {video_id}")
        return [FakeSnippet(t) for t in self.transcripts[video_id]]


@pytest.fixture(autouse=True)
def fake_youtube(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    FakeYoutubeDL.calls = []
    FakeYoutubeDL.entries = ENTRIES
    FakeTranscriptApi.transcripts = {
        "aaaaaaaaaaa": ["hello", "world"],
        "bbbbbbbbbbb": ["x" * 9000],
    }
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr(server, "YouTubeTranscriptApi", FakeTranscriptApi)
    yield
