"""Scoring + groundedness contracts (Agents 3 and 5)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MatchResult(BaseModel):
    """Agent 3 (Matchmaker) verdict for one (student, opportunity) pair.

    NOTE: ``opportunity_id``/``opportunity_title`` and the deterministic signals
    (``semantic_score``, ``graph_score``, ``eligible``) are OVERWRITTEN by the
    matchmaker after parsing — they are computed from retrieval/graph, not the
    model. So they carry defaults and no bounds here: the model often emits
    out-of-range guesses (e.g. semantic_score=1.33) and we don't want that to
    fail validation for values we're about to discard anyway.
    """

    # Model's real output:
    score: int = Field(ge=0, le=100, description="0-100 calibrated match score")
    rationale: str = Field("", description="Why this matched, citing shared skills/topics")
    matched_skills: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list, description="Missing requirements")

    # Deterministic, overwritten post-parse (defaults + unbounded on purpose):
    opportunity_id: str = ""
    opportunity_title: str = ""
    semantic_score: float = 0.0
    graph_score: float = 0.0
    eligible: bool = False

    # Display fields copied from the matched Opportunity so the UI can show the
    # source link + key facts without a second lookup. Also overwritten post-parse.
    source_url: str = ""
    university: str | None = None
    department: str | None = None
    kind: str = ""
    deadline: str | None = None
    funding_summary: str = ""
    professor_name: str = ""
    description: str = ""


class Claim(BaseModel):
    text: str
    supported: bool
    evidence: str | None = Field(None, description="Quote from CV or professor record")


class GroundednessReport(BaseModel):
    """Agent 5 (Quality Gate) verdict on a synthesised artifact."""

    approved: bool
    score: float = Field(ge=0, le=1, description="fraction of claims supported")
    claims: list[Claim] = Field(default_factory=list)
    hallucinations: list[str] = Field(
        default_factory=list, description="Unsupported claims that force a rewrite"
    )
    feedback: str = Field("", description="Actionable notes fed back to the Scribe")
