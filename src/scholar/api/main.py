"""FastAPI serving layer — the orchestrator's front door (the "Hands").

Endpoints:
  * GET  /app/            — the web UI (static, served from ../../../web)
  * POST /ingest          — upload a CV (pdf/txt) -> extracted text
  * POST /pipeline/run    — run to completion, return everything
  * POST /pipeline/stream — SSE: live per-stage progress + a final `result` event
  * POST /draft           — on-demand email/SOP/artifacts for one opportunity
  * POST /maintenance/sweep — freshness sweep (n8n cron)
  * GET  /health
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from ..config import get_settings
from ..graph_app import get_app, run_pipeline
from ..kb import get_graph, get_vectors
from ..observability import configure_logging, get_logger
from ..state import PipelineState

log = get_logger("api")
_WEB_DIR = Path(__file__).resolve().parents[3] / "web"

# The web-app layer (accounts + persistence) is optional: it needs the [web]
# extra (SQLAlchemy, passlib, pyjwt). If those aren't installed, the pipeline API
# still runs — the /auth routes are simply absent.
try:
    from ..auth.router import router as auth_router
    from ..db import init_db

    from .me import router as me_router

    _WEB_ENABLED = True
except ImportError:  # [web] extra not installed
    _WEB_ENABLED = False


class RunRequest(BaseModel):
    documents: list[str]
    query: str = ""
    mode: str = "deep"  # "fast" (DB-only) | "deep" (live research + write-back)
    artifacts: list[str] = []  # extra ArtifactType values for the best match


class DraftRequest(BaseModel):
    """On-demand drafting for ONE already-discovered opportunity (UI buttons)."""

    profile: dict                 # the StudentProfile dict returned by a prior run
    opportunity_id: str           # content-addressed id from a match
    artifacts: list[str] = []     # optional extra ArtifactType values to also build


def _dump(value: Any) -> Any:
    """JSON-able view of a state value that may contain Pydantic models."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_dump(v) for v in value]
    return value


def _progress_payload(state: Mapping[str, Any]) -> dict:
    """Live counts streamed mid-run so the UI shows real progress."""
    return {
        "opportunities": len(state.get("opportunities", []) or []),
        "matches": len(state.get("matches", []) or []),
        "shortlist": len(state.get("shortlist", []) or []),
        "bundles": len(state.get("bundles", []) or []),
        "log": (state.get("search_log", []) or [])[-1:],
    }


def _result_payload(state: Mapping[str, Any]) -> dict:
    return {
        "profile": _dump(state.get("profile")),
        "matches": _dump(state.get("matches", [])),
        "bundles": _dump(state.get("bundles", [])),
        "kit_artifacts": _dump(state.get("kit_artifacts", [])),
        "suggest_deep_research": state.get("suggest_deep_research", False),
        "errors": state.get("errors", []),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    try:
        get_vectors().ensure_collection()
    except Exception as exc:  # noqa: BLE001
        log.warning("qdrant_init_skipped", error=str(exc))
    if _WEB_ENABLED:
        try:
            init_db()  # create the accounts/applications tables if missing
        except Exception as exc:  # noqa: BLE001
            log.warning("db_init_skipped", error=str(exc))
    yield


app = FastAPI(title="scholar-agent", version="0.2.0", lifespan=lifespan)

# Mount the accounts/auth + per-user data APIs when the web layer is available.
if _WEB_ENABLED:
    app.include_router(auth_router)
    app.include_router(me_router)


@app.get("/health")
async def health() -> dict:
    s = get_settings()
    return {"status": "ok", "models": {"heavy": s.model_heavy, "fast": s.model_fast}}


@app.post("/ingest")
async def ingest(file: Annotated[UploadFile, File()]) -> dict:
    """Extract text from an uploaded CV (PDF or plain text) for the web UI."""
    data = await file.read()
    name = (file.filename or "upload").lower()
    if name.endswith(".pdf"):
        from ..ingest import extract_pdf_text

        text = extract_pdf_text(data)
    else:
        text = data.decode("utf-8", errors="ignore")
    return {"filename": file.filename, "text": text, "chars": len(text)}


@app.post("/maintenance/sweep")
async def maintenance_sweep() -> dict:
    """Freshness sweep: expire past-deadline opps, mark stale ones. n8n cron hits this."""
    counts = await get_graph().expire_sweep(get_settings().stale_ttl_days)
    return {"swept": counts}


@app.post("/pipeline/run")
async def pipeline_run(req: RunRequest) -> dict:
    final = await run_pipeline(req.documents, req.query, mode=req.mode, artifacts=req.artifacts)
    return _result_payload(final)


@app.post("/draft")
async def draft(req: DraftRequest) -> dict:
    """Generate a cold email + SOP (and optional kit artifacts) for ONE opportunity
    on demand. Powers the per-result 'Generate' buttons so users can draft for any
    match without re-running the whole pipeline. Reuses the Scribe + Kit agents."""
    from ..agents import scribe_node
    from ..agents.kit import kit_node
    from ..schemas import StudentProfile

    try:
        profile = StudentProfile.model_validate(req.profile)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"invalid profile: {exc}"}

    opp = get_vectors().fetch_by_id(req.opportunity_id)
    if opp is None:
        return {"error": "opportunity not found in knowledge base"}

    # Reuse the Scribe by handing it a one-item shortlist.
    state: PipelineState = {
        "profile": profile,
        "shortlist": [opp],
        "opportunities": [opp],
        "matches": [],
        "current_index": 0,
        "revision_count": 0,
    }
    try:
        bundle = (await scribe_node(state)).get("draft")
        if bundle is None:
            return {"error": "draft generation failed"}
        kit_artifacts: list = []
        if req.artifacts:
            kit_state: PipelineState = {
                "profile": profile,
                "opportunities": [opp],
                "bundles": [bundle],
                "artifacts_requested": req.artifacts,
            }
            kit_artifacts = _dump((await kit_node(kit_state)).get("kit_artifacts", []))
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the UI
        log.warning("draft_failed", opp_id=req.opportunity_id, error=str(exc))
        return {"error": str(exc)}

    return {"bundle": _dump(bundle), "kit_artifacts": kit_artifacts}


@app.post("/pipeline/stream")
async def pipeline_stream(req: RunRequest) -> EventSourceResponse:
    app_graph = get_app()
    initial = {
        "raw_documents": req.documents,
        "user_query": req.query,
        "mode": req.mode,
        "artifacts_requested": req.artifacts,
        "current_index": 0,
        "revision_count": 0,
    }

    async def event_gen():
        final_state: dict = {}
        try:
            async for mode, chunk in app_graph.astream(
                initial, stream_mode=["updates", "values"]
            ):
                if mode == "updates":
                    for node_name in chunk:
                        yield {"event": "node", "data": json.dumps({"node": node_name})}
                elif mode == "values":
                    final_state = chunk
                    # Live counts so the UI shows real progress, not a frozen spinner.
                    yield {"event": "progress", "data": json.dumps(_progress_payload(chunk))}
            yield {"event": "result", "data": json.dumps(_result_payload(final_state), default=str)}
        except Exception as exc:  # noqa: BLE001 - surface failures to the UI
            log.warning("pipeline_stream_error", error=str(exc))
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}
        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(event_gen())


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


# Mounted last so explicit API routes above take precedence.
if _WEB_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=str(_WEB_DIR), html=True), name="web")
