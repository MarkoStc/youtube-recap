"""Render domain objects as the plain text the MCP tools return to the model."""

from __future__ import annotations

from collections.abc import Sequence

from youtube_recap.models import RecapItem, Transcript, Video

RECAP_SEPARATOR = "\n\n---\n\n"


def format_views(views: int | None) -> str:
    return f"{views:,}" if views is not None else "unknown"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    hours, rem = divmod(int(seconds), 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def no_results(query: str) -> str:
    return f"No results for {query!r}."


def format_video_list(query: str, videos: Sequence[Video]) -> str:
    if not videos:
        return no_results(query)
    return "\n".join(
        f"- {v.title}\n"
        f"  id={v.id} | views={format_views(v.view_count)} | "
        f"channel={v.channel} | duration={format_duration(v.duration_seconds)}\n"
        f"  {v.url}"
        for v in videos
    )


def format_transcript(transcript: Transcript) -> str:
    return transcript.text


def format_unavailable(video_id: str, reason: str) -> str:
    return f"[transcript unavailable: {video_id}: {reason}]"


def format_recap(query: str, items: Sequence[RecapItem]) -> str:
    if not items:
        return no_results(query)
    return RECAP_SEPARATOR.join(_format_item(item) for item in items)


def _format_item(item: RecapItem) -> str:
    v = item.video
    header = f"## {v.title}\n{v.url} | views={format_views(v.view_count)} | channel={v.channel}"
    if item.transcript is None:
        body = format_unavailable(v.id, item.unavailable_reason or "unknown reason")
    else:
        body = item.transcript.text
    return f"{header}\n\n{body}"
