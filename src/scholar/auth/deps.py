"""FastAPI auth dependencies — the single choke point for per-user scoping.

Every user-owned endpoint depends on ``CurrentUser``; there is no other way to
read a user's data, which keeps isolation enforceable in one place.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..db import User, get_session
from .security import decode_token


def get_current_user(
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    user_id = decode_token(authorization.split(" ", 1)[1])
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user


# Convenience alias for endpoint signatures: ``user: CurrentUser``.
CurrentUser = Annotated[User, Depends(get_current_user)]
