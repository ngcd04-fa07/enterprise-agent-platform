import enum
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


class TaskComplexity(enum.StrEnum):
    """A caller-supplied hint, not a measurement of the actual prompt —
    the caller (extraction, triage synthesis, an eval judge) knows
    whether the task is high-volume/routine or reasoning-heavy; nothing
    below it could infer that from the text alone without adding a real
    classification step of its own. See RoutingLLMGateway for what a
    gateway is free to do with this.
    """

    SIMPLE = "simple"
    COMPLEX = "complex"


class LLMGateway(ABC):
    """Provider-neutral interface for schema-constrained structured
    generation. Business logic depends only on this — never on a specific
    provider SDK or HTTP API (see CLAUDE.md: "no hidden provider
    coupling"). Implementations: a local Ollama model (one size), and
    RoutingLLMGateway, which routes between two Ollama model sizes behind
    this same interface — a hosted API provider could be swapped in
    behind it later without touching callers either way.
    """

    @abstractmethod
    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        complexity: TaskComplexity = TaskComplexity.SIMPLE,
    ) -> SchemaT:
        """Runs one generation constrained to `schema`'s JSON shape and
        returns a validated instance of it. Raises LLMGenerationError
        (never returns a partially-valid or coerced result) if the model
        is unreachable or its output can't be validated against the
        schema after a bounded retry. `complexity` is only meaningful to
        a gateway that has more than one underlying model to choose from
        (see RoutingLLMGateway) — a single-model gateway is free to
        ignore it, which is exactly what OllamaGateway does.
        """
        ...
