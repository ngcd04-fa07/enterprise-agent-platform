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
from app.embeddings.base import EmbeddingProvider
from app.llm_gateway.base import LLMGateway
from app.models.base import Base
from app.storage.base import ObjectStorage
from app.storage.filesystem import FilesystemObjectStorage
from tests.fake_embeddings import FakeEmbeddingProvider
from tests.fake_llm_gateway import FakeLLMGateway

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


@pytest.fixture(autouse=True)
def _reset_rate_limiters() -> None:
    """The login/register rate limiters (Stage 20) are process-wide
    `@lru_cache` singletons — by design, so their in-memory state
    actually persists across requests within one running process. That's
    exactly wrong for a test *suite*, though: many tests each register/
    log in through the same ASGITransport test client, which reports the
    same client IP for all of them, so without a reset every test session
    would eventually trip the real limiter after enough tests ran,
    regardless of which specific test happened to be running. Clearing
    the cache before each test forces a fresh limiter instance (with a
    fresh, empty bucket) the next time a route calls the factory
    function, isolating tests from each other's request volume.
    """
    from app.api.routes.auth import (
        _login_identifier_limiter,
        _login_ip_limiter,
        _register_ip_limiter,
    )

    _login_ip_limiter.cache_clear()
    _login_identifier_limiter.cache_clear()
    _register_ip_limiter.cache_clear()


@pytest.fixture
def object_storage(tmp_path: Path) -> ObjectStorage:
    """A throwaway filesystem storage root per test — never the real
    STORAGE_ROOT, so test uploads can't leak into (or be confused with)
    real local dev data.
    """
    return FilesystemObjectStorage(str(tmp_path / "documents"))


@pytest.fixture
def embedding_provider() -> EmbeddingProvider:
    """Deterministic fake, not the real model — see fake_embeddings.py for
    why. Real-model behavior is covered separately in
    test_fastembed_provider.py.
    """
    return FakeEmbeddingProvider()


@pytest.fixture
def llm_gateway() -> LLMGateway:
    """Deterministic fake, not a real Ollama call — see fake_llm_gateway.py
    for why. Real-model behavior is covered separately in
    test_ollama_gateway.py.
    """
    return FakeLLMGateway()


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    object_storage: ObjectStorage,
    embedding_provider: EmbeddingProvider,
    llm_gateway: LLMGateway,
) -> AsyncIterator[AsyncClient]:
    """HTTP-level test client for the FastAPI app, wired to the same
    transactional db_session as the rest of the test (imported lazily so
    app.main — which reads Settings at import time — only loads after the
    env var defaults above are already set).
    """
    from app.db.session import get_db_session
    from app.embeddings.factory import get_embedding_provider
    from app.llm_gateway.factory import get_llm_gateway
    from app.main import app
    from app.storage.factory import get_object_storage

    async def _override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _override_get_db_session
    app.dependency_overrides[get_object_storage] = lambda: object_storage
    app.dependency_overrides[get_embedding_provider] = lambda: embedding_provider
    app.dependency_overrides[get_llm_gateway] = lambda: llm_gateway
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.pop(get_db_session, None)
    app.dependency_overrides.pop(get_object_storage, None)
    app.dependency_overrides.pop(get_embedding_provider, None)
    app.dependency_overrides.pop(get_llm_gateway, None)


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
