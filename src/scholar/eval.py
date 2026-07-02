"""Evaluation harness (Phase 6) — measure quality so prompt/model changes are
decisions backed by numbers, not vibes.

Pure metric functions (offline-testable). The CLI in ``scripts/eval.py`` runs a
pipeline result against a small golden set and prints these.

Metrics:
  * precision@k — of the top-k matched opportunities, how many are in the gold set.
  * grounding_rate — fraction of synthesised bundles the Quality Gate approved.
  * freshness_lag  — mean days since each shortlisted opp was last verified.
"""
from __future__ import annotations

from datetime import datetime, timezone


def precision_at_k(predicted_ids: list[str], gold_ids: set[str], k: int = 5) -> float:
    """Fraction of the top-k predictions that are in the gold set."""
    if k <= 0:
        return 0.0
    topk = predicted_ids[:k]
    if not topk:
        return 0.0
    hits = sum(1 for pid in topk if pid in gold_ids)
    return hits / len(topk)


def grounding_rate(bundles: list[dict]) -> float:
    """Fraction of bundles marked approved by the Quality Gate."""
    if not bundles:
        return 0.0
    return sum(1 for b in bundles if b.get("approved")) / len(bundles)


def freshness_lag_days(opportunities: list[dict], now: datetime | None = None) -> float:
    """Mean age (days) of ``last_verified_at`` across opportunities; -1 if none."""
    now = now or datetime.now(timezone.utc)
    ages = []
    for o in opportunities:
        ts = o.get("last_verified_at")
        if not ts:
            continue
        try:
            seen = datetime.fromisoformat(ts)
            ages.append((now - seen).total_seconds() / 86400.0)
        except ValueError:
            continue
    return sum(ages) / len(ages) if ages else -1.0


def evaluate(result: dict, gold_ids: set[str], k: int = 5) -> dict:
    """Score one pipeline result dict (as produced by the CLI/API)."""
    matches = result.get("matches", [])
    predicted = [m.get("opportunity_id", "") for m in matches]
    return {
        "precision_at_k": round(precision_at_k(predicted, gold_ids, k), 3),
        "grounding_rate": round(grounding_rate(result.get("bundles", [])), 3),
        "freshness_lag_days": round(
            freshness_lag_days([m for m in matches if isinstance(m, dict)]), 1
        ),
        "n_matches": len(matches),
        "n_bundles": len(result.get("bundles", [])),
    }
