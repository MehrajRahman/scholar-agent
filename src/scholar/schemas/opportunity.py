"""Opportunities + the entities around them — output of Agent 2 (The Scout)."""
from __future__ import annotations

import hashlib
from enum import Enum

from pydantic import BaseModel, Field


class OpportunityKind(str, Enum):
    scholarship = "scholarship"
    phd_position = "phd_position"
    masters_position = "masters_position"
    postdoc = "postdoc"
    grant = "grant"


class OppStatus(str, Enum):
    active = "active"      # verified, deadline in the future
    stale = "stale"        # not re-verified within the TTL
    expired = "expired"    # deadline has passed
    closed = "closed"      # explicitly filled/withdrawn


class Funding(BaseModel):
    is_fully_funded: bool = False
    stipend_amount: float | None = None
    currency: str = "USD"
    source: str | None = Field(None, description="e.g. 'NSF GRFP', 'university', 'ERC'")
    covers_tuition: bool = False


class Professor(BaseModel):
    name: str
    department: str | None = None
    university: str | None = None
    email: str | None = None
    openalex_id: str | None = None
    research_summary: str | None = Field(
        None, description="Grounding text — what they ACTUALLY publish on. No invention."
    )
    recent_works: list[str] = Field(default_factory=list)


class Opportunity(BaseModel):
    """A single discovered, normalised opportunity. Every field is evidence-backed."""

    title: str
    kind: OpportunityKind
    university: str | None = None
    department: str | None = None
    professor: Professor | None = None
    funding: Funding = Field(default_factory=Funding)

    description: str = ""
    required_skills: list[str] = Field(default_factory=list)
    min_gpa_4: float | None = None
    eligible_regions: list[str] = Field(default_factory=list)
    deadline: str | None = Field(None, description="ISO date")

    # Provenance — the Quality Gate refuses to cite anything without a source URL.
    source_url: str
    retrieved_at: str | None = None

    # Lifecycle / freshness (managed by the DB write-back; see kb/graph.py).
    status: OppStatus = OppStatus.active
    first_seen_at: str | None = None
    last_verified_at: str | None = None
    version: int = 1

    @property
    def id(self) -> str:
        """Stable, content-addressed id (used as Qdrant point id / Neo4j key)."""
        raw = f"{self.title}|{self.university}|{self.source_url}".lower()
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    @property
    def content_hash(self) -> str:
        """Hash of the *salient* fields — changes only when the offer itself does,
        so the write-back can tell a re-discovery from a real update."""
        salient = "|".join(
            [
                self.title,
                self.description,
                str(self.deadline),
                str(self.funding.is_fully_funded),
                str(self.min_gpa_4),
                ",".join(sorted(self.required_skills)),
            ]
        ).lower()
        return hashlib.sha1(salient.encode()).hexdigest()[:16]

    def embedding_text(self) -> str:
        prof = f" Supervisor: {self.professor.name}." if self.professor else ""
        return (
            f"{self.title} ({self.kind.value}) at {self.university or 'unknown'}.{prof} "
            f"{self.description} Skills: {', '.join(self.required_skills)}"
        )
