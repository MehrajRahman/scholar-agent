# scholar-agent — Master System Design & Build Plan (v2)

> **Goal:** a complete, real, $0-budget personal scholarship-application system you
> will *actually use* — that finds up-to-date funded opportunities, keeps a fresh
> local knowledge base, and generates a full grounded application kit (not just an
> email + SOP). A web app comes later; this plan makes the **core precise** first.

This supersedes the v1 scaffold's scope. It is research-backed (June 2026) and
opinionated — each decision is a recommendation, not a menu.

---

## 0. Design principles

1. **Two speeds.** Instant answers from the local DB; comprehensive answers from
   live "deep research" — the user chooses per run.
2. **Freshness is a feature.** Deep research re-verifies and *writes back* new/
   changed opportunities, so the DB compounds in value over time.
3. **Grounded or it doesn't ship.** Every generated sentence is fact-checked
   against the CV + the opportunity's real source. No invented claims, ever.
4. **Model-portable.** We hop across free LLM providers; a prompt-adapter layer
   keeps quality stable as the underlying model changes.
5. **Free-first.** Every component has a $0 path for development. Paid is opt-in.
6. **Buy the boring, build the core.** Adopt mature OSS for scraping, automation,
   notifications; build the stateful reasoning core ourselves (LangGraph).

---

## 1. Tooling verdicts (you asked about Hermes, n8n, OpenClaw + others)

