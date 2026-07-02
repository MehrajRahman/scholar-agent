"""Agent 2 — The Scout. Plans searches, gathers real-world evidence, extracts
structured opportunities, then indexes them into the graph + vector store.

This is the air-gap boundary: the *tools* hit the internet (in the Hands
container), and only clean text is handed back to the model.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ..kb import get_graph, get_vectors
from ..llm import Role, get_llm
from ..observability import get_logger
from ..prompts import system_for
from ..schemas import Opportunity
from ..state import PipelineState
from ..tools import fetch_clean_text, openalex_professor, openalex_works, web_search
from ..tools.ranking import rank_hits
from ..tools.scraper import _is_junk

log = get_logger("agent.scout")


class QueryPlan(BaseModel):
    queries: list[str] = Field(min_length=1, max_length=8)


class OpportunityList(BaseModel):
    opportunities: list[Opportunity] = Field(default_factory=list)


async def _gather_context(profile, plan: QueryPlan) -> tuple[str, int]:
    """Search → dedupe + prioritise authoritative sources → page text (Tavily
    raw_content where available, else crawl) + related OpenAlex works.

    Returns ``(context, n_pages)``.
    """
    search_results = await asyncio.gather(*(web_search(q) for q in plan.queries))
    hits: dict[str, dict] = {}
    for batch in search_results:
        for hit in batch:
            u = hit.get("url")
            if u and u not in hits:
                hits[u] = hit
    ordered = rank_hits(profile.embedding_text(), list(hits.values()))[:12]

    async def _page_text(h: dict) -> str:
        rc = (h.get("raw_content") or "").strip()
        if rc and not _is_junk(rc):
            return rc[:8000]
        return await fetch_clean_text(h["url"])

    page_texts, works = await asyncio.gather(
        asyncio.gather(*(_page_text(h) for h in ordered)),
        asyncio.gather(*(openalex_works(t) for t in profile.research_interests[:3])),
    )
    context = "\n\n".join(
        f"SOURCE_URL: {h['url']}\n{txt}" for h, txt in zip(ordered, page_texts) if txt
    )
    context += "\n\nRELATED OPENALEX WORKS:\n" + str(works)
    return context, len(ordered)


async def scout_node(state: PipelineState) -> dict:
    profile = state["profile"]
    llm = get_llm()

    # 1. Plan focused queries from the profile.
    plan = await llm.structured(
        Role.FAST,
        system_for("scout_planner", Role.FAST),
        profile.model_dump_json(),
        QueryPlan,
    )
    log.info("scout_plan", n_queries=len(plan.queries))

    # 2-3. Gather evidence: search → prioritise authoritative sources → page text
    #      (Tavily raw_content or crawl) + related OpenAlex works.
    context, n_urls = await _gather_context(profile, plan)

    if not context.strip():
        return {"search_log": ["scout: no usable context retrieved"], "opportunities": []}

    # 4. Extract structured opportunities from the gathered evidence.
    extracted = await llm.structured(
        Role.FAST, system_for("scout_extractor", Role.FAST), context[:24000], OpportunityList
    )
    opps = extracted.opportunities
    now = datetime.now(timezone.utc).isoformat()

    # 5. Ground each professor against their REAL OpenAlex footprint.
    async def enrich(o: Opportunity) -> Opportunity:
        o.retrieved_at = now
        if o.professor and o.professor.name:
            record = await openalex_professor(o.professor.name)
            if record:
                o.professor.openalex_id = record["openalex_id"]
                o.professor.research_summary = record["research_summary"]
                o.professor.recent_works = record["recent_works"]
                o.professor.university = o.professor.university or record.get("institution")
        return o

    opps = await asyncio.gather(*(enrich(o) for o in opps))

    # 6. Index into the KB (Knowledge Graph Construction, blueprint step 3).
    graph = get_graph()
    get_vectors().upsert(list(opps))
    await asyncio.gather(*(graph.upsert_opportunity(o) for o in opps))

    log.info("scout_done", found=len(opps))
    return {
        "opportunities": list(opps),
        "search_log": [f"scout: {len(opps)} opportunities from {n_urls} pages"],
    }
