"""Writing Studio — IELTS & academic-writing practice with AI feedback.

The right-sized English-prep module (design §15.3): not a course, but a
practice loop — submit writing, get calibrated band-style scoring against the
four public IELTS criteria, concrete strengths/improvements, and targeted
rewrites of weak sentences. The same loop doubles for SOP/motivation-letter
polishing, so it sharpens applications as well as test prep.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..auth.deps import CurrentUser
from ..observability import get_logger

router = APIRouter(prefix="/studio", tags=["studio"])
log = get_logger("api.studio")

_MIN_WORDS = 50
_MAX_CHARS = 12000

_MODES = {
    "ielts_task2": "IELTS Academic Writing Task 2 (opinion/discussion essay, 250+ words)",
    "ielts_task1": "IELTS Academic Writing Task 1 (describe a chart/process, 150+ words)",
    "sop": "Statement of Purpose / motivation letter for a scholarship or PhD application",
    "academic": "General academic paragraph/abstract",
}

_SYSTEM = """You are a strict, experienced IELTS examiner and academic writing coach.
Assess the submission against the four public IELTS writing criteria:
- task_response (or task_achievement): does it fully address the task?
- coherence_cohesion: organisation, paragraphing, linking.
- lexical_resource: vocabulary range, precision, collocation.
- grammatical_range_accuracy: sentence variety and error density.

Rules:
- Score each criterion 4.0-9.0 in 0.5 steps, calibrated to real IELTS standards —
  be honest, not encouraging. band_overall is the average rounded to the nearest 0.5.
- For non-IELTS modes (SOP/academic), apply the same criteria interpreted for the
  genre (task_response = "fit for purpose and prompt").
- strengths/improvements: concrete and specific to THIS text, max 4 each.
- rewrites: pick up to 3 genuinely weak sentences from the text; show the original,
  an improved version, and a one-line reason. Never invent sentences not in the text.
"""


class Rewrite(BaseModel):
    original: str
    improved: str
    why: str


class WritingFeedback(BaseModel):
    band_overall: float = Field(ge=0, le=9)
    task_response: float = Field(ge=0, le=9)
    coherence_cohesion: float = Field(ge=0, le=9)
    lexical_resource: float = Field(ge=0, le=9)
    grammatical_range_accuracy: float = Field(ge=0, le=9)
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)
    rewrites: list[Rewrite] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    mode: str = "ielts_task2"
    prompt: str = ""      # the task question (optional but improves task_response scoring)
    text: str


@router.post("/feedback", response_model=WritingFeedback)
async def feedback(req: FeedbackRequest, user: CurrentUser) -> WritingFeedback:
    from ..llm import Role, get_llm

    words = len(req.text.split())
    if words < _MIN_WORDS:
        raise HTTPException(
            422,
            f"submit at least {_MIN_WORDS} words (got {words}) — a fair assessment needs more text",
        )
    mode = _MODES.get(req.mode, _MODES["ielts_task2"])
    userload = (
        f"GENRE: {mode}\n"
        + (f"TASK PROMPT:\n{req.prompt.strip()}\n\n" if req.prompt.strip() else "")
        + f"SUBMISSION ({words} words):\n{req.text[:_MAX_CHARS]}"
    )
    try:
        result = await get_llm().structured(Role.HEAVY, _SYSTEM, userload, WritingFeedback)
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the UI
        log.warning("studio_feedback_failed", error=str(exc))
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"feedback failed: {exc}") from exc
    log.info("studio_feedback", mode=req.mode, words=words, band=result.band_overall)
    return result
