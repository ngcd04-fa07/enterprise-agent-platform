"""Pure unit tests for InMemoryRateLimiter (Stage 20) — a fake, manually
advanced clock makes window expiry deterministic instead of depending on
real elapsed wall-clock time. See test_auth_api.py for the integration
tests proving login/register actually enforce this at the route level.
"""

import pytest

from app.security.rate_limiter import InMemoryRateLimiter, RateLimitExceeded


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _limiter(
    *, max_attempts: int = 3, window_seconds: float = 60.0
) -> tuple[InMemoryRateLimiter, _FakeClock]:
    clock = _FakeClock()
    limiter = InMemoryRateLimiter(
        max_attempts=max_attempts, window_seconds=window_seconds, clock=clock
    )
    return limiter, clock


def test_allows_attempts_up_to_the_threshold() -> None:
    limiter, _ = _limiter(max_attempts=3)
    limiter.check("k")
    limiter.check("k")
    limiter.check("k")  # the 3rd attempt is still allowed


def test_rejects_the_attempt_that_would_exceed_the_threshold() -> None:
    limiter, _ = _limiter(max_attempts=3)
    limiter.check("k")
    limiter.check("k")
    limiter.check("k")

    with pytest.raises(RateLimitExceeded):
        limiter.check("k")


def test_retry_after_is_bounded_by_the_window() -> None:
    limiter, _ = _limiter(max_attempts=1, window_seconds=60.0)
    limiter.check("k")

    with pytest.raises(RateLimitExceeded) as exc_info:
        limiter.check("k")

    assert 0.0 < exc_info.value.retry_after_seconds <= 60.0


def test_limit_lifts_once_the_window_passes() -> None:
    """Rate-limit, don't lock out: the same key must succeed again once
    its oldest recorded attempt ages out of the window — no manual reset,
    no permanent lockout.
    """
    limiter, clock = _limiter(max_attempts=1, window_seconds=60.0)
    limiter.check("k")

    with pytest.raises(RateLimitExceeded):
        limiter.check("k")

    clock.advance(60.0)
    limiter.check("k")  # succeeds — the earlier attempt is now outside the window


def test_different_keys_have_independent_buckets() -> None:
    limiter, _ = _limiter(max_attempts=1)
    limiter.check("victim-from-attacker-ip")

    with pytest.raises(RateLimitExceeded):
        limiter.check("victim-from-attacker-ip")

    # A different key (e.g. the same identifier from a *different* IP —
    # the victim's own usual IP) is a completely separate bucket.
    limiter.check("victim-from-victims-own-ip")
