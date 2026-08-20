import logging
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped session: commits once the endpoint returns without
    raising, rolls back otherwise. FastAPI caches this per request, so every
    dependency/route handler sharing it via Depends(get_db_session) sees the
    same session and this commit/rollback runs exactly once.
    """
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def ping_database() -> bool:
    """Best-effort DB reachability check for the health endpoint.

    Broad exception handling is intentional here: this is a boundary call
    against an external system and the caller only needs a reachable/
    unreachable signal, not a specific failure mode. The exception is
    logged, not swallowed silently.
    """
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("database ping failed", exc_info=True)
        return False
