"""Pure unit tests for CircuitBreaker (Stage 19) — a fake, manually
advanced clock makes cooldown/half-open transitions deterministic instead
of depending on real elapsed wall-clock time.
"""

from app.llm_gateway.circuit_breaker import CircuitBreaker, CircuitState


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _breaker(
    *, failure_threshold: int = 3, cooldown_seconds: float = 30.0
) -> tuple[CircuitBreaker, _FakeClock]:
    clock = _FakeClock()
    breaker = CircuitBreaker(
        failure_threshold=failure_threshold, cooldown_seconds=cooldown_seconds, clock=clock
    )
    return breaker, clock


def test_starts_closed_and_allows_requests() -> None:
    breaker, _ = _breaker()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_stays_closed_below_the_failure_threshold() -> None:
    breaker, _ = _breaker(failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_opens_at_the_failure_threshold_and_rejects_requests() -> None:
    breaker, _ = _breaker(failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False


def test_a_success_resets_the_failure_count() -> None:
    breaker, _ = _breaker(failure_threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    breaker.record_failure()
    breaker.record_failure()
    # Two more failures after the reset shouldn't reach the threshold of 3.
    assert breaker.state == CircuitState.CLOSED


def test_stays_open_before_cooldown_elapses() -> None:
    breaker, clock = _breaker(failure_threshold=1, cooldown_seconds=30.0)
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    clock.advance(29.9)
    assert breaker.state == CircuitState.OPEN
    assert breaker.allow_request() is False


def test_becomes_half_open_after_cooldown_and_allows_one_probe() -> None:
    breaker, clock = _breaker(failure_threshold=1, cooldown_seconds=30.0)
    breaker.record_failure()
    clock.advance(30.0)
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker.allow_request() is True


def test_half_open_probe_success_closes_the_breaker() -> None:
    breaker, clock = _breaker(failure_threshold=1, cooldown_seconds=30.0)
    breaker.record_failure()
    clock.advance(30.0)
    assert breaker.state == CircuitState.HALF_OPEN
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.allow_request() is True


def test_half_open_probe_failure_reopens_and_restarts_cooldown() -> None:
    breaker, clock = _breaker(failure_threshold=1, cooldown_seconds=30.0)
    breaker.record_failure()
    clock.advance(30.0)
    assert breaker.state == CircuitState.HALF_OPEN
    breaker.record_failure()
    assert breaker.state == CircuitState.OPEN
    # Cooldown restarted from this failure, not the original one — not
    # enough time has passed since *this* reopen for it to be half-open yet.
    clock.advance(5.0)
    assert breaker.state == CircuitState.OPEN
    clock.advance(25.0)
    assert breaker.state == CircuitState.HALF_OPEN
