import time
from collections import deque
from collections.abc import Callable


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__(f"rate limit exceeded, retry after {retry_after_seconds:.1f}s")
        self.retry_after_seconds = retry_after_seconds


class InMemoryRateLimiter:
    """Sliding-window-log limiter — in-memory, per-process (Stage 20;
    same reasoning as Stage 19's CircuitBreaker: this app is single-
    instance today, so process-local state is the right amount of
    machinery, not a hypothetical multi-replica one — a shared/
    distributed limiter is a Stage 21 concern if it's ever needed).

    `check(key)` records one attempt for `key` and raises
    RateLimitExceeded if that attempt would push `key` over
    `max_attempts` within the trailing `window_seconds` — every attempt
    counts, not just failures, so the limiter bounds request *volume*
    for a key regardless of outcome. Bounded window means the limit
    always eventually lifts on its own (no permanent lockout, no manual
    reset needed) — the oldest recorded attempt ages out and space opens
    up again, satisfying "rate-limit, don't lock out."

    Accepted memory tradeoff, stated plainly rather than hidden: a
    bucket for a key that's used once and never again lives for the rest
    of the process's life (each is just a deque of a handful of floats).
    At this app's actual scale — a single instance, a small user base —
    this is negligible; a real high-traffic deployment would want a
    periodic sweep or a proper TTL cache instead, which is more machinery
    than this stage's scale justifies.
    """

    def __init__(
        self,
        *,
        max_attempts: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._clock = clock
        self._buckets: dict[str, deque[float]] = {}

    def check(self, key: str) -> None:
        now = self._clock()
        bucket = self._buckets.setdefault(key, deque())

        while bucket and now - bucket[0] >= self._window_seconds:
            bucket.popleft()

        if len(bucket) >= self._max_attempts:
            retry_after = self._window_seconds - (now - bucket[0])
            raise RateLimitExceeded(max(retry_after, 0.0))

        bucket.append(now)
