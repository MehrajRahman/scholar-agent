"""Auth flow tests — TestClient against an isolated in-memory SQLite DB."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scholar.api.main import app
from scholar.auth.security import create_access_token, decode_token
from scholar.db import Base, get_session


@pytest.fixture
def client():
    # StaticPool = one shared connection, so ":memory:" is a single DB across the
    # session (the default pool gives each connection its own empty DB).
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)

    def _override():
        with TestingSession() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_signup_login_me_flow(client):
    # signup
    r = client.post("/auth/signup", json={"email": "Ada@Example.com", "password": "password123"})
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert r.json()["email"] == "ada@example.com"  # normalised

    # /me with the token
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "ada@example.com"

    # login with correct creds
    assert client.post("/auth/login", json={"email": "ada@example.com", "password": "password123"}).status_code == 200


def test_duplicate_signup_conflicts(client):
    body = {"email": "dup@example.com", "password": "password123"}
    assert client.post("/auth/signup", json=body).status_code == 200
    assert client.post("/auth/signup", json=body).status_code == 409


def test_wrong_password_and_unknown_user_rejected(client):
    client.post("/auth/signup", json={"email": "x@example.com", "password": "password123"})
    assert client.post("/auth/login", json={"email": "x@example.com", "password": "wrongpass1"}).status_code == 401
    assert client.post("/auth/login", json={"email": "nobody@example.com", "password": "password123"}).status_code == 401


def test_short_password_rejected(client):
    r = client.post("/auth/signup", json={"email": "y@example.com", "password": "short"})
    assert r.status_code == 422  # pydantic min_length


def test_me_requires_valid_token(client):
    assert client.get("/auth/me").status_code == 401                               # no header
    assert client.get("/auth/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_token_roundtrip():
    assert decode_token(create_access_token(42)) == 42
    assert decode_token("not.a.token") is None