| Tool | What it is | Verdict for this project | Phase |
|------|-----------|--------------------------|-------|
| **LangGraph** | Stateful agent graph engine | ✅ **Core engine.** Best for cyclic, reflective, multi-agent state machines. Keep. | now |
| **Hermes 3** ([Nous](https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B)) | Llama-3.1 fine-tune, 4.3% tool-use training, `<tool_call>` format, ~GPT-4 tool use | ✅ **Adopt as the tool-calling model** for Profiler/Scout (8B fast, 70B heavy). Free via OpenRouter or local. | 1 |
| **GPT Researcher** ([repo](https://github.com/assafelovic/gpt-researcher)) / **open_deep_research** ([LangChain](https://github.com/langchain-ai/open_deep_research)) / **DeerFlow** | Recursive deep-research agents (plan→search→reflect→expand), Apache-2.0 | ✅ **Adopt the *pattern*** as our "Deep Scout" subgraph (native, tied to our KB). Optionally call gpt-researcher as a turbo engine. | 2 |
| **Crawl4AI** ([repo](https://www.firecrawl.dev/blog/best-open-source-web-crawler)) | Apache-2.0, free, self-host crawler → LLM-ready markdown | ✅ **Adopt** for deep-research crawling (vs Firecrawl $83/mo). | 2 |
| **OpenRouter** ([free tiers](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)) | One API key → many providers w/ failover; free Qwen2.5-72B, Llama, Hermes | ✅ **Adopt as the LLM gateway** for $0 multi-provider routing. | 1 |
| **n8n** ([self-host kit](https://github.com/n8n-io/self-hosted-ai-starter-kit)) | Self-hosted (free) workflow automation, 70+ LangChain nodes, native MCP | ✅ **Adopt for the *ops layer*** — scheduled DB refresh, email/Telegram alerts, Gmail/Calendar/Sheets glue. ❌ Not the reasoning core. | 4 |
| **OpenClaw** ([guide](https://www.kdnuggets.com/openclaw-explained-the-free-ai-agent-tool-going-viral-already-in-2026)) | Free OSS autonomous agent with messaging-channel UX (Telegram/WhatsApp/Slack…) | 🟡 **Optional front-end/notifier** — chat with the system, approve drafts, get alerts on Telegram. Phase-2+ nicety, not core. | 4–5 |
| **Cerebras / Groq / Gemini free** | Ultra-fast free inference (~1M tok/day Cerebras; Groq 70B @320 tok/s) | ✅ **Adopt in the failover pool** for speed. | 1 |

**Bottom line:** keep LangGraph as the brain; use **Hermes via OpenRouter** for tool-calling; build a **Deep Scout** modeled on **GPT Researcher** using **Crawl4AI**; bolt on **n8n** for scheduling/alerts; offer **OpenClaw/Telegram** as the chat surface later.

---

## 2. Target architecture

```
                                   ┌──────────────────────────────┐
                            ┌──────►│  FAST MODE  (DB-only)         │
  CV/PDF ─► Profiler ─► MODE│       │  Matchmaker → Scribe → QGate  │──┐
            (+intake)  ROUTER       └──────────────────────────────┘  │
                            │       ┌──────────────────────────────┐  │
                            └──────►│  DEEP MODE (live research)    │  │
                                    │  Deep Scout (recursive) →     │  │
                                    │  Verify → Dedup/Upsert to DB →│  │
                                    │  Matchmaker → Scribe → QGate  │──┤
                                    └──────────────────────────────┘  │
                                                                      ▼
                                                         Application Kit (artifacts)
                                                         + freshness write-back to DB

  Cross-cutting layers:
   • Prompt Adapter   (model-family-aware templates + few-shots)
   • LLM Gateway      (OpenRouter/Groq/Cerebras/Gemini failover, $0)
   • Knowledge Base   (Neo4j graph + Qdrant vectors + freshness metadata)
   • Ops (n8n)        (cron refresh, email/Telegram alerts)  [Phase 4]
   • Chat surface     (OpenClaw / Telegram)                  [Phase 4–5]
```

---

## 3. The two modes (your core requirement)

### Fast mode — `mode="fast"`
- **Path:** Profiler → Matchmaker (queries existing Neo4j + Qdrant only) → Scribe → Quality Gate.
- **No internet.** Sub-second-to-seconds. Uses whatever the DB already knows.
- **If the DB is thin** for the student's topics, it returns best-effort matches **and** flags `"suggest_deep_research": true`.
- **Use it for:** iterating on drafts, re-running with tweaked constraints, demos.

### Deep Research mode — `mode="deep"`
- **Path:** Profiler → **Deep Scout** (recursive live research) → **Verify & Freshness** → **Dedup/Upsert to DB** → Matchmaker → Scribe → Quality Gate.
- **Live, comprehensive, up-to-date.** Minutes, runs as a background job with progress events.
- **Writes back:** new opportunities inserted; changed ones updated (version bumped); stale ones flagged. The DB gets richer every deep run.
- **Use it for:** the real hunt — "find me everything open right now."

### The Deep Scout subgraph (pattern from GPT Researcher / open_deep_research)
A bounded recursive loop — `breadth` sub-questions × `depth` levels (both configurable to cap cost/time):

```
1. PLAN     (HEAVY) profile+constraints → N research sub-questions
              e.g. "fully funded ML PhD Germany 2026", "DAAD CS scholarships",
                   "TU Munich GNN labs accepting PhD students"
2. GATHER   (tools) per sub-question: SearXNG/Tavily + OpenAlex + NSF/NIH +
              university pages → Crawl4AI → clean markdown
3. EXTRACT  (FAST)  markdown → structured Opportunity[] (real source_url + dates)
4. REFLECT  (HEAVY) "what's missing / unverified?" → follow-up sub-questions
              ── loop GATHER→EXTRACT→REFLECT until depth or no new gaps ──
5. VERIFY   (rules+LLM) deadline in future? page recent? funding confirmed?
6. WRITEBACK(KB)    content-hash dedup → insert new / update changed / mark stale
```

This is the same plan→search→reflect→expand→synthesize loop that tops the deep-
research benchmarks, but tuned to emit **opportunities into our graph**, not prose.

---

## 4. Prompt-engineering layer (your "while surfing model to model" requirement)

**Problem:** Hermes wants `<tool_call>` + ChatML; Qwen, Llama, Gemini each have
different sweet spots for system-prompt phrasing, JSON instruction, and stop
tokens. Naively reusing one prompt across them degrades quality.

**Solution — a Prompt Adapter Registry:**

```
src/scholar/prompts/
├── registry.py            get_prompt(role, model_family, version) -> PromptSpec
├── families.py            detect family from model id (hermes|qwen|llama|gemini|mistral|generic)
├── templates/
│   ├── profiler/
│   │   ├── generic.j2      # default
│   │   ├── hermes.j2       # ChatML + <tool_call> conventions
│   │   └── qwen.j2
│   ├── scout/ …
│   ├── matchmaker/ …
│   ├── scribe/ …
│   └── quality_gate/ …
└── fewshots/
    └── profiler.jsonl      # 3–5 curated CV→profile examples to stabilize output
```

- `PromptSpec` = `{system, fewshots, output_format, tool_format, stop}`.
- The **router** (`llm/router.py`) is extended to return `(model, temperature,
  family)`; the agent asks the registry for the right template by family.
- **Few-shot slots** per role make extraction consistent regardless of model.
- **Versioned** (`v1`, `v2`) so you can A/B prompts and measure (Phase 4 eval).
- Templates are Jinja2 — variables (`{{ profile }}`, `{{ context }}`) injected at call time.

This is the layer that makes provider-hopping safe and is where your "prompt
engineering" lives, isolated from agent logic.

---

## 5. Freshness & DB write-back (your "info should be up to date" requirement)

Extend `Opportunity` with lifecycle metadata:

| field | purpose |
|-------|---------|
| `first_seen_at` | when we discovered it |
| `last_verified_at` | last time deep research confirmed it still exists |
| `content_hash` | sha1 of salient fields → cheap change detection |
| `version` | bumped on each change |
| `status` | `active \| stale \| expired \| closed` |
| `deadline` | drives expiry + alert urgency |

**Write-back algorithm (Deep Scout step 6):**
```
for each extracted opp:
    existing = graph.get(opp.id)
    if not existing:                      insert (status=active, v1)
    elif existing.content_hash != new:    update + version++ + last_verified_at=now
    else:                                 touch last_verified_at=now
# expiry sweep:
mark status=expired where deadline < today
mark status=stale    where last_verified_at older than TTL (e.g. 21 days)
```

**Scheduled refresh (Phase 4, via n8n cron):** nightly, re-verify opportunities
with deadlines within 30 days or `status=stale`; alert the user about new matches
+ approaching deadlines (email/Telegram). This is how the DB stays current without
the user lifting a finger.

---

## 6. Beyond email + SOP — the **Application Kit** (your "other relevant stuff")

The Scribe becomes a configurable artifact factory; the request says which to
generate. Every artifact is fact-checked by the Quality Gate against the
profile + opportunity + professor record.

| # | Artifact | Notes |
|---|----------|-------|
| 1 | **Cold email** to professor | grounded, <200 words |
| 2 | **Statement of Purpose** | tailored per program |
| 3 | **Personal statement** | narrative/background variant |
| 4 | **Motivation / cover letter** | scholarship-specific |
| 5 | **CV tailoring report** | ATS keywords, reordering, gap flags — *suggests*, never fabricates |
| 6 | **Research proposal outline** | aligned to the lab's actual work |
| 7 | **Recommendation-request kit** | emails to referees + a "brag sheet" of your achievements |
| 8 | **Professor / lab dossier** | recent papers, funding, group size — interview prep brief |
| 9 | **Interview Q&A prep** | likely questions + grounded answer scaffolds |
| 10 | **Deadline checklist + calendar** | per-application doc list + `.ics` export |
| 11 | **LinkedIn note** | short connection message |

Implementation: an `ArtifactType` enum + a registry mapping each to a
prompt-template + output schema; the synthesis stage maps over the requested set.

---

## 7. The $0 / low-budget stack

| Layer | Free choice (dev) | Notes / paid upgrade |
|-------|-------------------|----------------------|
| **LLM inference** | **OpenRouter** free models (Qwen2.5-72B, Llama-3.3-70B, Hermes) + **Groq** + **Cerebras** + **Gemini (AI Studio)** | Rotate via gateway w/ failover. Upgrade: Together/DeepInfra pennies-per-call. |
| **Embeddings** | **fastembed** (local CPU, bge) | free forever |
| **Reranking** | **fastembed** cross-encoder (local) | free forever |
| **Vector DB** | **Qdrant** (Docker) — or **Chroma** for zero-infra dev | free, self-host |
| **Graph DB** | **Neo4j Community** (Docker) | free; low-RAM alt: **Kùzu** (embedded) |
| **Web search** | **SearXNG** (self-host) + **Tavily** free tier | $0 |
| **Crawling** | **Crawl4AI** (self-host) | $0 (vs Firecrawl $83/mo) |
| **Deep research** | our Deep Scout, or **gpt-researcher** lib | Apache-2.0, $0 |
| **Orchestration** | **LangGraph** | $0 OSS |
| **Automation/alerts** | **n8n** Community (self-host) | $0; ~$5/mo VPS if always-on |
| **Chat surface** | **OpenClaw** + Telegram bot (free) | optional |
| **Hosting (later)** | **Oracle Cloud Always Free** (4 ARM cores / **24 GB RAM**) | genuinely runs this whole stack for $0; alts: HF Spaces, Fly.io, Render free tiers |

**Recurring cost for development: $0.** (Your laptop runs the Hands; free APIs run
the Brains.) An always-on deployment is $0 on Oracle's free ARM box, or ~$5/mo on a
small VPS.

> ⚠️ Free-tier rate limits are real (Groq ~1k req/day; Cerebras ~1M tok/day). The
> **LLM Gateway with failover** (Phase 1) is what makes $0 viable — when one
> provider rate-limits, it rolls to the next.

---

## 8. Implementation roadmap (precise, phased)

### ✅ Phase 0 — v1 core (done)
5-agent LangGraph pipeline, KB layer, tools, Docker, tests. Runs end-to-end.

### ✅ Phase 1 — Core precision (DONE) — make model-hopping + modes solid
- `llm/gateway.py` — multi-provider failover client (OpenRouter→Groq→Cerebras→Gemini), honoring per-provider rate limits; keep the OpenAI-compatible surface.
- `llm/router.py` — return `family` alongside `(model, temperature)`.
- `prompts/` — the Prompt Adapter Registry + templates + few-shots (Profiler, Scout, Matchmaker, Scribe, QGate).
- `state.py` + `api` — add `mode: fast|deep` and a `mode_router` node.
- `schemas/opportunity.py` — add freshness fields (`first_seen_at`, `last_verified_at`, `content_hash`, `version`, `status`).
- Tests for: family detection, prompt selection, mode routing, hash/dedup.

### ✅ Phase 2 — Deep Research (DONE)
- `agents/deep_scout.py` — the recursive plan→gather→extract→reflect→verify subgraph.
- `tools/crawl.py` — Crawl4AI integration (replace/augment trafilatura for heavy crawl).
- `kb/graph.py` — `upsert_with_versioning()`, `expire_sweep()`, `get_by_hash()`.
- Bounded by `DEEP_BREADTH`, `DEEP_DEPTH` config.

### ✅ Phase 3 — Application Kit (DONE)
- `schemas/artifacts.py` — schemas for all 11 artifact types.
- `agents/scribe.py` — artifact registry + map over requested types.
- `agents/quality_gate.py` — per-artifact grounding checks (+ `.ics` builder for deadlines).

### 🟡 Phase 4 — Ops & automation (PARTIAL: sweep endpoint + n8n workflow shipped)
- n8n workflows: nightly deep-research refresh (cron); "new match / deadline soon" email + Telegram alerts; Gmail draft creation for approved emails.
- `api` — job queue + SSE progress for long deep runs; webhook endpoints n8n calls.
- Optional: OpenClaw/Telegram bot to chat + approve drafts.

### Phase 5 — Web app (we design together)
Next.js front-end: upload CV, pick mode, watch live progress, browse ranked
matches, edit/approve the application kit, track deadlines. Talks to the Phase-1+
API. (Separate design session, as you said.)

### ✅ (Continuous) Phase 6 — Evaluation (DONE: metric harness shipped)
Small golden set (your real target scholarships) + metrics: match precision@k,
grounding pass-rate, freshness lag. Lets you tune prompts/models with evidence.

---

## 9. What I recommend building first

**Phase 1, in this order** — it's the "make the core precise" work you asked for,
and it unblocks everything else:

1. **LLM Gateway with failover** → makes $0 multi-provider real and stops
   rate-limit dead-ends.
2. **Prompt Adapter Registry** → your prompt-engineering layer; stabilizes quality
   across Hermes/Qwen/Llama/Gemini.
3. **Mode router + freshness fields** → the fast-vs-deep split + write-back groundwork.

Each is self-contained, testable offline, and leaves the working v1 pipeline
runnable throughout.

---

## Sources
- n8n self-hosted AI: [github.com/n8n-io/self-hosted-ai-starter-kit](https://github.com/n8n-io/self-hosted-ai-starter-kit), [n8n.io/ai-agents](https://n8n.io/ai-agents/)
- Hermes 3: [HF model card](https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B), [Hermes-Function-Calling](https://github.com/NousResearch/Hermes-Function-Calling)
- Deep research: [GPT Researcher](https://github.com/assafelovic/gpt-researcher), [LangChain open_deep_research](https://github.com/langchain-ai/open_deep_research)
- Crawl4AI vs Firecrawl: [firecrawl.dev best open-source crawlers](https://www.firecrawl.dev/blog/best-open-source-web-crawler)
- Free LLM tiers: [OpenRouter comparison](https://openrouter.ai/blog/tutorials/free-llm-apis-compared/)
- OpenClaw: [KDnuggets explainer](https://www.kdnuggets.com/openclaw-explained-the-free-ai-agent-tool-going-viral-already-in-2026), [repo](https://github.com/openclaw/openclaw)
