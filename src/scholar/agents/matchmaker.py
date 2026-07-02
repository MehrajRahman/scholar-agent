"""Agent 3 — The Matchmaker. GraphRAG scoring (blueprint step 4).

Fuses three orthogonal signals so no single failure mode dominates:
  * semantic_score — hybrid dense+BM25 retrieval, cross-encoder reranked.
  * graph_score    — shared-skill path coverage in Neo4j.
  * eligibility    — hard constraints (GPA/region/funding) as a graph gate.
A HEAVY model then turns the signals into a calibrated 0-100 score + rationale.
"""
from __future__ import annotations

import asyncio
import json

from ..config import get_settings
from ..kb import get_graph, get_vectors
from ..llm import Role, get_llm
from ..observability import get_logger
from ..prompts import system_for
from ..schemas import MatchResult
from ..state import PipelineState

log = get_logger("agent.matchmaker")


def _funding_summary(fund) -> str:
    if fund.is_fully_funded:
        return "Fully funded"
    if fund.stipend_amount:
        return f"{fund.stipend_amount:g} {fund.currency}"
    return ""


def _attach_display(result: MatchResult, opp) -> None:
    """Copy source link + key facts from the Opportunity onto the match for the UI."""
    result.source_url = opp.source_url
    result.university = opp.university
    result.department = opp.department
    result.kind = opp.kind.value
    result.deadline = opp.deadline
    result.funding_summary = _funding_summary(opp.funding)
    result.professor_name = opp.professor.name if opp.professor else ""
    result.description = (opp.description or "")[:400]


async def matchmaker_node(state: PipelineState) -> dict:
    profile = state["profile"]
    settings = get_settings()
    graph = get_graph()
    llm = get_llm()

    # Candidate pool = this run's fresh opps + the most relevant existing KB
    # entries. Deep mode write-back accumulates opportunities across runs, so the
    # matchmaker must score against the whole relevant pool — not only the handful
    # scouted this run (otherwise retrieval pulls older KB points that aren't in
    # `opps` and the intersection comes back empty => scored: 0).
    opps = {o.id: o for o in state.get("opportunities", [])}
    pool_k = max(settings.top_k_opportunities * 6, 30)
    try:
        for o in get_vectors().fetch_opportunities(profile.embedding_text(), top_k=pool_k):
            opps.setdefault(o.id, o)
    except Exception as exc:  # noqa: BLE001
        log.warning("kb_pool_fetch_failed", error=str(exc))
    if not opps:
        return {"matches": [], "shortlist": []}

    # Retrieval ranking over the full candidate pool.
    retrieved = get_vectors().hybrid_search(profile.embedding_text(), top_k=len(opps))
    max_score = max((s for _, s in retrieved), default=1.0) or 1.0
    semantic = {oid: s / max_score for oid, s in retrieved}

    # Score only the most promising candidates with the expensive model.
    ranked_ids = [oid for oid, _ in retrieved if oid in opps][: settings.top_k_opportunities * 2]

    async def score(oid: str) -> MatchResult:
        opp = opps[oid]
        graph_score, eligible = await asyncio.gather(
            graph.graph_proximity(profile, oid),
            graph.eligible(profile, oid),
        )
        sem = semantic.get(oid, 0.0)
        signals = {
            "semantic_score": round(sem, 3),
            "graph_score": round(graph_score, 3),
            "eligible": eligible,
        }
        user = (
            f"APPLICANT:\n{profile.model_dump_json()}\n\n"
            f"OPPORTUNITY:\n{opp.model_dump_json()}\n\n"
            f"RETRIEVAL SIGNALS:\n{json.dumps(signals)}"
        )
        result = await llm.structured(
            Role.HEAVY, system_for("matchmaker", Role.HEAVY), user, MatchResult
        )
        # Trust the deterministic signals over any model drift.
        result.opportunity_id = oid
        result.opportunity_title = opp.title
        result.semantic_score = sem
        result.graph_score = graph_score
        result.eligible = eligible
        _attach_display(result, opp)  # source link + key facts for the UI
        return result

    # Score concurrently, but never let one bad candidate sink the whole batch:
    # a model/validation failure on a single opp is dropped, not propagated.
    scored = await asyncio.gather(
        *(score(oid) for oid in ranked_ids), return_exceptions=True
    )
    matches: list[MatchResult] = []
    for oid, res in zip(ranked_ids, scored):
        if isinstance(res, BaseException):
            log.warning("score_failed", opportunity_id=oid, error=str(res))
            continue
        matches.append(res)
    matches = sorted(matches, key=lambda m: m.score, reverse=True)

    # Shortlist for drafting. Eligibility is a SOFT signal, not a hard gate:
    # opp.regions/fully_funded/min_gpa are scraped from messy web pages and are
    # often missing/wrong, so AND-ing on eligible wiped the shortlist (=> no
    # drafts). Prefer score>=threshold AND eligible; fall back to score-only;
    # last resort, draft the single best match so the user always gets output.
    threshold = settings.match_score_threshold
    k = settings.top_k_opportunities
    above = [m for m in matches if m.score >= threshold]
    chosen = [m for m in above if m.eligible] or above or matches[:1]
    shortlist = [opps[m.opportunity_id] for m in chosen][:k]

    log.info(
        "matched",
        scored=len(matches),
        shortlisted=len(shortlist),
        eligible=sum(1 for m in matches if m.eligible),
        above_threshold=len(above),
    )
    return {
        "matches": matches,
        "shortlist": shortlist,
        "current_index": 0,
        # In fast mode, a thin shortlist means the DB is stale/sparse -> go deep.
        "suggest_deep_research": not shortlist and state.get("mode") == "fast",
    }
