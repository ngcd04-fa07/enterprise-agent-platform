import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.tokens import hash_token
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.models.membership import MembershipRole, OrganisationMembership
from app.models.session import Session as SessionModel
from app.models.user import User
from app.repositories.membership_repository import OrganisationMembershipRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository

SESSION_COOKIE_NAME = "session_token"


async def get_current_session(
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> SessionModel:
    if session_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    token_hash = hash_token(session_token, settings.session_secret.get_secret_value())
    session_row = await SessionRepository(db).get_by_token_hash(token_hash)

    if (
        session_row is None
        or session_row.revoked_at is not None
        or session_row.expires_at < datetime.now(UTC)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")

    return session_row


async def get_current_user(
    session_row: Annotated[SessionModel, Depends(get_current_session)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> User:
    user = await UserRepository(db).get_by_id(session_row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


async def get_current_membership(
    session_row: Annotated[SessionModel, Depends(get_current_session)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> OrganisationMembership:
    """The active organisation's membership — the source of truth for
    "which org and role is this request acting as," derived entirely from
    the server-side session, never from anything the client asserts.
    """
    if session_row.active_organisation_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No active organisation selected")

    membership = await OrganisationMembershipRepository(db).get(
        organisation_id=session_row.active_organisation_id, user_id=session_row.user_id
    )
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of the active organisation")
    return membership


def require_role(
    *allowed_roles: MembershipRole,
) -> Callable[[OrganisationMembership], Awaitable[OrganisationMembership]]:
    async def _check(
        membership: Annotated[OrganisationMembership, Depends(get_current_membership)],
    ) -> OrganisationMembership:
        if membership.role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role for this action")
        return membership

    return _check


async def require_csrf(
    request: Request,
    session_row: Annotated[SessionModel, Depends(get_current_session)],
) -> None:
    """Double-submit CSRF check (see docs/architecture.md, auth decision):
    the csrf_token is returned in the login/register/me JSON body, so only
    JavaScript running on our own origin can read it and echo it back as a
    header — a cross-site form post can't.
    """
    header_value = request.headers.get("x-csrf-token")
    if not header_value or not secrets.compare_digest(header_value, session_row.csrf_token):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing or invalid CSRF token")
