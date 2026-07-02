"""Agent 1 — The Profiler. Messy CV/transcript text -> StudentProfile JSON."""
from __future__ import annotations

from ..kb import get_graph
from ..llm import Role, get_llm
from ..observability import get_logger
from ..prompts import system_for
from ..schemas import StudentProfile
from ..state import PipelineState

log = get_logger("agent.profiler")


async def profiler_node(state: PipelineState) -> dict:
    docs = state.get("raw_documents", [])
    if not docs:
        return {"errors": ["profiler: no documents to parse"]}

    user = (
        "APPLICANT DOCUMENTS:\n\n"
        + "\n\n---\n\n".join(docs)
        + (f"\n\nADDITIONAL CONSTRAINTS: {state['user_query']}" if state.get("user_query") else "")
    )

    profile = await get_llm().structured(
        Role.FAST, system_for("profiler", Role.FAST), user, StudentProfile
    )
    log.info("profiled", name=profile.full_name, skills=len(profile.skills))

    # Persist the applicant node so the Matchmaker can run graph traversals.
    await get_graph().upsert_student(profile)
    return {"profile": profile}
