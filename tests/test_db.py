"""DB foundation tests — run on in-memory SQLite, no Postgres needed."""
from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from scholar.db import APPLICATION_STATUSES, Base, Profile, SavedApplication, User


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_tables_registered():
    assert {"users", "profiles", "applications"} <= set(Base.metadata.tables)


def test_user_profile_and_application_relationships():
    s = _session()
    user = User(email="ada@example.com", password_hash="hashed")
    user.profile = Profile(full_name="Ada Lovelace")
    user.applications.append(
        SavedApplication(title="PhD in ML", status="interested", country="Germany")
    )
    s.add(user)
    s.commit()

    got = s.scalars(select(User).where(User.email == "ada@example.com")).one()
    assert got.profile is not None and got.profile.full_name == "Ada Lovelace"
    assert len(got.applications) == 1
    app = got.applications[0]
    assert app.title == "PhD in ML"
    # Every user-owned row carries the owner's id -> the basis for per-user scoping.
    assert app.user_id == got.id
    assert got.profile.user_id == got.id


def test_email_is_unique():
    import pytest
    from sqlalchemy.exc import IntegrityError

    s = _session()
    s.add(User(email="dup@example.com", password_hash="x"))
    s.commit()
    s.add(User(email="dup@example.com", password_hash="y"))
    with pytest.raises(IntegrityError):
        s.commit()


def test_default_status_is_interested():
    s = _session()
    u = User(email="x@y.com", password_hash="x")
    u.applications.append(SavedApplication(title="X"))
    s.add(u)
    s.commit()
    assert u.applications[0].status == "interested"
    assert "interested" in APPLICATION_STATUSES
