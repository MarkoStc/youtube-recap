from __future__ import annotations

import threading

import pytest

from youtube_recap.ratelimit import NoRateLimit, RateLimiter


class FakeTime:
    """Clock whose sleep advances it, so waits are exact and instant."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _limiter(t: FakeTime, rate: float = 2.0, burst: int = 3) -> RateLimiter:
    return RateLimiter(rate, burst, clock=t.clock, sleep=t.sleep)


def test_burst_passes_without_waiting() -> None:
    t = FakeTime()
    limiter = _limiter(t)
    assert [limiter.acquire() for _ in range(3)] == [0.0, 0.0, 0.0]
    assert t.sleeps == []


def test_after_burst_requests_are_spaced_by_rate() -> None:
    t = FakeTime()
    limiter = _limiter(t, rate=2.0, burst=1)
    limiter.acquire()
    assert limiter.acquire() == pytest.approx(0.5)
    assert limiter.acquire() == pytest.approx(0.5)
    assert t.now == pytest.approx(1.0)


def test_tokens_refill_over_time_up_to_burst() -> None:
    t = FakeTime()
    limiter = _limiter(t, rate=1.0, burst=2)
    limiter.acquire()
    limiter.acquire()
    t.now += 100  # long idle: refill is capped at burst
    assert [limiter.acquire() for _ in range(2)] == [0.0, 0.0]
    assert limiter.acquire() == pytest.approx(1.0)


@pytest.mark.parametrize(("rate", "burst"), [(0, 1), (-1, 1), (1, 0)])
def test_rejects_invalid_settings(rate: float, burst: int) -> None:
    with pytest.raises(ValueError):
        RateLimiter(rate, burst)


def test_concurrent_callers_queue_behind_each_other() -> None:
    # Frozen clock and no-op sleep: each caller must reserve the next free slot.
    limiter = RateLimiter(10.0, 1, clock=lambda: 0.0, sleep=lambda _: None)
    waits: list[float] = []
    lock = threading.Lock()

    def worker() -> None:
        wait = limiter.acquire()
        with lock:
            waits.append(wait)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sorted(round(w, 6) for w in waits) == [0.0, 0.1, 0.2, 0.3, 0.4]


def test_no_rate_limit_never_waits() -> None:
    assert NoRateLimit().acquire() == 0.0
