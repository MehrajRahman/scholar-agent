"""Freshness + lean-retention: sweep_and_prune wiring, config, empty-delete."""
from __future__ import annotations

import scholar.maintenance as m
from scholar.config import get_settings
from scholar.kb import get_vectors


class _FakeGraph:
    def __init__(self):
        self.pruned_cutoff = None

    async def expire_sweep(self, ttl):
        return {"expired": 2, "active": 5}

    async def prune_expired(self, cutoff):
        self.pruned_cutoff = cutoff
        return ["a", "b", "c"]


class _FakeVectors:
    def __init__(self):
        self.deleted = None

    def delete_by_ids(self, ids):
        self.deleted = list(ids)
        return len(ids)


async def test_sweep_and_prune_wires_graph_and_vectors(monkeypatch):
    fake_g, fake_v = _FakeGraph(), _FakeVectors()
    monkeypatch.setattr(m, "get_graph", lambda: fake_g)
    monkeypatch.setattr(m, "get_vectors", lambda: fake_v)

    result = await m.sweep_and_prune()

    assert result["swept"] == {"expired": 2, "active": 5}
    assert result["pruned"] == 3 and result["vectors_deleted"] == 3
    assert fake_v.deleted == ["a", "b", "c"]          # pruned ids also dropped from Qdrant
    assert fake_g.pruned_cutoff is not None            # a cutoff date was computed


async def test_run_daily_skips_refresh_without_query(monkeypatch):
    monkeypatch.setattr(m, "get_graph", lambda: _FakeGraph())
    monkeypatch.setattr(m, "get_vectors", lambda: _FakeVectors())
    # default config has no refresh query -> refresh (LLM) must NOT run
    result = await m.run_daily()
    assert "refresh" not in result


def test_maintenance_settings_defaults():
    s = get_settings()
    assert s.maintenance_daily is False          # opt-in, never surprises
    assert s.expired_grace_days == 0
    assert s.maintenance_refresh_query is None


def test_delete_by_ids_empty_is_noop():
    assert get_vectors().delete_by_ids([]) == 0
