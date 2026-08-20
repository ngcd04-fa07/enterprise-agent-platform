from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.membership import OrganisationMembership


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A person who can authenticate. password_hash is an Argon2id hash
    (see app.auth.password) — never a plaintext or reversibly-encrypted
    password. This model is also the identity the rest of the domain
    (memberships, submissions) refers to.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(sa.String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(sa.String(255))
    password_hash: Mapped[str] = mapped_column(sa.String(255))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True)

    memberships: Mapped[list["OrganisationMembership"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
