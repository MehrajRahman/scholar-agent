"""The LLM provider pool — the data behind the failover gateway.

A *provider* is one OpenAI-compatible endpoint (Groq, OpenRouter, Cerebras,
Gemini, a local vLLM, …) with its own base URL, key, and per-role model ids
(model names differ per provider). The pool is an ordered list: the gateway
tries them top-to-bottom and rolls to the next on rate-limit/outage.

Config source (first that exists wins):
  1. ``$PROVIDERS_FILE`` or ``./providers.json`` — the multi-provider pool.
  2. Fallback: a single provider synthesised from the ``LLM_*`` env settings,
     so the system still runs with zero extra config.

Secrets never live in ``providers.json``: each provider names the *env var*
that holds its key (``api_key_env``).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import get_settings
from ..observability import get_logger
from .router import Role

log = get_logger("llm.providers")


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    guided_json: bool
    models: dict[str, str]  # Role.value -> model id

    def model_for(self, role: Role) -> str:
        return self.models[role.value]


def _default_pool() -> list[ProviderConfig]:
    s = get_settings()
    return [
        ProviderConfig(
            name="default",
            base_url=s.llm_base_url,
            api_key=s.llm_api_key,
            guided_json=s.llm_guided_json,
            models={
                Role.HEAVY.value: s.model_heavy,
                Role.FAST.value: s.model_fast,
                Role.SCRIBE.value: s.model_scribe,
            },
        )
    ]


def _pool_path() -> Path | None:
    explicit = os.environ.get("PROVIDERS_FILE")
    if explicit and Path(explicit).is_file():
        return Path(explicit)
    local = Path("providers.json")
    return local if local.is_file() else None


def _ensure_env_loaded() -> None:
    """Mirror the .env file into os.environ.

    pydantic-settings reads .env into the Settings object only — it never
    populates os.environ. But providers.json resolves each provider's key via
    os.environ.get(api_key_env), so without this the keys are missing and every
    cloud provider falls back to the "not-needed" default (=> 401). Existing
    real env vars always win over the file.
    """
    try:
        from dotenv import dotenv_values
    except ImportError:  # dotenv is a pydantic-settings dep, but be defensive
        return
    for key, value in dotenv_values(".env").items():
        if value is not None and key not in os.environ:
            os.environ[key] = value


def _resolve_key(ref: str) -> str:
    """Resolve a provider's api_key_env field.

    Normally this is the *name* of an env var (e.g. "GROQ_API_KEY") and we look
    it up in os.environ. But it's an easy mistake to paste the literal key in
    instead — keys start with a recognisable prefix (gsk_, sk-, …), so if the
    value looks like a key rather than a var name, use it verbatim.
    """
    if not ref:
        return "not-needed"
    if ref.startswith(("gsk_", "sk-", "sk_", "or-", "csk-")):
        return ref  # a literal key was pasted in
    return os.environ.get(ref, "not-needed")


@lru_cache
def load_providers() -> list[ProviderConfig]:
    _ensure_env_loaded()
    path = _pool_path()
    if path is None:
        return _default_pool()
    try:
        raw = json.loads(path.read_text())
        pool: list[ProviderConfig] = []
        for entry in raw["providers"]:
            key = _resolve_key(entry.get("api_key_env", ""))
            pool.append(
                ProviderConfig(
                    name=entry["name"],
                    base_url=entry["base_url"],
                    api_key=key,
                    guided_json=entry.get("guided_json", False),
                    models=entry["models"],
                )
            )
        if not pool:
            raise ValueError("empty provider pool")
        log.info("loaded_provider_pool", n=len(pool), order=[p.name for p in pool])
        return pool
    except Exception as exc:  # noqa: BLE001 - never let bad config kill startup
        log.warning("provider_pool_load_failed", error=str(exc), fallback="default")
        return _default_pool()


def primary() -> ProviderConfig:
    return load_providers()[0]
