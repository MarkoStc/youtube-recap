"""Client-side rate limiting for requests to YouTube."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class RateLimiter:
    """Token bucket: allows bursts of up to ``burst`` requests, refilled at ``rate`` per second.

    ``acquire()`` blocks until a token is free. Thread-safe, so one limiter can be shared by
    the search and transcript adapters. ``clock`` and ``sleep`` are injectable for tests.
    """

    def __init__(
        self,
        rate: float,
        burst: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate <= 0 or burst < 1:
            raise ValueError("rate must be > 0 and burst >= 1")
        self._rate = rate
        self._burst = float(burst)
        self._clock = clock
        self._sleep = sleep
        self._tokens = float(burst)
        self._updated = clock()
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Take one token, waiting if needed. Return the seconds spent waiting."""
        with self._lock:
            now = self._clock()
            self._tokens = min(self._burst, self._tokens + (now - self._updated) * self._rate)
            self._updated = now
            wait = 0.0 if self._tokens >= 1 else (1 - self._tokens) / self._rate
            # Reserve the token now, so concurrent callers queue behind this one.
            self._tokens -= 1
        if wait > 0:
            self._sleep(wait)
        return wait


class NoRateLimit:
    """Stands in for RateLimiter when limiting is disabled."""

    def acquire(self) -> float:
        return 0.0
