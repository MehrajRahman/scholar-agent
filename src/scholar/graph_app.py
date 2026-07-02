"""LangGraph wiring — the deterministic State Machine from the blueprint.

                ┌─ fast ─► db_fetch ─┐
    profiler ─► │                    ├─► matchmaker -> scribe -> quality_gate
                └─ deep ─► scout ────┘                 ^            |
                                                       |  reject    | approve / exhausted
                                                       +-- (loop) --+--> commit --> (next | END)

A ``mode_router`` after the Profiler picks the source of opportunities: live web
research (Scout, deep mode) or the existing knowledge base (db_fetch, fast mode).
Both feed the same Matchmaker -> Scribe <-> Quality-Gate reflection loop, which
regenerates a draft until it is grounded or MAX_REFLECTION_LOOPS is hit.
"""
from __future__ import annotations

from functools import lru_cache

from langgraph.graph import END, StateGraph

from .agents import (
    critic_node,
    deep_scout_node,
    matchmaker_node,
    profiler_node,
    quality_gate_node,
    scribe_node,
)
from .agents.kit import kit_node
from .config import get_settings
from .kb import get_vectors
from .observability import get_logger
from .state import PipelineState

log = get_logger("graph")


# --- Control-flow nodes (cheap, no LLM) ----------------------------------

def db_fetch_node(state: PipelineState) -> dict:
    """Fast mode: load candidate opportunities straight from the knowledge base."""
    profile = state["profile"]
    try:
        opps = get_vectors().fetch_opportunities(
            profile.embedding_text(), top_k=max(30, get_settings().top_k_opportunities * 6)
        )
    except Exception as exc:  # noqa: BLE001
        return {"opportunities": [], "search_log": [f"db_fetch failed: {exc}"]}
    return {
        "opportunities": opps,
        "search_log": [f"fast: loaded {len(opps)} opportunities from DB"],
        "suggest_deep_research": len(opps) == 0,
    }


def commit_node(state: PipelineState) -> dict:
    """File the current draft and advance to the next shortlisted opportunity."""
    draft = state.get("draft")
    review = state.get("review")
    bundles = []
    if draft is not None:
        draft.approved = bool(review and review.approved)
        draft.revisions = state.get("revision_count", 0)
        bundles.append(draft)
    return {
        "bundles": bundles,
        "current_index": state.get("current_index", 0) + 1,
        "draft": None,
        "review": None,
        "revision_count": 0,
    }


# --- Conditional edges ----------------------------------------------------

def mode_router(state: PipelineState) -> str:
    """Pick the opportunity source: live Deep Scout (deep) or the DB (fast)."""
    return "db_fetch" if state.get("mode") == "fast" else "deep_scout"


def route_after_matchmaker(state: PipelineState) -> str:
    return "scribe" if state.get("shortlist") else END


def route_after_quality_gate(state: PipelineState) -> str:
    """Loop back to the Scribe on rejection, until the retry budget is spent."""
    review = state.get("review")
    revisions = state.get("revision_count", 0)
    if review and review.approved:
        return "commit"
    if revisions >= get_settings().max_reflection_loops:
        log.warning("reflection_budget_exhausted", revisions=revisions)
        return "commit"  # ship best-effort + flag as unapproved
    return "scribe"


def route_after_commit(state: PipelineState) -> str:
    """Map over the shortlist: more items -> draft next; done -> kit (if requested) or END."""
    if state.get("current_index", 0) < len(state.get("shortlist", [])):
        return "scribe"
    return "kit" if state.get("artifacts_requested") else END


# --- Graph factory --------------------------------------------------------

def build_graph():
    g = StateGraph(PipelineState)

    g.add_node("profiler", profiler_node)
    g.add_node("db_fetch", db_fetch_node)
    g.add_node("deep_scout", deep_scout_node)
    g.add_node("critic", critic_node)
    g.add_node("matchmaker", matchmaker_node)
    g.add_node("scribe", scribe_node)
    g.add_node("quality_gate", quality_gate_node)
    g.add_node("commit", commit_node)
    g.add_node("kit", kit_node)

    g.set_entry_point("profiler")
    g.add_conditional_edges(
        "profiler", mode_router, {"deep_scout": "deep_scout", "db_fetch": "db_fetch"}
    )
    # Deep path passes through the Critic (deadline enrichment); fast path is lean.
    g.add_edge("deep_scout", "critic")
    g.add_edge("critic", "matchmaker")
    g.add_edge("db_fetch", "matchmaker")
    g.add_conditional_edges("matchmaker", route_after_matchmaker, {"scribe": "scribe", END: END})
    g.add_edge("scribe", "quality_gate")
    g.add_conditional_edges(
        "quality_gate", route_after_quality_gate, {"scribe": "scribe", "commit": "commit"}
    )
    g.add_conditional_edges(
        "commit", route_after_commit, {"scribe": "scribe", "kit": "kit", END: END}
    )
    g.add_edge("kit", END)

    return g.compile()


@lru_cache
def get_app():
    """Compiled, cached LangGraph app (checkpointer can be added for resumability)."""
    return build_graph()


async def run_pipeline(
    raw_documents: list[str],
    user_query: str = "",
    mode: str = "deep",
    artifacts: list[str] | None = None,
) -> PipelineState:
    """Convenience entry point: run the whole pipeline to completion.

    ``mode="deep"`` runs the Deep Scout; ``mode="fast"`` uses the existing DB only.
    ``artifacts`` is the list of extra ``ArtifactType`` values for the best match.
    """
    app = get_app()
    initial: PipelineState = {
        "raw_documents": raw_documents,
        "user_query": user_query,
        "mode": mode,
        "artifacts_requested": artifacts or [],
        "current_index": 0,
        "revision_count": 0,
    }
    return await app.ainvoke(initial)
