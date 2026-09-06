import pytest

from app.llm_gateway.base import LLMFailureKind, LLMGenerationError, TaskComplexity
from app.llm_gateway.circuit_breaker import CircuitBreaker
from app.llm_gateway.routing_llm_gateway import RoutingLLMGateway
from app.schemas.extraction import ChunkExtraction
from tests.fake_llm_gateway import FakeLLMGateway


def _tight_breaker() -> CircuitBreaker:
    """Opens after a single failure — for tests that want a breaker
    already open without needing several failing calls first."""
    return CircuitBreaker(failure_threshold=1, cooldown_seconds=30.0)


async def test_simple_complexity_routes_to_fast_tier() -> None:
    fast = FakeLLMGateway()
    fast.default_response = {"named_insured": "Fast Tier Corp"}
    capable = FakeLLMGateway()
    capable.default_response = {"named_insured": "Capable Tier Corp"}
    router = RoutingLLMGateway(fast=fast, capable=capable)

    result = await router.generate_structured(
        system_prompt="sys", user_prompt="anything", schema=ChunkExtraction
    )

    assert result.named_insured == "Fast Tier Corp"
    assert fast.calls == ["anything"]
    assert capable.calls == []


async def test_complex_complexity_routes_to_capable_tier() -> None:
    fast = FakeLLMGateway()
    fast.default_response = {"named_insured": "Fast Tier Corp"}
    capable = FakeLLMGateway()
    capable.default_response = {"named_insured": "Capable Tier Corp"}
    router = RoutingLLMGateway(fast=fast, capable=capable)

    result = await router.generate_structured(
        system_prompt="sys",
        user_prompt="anything",
        schema=ChunkExtraction,
        complexity=TaskComplexity.COMPLEX,
    )

    assert result.named_insured == "Capable Tier Corp"
    assert fast.calls == []
    assert capable.calls == ["anything"]


async def test_fast_tier_failure_escalates_to_capable_tier() -> None:
    fast = FakeLLMGateway()
    fast.should_fail = True
    capable = FakeLLMGateway()
    capable.default_response = {"named_insured": "Rescued By Capable Tier"}
    router = RoutingLLMGateway(fast=fast, capable=capable)

    result = await router.generate_structured(
        system_prompt="sys", user_prompt="anything", schema=ChunkExtraction
    )

    assert result.named_insured == "Rescued By Capable Tier"
    assert fast.calls == ["anything"]
    assert capable.calls == ["anything"]


async def test_both_tiers_failing_raises_the_capable_tiers_error() -> None:
    fast = FakeLLMGateway()
    fast.should_fail = True
    capable = FakeLLMGateway()
    capable.should_fail = True
    router = RoutingLLMGateway(fast=fast, capable=capable)

    with pytest.raises(LLMGenerationError):
        await router.generate_structured(
            system_prompt="sys", user_prompt="anything", schema=ChunkExtraction
        )


# --- Stage 19: reason codes ---------------------------------------------


async def test_route_reason_is_complexity_route_fast_on_the_ordinary_simple_path() -> None:
    fast = FakeLLMGateway()
    fast.default_response = {"named_insured": "Fast Tier Corp"}
    capable = FakeLLMGateway()
    router = RoutingLLMGateway(fast=fast, capable=capable)

    await router.generate_structured(
        system_prompt="sys", user_prompt="anything", schema=ChunkExtraction
    )

    assert fast.route_reasons_seen == ["complexity_route_fast"]


async def test_route_reason_is_complexity_route_capable_on_the_ordinary_complex_path() -> None:
    fast = FakeLLMGateway()
    capable = FakeLLMGateway()
    capable.default_response = {"named_insured": "Capable Tier Corp"}
    router = RoutingLLMGateway(fast=fast, capable=capable)

    await router.generate_structured(
        system_prompt="sys",
        user_prompt="anything",
        schema=ChunkExtraction,
        complexity=TaskComplexity.COMPLEX,
    )

    assert capable.route_reasons_seen == ["complexity_route_capable"]


