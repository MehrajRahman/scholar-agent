"""Synthesised deliverables — output of Agent 4 (The Scribe) + the Kit stage.

The two core, per-opportunity artifacts (cold email + SOP) keep dedicated,
strongly-typed schemas because they run through the reflection loop. The wider
**Application Kit** (dossier, interview prep, CV report, …) uses one generic
``Artifact`` shape so new types are a registry entry, not a new class.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    cold_email = "cold_email"
    sop = "sop"
    personal_statement = "personal_statement"
    motivation_letter = "motivation_letter"
    cv_tailoring = "cv_tailoring"
    research_proposal = "research_proposal"
    recommendation_request = "recommendation_request"
    professor_dossier = "professor_dossier"
    interview_prep = "interview_prep"
    deadline_checklist = "deadline_checklist"
    linkedin_note = "linkedin_note"


class ColdEmail(BaseModel):
    to_name: str
    to_email: str | None = None
    subject: str
    body: str
    referenced_works: list[str] = Field(default_factory=list)


class SOPDraft(BaseModel):
    title: str = "Statement of Purpose"
    target: str = Field(description="University / programme this SOP is tailored to")
    body: str
    word_count: int = 0


class Artifact(BaseModel):
    """Generic kit item (everything beyond the core email + SOP)."""

    type: ArtifactType
    title: str
    body: str
    references: list[str] = Field(default_factory=list, description="grounding sources cited")
    metadata: dict = Field(default_factory=dict, description="e.g. {'ics': '...'} for calendars")


class SynthesisBundle(BaseModel):
    """Everything produced for a single high-scoring opportunity."""

    opportunity_id: str
    opportunity_title: str
    score: int
    cold_email: ColdEmail
    sop: SOPDraft
    artifacts: list[Artifact] = Field(
        default_factory=list, description="extended Application Kit items"
    )
    revisions: int = Field(0, description="reflection-loop iterations spent")
    approved: bool = False
