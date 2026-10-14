"""Tests for ranking, limits and truncation in RecapService."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from tests.conftest import HIGH, LOW, UNKNOWN, FakeSearcher, FakeTranscripts
from youtube_recap.config import AppConfig
from youtube_recap.errors import InvalidInputError, YouTubeUnavailableError
from youtube_recap.models import Transcript
from youtube_recap.service import RecapService


def test_search_ranks_most_viewed_first_unknown_last(service: RecapService) -> None:
    assert service.search("q", 3) == [HIGH, LOW, UNKNOWN]


def test_search_uses_configured_default(
    service: RecapService, searcher: FakeSearcher, config: AppConfig
) -> None:
    service.search("q")
    assert searcher.calls == [("q", config.search.default_results)]


def test_search_count_is_clamped(
    service: RecapService, searcher: FakeSearcher, config: AppConfig
) -> None:
    service.search("q", 10_000)
    service.search("q", -5)
    assert searcher.calls == [("q", config.search.max_results), ("q", 1)]


def test_transcript_uses_configured_languages(
    service: RecapService, transcripts: FakeTranscripts, config: AppConfig
) -> None:
    service.transcript(LOW.id)
    service.transcript(LOW.id, ["fr"])
    assert transcripts.calls == [(LOW.id, config.transcripts.languages), (LOW.id, ("fr",))]


def test_recap_keeps_top_videos_and_truncates(service: RecapService, config: AppConfig) -> None:
    items = service.recap("q", num_videos=2, search_pool=3)
    assert [i.video for i in items] == [HIGH, LOW]
    high, low = items
    assert high.truncated and high.transcript is not None
    assert len(high.transcript.text) == config.recap.max_transcript_chars
    assert not low.truncated and low.transcript is not None
    assert low.transcript.text == "hello world"


def test_recap_search_pool_never_smaller_than_num_videos(
    service: RecapService, searcher: FakeSearcher
) -> None:
    service.recap("q", num_videos=3, search_pool=1)
    assert searcher.calls == [("q", 3)]


def test_recap_negative_count_is_clamped_to_one(service: RecapService) -> None:
    assert len(service.recap("q", num_videos=-1)) == 1


def test_recap_marks_missing_transcripts(service: RecapService) -> None:
    items = service.recap("q", num_videos=3, search_pool=3)
    missing = items[-1]
    assert missing.video == UNKNOWN
    assert missing.transcript is None
    assert missing.unavailable_reason == "TranscriptsDisabled"


def test_recap_no_results(config: AppConfig, transcripts: FakeTranscripts) -> None:
    service = RecapService(config, FakeSearcher(videos=[]), transcripts)
    assert service.recap("nothing") == []


@pytest.mark.parametrize("query", ["", "   "])
def test_empty_query_is_rejected(service: RecapService, query: str) -> None:
    with pytest.raises(InvalidInputError):
        service.search(query)
    with pytest.raises(InvalidInputError):
        service.recap(query)


@pytest.mark.parametrize("video_id", ["short", "https://youtu.be/aaaaaaaaaaa", "aaaaaaaaaa!"])
def test_bad_video_id_is_rejected(service: RecapService, video_id: str) -> None:
    with pytest.raises(InvalidInputError, match="not a YouTube video id"):
        service.transcript(video_id)


def test_video_id_whitespace_is_stripped(
    service: RecapService, transcripts: FakeTranscripts
) -> None:
    service.transcript("  aaaaaaaaaaa \n")
    assert transcripts.calls[0][0] == "aaaaaaaaaaa"


class FlakyTranscripts(FakeTranscripts):
    def fetch(self, video_id: str, languages: Sequence[str]) -> Transcript:
        if video_id == HIGH.id:
            raise YouTubeUnavailableError("timeout")
        return super().fetch(video_id, languages)


def test_recap_survives_network_error_on_one_video(
    config: AppConfig, searcher: FakeSearcher
) -> None:
    service = RecapService(config, searcher, FlakyTranscripts())
    high, low = service.recap("q", num_videos=2)
    assert high.transcript is None and high.unavailable_reason == "network error"
    assert low.transcript is not None
