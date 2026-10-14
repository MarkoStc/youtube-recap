"""Composition root: builds the real object graph from config. Used by every entry point."""

from __future__ import annotations

import truststore

from youtube_recap.cache import CachedSearcher, CachedTranscripts, DiskCache
from youtube_recap.config import AppConfig
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


def build_service(config: AppConfig) -> RecapService:
    """Wire the real YouTube adapters, rate limiter and cache according to ``config``."""
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
