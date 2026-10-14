"""Tests for DiskCache and the caching adapter wrappers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import HIGH, LOW, FakeSearcher, FakeTranscripts
from youtube_recap.cache import CachedSearcher, CachedTranscripts, DiskCache
from youtube_recap.errors import TranscriptUnavailableError


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def cache(tmp_path: Path, clock: Clock) -> DiskCache:
    return DiskCache(tmp_path / "cache", clock)


def test_roundtrip_and_ttl(cache: DiskCache, clock: Clock) -> None:
    cache.set("ns", "k", {"a": [1, 2]})
    assert cache.get("ns", "k", ttl_seconds=10) == {"a": [1, 2]}
    clock.now += 11
    assert cache.get("ns", "k", ttl_seconds=10) is None


def test_missing_key(cache: DiskCache) -> None:
    assert cache.get("ns", "nope", ttl_seconds=10) is None


def test_namespaces_do_not_collide(cache: DiskCache) -> None:
    cache.set("a", "k", 1)
    cache.set("b", "k", 2)
    assert cache.get("a", "k", 10) == 1
    assert cache.get("b", "k", 10) == 2


def test_corrupt_file_is_a_miss_and_removed(cache: DiskCache) -> None:
    cache.set("ns", "k", 1)
    (path,) = cache.directory.glob("ns/*.json")
    path.write_text("{not json", encoding="utf-8")
    assert cache.get("ns", "k", 10) is None
    assert not path.exists()


def test_clear_removes_all_entries(cache: DiskCache) -> None:
    cache.set("a", "k1", 1)
    cache.set("b", "k2", 2)
    assert cache.clear() == 2
    assert cache.get("a", "k1", 10) is None


def test_set_leaves_no_temp_files(cache: DiskCache) -> None:
    cache.set("ns", "k", 1)
    assert list(cache.directory.glob("ns/*.tmp")) == []


def test_cached_searcher_hits_inner_once_per_key(cache: DiskCache) -> None:
    inner = FakeSearcher()
    searcher = CachedSearcher(inner, cache, ttl_seconds=60)
    first = searcher.search("q", 2)
    second = searcher.search("q", 2)
    searcher.search("q", 3)
    assert first == second == [LOW, HIGH]
    assert inner.calls == [("q", 2), ("q", 3)]


def test_cached_searcher_refetches_after_ttl(cache: DiskCache, clock: Clock) -> None:
    inner = FakeSearcher()
    searcher = CachedSearcher(inner, cache, ttl_seconds=60)
    searcher.search("q", 1)
    clock.now += 61
    searcher.search("q", 1)
    assert len(inner.calls) == 2


def test_cached_transcripts_roundtrip(cache: DiskCache) -> None:
    inner = FakeTranscripts()
    source = CachedTranscripts(inner, cache, ttl_seconds=60)
    first = source.fetch(LOW.id, ["en"])
    second = source.fetch(LOW.id, ["en"])
    source.fetch(LOW.id, ["de"])
    assert first == second
    assert [c[1] for c in inner.calls] == [("en",), ("de",)]


def test_cached_transcripts_do_not_cache_failures(cache: DiskCache) -> None:
    inner = FakeTranscripts()
    source = CachedTranscripts(inner, cache, ttl_seconds=60)
    for _ in range(2):
        with pytest.raises(TranscriptUnavailableError):
            source.fetch("zzzzzzzzzzz", ["en"])
    assert len(inner.calls) == 2
