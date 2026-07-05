"""Password hashing (argon2) + stateless session tokens (JWT).

Keeps crypto in one place so the rest of the app never touches raw hashes or
token internals.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from ..config import get_settings

_pwd = CryptContext(schemes=["argon2"], deprecated="auto")
_ALGO = "HS256"
_TOKEN_TTL = timedelta(days=7)


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd.verify(password, hashed)
    except Exception:  # noqa: BLE001 - malformed hash -> not a match
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "iat": now, "exp": now + _TOKEN_TTL}
    return jwt.encode(payload, get_settings().auth_secret, algorithm=_ALGO)


def decode_token(token: str) -> int | None:
    """Return the user id from a valid token, or None if invalid/expired."""
    try:
        payload = jwt.decode(token, get_settings().auth_secret, algorithms=[_ALGO])
        return int(payload["sub"])
    except Exception:  # noqa: BLE001 - any decode/expiry/format error -> unauthenticated
        return None
