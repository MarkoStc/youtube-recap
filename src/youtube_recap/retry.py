"""Retry with exponential backoff and jitter for transient network failures."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

from youtube_recap.config import RetryConfig

T = TypeVar("T")

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetryPolicy:
    """Call a function again when it raises one of the given exception types.

    The wait before try ``n + 1`` is a random value between half and all of
    ``initial * multiplier**(n - 1)``, capped at ``max_backoff``. The jitter spreads
    out retries from parallel calls. ``sleep`` and ``rng`` are injectable for tests.
    """

    attempts: int
    initial_backoff: float
    max_backoff: float
    multiplier: float
    sleep: Callable[[float], None] = field(default=time.sleep, repr=False)
    rng: random.Random = field(default_factory=random.Random, repr=False)

    @classmethod
    def from_config(cls, config: RetryConfig) -> RetryPolicy:
        return cls(
            attempts=config.attempts,
            initial_backoff=config.initial_backoff_seconds,
            max_backoff=config.max_backoff_seconds,
            multiplier=config.multiplier,
        )

    def backoff(self, attempt: int) -> float:
        """Seconds to wait after failed try number ``attempt`` (1-based)."""
        ceiling = min(self.max_backoff, self.initial_backoff * self.multiplier ** (attempt - 1))
        return self.rng.uniform(ceiling / 2, ceiling)

    def call(
        self,
        fn: Callable[[], T],
        retry_on: tuple[type[BaseException], ...],
        description: str,
    ) -> T:
        """Return ``fn()``; on ``retry_on`` errors wait and try again, up to ``attempts`` tries.

        The last error is re-raised unchanged when all tries fail.
        """
        for attempt in range(1, self.attempts + 1):
            try:
                return fn()
            except retry_on as exc:
                if attempt == self.attempts:
                    logger.warning("%s failed after %d tries: %r", description, attempt, exc)
                    raise
                wait = self.backoff(attempt)
                logger.info(
                    "%s failed (try %d/%d): %r; retrying in %.1fs",
                    description,
                    attempt,
                    self.attempts,
                    exc,
                    wait,
                )
                self.sleep(wait)
        raise AssertionError("unreachable: attempts >= 1")
