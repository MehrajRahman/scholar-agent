"""Phase-6 offline tests: the evaluation metric functions."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scholar.eval import evaluate, freshness_lag_days, grounding_rate, precision_at_k


def test_precision_at_k():
    pred = ["a", "b", "c", "d", "e"]
    gold = {"a", "c", "z"}
    assert precision_at_k(pred, gold, k=5) == 2 / 5
    assert precision_at_k(pred, gold, k=2) == 1 / 2  # only a,b -> a hits
    assert precision_at_k([], gold, k=5) == 0.0


def test_grounding_rate():
    bundles = [{"approved": True}, {"approved": False}, {"approved": True}]
    assert grounding_rate(bundles) == 2 / 3
    assert grounding_rate([]) == 0.0


def test_freshness_lag():
    now = datetime(2026, 6, 26, tzinfo=timezone.utc)
    opps = [
        {"last_verified_at": (now - timedelta(days=2)).isoformat()},
        {"last_verified_at": (now - timedelta(days=4)).isoformat()},
        {"last_verified_at": None},  # ignored
    ]
    assert freshness_lag_days(opps, now=now) == 3.0
    assert freshness_lag_days([], now=now) == -1.0


def test_evaluate_end_to_end():
    result = {
        "matches": [
            {"opportunity_id": "a"},
            {"opportunity_id": "b"},
        ],
        "bundles": [{"approved": True}],
    }
    scores = evaluate(result, gold_ids={"a"}, k=2)
    assert scores["precision_at_k"] == 0.5
    assert scores["grounding_rate"] == 1.0
    assert scores["n_matches"] == 2
