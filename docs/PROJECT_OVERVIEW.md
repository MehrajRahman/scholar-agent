# scholar-agent — In-Depth Project Description

> A complete, narrative explanation of **what** this project is and **how** every
> piece works together. If [README.md](README.md) is the map, this is the guided tour.

---

## Table of contents
1. [What problem does this solve?](#1-what-problem-does-this-solve)
2. [The one mental model: Brains vs Hands](#2-the-one-mental-model-brains-vs-hands)
3. [The 30-second version](#3-the-30-second-version)
4. [A full end-to-end trace (follow one CV through the machine)](#4-a-full-end-to-end-trace)
5. [The five agents, in depth](#5-the-five-agents-in-depth)
6. [The Knowledge Base: graph + vectors](#6-the-knowledge-base-graph--vectors)
7. [The anti-hallucination reflection loop](#7-the-anti-hallucination-reflection-loop)
8. [The LLM layer: routing + structured outputs](#8-the-llm-layer-routing--structured-outputs)
9. [The state machine: how LangGraph actually moves data](#9-the-state-machine)
10. [Data contracts (the schemas)](#10-data-contracts)
11. [Infrastructure & the air-gap](#11-infrastructure--the-air-gap)
12. [Why these "trendy" choices](#12-why-these-trendy-choices)
13. [File-by-file map](#13-file-by-file-map)
14. [Glossary](#14-glossary)

---

## 1. What problem does this solve?

A student hunting for a **funded PhD / Master's position or scholarship** has to:
1. Read dozens of university pages, lab sites, and funding databases.
2. Figure out which ones they're actually *eligible* for (GPA, region, funding type).
3. Judge which ones *fit* their research interests.
4. Write a unique, personalised cold email + Statement of Purpose for each —
   without lying about themselves or misrepresenting the professor's work.

That's days of tedious, error-prone work. **scholar-agent automates it** as a
pipeline of five specialised AI agents that discover opportunities, score them
against a real knowledge graph, and draft application materials that are
**fact-checked against evidence** before you ever see them.

The hard part isn't "generate an email." Any chatbot does that. The hard part is
generating an email that contains **zero invented facts** — no fake shared
interests, no papers the professor never wrote, no skills you don't have. That
guarantee is the whole reason this is a *pipeline* and not a prompt.

---

## 2. The one mental model: Brains vs Hands

If you remember nothing else, remember this split. The entire system is two
halves with opposite jobs and opposite hardware needs:

```
        BRAINS (think)                         HANDS (act)
   ┌─────────────────────┐            ┌──────────────────────────┐
   │  The LLMs:           │            │  LangGraph orchestrator   │
   │  Qwen2.5-72B (heavy) │  ◄──REST──►│  + the 5 agent functions  │
   │  Nemo-12B   (fast)   │  OpenAI    │  + tools (web/APIs)       │
   │  Qwen2.5-32B(scribe) │  protocol  │  + Neo4j + Qdrant         │
   │                      │            │                           │
   │  Need: big GPUs      │            │  Need: CPU + a few GB RAM │
   │  Touch internet: NO  │            │  Touch internet: YES      │
   └─────────────────────┘            └──────────────────────────┘
```

- The **Brains** are dumb-but-powerful text engines. They never browse the web.
  They receive a prompt, return text. That's it.
- The **Hands** are the orchestration: they decide *what* to ask the Brains,
  fetch real-world data, store it, and enforce the rules.

This split is *physical* in production (Brains = air-gapped GPU VMs, Hands =
a Docker container), and it's why you can run the Hands on a laptop while the
Brains live in the cloud — the seam between them is just an HTTP URL
(`LLM_BASE_URL`).

---

## 3. The 30-second version

```
 CV/transcript ─► Profiler ─► Scout ─► Matchmaker ─► Scribe ⇄ Quality Gate ─► bundles
   (a PDF)        extract    search &   score every    write       fact-check
                  a profile  index      opportunity    email+SOP   & loop if lying
```

Five agents, each a small async Python function. Data flows left to right through
a shared **state object**. The only backward arrow is the Scribe ⇄ Quality Gate
loop, which rewrites a draft until it passes the fact-check. Everything is wired
in [graph_app.py](src/scholar/graph_app.py).

---

## 4. A full end-to-end trace

Let's follow the real sample CV — *Ada Researcher* ([examples/sample_cv.txt](examples/sample_cv.txt)) —
through the whole machine, step by step, so "what is happening" becomes concrete.

**Input:** a text CV saying Ada has a 3.85 GPA, knows PyTorch + graph neural
networks, and wants a *fully funded PhD in Germany or the Netherlands* in ML for
drug discovery.

### Step 0 — Ingestion ([ingest.py](src/scholar/ingest.py))
The file is read into raw text. If it were a PDF, `pypdf` would extract the text.
No AI here — just bytes → string. The string goes into the pipeline state as
`raw_documents`.

### Step 1 — Profiler ([agents/profiler.py](src/scholar/agents/profiler.py))
The `FAST` model reads the messy CV text and returns a **validated**
`StudentProfile` JSON object:
```jsonc
{ "full_name": "Ada Researcher", "skills": ["python","pytorch","machine learning",...],
  "research_interests": ["graph neural networks","drug discovery",...],
  "education": [{"gpa": 3.85, "gpa_scale": 4.0}],
  "target_degree": "PhD", "geographic_constraints": ["Germany","Netherlands"],
  "requires_full_funding": true }
```
The profile is also written into Neo4j as a `(:Student)` node connected to
`(:Skill)` and `(:Topic)` nodes. **State updated:** `profile`.

### Step 2 — Scout ([agents/scout.py](src/scholar/agents/scout.py))
This is the busiest agent. In order:
1. **Plan** — the `FAST` model turns the profile into ~8 focused search queries
   (`"funded PhD graph neural networks drug discovery Netherlands 2026"`, …).
2. **Search** — all queries run *concurrently* against Tavily/SearXNG → a list of
   candidate URLs (deduped, capped at 12).
3. **Gather** — concurrently scrape those pages to clean text
   ([scraper.py](src/scholar/tools/scraper.py)) **and** query OpenAlex for related
   papers ([openalex.py](src/scholar/tools/openalex.py)).
4. **Extract** — the `FAST` model reads all that gathered text and emits a list of
   structured `Opportunity` objects, each with a **real `source_url`**.
5. **Ground the professors** — for each opportunity's professor, it calls OpenAlex
   to fetch their *actual* publication footprint and stores it as
   `research_summary`. This is the evidence the Quality Gate will check against later.
6. **Index** — every opportunity is written to **Qdrant** (as a vector) and
   **Neo4j** (as a `(:Opportunity)` node linked to skills, university, professor).

**State updated:** `opportunities`, `search_log`. This is the "Knowledge Graph
Construction" step from the blueprint.

### Step 3 — Matchmaker ([agents/matchmaker.py](src/scholar/agents/matchmaker.py))
Now it scores Ada against each opportunity by **fusing three independent signals**:
- **semantic_score** — Ada's profile text vs each opportunity, via hybrid
  search (dense + keyword) and cross-encoder reranking, in Qdrant.
- **graph_score** — how many of the opportunity's required skills Ada actually has,
  computed as a *Cypher traversal* in Neo4j (not a guess).
- **eligible** — a hard yes/no gate: does Ada meet the GPA floor, region, and
  funding requirement? Also a Cypher query.

The top candidates go to the `HEAVY` model, which combines the signals into a
calibrated **0–100 score** + a rationale citing the specific shared skills. A
crucial rule: **if `eligible` is false, the score is forced below 40** — you can't
recommend something Ada can't get, no matter how semantically similar it looks.

Opportunities scoring ≥ threshold (default 70) **and** eligible become the
**shortlist**. **State updated:** `matches`, `shortlist`, `current_index = 0`.

### Step 4 — Scribe ([agents/scribe.py](src/scholar/agents/scribe.py))
For shortlist item #0, the `SCRIBE` model writes a `ColdEmail` + `SOPDraft`. It's
given three things: Ada's profile, the opportunity, and the professor's **real
record** pulled back from Neo4j. The system prompt forbids inventing shared
interests or papers. If this is a *re-write* (loop iteration ≥ 2), it also receives
the Quality Gate's feedback and must fix exactly those issues.
**State updated:** `draft`.

### Step 5 — Quality Gate ([agents/quality_gate.py](src/scholar/agents/quality_gate.py))
The `HEAVY` model breaks the draft into **atomic claims** and checks each against
the evidence (Ada's profile + the professor's record). It returns a
`GroundednessReport`: `approved` (bool), a per-claim breakdown, a list of
`hallucinations`, and `feedback`.
**State updated:** `review`, `revision_count += 1`.

### The decision ([graph_app.py](src/scholar/graph_app.py))
- **Approved?** → `commit`: file the bundle, move to the next shortlist item.
- **Rejected but retries left?** → back to **Scribe** with the feedback (the loop).
- **Rejected and out of retries?** → `commit` anyway, but flagged `approved=false`
  so a human knows to review it.

`commit` advances `current_index`. If there are more shortlisted opportunities, it
loops back to the Scribe for the next one; otherwise the pipeline **ends**.

### Output
A list of `SynthesisBundle`s — each a scored opportunity with a fact-checked cold
email and SOP, plus how many revisions it took. Returned via CLI, REST, or MCP.

---

## 5. The five agents, in depth

Every agent is a pure `async def node(state) -> dict` function. It reads what it
needs from the shared state and returns a *partial* dict that LangGraph merges
back in. That purity is why each one is independently unit-testable.

| # | Agent | Model tier | Reads | Writes | Why this model |
|---|-------|-----------|-------|--------|----------------|
| 1 | **Profiler** | `FAST` (12B) | raw docs | `profile` | Extraction is easy; 12B is cheap & fast at JSON |
| 2 | **Scout** | `FAST` (12B) | profile | `opportunities` | Query-planning + extraction; tool-calling work |
| 3 | **Matchmaker** | `HEAVY` (72B) | profile, opps | `matches`, `shortlist` | Judgement/calibration needs the smart model |
| 4 | **Scribe** | `SCRIBE` (32B) | shortlist item | `draft` | Long-form writing; 32B has nuance + context |
| 5 | **Quality Gate** | `HEAVY` (72B) | draft | `review` | Verification is the highest-stakes reasoning |

The **prompts** that define each agent's behaviour live in one place,
[agents/prompts.py](src/scholar/agents/prompts.py), so they can be versioned and
tuned without touching logic.

---

## 6. The Knowledge Base: graph + vectors

Two databases, two jobs. They are complementary, not redundant.

### Qdrant — "what is *similar*?" (fuzzy)
A vector database. Every opportunity's text is turned into a 1024-dimensional
embedding (`bge-large-en-v1.5`) and stored. To find matches for Ada, we embed her
profile and find the nearest opportunity vectors. Good at *meaning* ("GNN" ≈
"graph representation learning") but blind to exact terms and hard rules.

The retrieval in [kb/vectors.py](src/scholar/kb/vectors.py) is **hybrid + reranked**,
the current best practice:
1. **Dense** search (embeddings) → candidates by meaning.
2. **BM25** keyword search over the same pool → candidates by exact terms.
3. **Reciprocal Rank Fusion** merges the two rankings.
4. **Cross-encoder rerank** (`bge-reranker-v2-m3`) re-scores the top candidates for
   precision — it reads query+doc *together* instead of comparing two fixed vectors.

### Neo4j — "what is *connected* and *allowed*?" (exact)
A graph database. This is what stops the system recommending things Ada can't get.
Instead of fuzzy similarity, it stores hard relationships
([kb/graph.py](src/scholar/kb/graph.py), schema in
[infra/neo4j/schema.cypher](infra/neo4j/schema.cypher)):

```
(Student)-[:HAS_SKILL]──────►(Skill)◄──────[:REQUIRES]-(Opportunity)
(Student)-[:INTERESTED_IN]──►(Topic)◄──────[:RESEARCHES]-(Professor)
(Professor)-[:OFFERS]───────►(Opportunity)-[:AT]──────►(University)
(Opportunity)-[:FUNDED_BY]──►(Funding)
```

From this graph we read two things by **traversal, not vibes**:
- **Eligibility** — `eligible()` checks GPA ≥ floor, region overlap, funding type.
  A pure SQL/Cypher boolean. No LLM can "creatively" approve an ineligible match.
- **Graph proximity** — `graph_proximity()` counts how many of the opportunity's
  required skills Ada *actually possesses*, normalised to a 0–1 coverage score.

> **This is "GraphRAG":** retrieval augmented not just by chunked text but by an
> explicit knowledge graph, so the model reasons over *facts and relationships*,
> not just paragraphs.

---

## 7. The anti-hallucination reflection loop

This is the single most important design decision, so it gets its own section.

LLMs hallucinate. A normal "write me an SOP" prompt will happily invent that you
share the professor's passion for a paper you've never read. For a real
application, that's a disaster. The defence is **separation of powers**:

- The **Scribe** writes. It is *creative* and will occasionally overreach.
- The **Quality Gate** is a separate, adversarial reviewer with a different model
  and a different prompt. Its only job is to *distrust* the Scribe.

```
        ┌──────────────────────────────────────────────┐
        │                                              ▼
   ┌────────┐                                   ┌──────────────┐
   │ Scribe │ ── draft ──────────────────────►  │ Quality Gate │
   └────────┘                                   └──────┬───────┘
        ▲                                              │ decomposes into atomic
        │  feedback:                                   │ claims, checks each vs
        │  "remove claim X — not in CV"                │ profile + prof record
        │                                              │
        └──── rejected & retries left ◄────────────────┤
                                                       │ approved OR
                                                       │ out of retries
                                                       ▼
                                                    ┌────────┐
                                                    │ commit │
                                                    └────────┘
```

The loop is **bounded** by `MAX_REFLECTION_LOOPS` (default 3) so a stubborn draft
can't spin forever — after the budget is spent it ships the best attempt but flags
`approved=false`. The routing logic is `route_after_quality_gate()` in
[graph_app.py](src/scholar/graph_app.py). This pattern — *generate → critique →
regenerate with targeted feedback* — is "reflection" / "self-correction," and it's
why the output can credibly be called "hallucination-free."

---

## 8. The LLM layer: routing + structured outputs

### One client, any backend ([llm/client.py](src/scholar/llm/client.py))
vLLM, Ollama, and most hosted providers all speak the **OpenAI protocol**
(`/v1/chat/completions`). So there's exactly one client. Swapping your entire model
backend = changing `LLM_BASE_URL`. That's the seam that lets you run Brains
anywhere.

### Tiered routing ([llm/router.py](src/scholar/llm/router.py))
"Right model for the job." Paying 72B prices to extract JSON is wasteful, so each
agent **role** maps to the cheapest model that clears its quality bar:
- `HEAVY` (72B, temp 0.0) — reasoning & verification (Matchmaker, Quality Gate).
- `FAST` (12B, temp 0.1) — extraction & tools (Profiler, Scout).
- `SCRIBE` (32B, temp 0.5) — writing, with a little warmth.

### Structured outputs (the reliability backbone)
Every agent returns a **validated Pydantic object**, not free text. The client's
`structured()` method asks the model for JSON matching a schema, using vLLM's
`guided_json` (constrained decoding) when available, and validates the result —
falling back to extracting the JSON object from the text if the engine didn't
enforce it. The payoff: the Scout never has to "re-parse" the Profiler's prose;
it receives a typed `StudentProfile`. This is what makes a 5-stage pipeline
robust instead of a game of telephone.

---

## 9. The state machine

LangGraph models the pipeline as a graph of nodes connected by edges. The data
that flows between them is a single dict, `PipelineState`
([state.py](src/scholar/state.py)).

- Each node returns a **partial** state dict; LangGraph **merges** it in.
- List fields use **reducers** (`Annotated[list, operator.add]`) so appends from
  different nodes accumulate instead of overwriting — e.g. each `commit` *appends*
  one finished bundle to `bundles`.
- **Edges** are the wiring. Most are straight (`profiler → scout`). Three are
  **conditional** — small Python functions that look at the state and return the
  name of the next node:
  - `route_after_matchmaker` → `scribe` if there's a shortlist, else `END`.
  - `route_after_quality_gate` → the reflection-loop decision.
  - `route_after_commit` → `scribe` for the next item, or `END`.

So the "synthesis" half of the pipeline is a **map-reduce**: map the Scribe over
each shortlisted opportunity, each pass guarded by the reflection loop, reducing
into the `bundles` list. The compiled graph is cached in `get_app()`.

---

## 10. Data contracts

All the typed objects passed between agents live in
[src/scholar/schemas/](src/scholar/schemas/). They *are* the API between stages:

- **`StudentProfile`** — the applicant. Has helpers like `best_gpa_4` (normalises
  GPA to a 4.0 scale for graph filtering) and `embedding_text()` (the surface used
  for vector search).
- **`Opportunity`** — one discovered position. Has a content-addressed `id`
  (sha1 of title+university+url) used as the stable key in *both* databases, and a
  mandatory `source_url` (provenance — nothing gets cited without a source).
- **`MatchResult`** — the Matchmaker's verdict: score, the three sub-scores,
  eligibility, rationale, matched skills, and honest gaps.
- **`GroundednessReport`** — the Quality Gate's verdict: approved, per-claim
  support, hallucinations, feedback.
- **`SynthesisBundle`** — the final deliverable: email + SOP + score + revision count.

Because these are Pydantic models, an invalid object literally cannot move to the
next stage — the validation error fires at the boundary.

---

## 11. Infrastructure & the air-gap

Defined in [docker-compose.yml](docker-compose.yml). The blueprint's security claim
— "the models are air-gapped; only the orchestrator touches the internet" — is
enforced with **Docker networks**, not just words:

```
┌─────────── network: brains (internal: true → NO internet) ───────────┐
│   vllm-heavy    vllm-fast    vllm-scribe      neo4j       qdrant      │
└──────────────────────────────┬───────────────────────────────────────┘
                               │  (OpenAI REST, internal only)
                  ┌────────────┴─────────────┐
                  │   orchestrator (Hands)    │  ◄── the ONLY dual-homed box
                  └────────────┬─────────────┘
                               │  network: hands (has egress)
                     SearXNG · Tavily · OpenAlex · NSF · NIH
```

The `brains` network is declared `internal: true`, so the model and database
containers have **no route to the internet**. Only the orchestrator sits on both
networks. On bare metal this maps 1:1 onto the Proxmox design: each `vllm-*`
service becomes an Ubuntu VM with PCIe-passthrough GPUs.

**Where to actually run it** (see the [README quick start](README.md#quick-start)):
the Hands run on a laptop; the Brains run wherever the GPUs are (a hosted
OpenAI-compatible API for dev, rented GPU VMs or your own Proxmox box for
production). The `gpu` Docker profile only activates the local vLLM servers when
you have GPUs.

---

## 12. Why these "trendy" choices

Each modern pattern earns its place by killing a specific failure mode:

| Pattern | Failure it prevents |
|---------|--------------------|
| Structured outputs (Pydantic + guided JSON) | Stage-to-stage "telephone" corruption |
| Hybrid search + reranking | Pure-vector search missing exact terms (grant names, labs) |
| GraphRAG (Neo4j traversals) | Recommending ineligible / unqualified matches |
| Reflection loop (Scribe ⇄ Quality Gate) | Hallucinated facts in an application |
| Tiered model routing | Burning 72B compute on trivial extraction |
| MCP server | Being a closed silo instead of an ecosystem tool |
| Local `fastembed` (ONNX) | Forcing a GPU/torch dependency into the light Hands box |
| Observability (structlog + Langfuse) | A black box you can't debug |

---

## 13. File-by-file map

```
src/scholar/
├── config.py            Typed settings from env/.env (one source of truth)
├── observability.py     JSON logging + optional Langfuse tracing
├── ingest.py            PDF/txt/md → raw text (no AI; step 1)
├── state.py             PipelineState: the dict that flows through the graph
├── graph_app.py         ★ The state machine: nodes, edges, reflection loop
├── cli.py               `scholar run cv.pdf --query "..."`
├── mcp_server.py        Exposes tools + pipeline over MCP (stdio)
│
├── schemas/             ★ The typed contracts between every stage
│   ├── profile.py         StudentProfile, EducationEntry
│   ├── opportunity.py     Opportunity, Professor, Funding, OpportunityKind
│   ├── match.py           MatchResult, GroundednessReport, Claim
│   └── artifacts.py       ColdEmail, SOPDraft, SynthesisBundle
│
├── llm/
│   ├── client.py          OpenAI-compatible async client + structured outputs
│   └── router.py          Role → (model, temperature) tiering
│
├── kb/
│   ├── embeddings.py      fastembed bge embeddings + cross-encoder reranker
│   ├── vectors.py         Qdrant store + hybrid (dense+BM25) search + RRF
│   └── graph.py           Neo4j GraphRAG: eligibility + proximity traversals
│
├── tools/                ★ The only code that touches the public internet
│   ├── search.py          Tavily → SearXNG web search
│   ├── openalex.py        Scholarly graph: papers + professor footprints
│   ├── funding.py         NSF Awards + NIH RePORTER
│   └── scraper.py         URL → clean main text (trafilatura)
│
├── agents/               ★ The five agents + their prompts
│   ├── profiler.py        1. CV → StudentProfile
│   ├── scout.py           2. plan → search → extract → index opportunities
│   ├── matchmaker.py      3. fuse semantic+graph+rules → 0–100 score
│   ├── scribe.py          4. write grounded email + SOP
│   ├── quality_gate.py    5. fact-check claims, approve or reject
│   └── prompts.py         All system prompts, versioned in one place
│
└── api/main.py            FastAPI: /pipeline/run + /pipeline/stream (SSE)

infra/neo4j/   schema.cypher (constraints + vector index) + seed.cypher
docker-compose.yml   Full stack + the air-gapped network topology
tests/test_smoke.py  Offline tests: schemas, graph topology, routing, RRF
examples/sample_cv.txt  The "Ada Researcher" CV used in the trace above
```

★ = start here if you're reading the code for the first time.

**Suggested reading order:** `state.py` → `schemas/` → `graph_app.py` →
then each agent in pipeline order → then `kb/` and `tools/` for the details.

---

## 14. Glossary

- **Agent** — one specialised step; here, an `async` function that calls a model
  and/or tools and returns a partial state update.
- **LangGraph** — the library that runs the agents as a directed graph with shared
  state and conditional edges.
- **Brains / Hands** — the LLM servers (GPU, air-gapped) vs the orchestrator
  (CPU, internet-facing).
- **Structured output** — forcing the model to return JSON matching a schema, then
  validating it.
- **Embedding** — a vector of numbers representing the *meaning* of text; similar
  meanings → nearby vectors.
- **Hybrid search** — combining dense (embedding) and sparse (BM25 keyword)
  retrieval.
- **Reranker / cross-encoder** — a model that scores a (query, document) *pair*
  together for higher precision than vector distance.
- **RRF (Reciprocal Rank Fusion)** — a simple, robust way to merge multiple ranked
  lists into one.
- **GraphRAG** — retrieval augmented by an explicit knowledge graph (relationships),
  not just text chunks.
- **Reflection loop** — generate → critique → regenerate-with-feedback, bounded by
  a retry budget.
- **Eligibility gate** — a hard, rule-based yes/no (GPA, region, funding) computed
  in the graph, immune to LLM "creativity."
- **MCP (Model Context Protocol)** — an open standard for exposing tools/data to
  any AI client; this project is both a consumer and a provider.
- **Provenance** — every opportunity carries a real `source_url`; nothing is cited
  without it.
```
