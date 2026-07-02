"""Phase-3 offline tests: Application Kit registry, ICS builder, graph routing."""
from __future__ import annotations

from scholar.agents.kit import ARTIFACT_SPECS
from scholar.graph_app import build_graph, route_after_commit
from scholar.ics import build_ics
from scholar.schemas import Artifact, ArtifactType


def test_kit_node_in_graph():
    nodes = set(build_graph().get_graph().nodes)
    assert "kit" in nodes


def test_route_after_commit_to_kit_only_when_requested():
    done = {"current_index": 1, "shortlist": [1], "artifacts_requested": ["professor_dossier"]}
    assert route_after_commit(done) == "kit"
    done_no_kit = {"current_index": 1, "shortlist": [1], "artifacts_requested": []}
    from langgraph.graph import END

    assert route_after_commit(done_no_kit) == END
    more = {"current_index": 0, "shortlist": [1, 2], "artifacts_requested": ["x"]}
    assert route_after_commit(more) == "scribe"


def test_artifact_specs_cover_extended_types_only():
    # Core types are produced by the Scribe, not the kit registry.
    assert ArtifactType.cold_email not in ARTIFACT_SPECS
    assert ArtifactType.sop not in ARTIFACT_SPECS
    # The richer kit types are all present.
    for t in [
        ArtifactType.motivation_letter,
        ArtifactType.professor_dossier,
        ArtifactType.interview_prep,
        ArtifactType.deadline_checklist,
        ArtifactType.cv_tailoring,
    ]:
        assert t in ARTIFACT_SPECS and ARTIFACT_SPECS[t]


def test_ics_builder_well_formed():
    ics = build_ics(
        [
            {"title": "DAAD deadline", "date": "2026-10-31", "url": "http://daad.de"},
            {"title": "no date — skipped"},  # skipped (no date)
        ]
    )
    assert ics.startswith("BEGIN:VCALENDAR")
    assert ics.strip().endswith("END:VCALENDAR")
    assert "DTSTART;VALUE=DATE:20261031" in ics
    assert "SUMMARY:DAAD deadline" in ics
    assert ics.count("BEGIN:VEVENT") == 1  # the dateless entry was skipped


def test_artifact_model_roundtrip():
    a = Artifact(type=ArtifactType.linkedin_note, title="Note", body="Hi prof", references=["cv"])
    assert Artifact.model_validate_json(a.model_dump_json()).type == ArtifactType.linkedin_note
