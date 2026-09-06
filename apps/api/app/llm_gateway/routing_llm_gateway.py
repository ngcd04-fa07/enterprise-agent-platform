import logging

from app.llm_gateway.base import (
    LLMFailureKind,
    LLMGateway,
    LLMGenerationError,
    SchemaT,
    TaskComplexity,
)
from app.llm_gateway.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

_DEFAULT_FAILURE_THRESHOLD = 3
_DEFAULT_COOLDOWN_SECONDS = 30.0


class RoutingLLMGateway(LLMGateway):
    """Routes between two underlying gateways behind the same LLMGateway
    interface — callers never see which one actually ran (see
    docs/architecture.md, model routing decision). Two distinct reasons
    to route, addressing two distinct real problems:

    1. Static, task-declared routing: `complexity=COMPLEX` always goes to
       `capable`. Stage 12/15 found that a small model's *reasoning*
       quality (not just its factual recall) is where it's weakest — the
       triage summary and the eval judge both need that reasoning, so
       they ask for it explicitly, while extraction's high-volume
       per-chunk calls stay on `fast` by default (cost/latency, not
       reliability — see extraction's own SIMPLE default).
    2. Failure escalation: if `fast` can't produce valid output at all
       (LLMGenerationError — model unreachable, or genuinely malformed
       output even after its own bounded retry), try `capable` once
       before giving up. This is a resilience behavior for outages/
       malformed output, not a fix for "the fast model returned null for
       a field it should have found" — a null isn't a failure this layer
       can see, only the eval harness can (see evals/extraction/).

    Stage 19 hardening: one `CircuitBreaker` per tier (in-memory,
    per-process — see CircuitBreaker's docstring for why that's the right
    amount of state for this app's current single-instance deployment).
    Only a `LLMFailureKind.TRANSIENT` failure — a connection problem, a
    timeout, a 5xx — is ever recorded against a breaker; a `CONTENT`
    failure (the model's own output didn't validate) or a `PERMANENT`
    one (a bad request/config) says nothing about the tier's health and
    must never trip it (see LLMFailureKind's docstring) — one bad
    generation must not incorrectly mark an otherwise healthy provider as
    unavailable. When a tier's breaker is open, calls skip it (or, if
    it's the last remaining option, fail immediately) rather than paying
    a full timeout against a tier that's actually down.

    Every call made into `fast` or `capable` carries a `route_reason` —
    reusing the existing tracing architecture (Stage 14/16), not a new
    observability subsystem: `TracingLLMGateway` records it in the call's
    trace `call_metadata`, so *why* a tier was picked is visible after
    the fact, not just *which* tier was picked. Reason codes:

    - `complexity_route_fast` / `complexity_route_capable`: the ordinary,
      no-failure routing decision, keyed only on `complexity`.
    - `fast_breaker_open`: fast's breaker was open, so capable was tried
      without even attempting fast.
    - `fast_failed_escalate_capable`: fast was tried, failed, and capable
      was tried as the escalation.

    One case produces no call at all — capable's own breaker is also
    open, so there is no remaining tier to try. That's logged (a
    `logger.warning`) but not separately traced in `ai_call_traces`: there
    is no underlying `generate_structured` call to attach a trace row to,
    and fabricating one for a call that never happened would misrepresent
    what actually occurred. Practical scope, not an oversight — see
    docs/architecture.md, Stage 19 decision.
    """

    def __init__(
        self,
        *,
        fast: LLMGateway,
        capable: LLMGateway,
        fast_breaker: CircuitBreaker | None = None,
        capable_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._fast = fast
        self._capable = capable
        # Defaults exist for tests/ad-hoc construction convenience only —
        # the real app (see factory.py) always builds explicit breakers
        # from Settings so their thresholds are actually configurable.
        self._fast_breaker = fast_breaker or CircuitBreaker(
            failure_threshold=_DEFAULT_FAILURE_THRESHOLD, cooldown_seconds=_DEFAULT_COOLDOWN_SECONDS
        )
        self._capable_breaker = capable_breaker or CircuitBreaker(
            failure_threshold=_DEFAULT_FAILURE_THRESHOLD, cooldown_seconds=_DEFAULT_COOLDOWN_SECONDS
        )

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        complexity: TaskComplexity = TaskComplexity.SIMPLE,
        route_reason: str | None = None,
    ) -> SchemaT:
        del route_reason  # the router decides its own reason for each call it makes below

        if complexity == TaskComplexity.COMPLEX:
            return await self._call_capable(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                complexity=complexity,
                reason="complexity_route_capable",
            )

        if not self._fast_breaker.allow_request():
            logger.warning("fast-tier circuit open, routing directly to capable tier")
            return await self._call_capable(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                complexity=complexity,
                reason="fast_breaker_open",
            )

        try:
            result = await self._fast.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                complexity=complexity,
                route_reason="complexity_route_fast",
            )
            self._fast_breaker.record_success()
            return result
        except LLMGenerationError as exc:
            if exc.kind == LLMFailureKind.TRANSIENT:
                self._fast_breaker.record_failure()
            logger.warning("fast-tier model failed, escalating to capable tier", exc_info=True)
            return await self._call_capable(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                complexity=complexity,
                reason="fast_failed_escalate_capable",
            )

    async def _call_capable(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        complexity: TaskComplexity,
        reason: str,
    ) -> SchemaT:
        if not self._capable_breaker.allow_request():
            logger.warning(
                "capable-tier circuit also open (reached via %s); failing fast, no fallback left",
                reason,
            )
            raise LLMGenerationError(
                f"capable tier's circuit breaker is open (reached via {reason}); "
                "no fallback tier is available",
                kind=LLMFailureKind.TRANSIENT,
            )

        try:
            result = await self._capable.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                complexity=complexity,
                route_reason=reason,
            )
            self._capable_breaker.record_success()
            return result
        except LLMGenerationError as exc:
            if exc.kind == LLMFailureKind.TRANSIENT:
                self._capable_breaker.record_failure()
            raise
