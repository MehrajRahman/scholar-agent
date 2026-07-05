"""Knowledge-base builder ("the surfer").

A dedicated, authenticated operation — distinct from the per-CV deep search:
given a set of keywords, it runs a bounded deep-research pass per keyword and
writes discovered/updated opportunities into the shared Neo4j + Qdrant KB. Streams
per-keyword progress over SSE so the web UI shows live feedback instead of a
frozen spinner during a multi-minute crawl.
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..auth.deps import CurrentUser
from ..kb import get_vectors
from ..observability import get_logger

router = APIRouter(tags=["maintenance"])
log = get_logger("api.surf")

_MAX_KEYWORDS = 12  # bound a run so it can't blow a free-tier budget


class SurfRequest(BaseModel):
    keywords: list[str]


@router.post("/maintenance/surf")
async def surf(req: SurfRequest, user: CurrentUser) -> EventSourceResponse:
    """Surf the web for each keyword and populate the KB. Auth-gated (any signed-in
    user) so an anonymous caller can't trigger expensive LLM/crawl work."""
    from ..maintenance import refresh

    keywords = [k.strip() for k in req.keywords if k.strip()][:_MAX_KEYWORDS]

    async def event_gen():
        try:
            vectors = get_vectors()
            db_before = vectors.count()
            yield {"event": "start", "data": json.dumps({"keywords": len(keywords), "db_before": db_before})}
            total = 0
            for i, kw in enumerate(keywords, 1):
                yield {"event": "progress", "data": json.dumps({"i": i, "n": len(keywords), "keyword": kw, "status": "surfing"})}
                try:
                    found = (await refresh(kw)).get("discovered", 0)
                    total += found
                    yield {"event": "progress", "data": json.dumps({"i": i, "n": len(keywords), "keyword": kw, "found": found, "status": "done"})}
                except Exception as exc:  # noqa: BLE001 - one keyword failing shouldn't stop the run
                    log.warning("surf_keyword_failed", keyword=kw, error=str(exc))
                    yield {"event": "progress", "data": json.dumps({"i": i, "n": len(keywords), "keyword": kw, "status": "error", "error": str(exc)})}
            db_after = vectors.count()
            yield {"event": "result", "data": json.dumps({"total_found": total, "db_after": db_after, "added": max(0, db_after - db_before)})}
        except Exception as exc:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_gen())
