"""Agent 5 — The Quality Gate. The anti-hallucination validator (blueprint §2).

Decomposes the draft into atomic claims and checks each against the applicant
profile and the professor's real record. Emits a GroundednessReport; the graph's
conditional edge sends the draft back to the Scribe on rejection.
"""
from __future__ import annotations

from ..kb import get_graph
from ..llm import Role, get_llm
from ..observability import get_logger
from ..prompts import system_for
from ..schemas import GroundednessReport
from ..state import PipelineState

log = get_logger("agent.quality_gate")


async def quality_gate_node(state: PipelineState) -> dict:
    draft = state.get("draft")
    if draft is None:
        return {}

    profile = state["profile"]
    prof_record = await get_graph().professor_record(draft.opportunity_id)

    artifact = (
        f"COLD EMAIL:\nSubject: {draft.cold_email.subject}\n{draft.cold_email.body}\n\n"
        f"SOP:\n{draft.sop.body}"
    )
    user = (
        f"GENERATED ARTIFACT:\n{artifact}\n\n"
        f"APPLICANT PROFILE (evidence):\n{profile.model_dump_json()}\n\n"
        f"PROFESSOR REAL RECORD (evidence):\n{prof_record}"
    )

    report = await get_llm().structured(
        Role.HEAVY, system_for("quality_gate", Role.HEAVY), user, GroundednessReport
    )
    log.info(
        "quality_gate",
        approved=report.approved,
        score=round(report.score, 2),
        hallucinations=len(report.hallucinations),
    )
    return {"review": report, "revision_count": state.get("revision_count", 0) + 1}
