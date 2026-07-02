# """Fetch a URL and return clean, boilerplate-free main text.

# ``trafilatura`` strips nav/ads/footers far better than naive ``BeautifulSoup``
# ``get_text``, which keeps the context we feed the model dense and on-topic.
# """
# from __future__ import annotations

# import httpx
# import trafilatura

# from ..observability import get_logger

# log = get_logger("tool.scraper")


# async def fetch_clean_text(url: str, max_chars: int = 8000) -> str:
#     """Download ``url`` and extract the main article/body text."""
#     try:
#         async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
#             r = await client.get(url, headers={"User-Agent": "scholar-agent/0.1"})
#             r.raise_for_status()
#             html = r.text
#     except Exception as exc:  # noqa: BLE001
#         log.warning("fetch_failed", url=url, error=str(exc))
#         return ""

#     text = trafilatura.extract(html, include_links=False, include_comments=False) or ""
#     return text[:max_chars]


"""Fetch a URL and return clean, boilerplate-free main text.

``trafilatura`` strips nav/ads/footers far better than naive ``BeautifulSoup``
``get_text``, which keeps the context we feed the model dense and on-topic.

An explicit junk check (error pages, cookie walls, bot challenges) is applied
after extraction so callers never receive content that would waste an LLM call.
Import ``_is_junk`` from here if you need the same check elsewhere; ``crawl.py``
re-exports it from this module to avoid duplicating the regex.
"""
from __future__ import annotations

import re

import httpx
import trafilatura

from ..observability import get_logger

log = get_logger("tool.scraper")

# ── Junk-page detection ──────────────────────────────────────────────────────
_MIN_CONTENT_CHARS = 200
_SHORT_PAGE = 600
# Hard bot-wall / error-stub signatures. Deliberately NOT including cookie-consent
# phrases ("we use cookies", "cookie policy") or a bare "404": EU university pages
# routinely carry a GDPR cookie banner at the top, and "404" matches years/IDs —
# both caused real opportunity pages to be wrongly discarded. A wall is only
# decisive when the page is ALSO short, so a long article that merely mentions one
# of these phrases in a footer is kept.
_WALL_RE = re.compile(
    r"(enable javascript to|access denied|403 forbidden|page not found|"
    r"just a moment\b|checking your browser|verify you are human|attention required)",
    re.IGNORECASE,
)


def _is_junk(text: str) -> bool:
    """Return True if *text* looks like an error page, bot-wall, or redirect."""
    t = text.strip()
    if len(t) < _MIN_CONTENT_CHARS:
        return True
    return len(t) < _SHORT_PAGE and bool(_WALL_RE.search(t[:500]))


# ── Main fetcher ─────────────────────────────────────────────────────────────

async def fetch_clean_text(url: str, max_chars: int = 8000) -> str:
    """Download ``url`` and extract the main article/body text.

    Returns ``""`` on network failure *or* when the extracted content fails the
    junk filter, so callers can safely skip LLM extraction on an empty result.
    """
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "scholar-agent/0.1"})
            r.raise_for_status()
            content_type = r.headers.get("content-type", "").lower()
            raw_bytes = r.content
            html = "" if "application/pdf" in content_type else r.text
    except Exception as exc:  # noqa: BLE001
        log.warning("fetch_failed", url=url, error=str(exc))
        return ""

    # Many scholarship calls/studentships are PDFs. A plain trafilatura parse of
    # PDF bytes yields nothing, so route them through the layout-aware extractor.
    is_pdf = "application/pdf" in content_type or url.lower().split("?")[0].endswith(".pdf")
    if is_pdf:
        from ..ingest import extract_pdf_text

        text = extract_pdf_text(raw_bytes)
    else:
        text = trafilatura.extract(html, include_links=False, include_comments=False) or ""

    if _is_junk(text):
        log.debug("scraper_junk_skipped", url=url, chars=len(text))
        return ""
    return text[:max_chars]