import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password, verify_password
from app.auth.tokens import generate_token, hash_token
from app.core.config import Settings
from app.models.session import Session as SessionModel
from app.models.user import User
from app.repositories.membership_repository import OrganisationMembershipRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.organisation_service import OrganisationService

SESSION_LIFETIME = timedelta(days=14)


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


@dataclass
class AuthResult:
    user: User
    session: SessionModel
    raw_token: str


class AuthService:
    def __init__(self, db: AsyncSession, settings: Settings) -> None:
        self._db = db
        self._settings = settings
        self._users = UserRepository(db)
        self._sessions = SessionRepository(db)
        self._memberships = OrganisationMembershipRepository(db)

    async def register(
        self, *, email: str, full_name: str, password: str, organisation_name: str
    ) -> AuthResult:
        if await self._users.get_by_email(email) is not None:
            raise EmailAlreadyRegisteredError(email)

        user = await self._users.create(
            email=email, full_name=full_name, password_hash=hash_password(password)
        )
        organisation = await OrganisationService(self._db).create_organisation_with_owner(
            name=organisation_name, owner_user_id=user.id
        )
        return await self._issue_session(user, active_organisation_id=organisation.id)

    async def login(self, *, email: str, password: str) -> AuthResult:
        user = await self._users.get_by_email(email)
        # Deliberately identical failure whether the email doesn't exist or
        # the password is wrong — verify_password still runs against a
        # throwaway hash in the "no such user" case so the response timing
        # doesn't reveal which one it was.
        if user is None:
            verify_password(password, hash_password("not-a-real-password"))
            raise InvalidCredentialsError
        if not user.is_active or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError

        memberships = await self._memberships.list_for_user(user.id)
        active_organisation_id = memberships[0].organisation_id if memberships else None
        return await self._issue_session(user, active_organisation_id=active_organisation_id)

    async def logout(self, session_row: SessionModel) -> None:
        await self._sessions.revoke(session_row, revoked_at=datetime.now(UTC))

    async def _issue_session(
        self, user: User, *, active_organisation_id: uuid.UUID | None
    ) -> AuthResult:
        raw_token = generate_token()
        session_row = await self._sessions.create(
            user_id=user.id,
            token_hash=hash_token(raw_token, self._settings.session_secret.get_secret_value()),
            csrf_token=secrets.token_urlsafe(32),
            active_organisation_id=active_organisation_id,
            expires_at=datetime.now(UTC) + SESSION_LIFETIME,
        )
        return AuthResult(user=user, session=session_row, raw_token=raw_token)
