"""Structured logging + optional Langfuse tracing.

Observability is a 2025/26 non-negotiable for agentic systems: you need to see
every model call, tool call and the reflection-loop decisions. We use
``structlog`` for local logs and (optionally) Langfuse — fully open-source,
self-hostable — for distributed traces. Both degrade gracefully to no-ops when
unconfigured so the pipeline runs anywhere.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import structlog

from .config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        format="%(message)s", level=getattr(logging, settings.log_level.upper(), 20)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.log_level.upper(), 20)
        ),
    )


def get_logger(name: str) -> Any:
    return structlog.get_logger(name)


@lru_cache
def get_langfuse():  # pragma: no cover - thin optional wrapper
    """Return a Langfuse client if configured, else ``None``."""
    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:  # noqa: BLE001 - never let tracing break the pipeline
        return None
