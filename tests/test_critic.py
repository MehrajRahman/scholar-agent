"""Critic node + new deep-research settings (offline: only the no-network guards)."""
from __future__ import annotations

from scholar.agents.critic import critic_node
from scholar.config import get_settings
from scholar.schemas import Opportunity, OpportunityKind


def _opp(deadline: str | None) -> Opportunity:
    return Opportunity(
        title="PhD in ML",
        kind=OpportunityKind.phd_position,
        source_url="http://a.edu/1",
        deadline=deadline,
    )


async def test_critic_noop_when_no_opportunities():
    assert await critic_node({"opportunities": []}) == {}


async def test_critic_noop_when_all_have_deadlines():
    # No missing deadlines -> returns early, never touches the network/LLM.
    opps = [_opp("2027-01-01"), _opp("2027-06-30")]
    assert await critic_node({"opportunities": opps}) == {}


def test_new_settings_defaults():
    s = get_settings()
    assert s.deep_crawl_depth == 0          # single-page by default (laptop-safe)
    assert s.deep_crawl_max_pages >= 1
    assert s.critic_max_enrich >= 0
    assert hasattr(s, "hf_token")           # optional HF token plumbed through
