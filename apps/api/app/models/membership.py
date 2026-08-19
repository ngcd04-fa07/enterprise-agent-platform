import enum
import uuid
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.organisation import Organisation
    from app.models.user import User


class MembershipRole(enum.StrEnum):
    """RBAC roles (see docs/architecture.md). The column exists as core
    domain data now; permission *enforcement* is built in Stage 3.
    """

    ADMIN = "admin"
    UNDERWRITER = "underwriter"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class OrganisationMembership(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organisation_memberships"
    __table_args__ = (sa.UniqueConstraint("organisation_id", "user_id"),)

    organisation_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("organisations.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MembershipRole] = mapped_column(sa.Enum(MembershipRole, name="membership_role"))

    organisation: Mapped["Organisation"] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")
