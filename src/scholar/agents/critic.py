"""The Critic — verifies/enriches freshly-discovered opportunities.

Right now it does one high-value thing: for opportunities that were extracted
*without* a deadline, it runs a small, bounded set of targeted web searches to
try to fill the deadline in. A scholarship with a known deadline is far more
actionable than one without.

Deliberate non-goal: it does NOT hard-reject opportunities on scraped
eligibility metadata (GPA/region/funding). That data is frequently missing or
wrong, and hard-gating on it previously produced empty shortlists — the
Matchmaker already folds eligibility in as a *soft* score. Missing data means
"unverified", not "ineligible".
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ..config import get_settings
from ..llm import Role, get_llm
from ..observability import get_logger
from ..schemas import Opportunity
from ..state import PipelineState
from ..tools import web_search

log = get_logger("agent.critic")

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DEADLINE_SYSTEM = (
    "You extract the single application DEADLINE for the given opportunity from "
    "the evidence. Respond with a JSON object {\"deadline\": \"YYYY-MM-DD\"} if a "
    "clear deadline is stated, or {\"deadline\": null} otherwise. Never guess a date."
)


class _DeadlineGuess(BaseModel):
    deadline: str | None = Field(None, description="ISO date YYYY-MM-DD, or null")


async def _find_deadline(opp: Opportunity) -> str | None:
    """Targeted search + extraction for one opportunity's missing deadline."""
    query = f"{opp.title} {opp.university or ''} application deadline".strip()
    hits = await web_search(query, max_results=3)
    evidence = "\n".join(
        (h.get("raw_content") or h.get("snippet") or "")[:2000] for h in hits
    ).strip()
    if not evidence:
        return None
    guess = await get_llm().structured(
        Role.FAST,
        _DEADLINE_SYSTEM,
        f"OPPORTUNITY: {opp.title} ({opp.university or 'unknown'})\nEVIDENCE:\n{evidence[:6000]}",
        _DeadlineGuess,
    )
    d = (guess.deadline or "").strip()
    return d if _ISO_DATE.match(d) else None


async def critic_node(state: PipelineState) -> dict:
    """Fill in missing deadlines for up to ``CRITIC_MAX_ENRICH`` opportunities."""
    budget = get_settings().critic_max_enrich
    if budget <= 0:
        return {}
    missing = [o for o in state.get("opportunities", []) if not o.deadline][:budget]
    if not missing:
        return {}

    filled = 0
    for opp in missing:
        try:
            deadline = await _find_deadline(opp)
        except Exception as exc:  # noqa: BLE001 - one failure shouldn't sink the node
            log.warning("critic_enrich_failed", opp=opp.title, error=str(exc))
            continue
        if deadline:
            opp.deadline = deadline  # mutate in place — same object as in state
            filled += 1

    log.info("critic", checked=len(missing), filled=filled)
    return {"search_log": [f"critic: filled {filled}/{len(missing)} missing deadlines"]}
