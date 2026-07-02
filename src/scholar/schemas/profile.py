"""The Applicant — output of Agent 1 (The Profiler)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class EducationEntry(BaseModel):
    institution: str
    degree: str = Field(description="e.g. 'BSc in Computer Science'")
    gpa: float | None = Field(None, ge=0, le=4.0)
    gpa_scale: float = 4.0
    graduation_year: int | None = None


class StudentProfile(BaseModel):
    """Normalised applicant profile extracted from messy CV / transcript PDFs."""

    full_name: str
    email: str | None = None
    education: list[EducationEntry] = Field(default_factory=list)

    # The semantic payload used for matchmaking.
    research_interests: list[str] = Field(
        default_factory=list, description="Free-form topics, e.g. 'graph neural networks'"
    )
    skills: list[str] = Field(default_factory=list)
    publications: list[str] = Field(default_factory=list)

    # Hard constraints the Matchmaker must respect (graph filters, not vectors).
    target_degree: str = Field("PhD", description="PhD | Masters | PostDoc")
    geographic_constraints: list[str] = Field(
        default_factory=list, description="Allowed countries/regions, empty = anywhere"
    )
    requires_full_funding: bool = True
    earliest_start: str | None = Field(None, description="ISO date, e.g. 2026-09-01")

    @property
    def best_gpa_4(self) -> float | None:
        """Highest GPA normalised to a 4.0 scale (used as a graph filter)."""
        scaled = [e.gpa / e.gpa_scale * 4.0 for e in self.education if e.gpa]
        return max(scaled) if scaled else None

    def embedding_text(self) -> str:
        """Dense-retrieval surface for the applicant."""
        return " | ".join(
            [
                f"Interests: {', '.join(self.research_interests)}",
                f"Skills: {', '.join(self.skills)}",
                f"Target: {self.target_degree}",
            ]
        )
