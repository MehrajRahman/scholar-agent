"""Live web search with a Tavily -> SearXNG fallback.

Tavily gives LLM-ready snippets out of the box; SearXNG is the fully
self-hostable, no-API-key open-source fallback so the stack stays 100% OSS.
"""
from __future__ import annotations

import httpx

from ..config import get_settings
from ..observability import get_logger

log = get_logger("tool.search")


async def web_search(query: str, max_results: int = 8) -> list[dict]:
    """Return ``[{title, url, snippet, raw_content}]`` from the configured backend.

    ``raw_content`` is the full cleaned page text when the backend can supply it
    (Tavily renders the page server-side, so this covers JS-heavy pages and many
    PDFs the local crawler would miss). It is ``""`` when unavailable, so callers
    can fall back to crawling that URL.
    """
    s = get_settings()
    if s.tavily_api_key:
        return await _tavily(query, max_results, s.tavily_api_key)
    if s.searxng_url:
        return await _searxng(query, max_results, s.searxng_url)
    log.warning("no_search_backend_configured", query=query)
    return []


async def _tavily(query: str, k: int, api_key: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": k,
                "search_depth": "advanced",
                # Ask Tavily for the full extracted page text. It is rendered
                # server-side, so it bypasses our crawler's JS/PDF blind spots.
                "include_raw_content": True,
            },
        )
        r.raise_for_status()
        data = r.json()
    return [
        {
            "title": x.get("title", ""),
            "url": x["url"],
            "snippet": x.get("content", ""),
            "raw_content": x.get("raw_content") or "",
        }
        for x in data.get("results", [])
    ]


async def _searxng(query: str, k: int, base: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{base.rstrip('/')}/search",
            params={"q": query, "format": "json"},
        )
        r.raise_for_status()
        data = r.json()
    # SearXNG returns snippets only (no full page text), so raw_content is empty
    # and callers will crawl these URLs themselves.
    return [
        {
            "title": x.get("title", ""),
            "url": x.get("url", ""),
            "snippet": x.get("content", ""),
            "raw_content": "",
        }
        for x in data.get("results", [])[:k]
    ]
