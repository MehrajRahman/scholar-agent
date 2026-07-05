"""System health-check — verifies every runtime dependency is reachable.

    python scripts/healthcheck.py          # quick (skips model load)
    python scripts/healthcheck.py --full   # also loads the embedding model
    make check

Exits non-zero if any CRITICAL component is down, so it doubles as a CI/deploy
gate and a fast "is my whole system working?" answer.
"""
from __future__ import annotations

import sys

import httpx

from scholar.config import get_settings
from scholar.llm.providers import load_providers

PASS, WARN, FAIL, SKIP = "PASS", "WARN", "FAIL", "SKIP"
_ICON = {PASS: "OK ", WARN: "warn", FAIL: "FAIL", SKIP: "skip"}


def check_qdrant(s) -> tuple[str, str]:
    try:
        r = httpx.get(f"{s.qdrant_url}/collections", timeout=5)
        r.raise_for_status()
        n = len(r.json().get("result", {}).get("collections", []))
        return PASS, f"{s.qdrant_url} · {n} collection(s)"
    except Exception as exc:  # noqa: BLE001
        return FAIL, f"{s.qdrant_url} · {exc}"[:70]


def check_neo4j(s) -> tuple[str, str]:
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(s.neo4j_uri, auth=(s.neo4j_user, s.neo4j_password))
        driver.verify_connectivity()
        driver.close()
        return PASS, s.neo4j_uri
    except Exception as exc:  # noqa: BLE001
        return FAIL, f"{s.neo4j_uri} · {exc}"[:70]


def check_provider(p) -> tuple[str, str]:
    """Ping the OpenAI-compatible /models endpoint (works for Ollama, Groq, …)."""
    headers = {}
    if p.api_key and p.api_key != "not-needed":
        headers["Authorization"] = f"Bearer {p.api_key}"
    try:
        # rstrip so a base_url with a trailing slash (e.g. Gemini) doesn't become
        # "…/openai//models" (which 404s).
        r = httpx.get(f"{p.base_url.rstrip('/')}/models", headers=headers, timeout=8)
        if r.status_code == 200:
            return PASS, f"{p.base_url} · reachable"
        if r.status_code in (401, 403):
            return WARN, f"{p.base_url} · auth failed (bad key?)"
        return WARN, f"{p.base_url} · HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return WARN, f"{p.base_url} · {exc}"[:60]


def check_search(s) -> tuple[str, str]:
    if s.tavily_api_key:
        return PASS, "Tavily configured"
    if s.searxng_url:
        return PASS, f"SearXNG {s.searxng_url}"
    return WARN, "no search backend (set TAVILY_API_KEY or SEARXNG_URL)"


def check_embedder() -> tuple[str, str]:
    try:
        from scholar.kb.embeddings import get_embedder

        vec = get_embedder().embed_one("healthcheck")
        return PASS, f"dim={len(vec)}"
    except Exception as exc:  # noqa: BLE001
        return FAIL, str(exc)[:70]


def main() -> None:
    full = "--full" in sys.argv
    s = get_settings()
    providers = load_providers()
    rows: list[tuple[str, str, str]] = []

    rows.append((PASS, "config (.env + providers.json)", f"{len(providers)} provider(s)"))
    st, d = check_qdrant(s); rows.append((st, "Qdrant vector store", d))
    st, d = check_neo4j(s); rows.append((st, "Neo4j graph", d))

    provider_ok = False
    for p in providers:
        st, d = check_provider(p)
        provider_ok = provider_ok or st == PASS
        rows.append((st, f"LLM provider · {p.name}", d))
    if not provider_ok:
        rows.append((FAIL, "LLM availability", "NO provider reachable — pipeline cannot run"))

    st, d = check_search(s); rows.append((st, "web search backend", d))
    if full:
        st, d = check_embedder(); rows.append((st, "embeddings (fastembed)", d))
    else:
        rows.append((SKIP, "embeddings (fastembed)", "run --full to load the model"))

    print("\n  scholar-agent · system health\n  " + "-" * 60)
    for status, name, detail in rows:
        print(f"  [{_ICON[status]}] {name:32} {detail}")
    print("  " + "-" * 60)

    fails = [r for r in rows if r[0] == FAIL]
    warns = [r for r in rows if r[0] == WARN]
    if fails:
        print(f"  {len(fails)} CRITICAL failure(s) — the system will not run correctly.\n")
        sys.exit(1)
    tail = f" ({len(warns)} warning(s))" if warns else ""
    print(f"  All critical components healthy.{tail}\n")


if __name__ == "__main__":
    main()
