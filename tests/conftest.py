"""Shared pytest fixtures + hermetic configuration.

Tests must NOT depend on the developer's local ``.env`` (which is tuned for live
runs). We pin the pipeline-tuning knobs to known values here and clear the cached
singletons, so routing/threshold tests are deterministic on any machine.
"""
from __future__ import annotations

import os

# Pin BEFORE any scholar.config import reads settings. os.environ takes precedence
# over the .env file in pydantic-settings, so this overrides local tuning.
os.environ["MAX_REFLECTION_LOOPS"] = "2"
os.environ["MATCH_SCORE_THRESHOLD"] = "55"
os.environ["TOP_K_OPPORTUNITIES"] = "4"

from scholar.config import get_settings  # noqa: E402
from scholar.llm.providers import load_providers  # noqa: E402

# Drop any cache populated during import so the pinned values take effect.
get_settings.cache_clear()
load_providers.cache_clear()
