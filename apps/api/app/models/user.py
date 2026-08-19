from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.membership import OrganisationMembership


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A person who can authenticate. Credential storage (password hash,
    sessions) is deliberately not part of this model yet — it belongs to
    Stage 3 (Auth/RBAC), which owns the authentication mechanism. This model
    is the identity the rest of the domain (memberships, submissions) refers
    to.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(sa.String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(sa.String(255))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)

    memberships: Mapped[list["OrganisationMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
