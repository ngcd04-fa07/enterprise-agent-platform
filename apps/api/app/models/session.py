import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Session(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A server-side session backing an HTTP-only cookie (see
    docs/architecture.md, auth decision). Only token_hash is stored — never
    the raw session token — so a database read (backup, replica, dump)
    can't be used to impersonate a live session; the raw token exists only
    in the cookie and briefly in memory when issued.

    active_organisation_id is the org this session is currently acting
    within. A user can belong to multiple organisations; this is what makes
    "the current organisation" unambiguous for every request without the
    client asserting it. Nullable because a session can exist before an
    organisation is selected (not expected in practice: registration always
    creates one), and SET NULL on the org's deletion rather than cascading
    the session away.
    """

    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(sa.String(64))
    active_organisation_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
