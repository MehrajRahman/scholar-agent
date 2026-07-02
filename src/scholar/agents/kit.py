"""The Application Kit stage (Phase 3).

After the per-opportunity email + SOP are drafted (and reflection-checked), this
node generates the *wider* application kit for the single best-scoring match:
motivation letter, CV-tailoring report, research-proposal outline, referee-
request kit, professor dossier, interview prep, deadline checklist (+ .ics),
LinkedIn note. Each is grounded in the profile + opportunity + real professor
record. Generated only on request, for the top match, to protect token budgets.
"""
from __future__ import annotations

from ..ics import build_ics
from ..kb import get_graph
from ..llm import Role, get_llm
from ..observability import get_logger
from ..prompts import system_for
from ..schemas import Artifact, ArtifactType
from ..state import PipelineState

log = get_logger("agent.kit")

# Per-type generation instruction. Core types (cold_email/sop) are produced by
# the Scribe, so they're intentionally absent here.
ARTIFACT_SPECS: dict[ArtifactType, str] = {
    ArtifactType.personal_statement: "Write a personal statement: narrative of background, motivation and fit. Ground every fact in the profile.",
    ArtifactType.motivation_letter: "Write a scholarship motivation/cover letter tailored to this specific scheme. No invented achievements.",
    ArtifactType.cv_tailoring: "Produce a CV-tailoring report: ATS keywords to add, sections to reorder, and honest gaps to address. SUGGEST only; never fabricate experience.",
    ArtifactType.research_proposal: "Draft a 1-page research-proposal outline aligned to the professor's ACTUAL research (use the record). Problem, approach, fit, expected contribution.",
    ArtifactType.recommendation_request: "Write a polite email asking a referee for a recommendation, plus a concise 'brag sheet' of the applicant's real achievements they can cite.",
    ArtifactType.professor_dossier: "Write an interview-prep dossier on the professor/lab using only the provided record: recent works, themes, likely group focus.",
    ArtifactType.interview_prep: "Produce 8 likely interview questions with grounded answer scaffolds (drawing on the profile and the lab's work).",
    ArtifactType.deadline_checklist: "Produce a per-application document checklist and a chronological deadline list for this opportunity.",
    ArtifactType.linkedin_note: "Write a <300-char LinkedIn connection note to the professor — specific, no flattery clichés.",
}

_KIT_SYSTEM = (
    "You are The Scribe producing an application-kit document. Ground every "
    "claim about the applicant in their profile and every claim about the "
    "professor/lab in the provided record. Do not invent shared interests, "
    "papers, or achievements. Output a single JSON object for the artifact."
)


async def kit_node(state: PipelineState) -> dict:
    requested = [
        ArtifactType(a)
        for a in state.get("artifacts_requested", [])
        if a in ArtifactType._value2member_map_ and a in {t.value for t in ARTIFACT_SPECS}
    ]
    bundles = state.get("bundles", [])
    if not requested or not bundles:
        return {}

    best = max(bundles, key=lambda b: b.score)
    opp = next((o for o in state.get("opportunities", []) if o.id == best.opportunity_id), None)
    profile = state["profile"]
    prof_record = await get_graph().professor_record(best.opportunity_id)
    llm = get_llm()

    artifacts: list[Artifact] = []
    for atype in requested:
        user = (
            f"TASK: {ARTIFACT_SPECS[atype]}\n\n"
            f"APPLICANT PROFILE:\n{profile.model_dump_json()}\n\n"
            f"OPPORTUNITY:\n{opp.model_dump_json() if opp else best.opportunity_title}\n\n"
            f"PROFESSOR REAL RECORD:\n{prof_record}"
        )
        try:
            art = await llm.structured(
                Role.SCRIBE, system_for("scribe", Role.SCRIBE) + "\n" + _KIT_SYSTEM, user, Artifact
            )
        except Exception as exc:  # noqa: BLE001 - one bad artifact shouldn't sink the kit
            log.warning("kit_artifact_failed", type=atype.value, error=str(exc))
            continue
        art.type = atype  # trust the request over model drift

        # Deadline checklist gets a ready-to-import calendar.
        if atype is ArtifactType.deadline_checklist and opp and opp.deadline:
            art.metadata["ics"] = build_ics(
                [{"title": f"Deadline: {opp.title}", "date": opp.deadline, "url": opp.source_url}]
            )
        artifacts.append(art)

    log.info("kit_built", opp=best.opportunity_title, artifacts=len(artifacts))
    return {"kit_artifacts": artifacts, "kit_opportunity_id": best.opportunity_id}
