"""scholar-agent — Autonomous Academic Matchmaking & Synthesis Pipeline.

A deterministic LangGraph state machine that routes work across five
specialised, open-source LLM agents:

    Profiler -> Scout -> Matchmaker -> Scribe <-> Quality Gate

See ``scholar.graph_app`` for the wiring and ``README.md`` for the architecture.
"""

__version__ = "0.1.0"
