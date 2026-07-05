"""Auth operations against the DB — the only place users are created/verified."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import User
from .security import hash_password, verify_password


class AuthError(Exception):
    """Signup/login failure surfaced to the API layer."""


def _normalise(email: str) -> str:
    return email.strip().lower()


def create_user(session: Session, email: str, password: str) -> User:
    email = _normalise(email)
    if session.scalar(select(User).where(User.email == email)) is not None:
        raise AuthError("email already registered")
    user = User(email=email, password_hash=hash_password(password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate(session: Session, email: str, password: str) -> User | None:
    user = session.scalar(select(User).where(User.email == _normalise(email)))
    if user is not None and verify_password(password, user.password_hash):
        return user
    return None
