"""Knowledge-base browsing: the read-only catalog over everything the surfer
and watchlists have collected. Auth-gated for consistency with the rest of the
web app (and because Save-to-pipeline needs a user anyway)."""
from __future__ import annotations

from fastapi import APIRouter

from ..auth.deps import CurrentUser
from ..kb import get_vectors

router = APIRouter(tags=["kb"])


def _card(o) -> dict:
    """Card-shaped view of an Opportunity for the Browse page."""
    return {
        "id": o.id,
        "title": o.title,
        "kind": o.kind.value,
        "university": o.university,
        "deadline": o.deadline,
        "fully_funded": o.funding.is_fully_funded,
        "source_url": o.source_url,
        "description": (o.description or "")[:300],
        "professor": o.professor.name if o.professor else None,
        "status": o.status.value,
        "retrieved_at": o.retrieved_at,
    }


@router.get("/kb/opportunities")
def list_kb_opportunities(user: CurrentUser) -> list[dict]:
    """Everything currently in the KB, expired excluded, deadline-soonest first
    (unknown deadlines last, newest-retrieved first within them)."""
    opps = [o for o in get_vectors().scroll_all() if o.status.value != "expired"]
    # Two stable sorts: newest-retrieved first, then dated-before-undated with
    # the soonest deadline on top (ties keep the newest-first order).
    opps.sort(key=lambda o: o.retrieved_at or "", reverse=True)
    opps.sort(key=lambda o: (o.deadline is None, o.deadline or "9999-12-31"))
    return [_card(o) for o in opps]
