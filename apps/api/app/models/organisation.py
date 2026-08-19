from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.membership import OrganisationMembership


class Organisation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organisations"

    name: Mapped[str] = mapped_column(sa.String(255))

    memberships: Mapped[list["OrganisationMembership"]] = relationship(
        back_populates="organisation", cascade="all, delete-orphan"
    )
