"""Public funding databases: NSF Awards API and NIH RePORTER.

Both are free government APIs. We surface active awards so the Scout can tie a
lab/professor to real money — strong signal that a position is funded.
"""
from __future__ import annotations

import httpx

from ..observability import get_logger

log = get_logger("tool.funding")


async def search_nsf(keyword: str, n: int = 10) -> list[dict]:
    """NSF Awards API — https://www.research.gov/common/webapi/awardapisearch-v1.htm"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(
            "https://api.nsf.gov/services/v1/awards.json",
            params={
                "keyword": keyword,
                "printFields": "title,piFirstName,piLastName,awardeeName,fundsObligatedAmt,startDate",
                "rpp": n,
            },
        )
        r.raise_for_status()
        awards = r.json().get("response", {}).get("award", [])
    return [
        {
            "title": a.get("title"),
            "pi": f"{a.get('piFirstName', '')} {a.get('piLastName', '')}".strip(),
            "institution": a.get("awardeeName"),
            "amount": a.get("fundsObligatedAmt"),
            "start_date": a.get("startDate"),
            "source": "NSF",
        }
        for a in awards
    ]


async def search_nih(keyword: str, n: int = 10) -> list[dict]:
    """NIH RePORTER v2 — https://api.reporter.nih.gov/"""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.reporter.nih.gov/v2/projects/search",
            json={
                "criteria": {"advanced_text_search": {"search_text": keyword}},
                "limit": n,
                "sort_field": "award_amount",
                "sort_order": "desc",
            },
        )
        r.raise_for_status()
        results = r.json().get("results", [])
    return [
        {
            "title": p.get("project_title"),
            "pi": (p.get("contact_pi_name") or "").strip(),
            "institution": (p.get("organization") or {}).get("org_name"),
            "amount": p.get("award_amount"),
            "start_date": p.get("project_start_date"),
            "source": "NIH",
        }
        for p in results
    ]
