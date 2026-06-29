"""MCP server that searches YouTube, pulls transcripts, and hands them to Claude to summarize.

Exposes three tools over stdio via FastMCP:

- ``search_videos``: rank matching videos by view count (so the model can pick).
- ``get_transcript``: fetch the transcript for one video id.
- ``recap``: search, keep the most-viewed videos, and return their transcripts to summarize.

The summarizing itself is done by the MCP client (Claude) reading the returned text.
"""

from __future__ import annotations

import truststore

# Route TLS verification through the OS trust store before importing any networking
# library, so yt-dlp / youtube-transcript-api work behind TLS-intercepting proxies.
truststore.inject_into_ssl()

import yt_dlp  # noqa: E402  (must follow inject_into_ssl)
from mcp.server.fastmcp import FastMCP  # noqa: E402
from youtube_transcript_api import YouTubeTranscriptApi  # noqa: E402

mcp = FastMCP("youtube-recap")

# Cap transcript length per video so a multi-video recap stays within a sane token budget.
_MAX_TRANSCRIPT_CHARS = 8000


def _search(query: str, limit: int) -> list[dict]:
    """Return flat metadata for the top ``limit`` YouTube results for ``query``."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        # Flat extraction skips per-video page loads: fast, and still carries
        # id/title/view_count/channel/duration for ranking.
        "extract_flat": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
    return info.get("entries", []) if info else []


def _snippet_text(snippet: object) -> str:
    """Extract text from a transcript snippet across youtube-transcript-api versions."""
    return snippet.text if hasattr(snippet, "text") else snippet["text"]


def _fetch_transcript(video_id: str, languages: list[str]) -> str:
    """Return the plain-text transcript for a video, or a placeholder on failure."""
    try:
        try:
            # youtube-transcript-api >= 1.0 uses an instance method.
            snippets = YouTubeTranscriptApi().fetch(video_id, languages=languages)
        except AttributeError:
            # Older releases exposed a static get_transcript.
            snippets = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
    except Exception as exc:  # no transcript, disabled, region-locked, ...
        return f"[transcript unavailable: {exc}]"
    return " ".join(_snippet_text(s) for s in snippets)


def _format_views(views: int | None) -> str:
    return f"{views:,}" if isinstance(views, int) else "unknown"


def _format_duration(seconds: float | None) -> str:
    if not isinstance(seconds, (int, float)):
        return "unknown"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _channel_of(entry: dict) -> str:
    return entry.get("channel") or entry.get("uploader") or "unknown"


def _ranked_by_views(query: str, limit: int) -> list[dict]:
    """Search and return entries sorted by view count, most-viewed first."""
    entries = _search(query, limit)
    entries.sort(key=lambda e: e.get("view_count") or 0, reverse=True)
    return entries


@mcp.tool()
def search_videos(query: str, max_results: int = 10) -> str:
    """Search YouTube and list matching videos with view counts, channel, and duration.

    Results are ranked most-viewed first so you can choose which videos to recap.
    """
    entries = _ranked_by_views(query, max_results)
    if not entries:
        return f"No results for {query!r}."
    lines = [
        f"- {e.get('title', 'Untitled')}\n"
        f"  id={e.get('id')} | views={_format_views(e.get('view_count'))} | "
        f"channel={_channel_of(e)} | duration={_format_duration(e.get('duration'))}\n"
        f"  https://youtu.be/{e.get('id')}"
        for e in entries
    ]
    return "\n".join(lines)


@mcp.tool()
def get_transcript(video_id: str, languages: list[str] | None = None) -> str:
    """Fetch the full plain-text transcript for a single YouTube video id."""
    return _fetch_transcript(video_id, languages or ["en"])


@mcp.tool()
def recap(query: str, num_videos: int = 3, search_pool: int = 10) -> str:
    """Search YouTube, keep the most-viewed videos, and return their transcripts to summarize.

    Searches ``search_pool`` results, keeps the top ``num_videos`` by view count, and returns
    each (truncated) transcript so you can read and summarize them.
    """
    entries = _ranked_by_views(query, max(search_pool, num_videos))[:num_videos]
    if not entries:
        return f"No results for {query!r}."
    blocks = []
    for e in entries:
        vid = e.get("id")
        transcript = _fetch_transcript(vid, ["en"])[:_MAX_TRANSCRIPT_CHARS]
        blocks.append(
            f"## {e.get('title', 'Untitled')}\n"
            f"https://youtu.be/{vid} | views={_format_views(e.get('view_count'))} | "
            f"channel={_channel_of(e)}\n\n"
            f"{transcript}"
        )
    return "\n\n---\n\n".join(blocks)


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
