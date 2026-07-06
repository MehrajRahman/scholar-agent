"""Browse endpoint: auth gate, card shape, expired exclusion, deadline sorting."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import scholar.api.kb as kb_api
from scholar.api.main import app
from scholar.db import Base, get_session
from scholar.schemas.opportunity import Opportunity, OpportunityKind, OppStatus


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


def _opp(title: str, deadline: str | None, status: OppStatus = OppStatus.active) -> Opportunity:
    return Opportunity(
        title=title,
        kind=OpportunityKind.phd_position,
        source_url=f"http://x.edu/{title}",
        deadline=deadline,
        status=status,
    )


class _FakeVectors:
    def scroll_all(self, limit: int = 1000):
        return [
            _opp("undated", None),
            _opp("later", "2026-12-01"),
            _opp("dead", "2026-01-01", OppStatus.expired),
            _opp("soonest", "2026-08-01"),
        ]


def test_browse_requires_auth(client):
    assert client.get("/kb/opportunities").status_code == 401


def test_browse_sorting_shape_and_expired_excluded(client, monkeypatch):
    monkeypatch.setattr(kb_api, "get_vectors", lambda: _FakeVectors())
    tok = client.post(
        "/auth/signup", json={"email": "kb@x.com", "password": "password123"}
    ).json()["access_token"]

    r = client.get("/kb/opportunities", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    cards = r.json()
    # expired excluded; dated soonest-first; undated last
    assert [c["title"] for c in cards] == ["soonest", "later", "undated"]
    # card shape has what the Browse page renders
    assert {"id", "title", "kind", "university", "deadline", "fully_funded",
            "source_url", "description", "status"} <= set(cards[0])
