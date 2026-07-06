"""Per-role provider preference: ordering, fallback, unknown-name safety."""
from __future__ import annotations

import pytest

from scholar.config import get_settings
from scholar.llm.providers import load_providers, provider_for, providers_for
from scholar.llm.router import Role, route


@pytest.fixture
def _reset_settings_cache():
    yield
    get_settings.cache_clear()  # drop any monkeypatched env values


def test_default_order_is_pool_order(_reset_settings_cache):
    pool = load_providers()
    assert [p.name for p in providers_for(Role.HEAVY)] == [p.name for p in pool]


def test_preference_moves_provider_first_keeps_rest(monkeypatch, _reset_settings_cache):
    pool = load_providers()
    if len(pool) < 2:
        pytest.skip("needs a multi-provider pool")
    target = pool[1].name  # prefer the second provider in the pool
    monkeypatch.setenv("LLM_PROVIDER_FAST", target)
    get_settings.cache_clear()

    ordered = providers_for(Role.FAST)
    assert ordered[0].name == target
    # nothing lost, everything else still available as fallback
    assert sorted(p.name for p in ordered) == sorted(p.name for p in pool)
    # other roles unaffected
    assert providers_for(Role.HEAVY)[0].name == pool[0].name
    # route() (prompt-family detection) follows the same preference
    model, _ = route(Role.FAST)
    assert model == ordered[0].model_for(Role.FAST)


def test_unknown_preference_falls_back_to_pool_order(monkeypatch, _reset_settings_cache):
    monkeypatch.setenv("LLM_PROVIDER_SCRIBE", "no-such-provider")
    get_settings.cache_clear()
    pool = load_providers()
    assert providers_for(Role.SCRIBE)[0].name == pool[0].name
    assert provider_for(Role.SCRIBE).name == pool[0].name
