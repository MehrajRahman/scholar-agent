"""Offline smoke tests — no network, no GPU, no databases required.

They verify the wiring that must hold regardless of infra: schemas validate,
the graph compiles with the right topology, and the pure helpers behave.
"""
from __future__ import annotations

from scholar.graph_app import (
    build_graph,
    route_after_commit,
    route_after_matchmaker,
    route_after_quality_gate,
)
from scholar.kb.vectors import _rrf
from scholar.llm.client import _extract_json
from scholar.schemas import EducationEntry, Opportunity, OpportunityKind, StudentProfile


def test_profile_gpa_normalisation():
    p = StudentProfile(
        full_name="Ada",
        education=[EducationEntry(institution="X", degree="BSc", gpa=3.6, gpa_scale=4.0)],
    )
    assert p.best_gpa_4 == 3.6


def test_opportunity_stable_id():
    o = Opportunity(
        title="PhD in ML", kind=OpportunityKind.phd_position, source_url="http://a.edu/1"
    )
    assert o.id == Opportunity(
        title="PhD in ML", kind=OpportunityKind.phd_position, source_url="http://a.edu/1"
    ).id
    assert len(o.id) == 16


def test_graph_compiles_and_has_nodes():
    app = build_graph()
    nodes = set(app.get_graph().nodes)
    for expected in {
        "profiler", "db_fetch", "deep_scout", "critic",
        "matchmaker", "scribe", "quality_gate", "commit",
    }:
        assert expected in nodes


def test_reflection_routing():
    # Approved -> commit.
    from scholar.schemas import GroundednessReport

    approved = {"review": GroundednessReport(approved=True, score=1.0), "revision_count": 1}
    assert route_after_quality_gate(approved) == "commit"

    # Rejected but budget left -> loop back to scribe.
    rejected = {
        "review": GroundednessReport(approved=False, score=0.4),
        "revision_count": 1,
    }
    assert route_after_quality_gate(rejected) == "scribe"


def test_matchmaker_routing_without_shortlist_ends():
    from langgraph.graph import END

    assert route_after_matchmaker({"shortlist": []}) == END
    assert route_after_matchmaker({"shortlist": [object()]}) == "scribe"


def test_commit_routing_maps_over_shortlist():
    from langgraph.graph import END

    assert route_after_commit({"current_index": 0, "shortlist": [1, 2]}) == "scribe"
    assert route_after_commit({"current_index": 2, "shortlist": [1, 2]}) == END


def test_rrf_fuses_rankings():
    fused = _rrf([["a", "b", "c"], ["b", "a"]])
    assert fused["a"] > fused["c"]  # a is high in both lists


def test_extract_json_handles_preamble():
    assert _extract_json('Sure! {"x": 1} done') == '{"x": 1}'
