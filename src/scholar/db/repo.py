"""User-scoped data access — the ONLY place the web app reads/writes user rows.

Every function takes ``user_id`` and filters by it, so isolation is enforced
here in one layer: a user can never touch another user's profile or
applications (mismatched ids simply return ``None``/no rows).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Profile, ProfessorContact, SavedApplication, WatchlistItem

# Fields a client may set on an application (whitelist — never trust arbitrary keys).
_APP_FIELDS = {
    "opportunity_ref", "title", "institution", "country",
    "kind", "status", "deadline", "source_url", "notes", "checklist",
}
_PROF_FIELDS = {
    "name", "university", "department", "email", "research_fit",
    "status", "linked_application_id", "next_followup_at", "thread",
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


# --- Professor contacts (outreach CRM) -------------------------------------

def list_professors(
    session: Session, user_id: int, status: str | None = None
) -> list[ProfessorContact]:
    stmt = select(ProfessorContact).where(ProfessorContact.user_id == user_id)
    if status:
        stmt = stmt.where(ProfessorContact.status == status)
    return list(session.scalars(stmt.order_by(ProfessorContact.updated_at.desc())))


def get_professor(session: Session, user_id: int, prof_id: int) -> ProfessorContact | None:
    return session.scalar(
        select(ProfessorContact).where(
            ProfessorContact.id == prof_id, ProfessorContact.user_id == user_id
        )
    )


def create_professor(session: Session, user_id: int, fields: dict[str, Any]) -> ProfessorContact:
    clean = {k: v for k, v in fields.items() if k in _PROF_FIELDS}
    prof = ProfessorContact(user_id=user_id, **clean)
    session.add(prof)
    session.commit()
    session.refresh(prof)
    return prof


def update_professor(
    session: Session, user_id: int, prof_id: int, fields: dict[str, Any]
) -> ProfessorContact | None:
    prof = get_professor(session, user_id, prof_id)
    if prof is None:
        return None
    for key, value in fields.items():
        if key in _PROF_FIELDS and value is not None:
            setattr(prof, key, value)
    session.commit()
    session.refresh(prof)
    return prof


def delete_professor(session: Session, user_id: int, prof_id: int) -> bool:
    prof = get_professor(session, user_id, prof_id)
    if prof is None:
        return False
    session.delete(prof)
    session.commit()
    return True


# --- Watchlist (standing interests, auto-surfed by the daily job) ----------

def list_watchlist(session: Session, user_id: int) -> list[WatchlistItem]:
    return list(
        session.scalars(
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.created_at.desc())
        )
    )


def add_watchlist_item(session: Session, user_id: int, keyword: str) -> WatchlistItem:
    item = WatchlistItem(user_id=user_id, keyword=keyword.strip())
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def delete_watchlist_item(session: Session, user_id: int, item_id: int) -> bool:
    item = session.scalar(
        select(WatchlistItem).where(
            WatchlistItem.id == item_id, WatchlistItem.user_id == user_id
        )
    )
    if item is None:
        return False
    session.delete(item)
    session.commit()
    return True


def due_watchlist_items(session: Session, limit: int) -> list[WatchlistItem]:
    """Active items across ALL users, least-recently-surfed first (never-surfed
    before everything else). The daily job takes the top ``limit`` — a rotation,
    so every keyword gets its turn without exceeding the daily budget.

    NULLs-first is expressed with a portable boolean sort key (SQLite + Postgres).
    """
    stmt = (
        select(WatchlistItem)
        .where(WatchlistItem.active.is_(True))
        .order_by(WatchlistItem.last_surfed_at.isnot(None), WatchlistItem.last_surfed_at.asc())
        .limit(max(0, limit))
    )
    return list(session.scalars(stmt))


def mark_watchlist_surfed(session: Session, item_id: int, surfed_at: str) -> None:
    item = session.get(WatchlistItem, item_id)
    if item is not None:
        item.last_surfed_at = surfed_at
        session.commit()
