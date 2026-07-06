"""Writing Studio: auth gate, length guard, band-feedback happy path."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scholar.api.main import app
from scholar.api.studio import WritingFeedback
from scholar.db import Base, get_session


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    SM = sessionmaker(bind=engine, expire_on_commit=False)

    def _override():
        with SM() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _auth(client: TestClient, email: str) -> dict:
    r = client.post("/auth/signup", json={"email": email, "password": "password123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}



class _FakeStudioLLM:
    async def structured(self, role, system, user, schema, **kw):
        return WritingFeedback(
            band_overall=6.5, task_response=6.0, coherence_cohesion=6.5,
            lexical_resource=6.5, grammatical_range_accuracy=7.0,
            strengths=["clear position"], improvements=["paragraphing"], rewrites=[],
        )


def test_studio_requires_auth(client):
    assert client.post("/studio/feedback", json={"text": "word " * 60}).status_code == 401


def test_studio_rejects_too_short(client):
    h = _auth(client, "s@x.com")
    r = client.post("/studio/feedback", json={"text": "too short"}, headers=h)
    assert r.status_code == 422
    assert "50 words" in r.json()["detail"]


def test_studio_happy_path(client, monkeypatch):
    monkeypatch.setattr("scholar.llm.get_llm", lambda: _FakeStudioLLM())
    h = _auth(client, "s2@x.com")
    r = client.post(
        "/studio/feedback",
        json={"mode": "ielts_task2", "prompt": "Discuss.", "text": "essay " * 260},
        headers=h,
    )
    assert r.status_code == 200
    fb = r.json()
    assert fb["band_overall"] == 6.5 and fb["strengths"] == ["clear position"]
