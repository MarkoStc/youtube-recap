"""MCP server that searches YouTube, pulls transcripts, and hands them to Claude to summarize.

Exposes three tools over stdio via FastMCP:

- ``search_videos``: rank matching videos by view count (so the model can pick).
- ``get_transcript``: fetch the transcript for one video id.
- ``recap``: search, keep the most-viewed videos, and return their transcripts to summarize.

The summarizing itself is done by the MCP client (Claude) reading the returned text.
"""

from __future__ import annotations

import logging

import truststore
from mcp.server.fastmcp import FastMCP

from youtube_recap import formatting
from youtube_recap.cache import CachedSearcher, CachedTranscripts, DiskCache
from youtube_recap.config import AppConfig, load_config
from youtube_recap.errors import TranscriptUnavailableError
from youtube_recap.log import configure_logging
from youtube_recap.ratelimit import NoRateLimit, RateLimiter
from youtube_recap.retry import RetryPolicy
from youtube_recap.service import RecapService
from youtube_recap.youtube import (
    TranscriptSource,
    VideoSearcher,
    YouTubeTranscriptSource,
    YtDlpSearcher,
)

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


def build_service(config: AppConfig) -> RecapService:
    """Wire the real YouTube adapters with ``config``."""
    net = config.network
    retry = RetryPolicy.from_config(net.retry)
    rl = config.rate_limit
    limiter = RateLimiter(rl.requests_per_second, rl.burst) if rl.enabled else NoRateLimit()
    searcher: VideoSearcher = YtDlpSearcher(retry, net.timeout_seconds, limiter)
    transcripts: TranscriptSource = YouTubeTranscriptSource(
        retry, net.timeout_seconds, limiter, fallback=config.transcripts.fallback
    )
    if config.cache.enabled:
        cache = DiskCache(config.cache.directory)
        searcher = CachedSearcher(searcher, cache, config.cache.search_ttl_seconds)
        transcripts = CachedTranscripts(transcripts, cache, config.cache.transcript_ttl_seconds)
    return RecapService(config, searcher, transcripts)


def prepare_runtime(config: AppConfig) -> None:
    """Process-wide setup shared by every entry point: logging and TLS trust."""
    configure_logging(config.logging)
    if config.network.use_os_trust_store:
        # Verify TLS with the OS store so yt-dlp and youtube-transcript-api work behind
        # TLS-intercepting proxies. truststore patches ssl, urllib3 and requests in place.
        truststore.inject_into_ssl()


def main() -> None:
    """Console-script entry point: run the MCP server over stdio."""
    config = load_config()
    prepare_runtime(config)
    logger.info("starting %s over stdio", SERVER_NAME)
    build_server(build_service(config)).run()


if __name__ == "__main__":
    main()
