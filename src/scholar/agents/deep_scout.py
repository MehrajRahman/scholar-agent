"""Deep Scout — the recursive live-research agent (Phase 2).

Implements the GPT-Researcher / open_deep_research pattern, tuned to emit
*opportunities into the knowledge base* rather than a prose report:

    PLAN -> [ GATHER -> EXTRACT -> REFLECT ]×depth -> VERIFY -> WRITE-BACK

Bounded by DEEP_BREADTH (sub-questions/round) and DEEP_DEPTH (rounds) so a single
run can't exhaust a free-tier token budget. Crawl4AI does the heavy crawling
(falling back to trafilatura), and every discovered opportunity is content-hash
deduped + version-tracked on write-back, then a freshness sweep runs.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone

from ..config import get_settings
from ..kb import get_graph, get_vectors
from ..llm import Role, get_llm
from ..observability import get_logger
from ..prompts import system_for
from ..schemas import Opportunity
from ..state import PipelineState
from ..tools import crawl_many, openalex_professor, web_search
from ..tools.ranking import rank_hits  # cross-encoder relevance + reputation
from ..tools.scraper import _is_junk  # shared quality gate, reused on raw_content
from .scout import OpportunityList, QueryPlan  # reuse the shared research schemas

log = get_logger("agent.deep_scout")


def _future_or_unknown(deadline: str | None) -> bool:
    """Keep opportunities whose deadline is in the future or simply unstated."""
    if not deadline:
        return True
    try:
        return deadline >= date.today().isoformat()
    except Exception:  # noqa: BLE001
        return True


# Per extraction request we keep enough context that funding/eligibility/deadline
# (usually lower on the page) survive, while staying under free-tier per-request
# token caps (Groq returns 413 on oversized requests).
_PAGE_CHARS = 6000       # max clean text kept per page (was 3500 — cut key details)
_BATCH_PAGES = 2         # pages per extraction request
_BATCH_CHARS = 11000     # hard cap on a single request's page context


def _collect_ordered_hits(results: list[list[dict]], cap: int, query_text: str) -> list[dict]:
    """Dedupe hits by URL, rank by relevance×reputation, then cap fan-out."""
    hits: dict[str, dict] = {}
    for batch in results:
        for h in batch:
            u = h.get("url")
            if u and u not in hits:
                hits[u] = h
    return rank_hits(query_text, list(hits.values()))[:cap]


def _split_raw_vs_crawl(ordered: list[dict]) -> tuple[list[tuple[str, str]], list[str]]:
    """Use Tavily's server-rendered raw_content where present (covers JS + PDFs);
    return ``(pages, urls_still_needing_a_crawl)``."""
    pages: list[tuple[str, str]] = []
    to_crawl: list[str] = []
    for h in ordered:
        rc = (h.get("raw_content") or "").strip()
        if rc and not _is_junk(rc):
            pages.append((h["url"], rc[:_PAGE_CHARS]))
        else:
            to_crawl.append(h["url"])
    return pages, to_crawl


async def _extract_pages(llm, pages: list[tuple[str, str]]) -> list[Opportunity]:
    """Batched structured extraction over gathered pages."""
    opps: list[Opportunity] = []
    system = system_for("scout_extractor", Role.FAST)
    for i in range(0, len(pages), _BATCH_PAGES):
        chunk = pages[i : i + _BATCH_PAGES]
        context = "\n\n".join(f"SOURCE_URL: {u}\n{t}" for u, t in chunk)[:_BATCH_CHARS]
        try:
            extracted = await llm.structured(Role.FAST, system, context, OpportunityList)
            opps.extend(extracted.opportunities)
        except Exception as exc:  # noqa: BLE001 - one bad batch shouldn't sink the round
            log.warning("extract_batch_failed", error=str(exc))
    return opps


async def _gather_and_extract(
    llm, queries: list[str], cap: int, query_text: str
) -> list[Opportunity]:
    """One research round: search -> rank -> (raw_content | crawl) -> extraction."""
    results = await asyncio.gather(*(web_search(q) for q in queries))
    ordered = _collect_ordered_hits(results, cap, query_text)
    if not ordered:
        return []
    pages, to_crawl = _split_raw_vs_crawl(ordered)
    n_raw = len(pages)
    if to_crawl:
        pages.extend(await crawl_many(to_crawl, max_chars=_PAGE_CHARS))
    log.info("gather", urls=len(ordered), from_raw=n_raw, crawled=len(pages) - n_raw)
    if not pages:
        return []
    return await _extract_pages(llm, pages)


async def deep_scout_node(state: PipelineState) -> dict:
    profile = state["profile"]
    s = get_settings()
    llm = get_llm()

    # 1. PLAN — initial breadth of sub-questions.
    plan = await llm.structured(
        Role.HEAVY, system_for("deep_planner", Role.HEAVY), profile.model_dump_json(), QueryPlan
    )
    queries = plan.queries[: s.deep_breadth]
    log.info("deep_plan", queries=len(queries))

    # Relevance query for ranking candidate pages: the applicant's profile text.
    query_text = profile.embedding_text()
    found: dict[str, Opportunity] = {}
    explored: list[str] = []

    # 2. depth rounds of GATHER -> EXTRACT -> REFLECT.
    for round_i in range(s.deep_depth):
        if not queries:
            break
        explored.extend(queries)
        opps = await _gather_and_extract(llm, queries, s.deep_max_pages, query_text)
        for o in opps:
            found[o.id] = o  # content-addressed dedup across rounds
        log.info("deep_round", round=round_i, new=len(opps), total=len(found))

        if round_i == s.deep_depth - 1:
            break
        # REFLECT — what's still missing?
        reflect_input = (
            f"GOAL:\n{profile.model_dump_json()}\n\n"
            f"EXPLORED:\n{explored}\n\n"
            f"FOUND ({len(found)}):\n{[o.title for o in found.values()]}"
        )
        followup = await llm.structured(
            Role.HEAVY, system_for("deep_reflect", Role.HEAVY), reflect_input, QueryPlan
        )
        queries = [q for q in followup.queries if q not in explored][: s.deep_breadth]

    # 3. VERIFY + enrich professors against their real OpenAlex footprint.
    now = datetime.now(timezone.utc).isoformat()
    fresh = [o for o in found.values() if _future_or_unknown(o.deadline)]

    async def enrich(o: Opportunity) -> Opportunity:
        o.retrieved_at = now
        if o.professor and o.professor.name:
            rec = await openalex_professor(o.professor.name)
            if rec:
                o.professor.openalex_id = rec["openalex_id"]
                o.professor.research_summary = rec["research_summary"]
                o.professor.recent_works = rec["recent_works"]
                o.professor.university = o.professor.university or rec.get("institution")
        return o

    fresh = list(await asyncio.gather(*(enrich(o) for o in fresh)))

    # 4. WRITE-BACK — version-tracked upsert + freshness sweep.
    graph = get_graph()
    get_vectors().upsert(fresh)
    await asyncio.gather(*(graph.upsert_opportunity(o) for o in fresh))
    sweep = await graph.expire_sweep(s.stale_ttl_days)

    log.info("deep_done", kept=len(fresh), sweep=sweep)
    return {
        "opportunities": fresh,
        "search_log": [
            f"deep: {len(fresh)} fresh opps over {len(explored)} queries; sweep={sweep}"
        ],
    }
