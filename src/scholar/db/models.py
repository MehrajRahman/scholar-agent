"""ORM models — the web app's system of record.

Every user-owned row carries ``user_id`` from day one, so enforcing per-user
isolation (and, later, multi-tenant SaaS) is a query-scoping concern, not a
schema migration. These are distinct from the discovery *engine*'s Neo4j/Qdrant
entities: those answer "what opportunities exist?"; these answer "what is THIS
user doing about them?".
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

# Application pipeline stages (see docs/WEB_APP_EVOLUTION.md §7.1).
APPLICATION_STATUSES = (
    "interested", "preparing", "applied", "interview",
    "offer", "rejected", "waitlisted",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    profile: Mapped[Profile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    applications: Mapped[list[SavedApplication]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    full_name: Mapped[str] = mapped_column(String(200), default="")
    cv_text: Mapped[str] = mapped_column(Text, default="")
    # The structured StudentProfile (Profiler output) as JSON.
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped[User] = relationship(back_populates="profile")


class SavedApplication(Base):
    """A user's saved opportunity + its tracking state (the pipeline card)."""

    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # Content-addressed id of a discovered Opportunity, or null if added manually.
    opportunity_ref: Mapped[str | None] = mapped_column(String(32), default=None)
    title: Mapped[str] = mapped_column(String(500))
    institution: Mapped[str | None] = mapped_column(String(300), default=None)
    country: Mapped[str | None] = mapped_column(String(120), default=None)
    kind: Mapped[str] = mapped_column(String(40), default="scholarship")
    status: Mapped[str] = mapped_column(String(40), default="interested", index=True)
    deadline: Mapped[str | None] = mapped_column(String(32), default=None)
    source_url: Mapped[str | None] = mapped_column(Text, default=None)
    notes: Mapped[str] = mapped_column(Text, default="")
    # Requirement checklist: [{"label": "SOP", "done": false}, ...] (embedded JSON
    # — a small, bounded, per-application list; no separate table needed).
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped[User] = relationship(back_populates="applications")
