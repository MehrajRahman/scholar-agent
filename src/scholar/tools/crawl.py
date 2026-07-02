# """Crawl4AI integration — the heavy-duty crawler for Deep Research.

# Crawl4AI (Apache-2.0, free, self-host) renders JS-heavy university pages with a
# real browser and returns LLM-ready markdown — far better than a plain HTTP GET on
# modern opportunity/lab pages. It's an *optional* dependency: if it isn't
# installed (or a page fails), we fall back to the lightweight ``trafilatura``
# scraper, so the pipeline always works.

# Install (optional):  pip install "crawl4ai>=0.4" && crawl4ai-setup
# """
# from __future__ import annotations

# import asyncio

# from ..observability import get_logger
# from .scraper import fetch_clean_text

# log = get_logger("tool.crawl")

# _crawler_unavailable = False  # cache the import result after the first miss


# async def crawl_clean_text(url: str, max_chars: int = 8000) -> str:
#     """Return clean markdown/text for ``url`` via Crawl4AI, else trafilatura."""
#     global _crawler_unavailable
#     if not _crawler_unavailable:
#         try:
#             from crawl4ai import AsyncWebCrawler  # type: ignore

#             async with AsyncWebCrawler(verbose=False) as crawler:
#                 result = await crawler.arun(url=url)
#             text = getattr(result, "markdown", None) or getattr(result, "text", "") or ""
#             if text:
#                 return text[:max_chars]
#         except ImportError:
#             _crawler_unavailable = True
#             log.info("crawl4ai_not_installed", fallback="trafilatura")
#         except Exception as exc:  # noqa: BLE001 - any crawl failure -> fallback
#             log.warning("crawl4ai_failed", url=url, error=str(exc))
#     return await fetch_clean_text(url, max_chars=max_chars)


# async def crawl_many(urls: list[str], max_chars: int = 8000) -> list[tuple[str, str]]:
#     """Crawl several URLs concurrently -> ``[(url, clean_text)]`` (non-empty only)."""
#     texts = await asyncio.gather(*(crawl_clean_text(u, max_chars) for u in urls))
#     return [(u, t) for u, t in zip(urls, texts) if t]



"""Crawl4AI integration — the heavy-duty crawler for Deep Research.

Crawl4AI (Apache-2.0, free, self-host) renders JS-heavy university pages with a
real browser and returns LLM-ready markdown — far better than a plain HTTP GET on
modern opportunity/lab pages. It's an *optional* dependency: if it isn't
installed (or a page fails), we fall back to the lightweight ``trafilatura``
scraper, so the pipeline always works.

Install (optional):  pip install "crawl4ai>=0.4" && crawl4ai-setup

Rate-limiting notes
-------------------
``crawl_many`` intentionally serialises crawl + downstream LLM extraction so
we never produce more concurrent Groq requests than ``CRAWL_CONCURRENCY``
(default 3). Junk pages (error bodies, cookie walls, blank content) are dropped
before they reach the LLM to avoid wasting RPM budget on useless round-trips.
"""
from __future__ import annotations

import asyncio

from ..observability import get_logger
from .scraper import _is_junk, fetch_clean_text  # junk filter lives in scraper to avoid duplication

log = get_logger("tool.crawl")

_crawler_unavailable = False  # cache the import result after the first miss

# Max simultaneous crawl+extract tasks. Keep this at or below llm_max_concurrency
# so the crawler never builds a backlog larger than the LLM gate.
CRAWL_CONCURRENCY = 3


async def crawl_clean_text(url: str, max_chars: int = 8000) -> str:
    """Return clean markdown/text for ``url`` via Crawl4AI, else trafilatura."""
    global _crawler_unavailable
    if not _crawler_unavailable:
        try:
            from crawl4ai import AsyncWebCrawler  # type: ignore

            async with AsyncWebCrawler(verbose=False) as crawler:
                result = await crawler.arun(url=url)
            text = getattr(result, "markdown", None) or getattr(result, "text", "") or ""
            if text:
                return text[:max_chars]
        except ImportError:
            _crawler_unavailable = True
            log.info("crawl4ai_not_installed", fallback="trafilatura")
        except Exception as exc:  # noqa: BLE001 - any crawl failure -> fallback
            log.warning("crawl4ai_failed", url=url, error=str(exc))
    return await fetch_clean_text(url, max_chars=max_chars)


async def crawl_many(
    urls: list[str],
    max_chars: int = 8000,
    concurrency: int = CRAWL_CONCURRENCY,
) -> list[tuple[str, str]]:
    """Crawl URLs with a concurrency cap and junk filter.

    Returns ``[(url, clean_text)]`` for pages that pass the quality gate.
    Crucially, at most ``concurrency`` fetches are in-flight at once, which
    prevents the pipeline from queuing a burst of LLM extraction calls that
    immediately trip Groq's rate limiter.

    Args:
        urls:        Target URLs to crawl.
        max_chars:   Character cap forwarded to the underlying fetcher.
        concurrency: Max simultaneous fetch tasks (default ``CRAWL_CONCURRENCY``).
                     Set lower (e.g. 2) when running against very strict RPM limits.
    """
    sem = asyncio.Semaphore(concurrency)
    results: list[tuple[str, str]] = []

    async def _fetch_one(url: str) -> tuple[str, str] | None:
        async with sem:
            text = await crawl_clean_text(url, max_chars=max_chars)
        if not text or _is_junk(text):
            log.debug("crawl_junk_skipped", url=url, chars=len(text))
            return None
        return url, text

    tasks = [_fetch_one(u) for u in urls]
    for coro in asyncio.as_completed(tasks):
        item = await coro
        if item is not None:
            results.append(item)

    return results