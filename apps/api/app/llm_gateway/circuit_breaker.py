import enum
import time
from collections.abc import Callable


class CircuitState(enum.StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """In-memory, per-process circuit breaker for one LLM tier (Stage 19)
    — protects against hammering a tier that's actually down, and lets
    routing fail fast instead of paying a full timeout on every call
    while an outage is ongoing. Per-process, not shared/persisted: this
    app is single-instance until Stage 21's multi-replica work, so
    process-local state is the right amount of machinery for the
    deployment that actually exists today, not a hypothetical one.

    Only `record_failure()` on a call the caller has already determined
    is `LLMFailureKind.TRANSIENT` should ever be invoked — a content or
    permanent failure says nothing about this tier's health and must
    never trip the breaker (see LLMFailureKind's docstring). This class
    itself is failure-kind-agnostic; that filtering is the caller's job
    (see RoutingLLMGateway).

    Standard three-state design: CLOSED (normal) -> OPEN (rejecting
    calls) after `failure_threshold` consecutive failures -> HALF_OPEN
    (one probe allowed) after `cooldown_seconds` have passed -> CLOSED
    again on the probe's success, or back to OPEN (cooldown restarted) on
    its failure.

    One accepted simplification, stated plainly rather than hidden: no
    locking around the half-open probe. Under concurrent requests, more
    than one call could see `allow_request() == True` during the same
    half-open window and all attempt a probe simultaneously. Building
    strict single-probe concurrency control is more machinery than this
    project's scale warrants; the worst case is a few extra probe
    attempts right as a tier recovers, not incorrect routing.
    """

    def __init__(
        self,
        *,
        failure_threshold: int,
        cooldown_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN and self._cooldown_elapsed():
            return CircuitState.HALF_OPEN
        return self._state

    def _cooldown_elapsed(self) -> bool:
        return self._opened_at is not None and (self._clock() - self._opened_at) >= (
            self._cooldown_seconds
        )

    def allow_request(self) -> bool:
        """CLOSED and HALF_OPEN both allow the call through (HALF_OPEN's
        probe included) — only a still-cooling-down OPEN breaker rejects.
        """
        return self.state != CircuitState.OPEN

    def record_success(self) -> None:
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            # The probe failed — reopen immediately and restart the
            # cooldown, without needing another `failure_threshold` count.
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            return

        self._consecutive_failures += 1
        if self._consecutive_failures >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
