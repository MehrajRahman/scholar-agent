"""The prompt registry: (agent_key, model_family, version) -> PromptSpec.

Resolution order for the system prompt body:
  1. ``templates/<agent>/<family>.<version>.txt``   (most specific)
  2. ``templates/<agent>/<family>.txt``
  3. ``templates/<agent>/generic.txt``
  4. the inline base in ``agents/prompts.py``        (always present fallback)

A small family-specific *guidance* suffix is appended (e.g. Hermes tool-call
conventions, Gemini "no code fences"), and any ``fewshots/<agent>.jsonl`` examples
are rendered in. Everything is cached so disk is touched once per key.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..llm import Role, family_of, route
from ..llm.families import Family

_TEMPLATES = Path(__file__).parent / "templates"
_FEWSHOTS = Path(__file__).parent / "fewshots"


@lru_cache(maxsize=1)
def _base() -> dict[str, str]:
    """Inline base prompts (always-available fallback). Imported lazily to avoid
    a prompts<->agents import cycle."""
    from ..agents import prompts as base_prompts

    return {
        "profiler": base_prompts.PROFILER,
        "scout_planner": base_prompts.SCOUT_PLANNER,
        "scout_extractor": base_prompts.SCOUT_EXTRACTOR,
        "deep_planner": base_prompts.DEEP_PLANNER,
        "deep_reflect": base_prompts.DEEP_REFLECT,
        "matchmaker": base_prompts.MATCHMAKER,
        "scribe": base_prompts.SCRIBE,
        "quality_gate": base_prompts.QUALITY_GATE,
    }

# Family-specific guidance appended to the base. Keep these short and additive.
_GUIDANCE: dict[Family, str] = {
    Family.HERMES: (
        "Formatting: you are a Hermes model — when invoking a tool, emit a single "
        "<tool_call>{...}</tool_call> block; for final answers output raw JSON only."
    ),
    Family.GEMINI: "Formatting: output raw JSON only. Do NOT wrap it in ``` markdown fences.",
    Family.QWEN: "",
    Family.LLAMA: "",
    Family.MISTRAL: "",
    Family.GENERIC: "",
}


@dataclass(frozen=True)
class PromptSpec:
    system: str
    fewshots: tuple[dict, ...] = field(default_factory=tuple)

    def render(self) -> str:
        """Full system string: base + guidance + rendered few-shot examples."""
        if not self.fewshots:
            return self.system
        blocks = "\n\n".join(
            f"EXAMPLE INPUT:\n{ex.get('input', '')}\nEXAMPLE OUTPUT:\n{ex.get('output', '')}"
            for ex in self.fewshots
        )
        return f"{self.system}\n\nFollow these examples:\n{blocks}"


def _load_template(agent_key: str, family: Family, version: str) -> str | None:
    for candidate in (
        _TEMPLATES / agent_key / f"{family.value}.{version}.txt",
        _TEMPLATES / agent_key / f"{family.value}.txt",
        _TEMPLATES / agent_key / "generic.txt",
    ):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8").strip()
    return None


def _load_fewshots(agent_key: str) -> tuple[dict, ...]:
    path = _FEWSHOTS / f"{agent_key}.jsonl"
    if not path.is_file():
        return ()
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return tuple(rows)


@lru_cache(maxsize=128)
def get_prompt(agent_key: str, family: Family, version: str = "v1") -> PromptSpec:
    base = _load_template(agent_key, family, version) or _base()[agent_key]
    guidance = _GUIDANCE.get(family, "")
    system = f"{base}\n\n{guidance}".strip() if guidance else base
    return PromptSpec(system=system, fewshots=_load_fewshots(agent_key))


def system_for(agent_key: str, role: Role, version: str = "v1") -> str:
    """Convenience for agents: resolve the model for ``role``, adapt to its family."""
    model, _ = route(role)
    return get_prompt(agent_key, family_of(model), version).render()
