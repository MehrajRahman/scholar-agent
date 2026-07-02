"""Detect a model's *family* from its id so the prompt layer can adapt.

Different open models reward different prompting: Hermes is trained on the
``<tool_call>`` ChatML convention, Gemini dislikes markdown code-fences around
JSON, etc. We map any provider's model id (e.g. ``meta-llama/llama-3.3-70b-
instruct``, ``llama-3.3-70b-versatile``, ``NousResearch/Hermes-3-Llama-3.1-8B``)
to a small closed set of families.
"""
from __future__ import annotations

from enum import Enum


class Family(str, Enum):
    HERMES = "hermes"
    QWEN = "qwen"
    LLAMA = "llama"
    GEMINI = "gemini"
    MISTRAL = "mistral"
    GENERIC = "generic"


# Order matters: check the most specific markers first (Hermes is a Llama
# fine-tune, so it must win over the bare "llama" check).
_MARKERS: list[tuple[Family, tuple[str, ...]]] = [
    (Family.HERMES, ("hermes", "nous")),
    (Family.QWEN, ("qwen",)),
    (Family.GEMINI, ("gemini", "gemma")),
    (Family.MISTRAL, ("mistral", "mixtral", "nemo")),
    (Family.LLAMA, ("llama", "meta-llama")),
]


def family_of(model_id: str) -> Family:
    name = (model_id or "").lower()
    for family, markers in _MARKERS:
        if any(m in name for m in markers):
            return family
    return Family.GENERIC
