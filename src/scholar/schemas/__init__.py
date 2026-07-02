"""Pydantic v2 contracts shared across every agent.

Structured outputs are the backbone of a reliable agentic pipeline: each agent
emits a validated model, so a downstream agent never has to re-parse free text.
"""
from .artifacts import Artifact, ArtifactType, ColdEmail, SOPDraft, SynthesisBundle
from .match import GroundednessReport, MatchResult
from .opportunity import Funding, Opportunity, OpportunityKind, OppStatus, Professor
from .profile import EducationEntry, StudentProfile

__all__ = [
    "StudentProfile",
    "EducationEntry",
    "Opportunity",
    "OpportunityKind",
    "OppStatus",
    "Professor",
    "Funding",
    "MatchResult",
    "GroundednessReport",
    "ColdEmail",
    "SOPDraft",
    "SynthesisBundle",
    "Artifact",
    "ArtifactType",
]