async def test_route_reason_is_fast_failed_escalate_capable_on_escalation() -> None:
    fast = FakeLLMGateway()
    fast.should_fail = True
    capable = FakeLLMGateway()
    capable.default_response = {"named_insured": "Rescued By Capable Tier"}
    router = RoutingLLMGateway(fast=fast, capable=capable)

    await router.generate_structured(
        system_prompt="sys", user_prompt="anything", schema=ChunkExtraction
    )

    assert capable.route_reasons_seen == ["fast_failed_escalate_capable"]


# --- Stage 19: circuit breakers -----------------------------------------


async def test_open_fast_breaker_skips_fast_tier_entirely() -> None:
    fast = FakeLLMGateway()
    fast.default_response = {"named_insured": "Should Never Be Called"}
    capable = FakeLLMGateway()
    capable.default_response = {"named_insured": "Capable Tier Corp"}
    router = RoutingLLMGateway(
        fast=fast, capable=capable, fast_breaker=_tight_breaker(), capable_breaker=_tight_breaker()
    )
    router._fast_breaker.record_failure()  # opens it (threshold=1)
    assert not router._fast_breaker.allow_request()

    result = await router.generate_structured(
        system_prompt="sys", user_prompt="anything", schema=ChunkExtraction
    )

    assert result.named_insured == "Capable Tier Corp"
    assert fast.calls == []  # never even attempted
    assert capable.route_reasons_seen == ["fast_breaker_open"]


async def test_content_failure_never_opens_the_breaker() -> None:
    """A malformed response from an otherwise healthy fast tier must not
    be mistaken for the fast tier being down — see LLMFailureKind."""
    fast = FakeLLMGateway()
    fast.should_fail = True
    fast.failure_kind = LLMFailureKind.CONTENT
    capable = FakeLLMGateway()
    capable.default_response = {"named_insured": "Rescued By Capable Tier"}
    breaker = _tight_breaker()  # would open after just 1 failure, if counted
    router = RoutingLLMGateway(fast=fast, capable=capable, fast_breaker=breaker)

    await router.generate_structured(
        system_prompt="sys", user_prompt="anything", schema=ChunkExtraction
    )

    assert breaker.allow_request() is True  # still closed


async def test_permanent_failure_never_opens_the_breaker() -> None:
    fast = FakeLLMGateway()
    fast.should_fail = True
    fast.failure_kind = LLMFailureKind.PERMANENT
    capable = FakeLLMGateway()
    capable.default_response = {"named_insured": "Rescued By Capable Tier"}
    breaker = _tight_breaker()
    router = RoutingLLMGateway(fast=fast, capable=capable, fast_breaker=breaker)

    await router.generate_structured(
        system_prompt="sys", user_prompt="anything", schema=ChunkExtraction
    )

    assert breaker.allow_request() is True  # still closed


async def test_transient_failure_does_open_the_breaker() -> None:
    fast = FakeLLMGateway()
    fast.should_fail = True
    fast.failure_kind = LLMFailureKind.TRANSIENT
    capable = FakeLLMGateway()
    capable.default_response = {"named_insured": "Rescued By Capable Tier"}
    breaker = _tight_breaker()
    router = RoutingLLMGateway(fast=fast, capable=capable, fast_breaker=breaker)

    await router.generate_structured(
        system_prompt="sys", user_prompt="anything", schema=ChunkExtraction
    )

    assert breaker.allow_request() is False  # now open


async def test_capable_breaker_open_fails_fast_with_no_call_attempted() -> None:
    fast = FakeLLMGateway()
    fast.default_response = {"named_insured": "Fast Tier Corp"}
    capable = FakeLLMGateway()
    router = RoutingLLMGateway(fast=fast, capable=capable, capable_breaker=_tight_breaker())
    router._capable_breaker.record_failure()  # opens it

    with pytest.raises(LLMGenerationError) as exc_info:
        await router.generate_structured(
            system_prompt="sys",
            user_prompt="anything",
            schema=ChunkExtraction,
            complexity=TaskComplexity.COMPLEX,
        )

    assert capable.calls == []  # never even attempted
    assert exc_info.value.kind == LLMFailureKind.TRANSIENT
