"""Agent 4 — The Scribe. Drafts a grounded cold email + SOP for one opportunity.

Reads any prior Quality-Gate feedback from state so the reflection loop actually
*improves* the draft instead of regenerating blindly.
"""
from __future__ import annotations

from pydantic import BaseModel

from ..kb import get_graph
from ..llm import Role, get_llm
from ..observability import get_logger
from ..prompts import system_for
from ..schemas import ColdEmail, SOPDraft, SynthesisBundle
from ..state import PipelineState

log = get_logger("agent.scribe")


class ScribeOutput(BaseModel):
    cold_email: ColdEmail
    sop: SOPDraft


async def scribe_node(state: PipelineState) -> dict:
    shortlist = state.get("shortlist", [])
    idx = state.get("current_index", 0)
    if idx >= len(shortlist):
        return {}  # nothing left to write; router will end synthesis

    opp = shortlist[idx]
    profile = state["profile"]
    match = next((m for m in state.get("matches", []) if m.opportunity_id == opp.id), None)

    # Ground professor claims in the real record stored by the Scout.
    prof_record = await get_graph().professor_record(opp.id)
    feedback = ""
    review = state.get("review")
    if review and not review.approved:
        feedback = (
            "\n\nREVIEWER FEEDBACK — fix exactly these issues:\n"
            + review.feedback
            + "\nHallucinations to remove: "
            + "; ".join(review.hallucinations)
        )

    user = (
        f"APPLICANT PROFILE:\n{profile.model_dump_json()}\n\n"
        f"OPPORTUNITY:\n{opp.model_dump_json()}\n\n"
        f"PROFESSOR REAL RECORD (only ground professor claims in this):\n{prof_record}"
        f"{feedback}"
    )

    out = await get_llm().structured(
        Role.SCRIBE, system_for("scribe", Role.SCRIBE), user, ScribeOutput, max_tokens=3000
    )
    out.sop.word_count = len(out.sop.body.split())

    revisions = state.get("revision_count", 0)
    bundle = SynthesisBundle(
        opportunity_id=opp.id,
        opportunity_title=opp.title,
        score=match.score if match else 0,
        cold_email=out.cold_email,
        sop=out.sop,
        revisions=revisions,
    )
    log.info("drafted", opp=opp.title, revision=revisions)
    return {"draft": bundle}
