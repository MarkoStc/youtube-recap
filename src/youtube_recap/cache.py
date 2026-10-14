"""On-disk JSON cache with per-namespace TTL, and caching wrappers for the YouTube adapters.

Each entry is one JSON file named by the SHA-256 of ``namespace`` and ``key``, written
atomically (temp file + rename), so parallel server processes can share a directory.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from youtube_recap.models import Transcript, Video
from youtube_recap.youtube import TranscriptSource, VideoSearcher

logger = logging.getLogger(__name__)


class DiskCache:
    """Key-value store of JSON-serialisable values, one file per entry."""

    def __init__(self, directory: Path, clock: Callable[[], float] = time.time) -> None:
        self._dir = directory
        self._clock = clock

    @property
    def directory(self) -> Path:
        return self._dir

    def _path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha256(f"{namespace}\0{key}".encode()).hexdigest()
        return self._dir / namespace / f"{digest}.json"

    def get(self, namespace: str, key: str, ttl_seconds: float) -> Any | None:
        """Return the stored value, or None if missing, expired, or unreadable."""
        path = self._path(namespace, key)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            stored_at = float(entry["stored_at"])
            value = entry["value"]
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as exc:
            logger.warning("dropping unreadable cache file %s: %r", path, exc)
            path.unlink(missing_ok=True)
            return None
        if self._clock() - stored_at > ttl_seconds:
            return None
        return value

    def set(self, namespace: str, key: str, value: Any) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"stored_at": self._clock(), "key": key, "value": value})
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def clear(self) -> int:
        """Delete every cache file; return how many were removed."""
        removed = 0
        for path in self._dir.glob("*/*.json"):
            path.unlink(missing_ok=True)
            removed += 1
        return removed


class CachedSearcher:
    """A VideoSearcher that serves repeated (query, limit) pairs from the cache."""

    NAMESPACE = "search"

    def __init__(self, inner: VideoSearcher, cache: DiskCache, ttl_seconds: float) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl_seconds

    def search(self, query: str, limit: int) -> list[Video]:
        key = f"{query}\0{limit}"
        cached = self._cache.get(self.NAMESPACE, key, self._ttl)
        if cached is not None:
            logger.debug("cache hit: search %r limit=%d", query, limit)
            return [Video(**item) for item in cached]
        videos = self._inner.search(query, limit)
        self._cache.set(self.NAMESPACE, key, [asdict(v) for v in videos])
        return videos


class CachedTranscripts:
    """A TranscriptSource that serves repeated (video, languages) pairs from the cache.

    Failures are not cached, so a transcript added later or a network error is retried.
    """

    NAMESPACE = "transcript"

    def __init__(self, inner: TranscriptSource, cache: DiskCache, ttl_seconds: float) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl_seconds

    def fetch(self, video_id: str, languages: Sequence[str]) -> Transcript:
        key = f"{video_id}\0{','.join(languages)}"
        cached = self._cache.get(self.NAMESPACE, key, self._ttl)
        if cached is not None:
            logger.debug("cache hit: transcript %s", video_id)
            return Transcript(**cached)
        transcript = self._inner.fetch(video_id, languages)
        self._cache.set(self.NAMESPACE, key, asdict(transcript))
        return transcript
