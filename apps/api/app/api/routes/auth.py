from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
from app.services.auth_service import (
    AuthService,
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
)

router = APIRouter(prefix="/auth", tags=["auth"])


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
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
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
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthResponse:
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
