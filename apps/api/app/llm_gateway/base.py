import enum
from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMFailureKind(enum.StrEnum):
    """Why a `generate_structured` call failed — distinguished so a
    caller like `RoutingLLMGateway` (Stage 19) can react differently to
    each kind, instead of treating every `LLMGenerationError` as evidence
    the provider itself is unhealthy.

    Only `TRANSIENT` is a signal about the *provider's* health (worth
    tripping a circuit breaker over, worth retrying). `PERMANENT` and
    `CONTENT` are not: a malformed request or one bad generation doesn't
    mean the next call will fail too, and treating it as if it does would
    let one bad response incorrectly mark an otherwise healthy provider
    as unavailable.
    """

    # Connection refused, timeout, 5xx/service-unavailable — plausibly
    # transient. Worth retrying (the same request might succeed a moment
    # later) and worth counting toward a circuit breaker (repeated
    # transient failures are a real signal the provider is unhealthy).
    TRANSIENT = "transient"
    # A 4xx-shaped failure — a bad request, an unknown model name, a
    # malformed application-side configuration. Retrying the identical
    # request won't help (it's deterministic, not transient), and it says
    # nothing about the provider's health — it's our bug, not theirs.
    PERMANENT = "permanent"
    # The provider responded, but its content didn't parse as JSON or
    # didn't validate against the requested schema. The provider itself
    # is healthy — generation is stochastic, so a retry is still worth
    # it — but this must never trip a circuit breaker; see this class's
    # docstring.
    CONTENT = "content"


class LLMGenerationError(Exception):
    """Raised when the model can't be reached, or its output can't be
    coerced into the requested schema even after a bounded retry. Callers
    must not silently substitute a default or partial value on this — see
    CLAUDE.md: "invalid output fails predictably or retries through a
    controlled path — never silently coerced."

    Carries `kind` (see LLMFailureKind) and `attempts` (how many times
    the underlying gateway actually tried before giving up) so a caller
    with fallback/breaker policy — RoutingLLMGateway (Stage 19) — can
    make an informed decision instead of treating every failure alike,
    and so a failure trace's `call_metadata` reflects a multi-attempt
    call honestly rather than looking identical to a single clean try.
    """

    def __init__(
        self,
        message: str,
        *,
        kind: LLMFailureKind = LLMFailureKind.TRANSIENT,
        attempts: int = 1,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.attempts = attempts


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
        route_reason: str | None = None,
    ) -> SchemaT:
        """Runs one generation constrained to `schema`'s JSON shape and
        returns a validated instance of it. Raises LLMGenerationError
        (never returns a partially-valid or coerced result) if the model
        is unreachable or its output can't be validated against the
        schema after a bounded retry. `complexity` is only meaningful to
        a gateway that has more than one underlying model to choose from
        (see RoutingLLMGateway) — a single-model gateway is free to
        ignore it, which is exactly what OllamaGateway does.

        `route_reason` (Stage 19) is a caller-supplied annotation of why
        *this particular gateway* was chosen to serve the call — set by
        RoutingLLMGateway on the calls it makes into its underlying
        tiers, e.g. "complexity_route_fast" or "fast_failed_escalate_
        capable" (see RoutingLLMGateway's docstring for the full set).
        Not meaningful as an input to RoutingLLMGateway itself (it
        decides its own reason for whatever it does next) or to a
        single-model gateway with nothing to route between — both are
        free to ignore it, same as `complexity`. A `TracingLLMGateway`
        wrapping the destination gateway records it in the call's trace
        `call_metadata` when present, so *why* a tier was picked is
        visible after the fact, not just *which* tier was picked.
        """
        ...
