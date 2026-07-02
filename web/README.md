# Web UI (Phase 5)

A beautiful, **zero-build** single-page app — Tailwind + Alpine via CDN, no Node
toolchain. It's served directly by the FastAPI orchestrator as static files.

## Run it
```bash
# 1. start the API (Docker, or locally)
make api          # uvicorn scholar.api.main:app --port 8080
# (Docker: `make up` then open the orchestrator's port 8080)

# 2. open the app
xdg-open http://localhost:8080/app/      # '/' also redirects here
```

## What it does
- **Upload** a CV (PDF/TXT, drag-and-drop) → `POST /ingest` extracts the text.
- Pick **Fast** (DB-only) or **Deep research** (live web) + optional **kit** items.
- **Live progress**: streams `POST /pipeline/stream` (SSE) and lights up each stage
  — Reading CV → Researching → Scoring → Drafting → Fact-checking → Kit.
- **Results**: ranked match cards with score rings + eligibility, a detail panel
  with the cold email / SOP (copy buttons, approval badge), and the application
  kit (with a one-click `.ics` calendar download for deadlines).

## Design notes
- Single file: [index.html](index.html). State + SSE parsing in one small Alpine
  component; no bundler, no framework install.
- Talks only to same-origin API routes, so there's no CORS/config to manage.
- To evolve into a full Next.js app later, these same endpoints (`/ingest`,
  `/pipeline/stream`, `/pipeline/run`) are the contract — nothing server-side changes.
```
