"""Tests GroqGateway's failure classification and retry policy,
deterministically, via httpx.MockTransport — no real Groq account or
network needed. Mirrors test_ollama_gateway_classification.py's shape,
plus the one real difference this gateway has to get right: 429 (a
hosted API's actual rate limit) must classify TRANSIENT, not PERMANENT
like a generic 4xx would.
"""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.llm_gateway.base import LLMFailureKind, LLMGenerationError
from app.llm_gateway.groq_gateway import GroqGateway


class _Simple(BaseModel):
    value: str | None = None


def _success_response() -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": '{"value": "ok"}'}}]})


async def test_5xx_is_transient_and_retried_up_to_max_attempts() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(503)

    gateway = GroqGateway(
        api_key="fake-key",
        model="fake-model",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMGenerationError) as exc_info:
        await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert exc_info.value.kind == LLMFailureKind.TRANSIENT
    assert exc_info.value.attempts == 2
    assert call_count == 2


async def test_429_rate_limit_is_transient_not_permanent() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(429)

    gateway = GroqGateway(
        api_key="fake-key",
        model="fake-model",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMGenerationError) as exc_info:
        await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert exc_info.value.kind == LLMFailureKind.TRANSIENT
    # Unlike a generic 4xx, a rate limit is worth a real retry.
    assert call_count == 2


async def test_401_bad_api_key_is_permanent_and_not_retried() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(401)

    gateway = GroqGateway(
        api_key="fake-key",
        model="fake-model",
        max_attempts=3,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMGenerationError) as exc_info:
        await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert exc_info.value.kind == LLMFailureKind.PERMANENT
    assert exc_info.value.attempts == 1
    assert call_count == 1


async def test_connection_error_is_classified_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    gateway = GroqGateway(
        api_key="fake-key",
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
        return httpx.Response(200, json={"choices": [{"message": {"content": "not valid json{{"}}]})

    gateway = GroqGateway(
        api_key="fake-key",
        model="fake-model",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(LLMGenerationError) as exc_info:
        await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert exc_info.value.kind == LLMFailureKind.CONTENT
    assert call_count == 2


async def test_succeeds_on_retry_after_one_transient_failure() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(503)
        return _success_response()

    gateway = GroqGateway(
        api_key="fake-key",
        model="fake-model",
        max_attempts=2,
        transport=httpx.MockTransport(handler),
    )

    result = await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    assert result.value == "ok"


async def test_request_carries_bearer_auth_and_json_object_response_format() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return _success_response()

    gateway = GroqGateway(
        api_key="fake-key-value",
        model="fake-model",
        transport=httpx.MockTransport(handler),
    )

    await gateway.generate_structured(system_prompt="s", user_prompt="u", schema=_Simple)

    request = captured["request"]
    assert request.headers["authorization"] == "Bearer fake-key-value"
    body = json.loads(request.content)
    assert body["response_format"] == {"type": "json_object"}
    assert body["model"] == "fake-model"
