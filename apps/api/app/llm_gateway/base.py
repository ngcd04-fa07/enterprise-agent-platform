from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMGenerationError(Exception):
    """Raised when the model can't be reached, or its output can't be
    coerced into the requested schema even after a bounded retry. Callers
    must not silently substitute a default or partial value on this — see
    CLAUDE.md: "invalid output fails predictably or retries through a
    controlled path — never silently coerced."
    """


class LLMGateway(ABC):
    """Provider-neutral interface for schema-constrained structured
    generation. Business logic depends only on this — never on a specific
    provider SDK or HTTP API (see CLAUDE.md: "no hidden provider
    coupling"). The only implementation right now is a local Ollama model;
    a hosted API provider could be swapped in behind the same interface
    later without touching callers.
    """

    @abstractmethod
    async def generate_structured(
        self, *, system_prompt: str, user_prompt: str, schema: type[SchemaT]
    ) -> SchemaT:
        """Runs one generation constrained to `schema`'s JSON shape and
        returns a validated instance of it. Raises LLMGenerationError
        (never returns a partially-valid or coerced result) if the model
        is unreachable or its output can't be validated against the
        schema after a bounded retry.
        """
        ...
