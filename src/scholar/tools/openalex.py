"""OpenAlex — free, open scholarly graph (250M+ works, no API key).

Used to (a) discover what a professor *actually* researches (grounding for the
Quality Gate) and (b) surface labs/topics aligned with the applicant.
"""
from __future__ import annotations

import httpx

from ..config import get_settings
from ..observability import get_logger

log = get_logger("tool.openalex")
_BASE = "https://api.openalex.org"


def _params() -> dict:
    # The "polite pool" gives higher, more reliable rate limits.
    return {"mailto": get_settings().openalex_mailto}


async def openalex_works(topic: str, per_page: int = 10) -> list[dict]:
    """Recent works on a topic -> ``[{title, year, doi, authorships}]``."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{_BASE}/works",
            params={
                **_params(),
                "search": topic,
                "per-page": per_page,
                "sort": "publication_date:desc",
            },
        )
        r.raise_for_status()
        results = r.json().get("results", [])
    return [
        {
            "title": w.get("title"),
            "year": w.get("publication_year"),
            "doi": w.get("doi"),
            "authors": [a["author"]["display_name"] for a in w.get("authorships", [])],
            "institutions": list(
                {
                    inst["display_name"]
                    for a in w.get("authorships", [])
                    for inst in a.get("institutions", [])
                }
            ),
        }
        for w in results
    ]


async def openalex_professor(name: str) -> dict | None:
    """Resolve an author and summarise their real research footprint."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            f"{_BASE}/authors", params={**_params(), "search": name, "per-page": 1}
        )
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        author = results[0]

        works = await client.get(
            f"{_BASE}/works",
            params={
                **_params(),
                "filter": f"author.id:{author['id']}",
                "per-page": 5,
                "sort": "cited_by_count:desc",
            },
        )
        works.raise_for_status()
        top_works = [w.get("title") for w in works.json().get("results", [])]

    concepts = [c["display_name"] for c in author.get("x_concepts", [])[:8]]
    return {
        "openalex_id": author["id"],
        "name": author["display_name"],
        "institution": (author.get("last_known_institution") or {}).get("display_name"),
        "works_count": author.get("works_count"),
        "research_summary": "Publishes on: " + ", ".join(concepts),
        "recent_works": [w for w in top_works if w],
    }
