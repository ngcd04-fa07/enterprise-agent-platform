"""Seeds one fixed, public demo account with a realistic-but-entirely-
synthetic underwriting submission — the only data a public demo
deployment (Settings.demo_mode=True) is meant to expose. Idempotent: if
the demo account already exists, does nothing rather than creating a
second copy.

Runs every real pipeline (upload -> ingestion -> extraction -> triage)
against whatever storage/embedding/LLM backends the environment is
actually configured for (app/storage/factory.py, app/embeddings/factory.py,
app/llm_gateway/factory.py) — the demo deployment's own S3-compatible
storage and hosted LLM gateway, or local filesystem/Ollama in dev. This
is not test data with a fake gateway; it's the real system, run once.

DEMO_ACCOUNT_EMAIL/DEMO_ACCOUNT_PASSWORD are intentionally public — this
is the one account a public demo deployment's login page hands out,
scoped to synthetic data only and protected by Settings.demo_mode's
rate limits (see app/security/demo_guard.py), not by secrecy.

Usage (from apps/api, with its venv active, and DEMO_MODE-appropriate
env vars set for whichever backends this environment targets):
    DATABASE_URL=... SESSION_SECRET=... python3 scripts/seed_demo_data.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.embeddings.factory import get_embedding_provider  # noqa: E402
from app.llm_gateway.factory import get_llm_gateway  # noqa: E402
from app.repositories.user_repository import UserRepository  # noqa: E402
from app.services.agent_service import AgentService  # noqa: E402
from app.services.auth_service import AuthService  # noqa: E402
from app.services.document_service import DocumentService  # noqa: E402
from app.services.extraction_service import ExtractionService  # noqa: E402
from app.services.ingestion_service import IngestionService  # noqa: E402
from app.services.submission_service import SubmissionService  # noqa: E402
from app.storage.factory import get_object_storage  # noqa: E402

DEMO_ACCOUNT_EMAIL = "demo@example.com"
DEMO_ACCOUNT_PASSWORD = "underwriting-demo-2026"  # noqa: S105 — intentionally public, see module docstring
DEMO_ORGANISATION_NAME = "Meridian Risk Partners (Demo)"
DEMO_SUBMISSION_TITLE = "Riverside Bakery Co. — Property & Casualty Renewal"


def _build_pdf(pages: list[list[str]]) -> bytes:
    """Hand-built, minimally valid PDF with real extractable text per
    page — same technique as tests/pdf_fixtures.py (no PDF-authoring
    library is a project dependency), extended to lay out several lines
    per page instead of one, since these pages are meant to actually be
    opened and read in the demo, not just parsed.
    """
    num_pages = len(pages)
    kids = " ".join(f"{3 + 3 * i} 0 R" for i in range(num_pages))
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {num_pages} >>".encode(),
    ]

    for i, lines in enumerate(pages):
        font_obj_num = 4 + 3 * i
        content_obj_num = 5 + 3 * i
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/Resources << /Font << /F1 {font_obj_num} 0 R >> >> "
                f"/MediaBox [0 0 612 792] /Contents {content_obj_num} 0 R >>"
            ).encode()
        )
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        parts = ["BT", "/F1 12 Tf", "100 720 Td", "14 TL"]
        for line_index, line in enumerate(lines):
            escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            if line_index > 0:
                parts.append("T*")
            parts.append(f"({escaped}) Tj")
        parts.append("ET")
        stream = "\n".join(parts).encode()
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )

    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for idx, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{idx} 0 obj\n".encode() + obj + b"\nendobj\n"

    xref_offset = len(pdf)
    n = len(objects) + 1
    pdf += f"xref\n0 {n}\n".encode()
    pdf += b"0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return pdf


def _application_pdf() -> bytes:
    return _build_pdf(
        [
            [
                "COMMERCIAL INSURANCE APPLICATION",
                "",
                "Named Insured: Riverside Bakery Co.",
                "Business Description: Retail and wholesale bakery, three storefronts",
                "and one commercial kitchen/distribution facility.",
                "Requested Effective Date: 2026-11-01",
                "Requested Coverage Limit: $2,000,000 per occurrence",
            ],
            [
                "COMMERCIAL INSURANCE APPLICATION (continued)",
                "",
                "Years in operation: 12",
                "Number of employees: 34",
                "Primary location: 118 Riverside Ave, Portland, OR",
                "No prior insurer non-renewals or cancellations reported.",
            ],
        ]
    )


def _financials_pdf() -> bytes:
    return _build_pdf(
        [
            [
                "FINANCIAL SUMMARY — RIVERSIDE BAKERY CO.",
                "",
                "Fiscal year ending: 2025-12-31",
                "Annual revenue: $4,850,000",
                "Net operating margin: 8.2%",
                "No outstanding litigation or liens reported.",
            ]
        ]
    )


def _loss_history_pdf() -> bytes:
    return _build_pdf(
        [
            [
                "LOSS HISTORY SUMMARY — PRIOR 5 POLICY YEARS",
                "",
                "2021: One small kitchen-fire claim, $12,400 paid, closed.",
                "2022: No claims.",
                "2023: No claims.",
                "2024: One slip-and-fall claim, $8,100 paid, closed.",
                "2025: No claims to date.",
                "",
                "Total incurred over period: $20,500 across 2 claims.",
            ]
        ]
    )


async def main() -> None:
    settings = get_settings()
    sessionmaker = get_sessionmaker()
    storage = get_object_storage()
    embeddings = get_embedding_provider()
    llm = get_llm_gateway()

    async with sessionmaker() as db:
        existing = await UserRepository(db).get_by_email(DEMO_ACCOUNT_EMAIL)
        if existing is not None:
            print(f"Demo account {DEMO_ACCOUNT_EMAIL!r} already exists — nothing to seed.")
            return

        auth_result = await AuthService(db, settings).register(
            email=DEMO_ACCOUNT_EMAIL,
            full_name="Demo Underwriter",
            password=DEMO_ACCOUNT_PASSWORD,
            organisation_name=DEMO_ORGANISATION_NAME,
        )
        await db.commit()
        if auth_result.session.active_organisation_id is None:
            # Unreachable in practice — AuthService.register always sets an
            # active organisation for a brand-new registration. A real
            # check, not an assert, so a future change to that behavior
            # fails loudly here instead of as a confusing None downstream.
            raise RuntimeError("newly registered demo user has no active organisation")
        organisation_id = auth_result.session.active_organisation_id
        user_id = auth_result.user.id
        print(f"Created demo organisation {organisation_id} and user {user_id}.")

        submission = await SubmissionService(db).create_submission(
            organisation_id=organisation_id,
            created_by_user_id=user_id,
            title=DEMO_SUBMISSION_TITLE,
        )
        await db.commit()
        print(f"Created demo submission {submission.id}.")

        for filename, pdf_bytes in [
            ("application.pdf", _application_pdf()),
            ("financial_summary.pdf", _financials_pdf()),
            ("loss_history.pdf", _loss_history_pdf()),
        ]:
            document = await DocumentService(db, storage).upload_document(
                organisation_id=organisation_id,
                submission_id=submission.id,
                filename=filename,
                content_type="application/pdf",
                data=pdf_bytes,
                max_upload_size_bytes=settings.max_upload_size_bytes,
            )
            document = await IngestionService(db, storage, embeddings, settings).ingest_document(
                document
            )
            await db.commit()
            print(f"Uploaded and ingested {filename} (status={document.status.value}).")

        extraction_run = await ExtractionService(db, llm, settings).extract_submission(
            organisation_id=organisation_id, submission_id=submission.id
        )
        await db.commit()
        print(f"Extraction run finished with status={extraction_run.status.value}.")

        agent_run = await AgentService(db, llm).run_triage(
            organisation_id=organisation_id,
            submission_id=submission.id,
            created_by_user_id=user_id,
        )
        await db.commit()
        recommendation = agent_run.recommendation.value if agent_run.recommendation else None
        print(
            f"Triage run finished with status={agent_run.status.value}, "
            f"recommendation={recommendation}."
        )

    print()
    print("Demo account ready:")
    print(f"  email:    {DEMO_ACCOUNT_EMAIL}")
    print(f"  password: {DEMO_ACCOUNT_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
