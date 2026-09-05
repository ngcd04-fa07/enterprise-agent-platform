"""Prints a summary of recorded AI call traces (app/observability) —
count, average latency, and error rate per call type, plus the most
recent failures if any. A quick way to actually look at AI-system health
without building a dashboard or a new HTTP endpoint for it yet — see
docs/architecture.md, Stage 14 decision, for why this data isn't exposed
through the tenant-facing API in this first version.

Usage (from apps/api, with its venv active):
    DATABASE_URL=... SESSION_SECRET=... python3 scripts/ai_traces_report.py
"""

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

# Running this file directly (not via `python3 -m`) puts scripts/ itself on
# sys.path, not apps/api/ — don't rely on the editable install's own path
# entry being present too; make it explicit.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import get_sessionmaker  # noqa: E402
from app.models.ai_call_trace import AICallStatus, AICallTrace  # noqa: E402

_RECENT_FAILURES_LIMIT = 5


async def main() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        all_traces = (await session.execute(select(AICallTrace))).scalars().all()

        by_type: dict[str, list[AICallTrace]] = defaultdict(list)
        for trace in all_traces:
            by_type[trace.call_type.value].append(trace)

        print(f"{'Call type':<20} {'Count':<8} {'Avg latency (ms)':<20} {'Error rate':<10}")
        for call_type, traces in sorted(by_type.items()):
            count = len(traces)
            avg_latency_ms = sum(t.latency_ms for t in traces) / count
            failure_count = sum(1 for t in traces if t.status == AICallStatus.FAILURE)
            print(
                f"{call_type:<20} {count:<8} {avg_latency_ms:<20.1f} {failure_count / count:<10.1%}"
            )
        if not by_type:
            print("(no traces recorded yet)")

        failures = sorted(
            (t for t in all_traces if t.status == AICallStatus.FAILURE),
            key=lambda t: t.created_at,
            reverse=True,
        )[:_RECENT_FAILURES_LIMIT]
        if failures:
            print(f"\nMost recent {len(failures)} failures:")
            for trace in failures:
                print(
                    f"  [{trace.created_at.isoformat()}] {trace.call_type.value} "
                    f"({trace.provider}/{trace.model}): {trace.error_message}"
                )


if __name__ == "__main__":
    asyncio.run(main())
