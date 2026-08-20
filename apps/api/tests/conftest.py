import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session

import app.models  # noqa: F401  registers all models on Base.metadata
from app.core.config import get_settings
from app.models.base import Base

# Matches the docker-compose / .env.example local dev defaults, so
# `docker compose up -d db && pytest` just works without exporting anything.
# Settings has no defaults for these (see app.core.config) so tests need
# them present before app.main is imported anywhere.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://enterprise_agent:enterprise_agent@localhost:5432/enterprise_agent",
)
os.environ.setdefault("SESSION_SECRET", "test-secret-do-not-use-in-production")


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """Session-scoped engine against a real Postgres. Skips (not fails) the
    DB-dependent tests that depend on this fixture when no Postgres is
    reachable, so the suite stays runnable in environments without Docker
    while still exercising real Postgres wherever it's available (local
    dev with `docker compose up -d db`, or CI's Postgres service).
    """
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres not reachable at {settings.database_url}: {exc}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Each test runs inside its own transaction, rolled back afterwards —
    tests never see each other's writes and never need manual cleanup.
    """
    connection = await db_engine.connect()
    transaction = await connection.begin()
    sessionmaker = async_sessionmaker(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    session = sessionmaker()

    # join_transaction_mode="create_savepoint" backs the session with a SAVEPOINT
    # on top of the outer connection-level transaction. Any rollback of that
    # SAVEPOINT (e.g. a repository test asserting a flush raises IntegrityError)
    # ends it — without restarting it here, the connection is left without an
    # active SAVEPOINT and later statements on it (including this fixture's own
    # teardown, and every subsequent test sharing the session-scoped engine) fail
    # with asyncpg InterfaceError. This is the SAVEPOINT-restart listener from
    # SQLAlchemy's documented external-transaction test recipe.
    @event.listens_for(session.sync_session, "after_transaction_end")
    def _restart_savepoint(sync_session: Session, sync_transaction: object) -> None:
        if connection.closed:
            return
        if not connection.sync_connection.in_nested_transaction():  # type: ignore[union-attr]
            connection.sync_connection.begin_nested()  # type: ignore[union-attr]

    yield session

    await session.close()
    if transaction.is_active:
        await transaction.rollback()
    await connection.close()
