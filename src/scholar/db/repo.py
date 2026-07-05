"""User-scoped data access — the ONLY place the web app reads/writes user rows.

Every function takes ``user_id`` and filters by it, so isolation is enforced
here in one layer: a user can never touch another user's profile or
applications (mismatched ids simply return ``None``/no rows).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Profile, SavedApplication

# Fields a client may set on an application (whitelist — never trust arbitrary keys).
_APP_FIELDS = {
    "opportunity_ref", "title", "institution", "country",
    "kind", "status", "deadline", "source_url", "notes",
}


# --- Profile ---------------------------------------------------------------

def get_profile(session: Session, user_id: int) -> Profile | None:
    return session.scalar(select(Profile).where(Profile.user_id == user_id))


def upsert_profile(
    session: Session, user_id: int, *, full_name: str, cv_text: str, data: dict
) -> Profile:
    profile = get_profile(session, user_id)
    if profile is None:
        profile = Profile(user_id=user_id)
        session.add(profile)
    profile.full_name = full_name
    profile.cv_text = cv_text
    profile.data = data
    session.commit()
    session.refresh(profile)
    return profile


# --- Applications (the pipeline board) -------------------------------------

def list_applications(
    session: Session, user_id: int, status: str | None = None
) -> list[SavedApplication]:
    stmt = select(SavedApplication).where(SavedApplication.user_id == user_id)
    if status:
        stmt = stmt.where(SavedApplication.status == status)
    stmt = stmt.order_by(SavedApplication.updated_at.desc())
    return list(session.scalars(stmt))


def get_application(session: Session, user_id: int, app_id: int) -> SavedApplication | None:
    """Ownership-scoped fetch: only returns the row if it belongs to this user."""
    return session.scalar(
        select(SavedApplication).where(
            SavedApplication.id == app_id, SavedApplication.user_id == user_id
        )
    )


def create_application(session: Session, user_id: int, fields: dict[str, Any]) -> SavedApplication:
    clean = {k: v for k, v in fields.items() if k in _APP_FIELDS}
    app = SavedApplication(user_id=user_id, **clean)
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def update_application(
    session: Session, user_id: int, app_id: int, fields: dict[str, Any]
) -> SavedApplication | None:
    app = get_application(session, user_id, app_id)
    if app is None:
        return None
    for key, value in fields.items():
        if key in _APP_FIELDS and value is not None:
            setattr(app, key, value)
    session.commit()
    session.refresh(app)
    return app


def delete_application(session: Session, user_id: int, app_id: int) -> bool:
    app = get_application(session, user_id, app_id)
    if app is None:
        return False
    session.delete(app)
    session.commit()
    return True
