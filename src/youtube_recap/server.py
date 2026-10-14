"""MCP server that searches YouTube, pulls transcripts, and hands them to Claude to summarize.

Exposes three tools over stdio via FastMCP:

- ``search_videos``: rank matching videos by view count (so the model can pick).
- ``get_transcript``: fetch the transcript for one video id.
- ``recap``: search, keep the most-viewed videos, and return their transcripts to summarize.

The summarizing itself is done by the MCP client (Claude) reading the returned text.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from youtube_recap import formatting
from youtube_recap.app import build_service, prepare_runtime
from youtube_recap.config import AppConfig, load_config
from youtube_recap.errors import TranscriptUnavailableError
from youtube_recap.service import RecapService

logger = logging.getLogger(__name__)

SERVER_NAME = "youtube-recap"


def build_server(service: RecapService) -> FastMCP:
    """Create the FastMCP server and register the tools against ``service``."""
    mcp = FastMCP(SERVER_NAME)

    @mcp.tool()
    def search_videos(query: str, max_results: int | None = None) -> str:
        """Search YouTube and list matching videos with view counts, channel, and duration.

        Results are ranked most-viewed first so you can choose which videos to recap.
        ``max_results`` defaults to the configured value and is capped by the configured maximum.
        """
        return formatting.format_video_list(query, service.search(query, max_results))

    @mcp.tool()
    def get_transcript(video_id: str, languages: list[str] | None = None) -> str:
        """Fetch the full plain-text transcript for a single YouTube video id.

        ``languages`` lists preferred language codes in order (default: configured languages).
        If none exists, the server may return a machine translation or another language;
        a ``[language: ...]`` line at the top says so.
        """
        requested = languages or service.config.transcripts.languages
        try:
            return formatting.format_transcript(service.transcript(video_id, languages), requested)
        except TranscriptUnavailableError as exc:
            return formatting.format_unavailable(video_id, exc.reason)

    @mcp.tool()
    def recap(query: str, num_videos: int | None = None, search_pool: int | None = None) -> str:
        """Search YouTube, keep the most-viewed videos, and return their transcripts to summarize.

        Searches ``search_pool`` results, keeps the top ``num_videos`` by view count, and returns
        each (truncated) transcript so you can read and summarize them. Both counts default to
        the configured values.
        """
        return formatting.format_recap(query, service.recap(query, num_videos, search_pool))

    return mcp


def serve(config: AppConfig) -> None:
    """Run the MCP server over stdio until the client disconnects."""
    prepare_runtime(config)
    logger.info("starting %s over stdio", SERVER_NAME)
    build_server(build_service(config)).run()


def main() -> None:
    """Run the server with the default config (``python -m youtube_recap.server``)."""
    serve(load_config())


if __name__ == "__main__":
    main()
