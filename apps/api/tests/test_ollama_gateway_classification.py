"""Tests OllamaGateway's failure classification and retry policy (Stage
19) — deterministically, via httpx.MockTransport (built into httpx
already, no new dependency, no real Ollama needed) rather than the real
model tests in test_ollama_gateway.py. Verifies the two explicit
constraints this stage was built around: a breaker-worthy transport/5xx
failure is classified TRANSIENT and retried; a permanent 4xx/bad-request
failure is classified PERMANENT and NOT retried (retrying an identical
bad request can't succeed); the model's own malformed output is
classified CONTENT and retried (generation is stochastic, unlike a
config bug) but must never be mistaken for a provider-health signal.
"""

import httpx
import pytest
from pydantic import BaseModel

from app.llm_gateway.base import LLMFailureKind, LLMGenerationError
from app.llm_gateway.ollama_gateway import OllamaGateway


class _Simple(BaseModel):
    value: str | None = None


def _success_response() -> httpx.Response:
    return httpx.Response(200, json={"message": {"content": '{"value": "ok"}'}})


async def test_5xx_is_transient_and_retried_up_to_max_attempts() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503)

    gateway = OllamaGateway(
        base_url="http://fake",
        model="fake-model",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMGenerationError) as exc_info:
        await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert exc_info.value.kind == LLMFailureKind.TRANSIENT
    assert exc_info.value.attempts == 2
    assert call_count == 2


async def test_4xx_is_permanent_and_not_retried() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(404)

    gateway = OllamaGateway(
        base_url="http://fake",
        model="fake-model",
        max_attempts=3,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMGenerationError) as exc_info:
        await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert exc_info.value.kind == LLMFailureKind.PERMANENT
    assert exc_info.value.attempts == 1
    # The whole point: a bad request must fail fast, not exhaust every
    # configured attempt on a request that can't ever succeed.
    assert call_count == 1


async def test_connection_error_is_classified_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    gateway = OllamaGateway(
        base_url="http://fake",
        model="fake-model",
        max_attempts=1,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMGenerationError) as exc_info:
        await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert exc_info.value.kind == LLMFailureKind.TRANSIENT


async def test_malformed_model_output_is_content_and_still_retried() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"message": {"content": "not valid json{{"}})

    gateway = OllamaGateway(
        base_url="http://fake",
        model="fake-model",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMGenerationError) as exc_info:
        await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert exc_info.value.kind == LLMFailureKind.CONTENT
    # Content failures ARE retried (generation is stochastic) — just never
    # counted against a circuit breaker (see RoutingLLMGateway).
    assert call_count == 2


async def test_configurable_max_attempts_is_actually_respected() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503)

    gateway = OllamaGateway(
        base_url="http://fake",
        model="fake-model",
        max_attempts=5,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMGenerationError):
        await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert call_count == 5


async def test_succeeds_on_retry_after_one_transient_failure() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503)
        return _success_response()

    gateway = OllamaGateway(
        base_url="http://fake",
        model="fake-model",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert result.value == "ok"
