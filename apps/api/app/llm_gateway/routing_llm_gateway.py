import logging

from app.llm_gateway.base import LLMGateway, LLMGenerationError, SchemaT, TaskComplexity

logger = logging.getLogger(__name__)


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
    """

    def __init__(self, *, fast: LLMGateway, capable: LLMGateway) -> None:
        self._fast = fast
        self._capable = capable

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema: type[SchemaT],
        complexity: TaskComplexity = TaskComplexity.SIMPLE,
    ) -> SchemaT:
        if complexity == TaskComplexity.COMPLEX:
            return await self._capable.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                complexity=complexity,
            )

        try:
            return await self._fast.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                complexity=complexity,
            )
        except LLMGenerationError:
            logger.warning("fast-tier model failed, escalating to capable tier", exc_info=True)
            return await self._capable.generate_structured(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                complexity=complexity,
            )
