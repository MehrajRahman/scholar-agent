"""Phase-1 offline tests: gateway pool, family detection, prompt adapter,
mode routing, and opportunity freshness/hashing. No network or DB required.
"""
from __future__ import annotations

import json

from scholar.graph_app import mode_router
from scholar.llm.families import Family, family_of
from scholar.llm.providers import ProviderConfig, load_providers
from scholar.llm.router import Role, route, temperature
from scholar.prompts import get_prompt, system_for
from scholar.schemas import Opportunity, OpportunityKind, OppStatus


# --- model family detection -------------------------------------------------

def test_family_detection_hermes_beats_llama():
    assert family_of("NousResearch/Hermes-3-Llama-3.1-8B") == Family.HERMES
    assert family_of("llama-3.3-70b-versatile") == Family.LLAMA
    assert family_of("qwen/qwen-2.5-72b-instruct") == Family.QWEN
    assert family_of("gemini-2.0-flash") == Family.GEMINI
    assert family_of("mistral-nemo-12b") == Family.MISTRAL
    assert family_of("some-unknown-model") == Family.GENERIC


# --- provider pool ----------------------------------------------------------

def test_default_provider_pool_is_single_from_env():
    pool = load_providers()
    assert len(pool) >= 1
    assert isinstance(pool[0], ProviderConfig)
    # every role must resolve to a model on the primary provider
    for role in Role:
        assert pool[0].model_for(role)


def test_route_uses_primary_provider():
    model, temp = route(Role.HEAVY)
    assert model == load_providers()[0].model_for(Role.HEAVY)
    assert temp == temperature(Role.HEAVY)


# --- prompt adapter ---------------------------------------------------------

def test_prompt_family_adaptation():
    # Hermes template override exists for scout_planner
    hermes = get_prompt("scout_planner", Family.HERMES).render()
    assert "Hermes" in hermes
    # Gemini guidance appended to any role
    gemini = get_prompt("matchmaker", Family.GEMINI).render()
    assert "markdown fences" in gemini
    # Profiler few-shot is injected
    assert "EXAMPLE OUTPUT" in get_prompt("profiler", Family.GENERIC).render()


def test_system_for_resolves_by_role():
    s = system_for("quality_gate", Role.HEAVY)
    assert isinstance(s, str) and len(s) > 50


# --- mode routing -----------------------------------------------------------

def test_mode_router():
    assert mode_router({"mode": "fast"}) == "db_fetch"
    assert mode_router({"mode": "deep"}) == "deep_scout"
    assert mode_router({}) == "deep_scout"  # default = deep/live


# --- freshness / change detection ------------------------------------------

def _opp(**kw) -> Opportunity:
    base = dict(
        title="PhD in ML",
        kind=OpportunityKind.phd_position,
        source_url="http://uni.edu/1",
        description="Funded position",
        required_skills=["python", "ml"],
    )
    base.update(kw)
    return Opportunity(**base)


def test_content_hash_detects_real_changes_only():
    a = _opp()
    b = _opp(required_skills=["ml", "python"])  # same set, different order
    c = _opp(deadline="2027-01-01")             # genuine change
    assert a.content_hash == b.content_hash      # order-insensitive
    assert a.content_hash != c.content_hash      # deadline change detected


def test_opportunity_defaults_active_v1():
    o = _opp()
    assert o.status == OppStatus.active
    assert o.version == 1
    # round-trips through JSON (used for DB payloads / API)
    assert Opportunity.model_validate(json.loads(o.model_dump_json())).id == o.id
