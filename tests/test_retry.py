from __future__ import annotations

import random

import pytest

from youtube_recap.config import load_config
from youtube_recap.retry import RetryPolicy


def _policy(attempts: int = 3, sleeps: list[float] | None = None) -> RetryPolicy:
    record = sleeps if sleeps is not None else []
    return RetryPolicy(
        attempts=attempts,
        initial_backoff=1.0,
        max_backoff=3.0,
        multiplier=2.0,
        sleep=record.append,
        rng=random.Random(0),
    )


def test_returns_first_success_without_sleeping() -> None:
    sleeps: list[float] = []
    assert _policy(sleeps=sleeps).call(lambda: 42, (OSError,), "x") == 42
    assert sleeps == []


def test_retries_transient_errors_then_succeeds() -> None:
    sleeps: list[float] = []
    results: list[int | Exception] = [OSError("a"), OSError("b"), 7]

    def flaky() -> int:
        item = results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    assert _policy(sleeps=sleeps).call(flaky, (OSError,), "x") == 7
    assert len(sleeps) == 2
    assert 0.5 <= sleeps[0] <= 1.0
    assert 1.0 <= sleeps[1] <= 2.0


def test_reraises_last_error_after_all_attempts() -> None:
    sleeps: list[float] = []
    calls = 0

    def always_fails() -> None:
        nonlocal calls
        calls += 1
        raise TimeoutError(calls)

    with pytest.raises(TimeoutError, match="3"):
        _policy(sleeps=sleeps).call(always_fails, (TimeoutError,), "x")
    assert calls == 3
    assert len(sleeps) == 2


def test_does_not_retry_other_errors() -> None:
    sleeps: list[float] = []

    def boom() -> None:
        raise KeyError("permanent")

    with pytest.raises(KeyError):
        _policy(sleeps=sleeps).call(boom, (OSError,), "x")
    assert sleeps == []


def test_backoff_is_capped() -> None:
    policy = _policy()
    assert all(1.5 <= policy.backoff(n) <= 3.0 for n in range(3, 10))


def test_from_config_uses_yaml_values() -> None:
    cfg = load_config().network.retry
    policy = RetryPolicy.from_config(cfg)
    assert policy.attempts == cfg.attempts
    assert policy.max_backoff == cfg.max_backoff_seconds
