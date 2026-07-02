"""API contract tests: request models, payload shapes, and route registration.

No server or DB needed — we test the pure request/response plumbing.
"""
from __future__ import annotations

from scholar.api.main import (
    DraftRequest,
    RunRequest,
    _progress_payload,
    _result_payload,
    app,
)


def test_run_request_defaults():
    r = RunRequest(documents=["cv text"])
    assert r.mode == "deep" and r.query == "" and r.artifacts == []


def test_draft_request_defaults():
    d = DraftRequest(profile={"full_name": "x"}, opportunity_id="abc123")
    assert d.artifacts == [] and d.opportunity_id == "abc123"


def test_result_payload_has_all_keys():
    p = _result_payload({})
    assert {
        "profile", "matches", "bundles", "kit_artifacts",
        "suggest_deep_research", "errors",
    } <= set(p)


def test_progress_payload_counts():
    p = _progress_payload({"opportunities": [1, 2], "matches": [1], "bundles": []})
    assert p["opportunities"] == 2 and p["matches"] == 1 and p["bundles"] == 0


def test_draft_route_registered():
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/draft" in paths
    assert "/pipeline/stream" in paths and "/ingest" in paths
