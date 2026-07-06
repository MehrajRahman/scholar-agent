"""Application assistant: calendar export + in-drawer AI drafting."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scholar.api.main import app
from scholar.db import Base, get_session
from scholar.schemas import ColdEmail, SOPDraft, SynthesisBundle


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


# --- calendar ----------------------------------------------------------------

def test_calendar_requires_auth(client):
    assert client.get("/me/calendar.ics").status_code == 401


def test_calendar_contains_deadlines_and_followups(client):
    h = _auth(client, "cal@x.com")
    client.post("/me/applications", json={"title": "Erasmus Mundus", "deadline": "2026-11-01"}, headers=h)
    client.post("/me/professors", json={"name": "Dr. Kim", "next_followup_at": "2026-09-15"}, headers=h)

    r = client.get("/me/calendar.ics", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/calendar")
    body = r.text
    assert "Deadline: Erasmus Mundus" in body and "20261101" in body
    assert "Follow up: Dr. Kim" in body and "20260915" in body


# --- draft for a saved application --------------------------------------------

async def _fake_scribe(state):
    return {
        "draft": SynthesisBundle(
            opportunity_id="x", opportunity_title=state["shortlist"][0].title, score=0,
            cold_email=ColdEmail(to_name="Prof", subject="PhD inquiry", body="Dear Prof..."),
            sop=SOPDraft(target="TUM", body="My purpose..."),
        )
    }


def test_draft_for_application_persists_documents(client, monkeypatch):
    monkeypatch.setattr("scholar.agents.scribe.scribe_node", _fake_scribe)
    h = _auth(client, "d@x.com")
    # manual application (no opportunity_ref) -> context synthesized, no Qdrant needed
    app_id = client.post(
        "/me/applications", json={"title": "PhD in ML", "institution": "TUM", "kind": "phd"},
        headers=h,
    ).json()["id"]

    r = client.post(f"/me/applications/{app_id}/draft", headers=h)
    assert r.status_code == 200, r.text
    docs = r.json()["documents"]
    assert [d["type"] for d in docs] == ["cold_email", "sop"]
    assert docs[0]["title"] == "PhD inquiry" and "Dear Prof" in docs[0]["body"]

    # persisted: still there on a plain GET
    again = client.get(f"/me/applications/{app_id}", headers=h).json()
    assert len(again["documents"]) == 2

    # ownership: another user gets 404
    other = _auth(client, "d2@x.com")
    assert client.post(f"/me/applications/{app_id}/draft", headers=other).status_code == 404


# --- draft email for a professor ----------------------------------------------

class _FakeLLM:
    async def structured(self, role, system, user, schema, **kw):
        assert schema is ColdEmail
        return ColdEmail(to_name="Dr. Lee", subject="Prospective student", body="Hello Dr. Lee...")


def test_draft_professor_email_prefills(client, monkeypatch):
    monkeypatch.setattr("scholar.llm.get_llm", lambda: _FakeLLM())
    h = _auth(client, "p@x.com")
    pid = client.post("/me/professors", json={"name": "Dr. Lee", "university": "KAIST"}, headers=h).json()["id"]

    r = client.post(f"/me/professors/{pid}/draft_email", headers=h)
    assert r.status_code == 200
    assert r.json() == {"subject": "Prospective student", "body": "Hello Dr. Lee..."}
