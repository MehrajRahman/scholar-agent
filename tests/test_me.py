"""Per-user persistence API: profile + applications CRUD, and cross-user isolation."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from scholar.api.main import app
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
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_endpoints_require_auth(client):
    assert client.get("/me/profile").status_code == 401
    assert client.get("/me/applications").status_code == 401


def test_profile_upsert_and_get(client):
    h = _auth(client, "a@x.com")
    assert client.get("/me/profile", headers=h).status_code == 404  # none yet
    put = client.put(
        "/me/profile",
        json={"full_name": "Ada", "cv_text": "cv...", "data": {"skills": ["ml"]}},
        headers=h,
    )
    assert put.status_code == 200 and put.json()["full_name"] == "Ada"
    got = client.get("/me/profile", headers=h)
    assert got.status_code == 200 and got.json()["data"] == {"skills": ["ml"]}


def test_application_crud(client):
    h = _auth(client, "b@x.com")
    # create (as if saving a discovered opportunity)
    created = client.post(
        "/me/applications",
        json={"title": "PhD in FL", "opportunity_ref": "abc123",
              "institution": "TUM", "country": "Germany", "kind": "phd"},
        headers=h,
    )
    assert created.status_code == 201, created.text
    app_id = created.json()["id"]
    assert created.json()["status"] == "interested"

    # list
    lst = client.get("/me/applications", headers=h)
    assert lst.status_code == 200 and len(lst.json()) == 1

    # update status
    patched = client.patch(f"/me/applications/{app_id}", json={"status": "applied"}, headers=h)
    assert patched.status_code == 200 and patched.json()["status"] == "applied"

    # filter by status
    assert len(client.get("/me/applications?status=applied", headers=h).json()) == 1
    assert len(client.get("/me/applications?status=interested", headers=h).json()) == 0

    # delete
    assert client.delete(f"/me/applications/{app_id}", headers=h).status_code == 204
    assert client.get(f"/me/applications/{app_id}", headers=h).status_code == 404


def test_invalid_status_rejected(client):
    h = _auth(client, "c@x.com")
    r = client.post("/me/applications", json={"title": "X", "status": "bogus"}, headers=h)
    assert r.status_code == 422


def test_cross_user_isolation(client):
    """The security-critical test: user B must not see/touch user A's data."""
    a = _auth(client, "alice@x.com")
    b = _auth(client, "bob@x.com")

    app_id = client.post("/me/applications", json={"title": "Alice's PhD"}, headers=a).json()["id"]

    # B sees nothing of A's
    assert client.get("/me/applications", headers=b).json() == []
    assert client.get(f"/me/applications/{app_id}", headers=b).status_code == 404
    assert client.patch(f"/me/applications/{app_id}", json={"status": "applied"}, headers=b).status_code == 404
    assert client.delete(f"/me/applications/{app_id}", headers=b).status_code == 404

    # A still owns it, untouched
    a_view = client.get(f"/me/applications/{app_id}", headers=a)
    assert a_view.status_code == 200 and a_view.json()["status"] == "interested"


def test_checklist_create_and_update(client):
    h = _auth(client, "cl@x.com")
    r = client.post(
        "/me/applications",
        json={"title": "PhD", "checklist": [{"label": "SOP"}, {"label": "IELTS", "done": True}]},
        headers=h,
    )
    assert r.status_code == 201
    assert [(i["label"], i["done"]) for i in r.json()["checklist"]] == [("SOP", False), ("IELTS", True)]

    aid = r.json()["id"]
    p = client.patch(f"/me/applications/{aid}", json={"checklist": [{"label": "SOP", "done": True}]}, headers=h)
    assert p.status_code == 200 and p.json()["checklist"] == [{"label": "SOP", "done": True}]


def test_checklist_out_coerces_legacy_null():
    """A row migrated in with NULL checklist must serialise as []."""
    from scholar.api.me import ApplicationOut

    class Row:  # noqa: D401 - stand-in for a legacy ORM row
        id, opportunity_ref, title, institution, country = 1, None, "x", None, None
        kind, status, deadline, source_url, notes = "scholarship", "interested", None, None, ""
        checklist = None
        created_at = updated_at = "2026-01-01"

    assert ApplicationOut.model_validate(Row()).checklist == []


# --- Professor CRM ---------------------------------------------------------

def test_professor_crud(client):
    h = _auth(client, "p@x.com")
    r = client.post(
        "/me/professors",
        json={"name": "Dr. Müller", "university": "TUM", "email": "m@tum.edu",
              "next_followup_at": "2026-08-01",
              "thread": [{"direction": "sent", "subject": "PhD inquiry", "body": "Hello"}]},
        headers=h,
    )
    assert r.status_code == 201 and r.json()["status"] == "to_contact"
    assert len(r.json()["thread"]) == 1
    pid = r.json()["id"]

    assert client.patch(f"/me/professors/{pid}", json={"status": "emailed"}, headers=h).json()["status"] == "emailed"
    assert len(client.get("/me/professors?status=emailed", headers=h).json()) == 1
    assert client.delete(f"/me/professors/{pid}", headers=h).status_code == 204
    assert client.get(f"/me/professors/{pid}", headers=h).status_code == 404


def test_professor_invalid_status_rejected(client):
    h = _auth(client, "p2@x.com")
    assert client.post("/me/professors", json={"name": "X", "status": "bogus"}, headers=h).status_code == 422


def test_professor_cross_user_isolation(client):
    a = _auth(client, "pa@x.com")
    b = _auth(client, "pb@x.com")
    pid = client.post("/me/professors", json={"name": "Alice's prof"}, headers=a).json()["id"]

    assert client.get("/me/professors", headers=b).json() == []
    assert client.get(f"/me/professors/{pid}", headers=b).status_code == 404
    assert client.patch(f"/me/professors/{pid}", json={"status": "emailed"}, headers=b).status_code == 404
    assert client.delete(f"/me/professors/{pid}", headers=b).status_code == 404
    assert client.get(f"/me/professors/{pid}", headers=a).status_code == 200
