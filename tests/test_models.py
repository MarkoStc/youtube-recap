from __future__ import annotations

from youtube_recap.models import Video


def test_from_yt_dlp_full_entry() -> None:
    entry = {"id": "abc", "title": "T", "channel": "Ch", "view_count": 7, "duration": 61}
    video = Video.from_yt_dlp(entry)
    assert video == Video("abc", "T", "Ch", 7, 61.0)
    assert video.url == "https://youtu.be/abc"


def test_from_yt_dlp_falls_back_to_uploader_and_placeholders() -> None:
    video = Video.from_yt_dlp({"id": "abc", "uploader": "Up", "view_count": "n/a"})
    assert video == Video("abc", "Untitled", "Up", None, None)


def test_from_yt_dlp_without_id_is_none() -> None:
    assert Video.from_yt_dlp({"title": "no id"}) is None
