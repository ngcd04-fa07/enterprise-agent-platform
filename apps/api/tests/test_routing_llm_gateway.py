import pytest

from app.llm_gateway.base import LLMGenerationError, TaskComplexity
from app.llm_gateway.routing_llm_gateway import RoutingLLMGateway
from app.schemas.extraction import ChunkExtraction
from tests.fake_llm_gateway import FakeLLMGateway


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
