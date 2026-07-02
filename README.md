# scholar-agent

**Autonomous Academic Matchmaking & Synthesis Pipeline** — a fully open-source,
agentic platform that discovers funded scholarships / PhD / Master's positions
and drafts **grounded** (non-hallucinated) cold emails and Statements of Purpose.

This repository is the complete build-out of the architecture blueprint in
[SKILLS/skills.md](SKILLS/skills.md). It delivers all three requested artifacts —
the LangGraph multi-agent boilerplate, the Neo4j Cypher schema, and the Docker
Compose architecture map — and folds in the agentic-AI patterns that matter in
2026 (see [What's "trending" here](#whats-trending-here-and-why)).

> 📖 **New here? Read [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)** — a
> full, in-depth narrative of *what* this is and *how* every piece works, with a
> step-by-step trace of one CV flowing through all five agents.

---

## The pipeline at a glance

```
 CV / transcript ─► Profiler ─► Scout ─► Matchmaker ─► Scribe ⇄ Quality Gate ─► bundles
   (ingest.py)      (Agent 1)  (Agent 2) (Agent 3)    (Agent 4)  (Agent 5)
                       │          │          │            └──── reflection loop ────┘
                  StudentProfile  │     GraphRAG score      (regenerate until grounded
                              web + OpenAlex   (semantic ⊕   or retry budget spent)
                              + NSF/NIH        graph ⊕ rules)
```

| Agent | Role | Model tier | Output contract |
|-------|------|-----------|-----------------|
| 1. **Profiler** | Parse messy CV/transcript → structured profile | `FAST` | `StudentProfile` |
| 2. **Scout** | Plan searches, scrape, query OpenAlex/NSF/NIH, index | `FAST` | `Opportunity[]` |
| 3. **Matchmaker** | Fuse semantic + graph + eligibility into 0–100 | `HEAVY` | `MatchResult[]` |
| 4. **Scribe** | Draft cold email + SOP, grounded in evidence | `SCRIBE` | `SynthesisBundle` |
| 5. **Quality Gate** | Claim-by-claim factuality audit; reject + feedback | `HEAVY` | `GroundednessReport` |

Each agent is a pure `async (state) -> partial_state` LangGraph node in
[src/scholar/agents/](src/scholar/agents/). The state machine — including the
bounded Scribe⇄Quality-Gate reflection loop and the map over the shortlist — is
wired in [src/scholar/graph_app.py](src/scholar/graph_app.py).

---

## Deliverables (mapped to the blueprint's §6)

1. **LangGraph multi-agent boilerplate** → [src/scholar/graph_app.py](src/scholar/graph_app.py) + [src/scholar/agents/](src/scholar/agents/)
2. **Neo4j Cypher schema** → [infra/neo4j/schema.cypher](infra/neo4j/schema.cypher) (constraints, property + native vector indexes) with [seed data](infra/neo4j/seed.cypher)
3. **Docker Compose / architecture map** → [docker-compose.yml](docker-compose.yml)

### The air-gap, realised in Docker networks

The blueprint's "models are air-gapped, only the orchestrator touches the
internet" security model is enforced concretely: the model servers and databases
sit on a `brains` network declared `internal: true` (no egress), and **only** the
orchestrator is dual-homed onto the internet-facing `hands` network.

```
┌───────────── network: brains (internal: true — NO internet) ─────────────┐
│  vllm-heavy   vllm-fast   vllm-scribe        neo4j        qdrant          │
│  Qwen2.5-72B  Nemo-12B    Qwen2.5-32B      (GraphRAG)   (vectors)         │
└───────────────────────────────┬──────────────────────────────────────────┘
                                 │ OpenAI-compatible REST (/v1/chat/completions)
                    ┌────────────┴─────────────┐
                    │  orchestrator (Hands)     │  LangGraph + FastAPI + MCP
                    └────────────┬─────────────┘
                                 │ network: hands (egress)
                       SearXNG · Tavily · OpenAlex · NSF · NIH
```

On bare metal this maps 1:1 onto the Proxmox design: each `vllm-*` service is an
Ubuntu VM with PCIe-passthrough GPUs; the orchestrator is the Docker/K8s
"Hands" layer.

---

## Quick start

### Option A — laptop / no GPU (Ollama as the "brains")
```bash
# 1. Serve open models locally
ollama pull qwen2.5:32b && ollama pull mistral-nemo && ollama serve

# 2. Point the orchestrator at Ollama
cp .env.example .env
#   LLM_BASE_URL=http://host.docker.internal:11434/v1
#   MODEL_HEAVY=qwen2.5:32b   MODEL_FAST=mistral-nemo   MODEL_SCRIBE=qwen2.5:32b

# 3. Bring up DBs + orchestrator (no GPU profile)
make up && make schema && make seed

# 4. Run the pipeline on the sample CV
make run            # or: scholar run examples/sample_cv.txt --query "funded PhD, EU, ML"
```

### Option B — full GPU stack (vLLM brains)
```bash
cp .env.example .env          # set NEO4J_PASSWORD, point LLM_BASE_URL at vllm-heavy
make brains                   # docker compose --profile gpu up -d --build
make schema && make seed
curl -s localhost:8080/health
```

### Use it three ways
```bash
scholar run examples/sample_cv.txt --query "ML, Netherlands"     # CLI
curl -XPOST localhost:8080/pipeline/run -d '{"documents":["..."]}' # REST
python -m scholar.mcp_server                                       # MCP (stdio)
```
The `/pipeline/stream` endpoint emits Server-Sent Events per node for live UIs.

---

## What's "trending" here (and why)

The blueprint asked for the state of the art; these are the deliberate, current
choices layered on top of it:

- **Structured outputs everywhere** — every agent returns a validated Pydantic
  model via constrained/guided JSON decoding (`guided_json` on vLLM), so no
  agent re-parses another's free text. See [llm/client.py](src/scholar/llm/client.py).
- **Hybrid retrieval + cross-encoder rerank** — dense (bge) ⊕ BM25 fused with
  Reciprocal Rank Fusion, then `bge-reranker-v2-m3` for precision. Pure vector
  search is no longer enough. See [kb/vectors.py](src/scholar/kb/vectors.py).
- **True GraphRAG** — eligibility (GPA/region/funding) and the *graph proximity*
  score are Cypher traversals, not LLM guesses, so the system never recommends
  something the student can't get. See [kb/graph.py](src/scholar/kb/graph.py).
- **Reflection / self-correction loop** — the Quality Gate decomposes each draft
  into atomic claims and bounces it back to the Scribe with targeted feedback
  until grounded (bounded by `MAX_REFLECTION_LOOPS`). This is the anti-
  hallucination guarantee, made operational.
- **Tiered model routing** — right model for the job (72B only for reasoning/
  verification; 12B for extraction/tools). See [llm/router.py](src/scholar/llm/router.py).
- **MCP server** — the platform is also an MCP *provider*, so its tools and the
  whole pipeline plug into Claude Desktop / IDEs / other agents. See
  [mcp_server.py](src/scholar/mcp_server.py).
- **Local, torch-free embeddings** — `fastembed` (ONNX) keeps the Hands
  container light; GPUs stay reserved for the Brains.
- **Observability built in** — `structlog` JSON logs + optional self-hosted
  Langfuse tracing, both no-op when unconfigured. See [observability.py](src/scholar/observability.py).
- **CPU/GPU split & air-gapped networking** — encoded in `docker-compose.yml`.

---

## Project layout

```
src/scholar/
├── config.py            # typed settings (pydantic-settings)
├── observability.py     # structlog + optional Langfuse
├── ingest.py            # PDF/txt loaders (step 1: context ingestion)
├── state.py             # LangGraph PipelineState (TypedDict + reducers)
├── graph_app.py         # the state machine: nodes, edges, reflection loop
├── cli.py               # `scholar run ...`
├── mcp_server.py        # MCP provider (tools + full pipeline)
├── schemas/             # Pydantic contracts shared by all agents
├── llm/                 # OpenAI-compatible client + tiered router
├── kb/                  # embeddings, Qdrant hybrid search, Neo4j GraphRAG
├── tools/               # web_search, openalex, nsf/nih, scraper (Scout's hands)
├── agents/              # the 5 agents + prompts
└── api/                 # FastAPI (run + SSE stream)
infra/neo4j/             # schema.cypher + seed.cypher (Deliverable #2)
docker-compose.yml       # full stack + air-gap networks (Deliverable #3)
tests/test_smoke.py      # offline tests (no infra needed)
```

## Development & testing
```bash
make dev      # editable install + dev extras
make test     # offline unit tests (no infra needed)
make check    # LIVE health-check: Qdrant, Neo4j, LLM providers, search, embeddings
make lint     # ruff + mypy
```
`make check` is the fastest way to answer *"is my whole system working?"* — it
pings every runtime dependency and exits non-zero if anything critical is down.
Run `make check ARGS=--full` to also load the embedding model.

## Security
Secrets (`.env`, `providers.json`) are git-ignored — copy the `*.example`
templates and keep real keys out of version control. If a key has ever been
exposed, **rotate it**. See [SECURITY.md](SECURITY.md) for the full policy and
the human-in-the-loop / air-gap safeguards.

## Notes & honest limitations
- The wiring, contracts, graph schema and infra are complete and the tests pass;
  a live end-to-end run needs reachable model servers (Ollama/vLLM), Neo4j and
  Qdrant (`make check` verifies these).
- Respect target sites' robots.txt / ToS when scraping, and the etiquette of the
  OpenAlex/NSF/NIH APIs (the `OPENALEX_MAILTO` polite pool is preconfigured).
- Generated emails/SOPs are **drafts for human review**, never auto-send.

## License
[MIT](LICENSE) © 2026 Mehraj Rahman
