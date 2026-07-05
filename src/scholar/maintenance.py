"""Knowledge-base freshness & lean retention.

Two operations, deliberately split by cost:

* ``sweep_and_prune`` — CHEAP, no LLM. Marks stale/expired opportunities, then
  *deletes* past-deadline ones from Neo4j **and** Qdrant. Keeps the KB small and
  current (a scholarship board shouldn't hoard last year's dead calls). Safe to
  run daily / on every restart.
* ``refresh`` — EXPENSIVE (deep research + LLM). Discovers new opportunities and
  updates changed ones (content-hash dedup on write-back). Only runs in the daily
  job when a query is configured, so it never silently burns a free-tier budget.

The daily scheduler lives in the API lifespan; these are the reusable units.
"""
from __future__ import annotations

from datetime import date, timedelta

from .config import get_settings
from .kb import get_graph, get_vectors
from .observability import get_logger
from .state import PipelineState

log = get_logger("maintenance")


async def sweep_and_prune() -> dict:
    """Mark stale/expired, then delete past-deadline opportunities from both stores."""
    s = get_settings()
    graph = get_graph()
    swept = await graph.expire_sweep(s.stale_ttl_days)
    cutoff = (date.today() - timedelta(days=max(0, s.expired_grace_days))).isoformat()
    pruned_ids = await graph.prune_expired(cutoff)
    vectors_deleted = get_vectors().delete_by_ids(pruned_ids)
    result = {"swept": swept, "pruned": len(pruned_ids), "vectors_deleted": vectors_deleted}
    log.info("maintenance_sweep", **result)
    return result


async def refresh(query: str) -> dict:
    """Bounded deep-research pass to pull in new/changed opportunities.

    Reuses the Deep Scout (which writes back with versioned, content-hash dedup),
    so re-discoveries update in place rather than duplicating.
    """
    from .agents import deep_scout_node
    from .schemas import StudentProfile

    profile = StudentProfile(
        full_name="daily-refresh", research_interests=[query], target_degree="PhD"
    )
    state: PipelineState = {
        "profile": profile, "mode": "deep", "current_index": 0, "revision_count": 0
    }
    out = await deep_scout_node(state)
    n = len(out.get("opportunities", []))
    log.info("maintenance_refresh", query=query, discovered=n)
    return {"discovered": n}


async def run_daily() -> dict:
    """One daily cycle: always sweep+prune; refresh only if a query is configured."""
    result = await sweep_and_prune()
    query = get_settings().maintenance_refresh_query
    if query:
        result["refresh"] = await refresh(query)
    return result
