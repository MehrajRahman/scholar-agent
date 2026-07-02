"""The single state object that LangGraph threads through every node.

LangGraph state is a ``TypedDict``; each node returns a partial dict that is
merged in. Lists use ``operator.add`` reducers so parallel/append nodes don't
clobber one another.
"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from .schemas import (
    Artifact,
    GroundednessReport,
    MatchResult,
    Opportunity,
    StudentProfile,
    SynthesisBundle,
)


class PipelineState(TypedDict, total=False):
    # --- Inputs ---
    raw_documents: list[str]          # CV / transcript text dumped by the loader
    user_query: str                   # optional free-text steer, e.g. "EU only, ML"
    mode: str                         # "fast" (DB-only) | "deep" (live research)

    # --- Routing signals ---
    suggest_deep_research: bool       # fast mode found little -> hint to go deep

    # --- Agent 1: Profiler ---
    profile: StudentProfile

    # --- Agent 2: Scout ---
    opportunities: Annotated[list[Opportunity], operator.add]
    search_log: Annotated[list[str], operator.add]

    # --- Agent 3: Matchmaker ---
    matches: list[MatchResult]        # sorted desc by score
    shortlist: list[Opportunity]      # >= threshold, the Scribe's worklist

    # --- Agent 4 & 5: Scribe <-> Quality Gate (reflection loop) ---
    current_index: int                # which shortlisted opp we're drafting
    draft: SynthesisBundle | None     # the in-flight artifact under review
    review: GroundednessReport | None # latest Quality Gate verdict
    revision_count: int               # loop guard for the current draft
    bundles: Annotated[list[SynthesisBundle], operator.add]  # finished, approved

    # --- Application Kit (Phase 3): extended artifacts for the best match ---
    artifacts_requested: list[str]    # ArtifactType values the user asked for
    kit_artifacts: Annotated[list[Artifact], operator.add]
    kit_opportunity_id: str

    # --- Bookkeeping ---
    errors: Annotated[list[str], operator.add]
