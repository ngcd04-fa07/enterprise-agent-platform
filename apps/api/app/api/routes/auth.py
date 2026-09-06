from datetime import datetime
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import SESSION_COOKIE_NAME, get_current_session, get_current_user, require_csrf
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models.session import Session as SessionModel
from app.models.user import User
from app.repositories.membership_repository import OrganisationMembershipRepository
from app.schemas.auth import (
    AuthResponse,
    CurrentUserResponse,
    LoginRequest,
    MembershipRead,
    RegisterRequest,
    UserRead,
)
from app.security.rate_limiter import InMemoryRateLimiter, RateLimitExceeded
from app.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# Deliberately keyed on `request.client.host` — the ASGI transport's own
# peer address — not on X-Forwarded-For/X-Real-IP. Those headers are
# entirely client-controlled unless a trusted reverse proxy sets (and a
# trusted boundary strips any client-supplied copy of) them; this project
# has no reverse proxy in its actual deployment topology yet (Stage 21),
# so trusting such a header today would let any client simply forge it
# and pick whatever rate-limit bucket it likes, defeating the limiter
# entirely. Revisit this the moment a real reverse proxy with a defined
# trusted-hop count exists.
#
# Two independent buckets for login, never a single one keyed on the
# identifier alone: a per-IP bucket throttles one source's overall
# attempt volume regardless of which account it targets, and a separate
# per-(IP, identifier) bucket slows a focused attempt against one account
# from one source — keying on the identifier by itself would let an
# attacker lock a *victim* out just by repeatedly guessing their email
# from anywhere, which is explicitly not the goal (rate-limit, don't
# lock out). Both are sliding-window limiters, so the limit always lifts
# on its own once the window passes — no permanent lockout, no manual
# reset. In-memory and per-process, same as Stage 19's circuit breakers —
# correct for this app's current single-instance deployment; a shared/
# distributed limiter is a Stage 21 concern if multi-replica ever needs
# it (see docs/architecture.md, Stage 20 decision).
@lru_cache
def _login_ip_limiter() -> InMemoryRateLimiter:
    settings = get_settings()
    return InMemoryRateLimiter(
        max_attempts=settings.login_rate_limit_per_ip_max_attempts,
        window_seconds=settings.login_rate_limit_per_ip_window_seconds,
    )


@lru_cache
def _login_identifier_limiter() -> InMemoryRateLimiter:
    settings = get_settings()
    return InMemoryRateLimiter(
        max_attempts=settings.login_rate_limit_per_identifier_max_attempts,
        window_seconds=settings.login_rate_limit_per_identifier_window_seconds,
    )


@lru_cache
def _register_ip_limiter() -> InMemoryRateLimiter:
    settings = get_settings()
    return InMemoryRateLimiter(
        max_attempts=settings.register_rate_limit_per_ip_max_attempts,
        window_seconds=settings.register_rate_limit_per_ip_window_seconds,
    )


def _client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _enforce_rate_limit(limiter: InMemoryRateLimiter, *, key: str) -> None:
    try:
        limiter.check(key)
    except RateLimitExceeded as exc:
        retry_after = int(exc.retry_after_seconds) + 1
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        ) from exc


def _set_session_cookie(
    response: Response, *, token: str, settings: Settings, expires_at: datetime
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.environment != "development",
        samesite="lax",
        expires=expires_at,
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    _enforce_rate_limit(_register_ip_limiter(), key=_client_ip(request))
    try:
        result = await AuthService(db, settings).register(
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password,
            organisation_name=payload.organisation_name,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered") from exc

    _set_session_cookie(
        response, token=result.raw_token, settings=settings, expires_at=result.session.expires_at
    )
    return AuthResponse(
        user=UserRead.model_validate(result.user),
        csrf_token=result.session.csrf_token,
        active_organisation_id=result.session.active_organisation_id,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
    client_ip = _client_ip(request)
    _enforce_rate_limit(_login_ip_limiter(), key=client_ip)
    _enforce_rate_limit(_login_identifier_limiter(), key=f"{client_ip}:{payload.email.lower()}")
    try:
        result = await AuthService(db, settings).login(
            email=payload.email, password=payload.password
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password") from exc

    _set_session_cookie(
        response, token=result.raw_token, settings=settings, expires_at=result.session.expires_at
    )
    return AuthResponse(
        user=UserRead.model_validate(result.user),
        csrf_token=result.session.csrf_token,
        active_organisation_id=result.session.active_organisation_id,
    )


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
async def logout(
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    session_row: Annotated[SessionModel, Depends(get_current_session)],
) -> None:
    await AuthService(db, settings).logout(session_row)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


@router.get("/me", response_model=CurrentUserResponse)
async def me(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    user: Annotated[User, Depends(get_current_user)],
    session_row: Annotated[SessionModel, Depends(get_current_session)],
) -> CurrentUserResponse:
    memberships = await OrganisationMembershipRepository(db).list_for_user(user.id)
    return CurrentUserResponse(
        user=UserRead.model_validate(user),
        csrf_token=session_row.csrf_token,
        active_organisation_id=session_row.active_organisation_id,
        memberships=[MembershipRead.model_validate(m) for m in memberships],
    )
