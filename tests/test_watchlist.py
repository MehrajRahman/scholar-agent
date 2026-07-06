"""Watchlist: API CRUD + isolation, and the daily-job rotation semantics."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from scholar.api.main import app
from scholar.db import Base, User, get_session
from scholar.db import repo


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


def test_watchlist_crud_and_isolation(client):
    a = _auth(client, "wa@x.com")
    b = _auth(client, "wb@x.com")

    created = client.post("/me/watchlist", json={"keyword": "funded PhD ML Europe"}, headers=a)
    assert created.status_code == 201 and created.json()["last_surfed_at"] is None
    wid = created.json()["id"]

    assert len(client.get("/me/watchlist", headers=a).json()) == 1
    # isolation: B sees nothing and cannot delete A's item
    assert client.get("/me/watchlist", headers=b).json() == []
    assert client.delete(f"/me/watchlist/{wid}", headers=b).status_code == 404
    # too-short keyword rejected
    assert client.post("/me/watchlist", json={"keyword": "ab"}, headers=a).status_code == 422
    # owner can delete
    assert client.delete(f"/me/watchlist/{wid}", headers=a).status_code == 204


def test_due_rotation_order_and_limit():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        u = User(email="r@x.com", password_hash="x")
        s.add(u)
        s.commit()
        never = repo.add_watchlist_item(s, u.id, "never surfed yet")
        old = repo.add_watchlist_item(s, u.id, "surfed long ago")
        recent = repo.add_watchlist_item(s, u.id, "surfed recently")
        inactive = repo.add_watchlist_item(s, u.id, "switched off")
        repo.mark_watchlist_surfed(s, old.id, "2026-01-01T00:00:00")
        repo.mark_watchlist_surfed(s, recent.id, "2026-07-01T00:00:00")
        inactive.active = False
        s.commit()

        due = repo.due_watchlist_items(s, limit=2)
        # never-surfed first, then least-recently-surfed; inactive excluded; limit respected
        assert [i.keyword for i in due] == ["never surfed yet", "surfed long ago"]

        # after surfing, the rotation moves on
        repo.mark_watchlist_surfed(s, never.id, "2026-07-06T00:00:00")
        due2 = repo.due_watchlist_items(s, limit=2)
        assert [i.keyword for i in due2] == ["surfed long ago", "surfed recently"]


async def test_run_daily_surfs_due_watchlist(monkeypatch, tmp_path):
    """run_daily surfs the due slice via refresh() and marks items surfed."""
    import scholar.maintenance as m

    calls: list[str] = []

    async def fake_refresh(q):
        calls.append(q)
        return {"discovered": 2}

    marked: list[int] = []
    monkeypatch.setattr(m, "refresh", fake_refresh)
    monkeypatch.setattr(m, "_due_watchlist", lambda: [(1, "kw one"), (2, "kw two")])
    monkeypatch.setattr(m, "_mark_surfed", lambda i: marked.append(i))

    async def fake_sweep():
        return {"swept": {}, "pruned": 0, "vectors_deleted": 0}

    monkeypatch.setattr(m, "sweep_and_prune", fake_sweep)

    result = await m.run_daily()
    assert calls == ["kw one", "kw two"]
    assert marked == [1, 2]
    assert result["watchlist"] == {"kw one": 2, "kw two": 2}
