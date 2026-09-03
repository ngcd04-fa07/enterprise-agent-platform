"""Tests the real Ollama-served model, not a fake — unlike the HTTP-level
extraction tests (which use FakeLLMGateway for speed/determinism, see
fake_llm_gateway.py), these confirm OllamaGateway actually produces valid,
schema-conforming structured output from a real local model. Skips
cleanly if Ollama isn't reachable, matching the project's DB-skip and
fastembed-skip patterns rather than failing the suite.
"""

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from pydantic import BaseModel

from app.core.config import get_settings
from app.llm_gateway.ollama_gateway import OllamaGateway


@pytest_asyncio.fixture(scope="module")
async def gateway() -> AsyncIterator[OllamaGateway]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            await client.get(f"{settings.ollama_base_url}/api/version")
    except httpx.HTTPError as exc:
        pytest.skip(f"Ollama not reachable at {settings.ollama_base_url}: {exc}")

    yield OllamaGateway(base_url=settings.ollama_base_url, model=settings.ollama_model)


class _NameAndDate(BaseModel):
    company_name: str | None = None
    effective_date: str | None = None


async def test_extracts_present_fields_from_real_text(gateway: OllamaGateway) -> None:
    result = await gateway.generate_structured(
        system_prompt=(
            "Extract the requested fields from the given text. Only use "
            "information explicitly present in the text; use null for "
            "anything not stated."
        ),
        user_prompt=(
            "This is a submission from Acme Roofing Co. requesting coverage effective 2026-01-01."
        ),
        schema=_NameAndDate,
    )

    assert result.company_name is not None
    assert "Acme" in result.company_name
    assert result.effective_date is not None
    assert "2026" in result.effective_date


async def test_returns_null_for_fields_absent_from_the_text(gateway: OllamaGateway) -> None:
    result = await gateway.generate_structured(
        system_prompt=(
            "Extract the requested fields from the given text. Only use "
            "information explicitly present in the text; use null for "
            "anything not stated."
        ),
        user_prompt="The weather today is sunny with a light breeze.",
        schema=_NameAndDate,
    )

    assert result.company_name is None
    assert result.effective_date is None
