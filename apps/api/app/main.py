import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.health import router as health_router
from app.api.routes.retrieval import router as retrieval_router
from app.api.routes.submissions import router as submissions_router
from app.core.config import get_settings
from app.embeddings.factory import get_embedding_provider

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Load the embedding model once at startup, not on the first request —
    # otherwise whoever happens to upload/search first pays a multi-second
    # cold-start cost (model download on first-ever run, or just loading
    # weights into memory afterward) that nobody else sees.
    await asyncio.to_thread(get_embedding_provider)
    yield


app = FastAPI(title="Enterprise Agent Platform API", lifespan=lifespan)

if settings.api_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(IntegrityError)
async def _integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    # A constraint violation (unique/FK) reaching here means a route didn't
    # already translate it to a specific error — without this, Starlette's
    # default handler would still hide the raw exception from the client
    # (no debug leak either way), but as a bare, unhelpful 500. No current
    # route can trigger this via ordinary use (all are checked beforehand),
    # but it's a real gap for a future write endpoint that races a unique
    # constraint (e.g. a membership invite) before it grows its own
    # specific handling.
    del request
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "The request conflicts with existing data."},
    )


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(submissions_router)
app.include_router(documents_router)
app.include_router(retrieval_router)
