import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
from app.storage.base import ObjectStorage
from app.storage.filesystem import FilesystemObjectStorage

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


@pytest.fixture
def object_storage(tmp_path: Path) -> ObjectStorage:
    """A throwaway filesystem storage root per test — never the real
    STORAGE_ROOT, so test uploads can't leak into (or be confused with)
    real local dev data.
    """
    return FilesystemObjectStorage(str(tmp_path / "documents"))


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession, object_storage: ObjectStorage
) -> AsyncIterator[AsyncClient]:
    """HTTP-level test client for the FastAPI app, wired to the same
    transactional db_session as the rest of the test (imported lazily so
    app.main — which reads Settings at import time — only loads after the
    env var defaults above are already set).
    """
    from app.db.session import get_db_session
    from app.main import app
    from app.storage.factory import get_object_storage

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_object_storage] = lambda: object_storage
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_object_storage, None)


@pytest_asyncio.fixture
async def second_client(client: AsyncClient) -> AsyncIterator[AsyncClient]:
    """A second HTTP client sharing `client`'s dependency override (same
    transactional db_session) but with its own cookie jar — for tests that
    need two independently-authenticated users in one test, e.g. proving
    one organisation's session can't act on another's data.
    """
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
