"""Matchmaker display-enrichment + MatchResult resilience tests (pure, offline)."""
from __future__ import annotations

from scholar.agents.matchmaker import _attach_display, _funding_summary
from scholar.schemas import MatchResult
from scholar.schemas.opportunity import (
    Funding,
    Opportunity,
    OpportunityKind,
    Professor,
)


def test_funding_summary_variants():
    assert _funding_summary(Funding(is_fully_funded=True)) == "Fully funded"
    assert _funding_summary(Funding(stipend_amount=1500, currency="EUR")) == "1500 EUR"
    assert _funding_summary(Funding()) == ""


def test_attach_display_copies_opportunity_fields():
    opp = Opportunity(
        title="PhD in Federated Learning",
        kind=OpportunityKind.phd_position,
        university="TU Munich",
        department="CS",
        source_url="https://www.tum.edu/phd/123",
        deadline="2026-12-01",
        description="x" * 500,  # longer than the 400-char display cap
        funding=Funding(is_fully_funded=True),
        professor=Professor(name="Dr. A. Müller"),
    )
    r = MatchResult(score=88)
    _attach_display(r, opp)
    assert r.source_url == "https://www.tum.edu/phd/123"
    assert r.university == "TU Munich" and r.department == "CS"
    assert r.kind == "phd_position" and r.deadline == "2026-12-01"
    assert r.funding_summary == "Fully funded"
    assert r.professor_name == "Dr. A. Müller"
    assert len(r.description) <= 400


def test_matchresult_tolerates_omitted_overwritten_fields():
    # The model only needs to emit score/rationale/skills/gaps; signals default.
    m = MatchResult.model_validate(
        {"score": 72, "rationale": "good fit", "matched_skills": ["ml"], "gaps": []}
    )
    assert m.score == 72
    assert m.semantic_score == 0.0 and m.eligible is False and m.source_url == ""


def test_matchresult_ignores_out_of_range_signal():
    # A hallucinated semantic_score=1.33 must not fail validation (overwritten anyway).
    m = MatchResult.model_validate({"score": 50, "semantic_score": 1.33, "graph_score": 9.9})
    assert m.score == 50
