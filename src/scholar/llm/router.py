"""Tiered model router — the "right model for the job" pattern.

Rather than paying 70B prices for JSON extraction, we route each agent role to
the cheapest model that clears the quality bar (the Open-Source Model Matrix
from the blueprint). Roles -> model names are config-driven so you can swap in
new open weights without touching agent code.
"""
from __future__ import annotations

from enum import Enum


class Role(str, Enum):
    HEAVY = "heavy"      # Orchestrator routing + Quality Gate verification
    FAST = "fast"        # Profiler extraction + Scout tool-calling
    SCRIBE = "scribe"    # Long-form academic writing


# How much determinism each role wants. Extraction/verification -> near-greedy;
# writing -> a little warmth.
_TEMPERATURE = {Role.HEAVY: 0.0, Role.FAST: 0.1, Role.SCRIBE: 0.5}


def temperature(role: Role) -> float:
    return _TEMPERATURE[role]


def route(role: Role) -> tuple[str, float]:
    """Return ``(model_name, temperature)`` for a role, using the role's
    preferred provider (LLM_PROVIDER_<ROLE>, else the pool head).

    Kept for callers that just want "the model for this role" (e.g. prompt-family
    detection). Actual inference iterates the whole provider pool — see
    ``llm.client`` and ``llm.providers``.
    """
    from .providers import provider_for  # lazy import to avoid an import cycle

    return provider_for(role).model_for(role), _TEMPERATURE[role]
