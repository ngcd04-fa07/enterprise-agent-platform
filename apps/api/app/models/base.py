import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Explicit naming convention so Alembic autogenerate produces deterministic,
# greppable constraint names instead of dialect-assigned ones.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    # Explicit timezone=True: Postgres TIMESTAMPTZ, not the ambiguous
    # naive TIMESTAMP that SQLAlchemy would otherwise default to.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # SQLAlchemy's "auto" eager_defaults only fetches server-generated
    # values (like the above) via RETURNING on INSERT, not on UPDATE. Without
    # this, `updated_at` is left expired after an UPDATE flush, and the next
    # plain attribute access (e.g. Pydantic's model_validate serializing the
    # ORM object right after a status-changing update, as
    # IngestionService/DocumentRepository.update_status do) triggers an
    # implicit lazy refresh — which raises MissingGreenlet because attribute
    # access from sync code can't await the async DB round-trip. Forcing
    # RETURNING on UPDATE too keeps the object's state fully populated
    # in-memory the moment flush() returns.
    __mapper_args__ = {"eager_defaults": True}


def str_enum_column(enum_cls: type[enum.Enum], *, name: str) -> sa.Enum:
    """sa.Enum for an enum.StrEnum, persisting each member's `.value`
    (lowercase, e.g. "draft") rather than SQLAlchemy's default of `.name`
    (uppercase, e.g. "DRAFT"). Omitting values_callable here is a silent
    runtime failure — every insert/read fails with
    InvalidTextRepresentationError against the Postgres enum type, not a
    type error caught by mypy — so this exists to make the correct call the
    only call.
    """
    return sa.Enum(enum_cls, name=name, values_callable=lambda e: [member.value for member in e])
