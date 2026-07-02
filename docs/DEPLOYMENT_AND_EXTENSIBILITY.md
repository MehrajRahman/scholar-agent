# Deployment, Extensibility & Optimization Guide

This doc answers: **Is it complete? Where to host? Do I train? How to embed CVs? How to improve? How to add agents/models?**

---

## 1. Is it a complete agentic AI solution? Yes — and what "complete" means.

**✅ What's complete:**
- **5 fully-wired agents** in a deterministic state machine (LangGraph) that route work, share state, and loop on failure.
- **Knowledge graph** (Neo4j) that enforces hard rules (eligibility) via traversals, not LLM whim.
- **Hybrid retrieval** (dense + sparse + rerank) so it finds both meaning *and* exact terms.
- **Reflection loop** (Scribe ⇄ Quality Gate) that rejects hallucinated claims, not just "sounds plausible."
- **Structured outputs** at every stage (Pydantic validation) so the pipeline is robust to model drift.
- **Multi-backend LLM client** that swaps Groq ↔ vLLM ↔ Ollama with one env var.
- **Real-world data** (OpenAlex, NSF, NIH) integrated as tools, not mocked.
- **Docker architecture** that encodes the "air-gap" blueprint (Brains air-gapped, Hands egress-enabled).

**⚠️ What's intentionally NOT here (and why):**
- **User authentication** — this is a dev scaffold, not a SaaS app. Add `FastAPI-Users` or Auth0 if you deploy publicly.
- **Frontend** — no React/UI layer. The API is `/pipeline/run` (JSON) or `/pipeline/stream` (Server-Sent Events); a UI is a separate build.
- **Multi-tenancy** — one Neo4j, one Qdrant, one user's data at a time. Shard them if you scale.
- **Fine-tuned models** — the base open-source models (Qwen2.5-72B, Llama-3.3-70B) are already SOTA; fine-tuning is only useful if you have 100K+ domain-specific examples.
- **Agentic loop at the top level** — the 5-agent pipeline is deterministic, not recursive. If you wanted agents to *call each other dynamically* (e.g., a Scout that spawns sub-Scouts), that's a different pattern; see "How to add agents" below.

**The truth:** it's complete as a **single-use-case pipeline** (scholarship matching). If you want to bolt on new use cases (e.g., "also draft cover letters"), you'd add them as parallel pipelines that share the KB layer, not retrofit them into the same state machine.

---

## 2. Agent Topology (who does what, on which model)

```
┌─ Agent 1: Profiler         → Role: FAST   (12B)  ◄── extract structured profile from messy CV
├─ Agent 2: Scout            → Role: FAST   (12B)  ◄── plan queries + scrape + extract opportunities
├─ Agent 3: Matchmaker       → Role: HEAVY  (70B)  ◄── fuse signals + score + gate on rules
├─ Agent 4: Scribe           → Role: SCRIBE (32B)  ◄── write email + SOP, grounded
└─ Agent 5: Quality Gate     → Role: HEAVY  (70B)  ◄── fact-check claims, reject or approve
```

- **FAST** (12B) = extraction, parsing, JSON, tool-calling. Cheap & precise at structured work.
- **SCRIBE** (32B) = long-form writing (email/SOP). 32B has enough nuance for coherent prose without burning 70B compute.
- **HEAVY** (70B) = reasoning, calibration, verification. The expensive calls, but worth it for correctness.

**You don't have to use these exact models.** The router in [llm/router.py](../src/scholar/llm/router.py) maps `Role` to model name. So you could:
- Use all Llama-3.3-70B (less variation, simpler, slightly lower quality).
- Use all Groq-hosted models, or all open-source via vLLM.
- Swap in Claude, GPT-4, Gemini on the Hands side (requires an adapter to the non-OpenAI protocols, ~50 LOC).

---

## 3. Where to host the models (the "Brains")

You have **zero GPU** on your laptop, so here's the decision tree:

### A. **Free (MVP / testing)**
| Platform | Setup | Cost | Quality | Latency | Notes |
|----------|-------|------|---------|---------|-------|
| **Groq** | 1 min (get API key) | Free (500K tokens/day) | Excellent (70B) | <1 sec | Best for today; free tier is genuinely usable. Llama-3.3-70B is fast + smart. |
| **Ollama local** | Download ~40 GB models | Free (your CPU/electricity) | Medium (7B–13B max locally) | 5–30 sec/token | Fully offline, super slow on CPU. Good for testing only. |

**Recommendation for right now:** **Stay on Groq free tier.** It's real, it's fast, it doesn't require signing up for a credit card, and the 70B model is genuinely good. Run until you hit the rate limit; by then you'll know if this is worth paying for.

### B. **Paid (production / serious use)**

| Platform | Setup | Cost | Use case | Notes |
|----------|-------|------|----------|-------|
| **Together.ai** | 5 min + API key | $0.60–$2/M tokens | High volume, cost-conscious | Fast, all open models, good uptime. Pay-as-you-go. |
| **DeepInfra** | 5 min + API key | Similar to Together | Same as Together | Competing provider, often slightly cheaper. |
| **Fireworks** | 5 min + API key | $0.50/M tokens | Same as Together | Newer, aggressive on price. |
| **Your own Proxmox box** | 1–2 days setup + GPUs ($8K–$50K) | Electricity only | Max control, volume, compliance | Run vLLM on your rented bare metal. Blueprint's original design. |
| **RunPod / Vast.ai** | 30 min + rented GPU | $0.25–$2/hour/GPU | Flexible workloads | Spot instances are cheap; long-running isn't. Good for bursting. |

**Simple rule:** For 1–100 users, **use Groq free → Together.ai paid.** For 1000+ users or compliance needs, **rent a GPU box or use your own Proxmox.**

The beauty of your code: you don't change the pipeline. You only change `.env`:
```bash
# Today: Groq free
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_...

# Tomorrow: Together.ai ($5 spent)
LLM_BASE_URL=https://api.together.xyz/v1
LLM_API_KEY=together...

# Next week: RunPod vLLM ($0.50/hr spent)
LLM_BASE_URL=https://YOUR-RUNPOD-IP:8000/v1
LLM_API_KEY=not-needed
```

---

## 4. Do you need to train the models?

**Short answer: No.**

The models used are **pre-trained, open-source base models** (Qwen2.5-72B, Llama-3.3-70B, Nemo-12B). They're trained on 100B–2T tokens of internet text, so they already understand CVs, scholarships, email writing, etc.

**When you'd train:**
- **Fine-tune** (days/weeks, 10K–1M examples): you have 10K+ scholarship CVs + good email/SOP examples, and they follow a narrow domain (e.g., "AI PhDs at Dutch universities"). Fine-tuning would squeeze out 5–15% better match accuracy.
- **Full retrain** (months, GPUs, 100B+ tokens): never. Retraining base models is a $100M+ endeavor.

**What you *could* do instead** (no training, same effect):
- **Prompt optimization** — refine the system prompts in [agents/prompts.py](../src/scholar/agents/prompts.py) to your domain.
- **In-context examples** — embed 3–5 good CV→profile examples in the Profiler's system prompt to guide its output.
- **Retrieval augmentation** — seed your Neo4j with 100 known-good scholarships so the Scout has a corpus to evaluate against.

So: **start with zero training.** If accuracy isn't good enough after prompt tuning, *then* consider a fine-tune. But you likely won't need it.

---

## 5. CV / Document Ingestion + Embeddings Optimization

### What you have now (works but basic)
- **Ingest** ([ingest.py](../src/scholar/ingest.py)): PDF → raw text via `pypdf`.
- **Profiler agent**: raw text → structured `StudentProfile` JSON via FAST model.
- **Embeddings**: local CPU, fastembed (384-dim `bge-small-en-v1.5`).

### What could be better (incremental improvements, no new agents needed)

#### 1. **Better document parsing** (before the Profiler)
```python
# Today: pypdf (dumb, gets confused by multi-column layouts, tables)
# Better: 
#   - DocumentIntelligence (Azure, $$): OCR + layout-aware parsing
#   - Unstructured.io (free tier): layout-aware open-source
#   - LlamaIndex (free): treats each section's structure separately
```
If your users upload badly-formatted PDFs, invest 1 day in swapping `pypdf` for `Unstructured.io`. Biggest ROI on document quality.

#### 2. **Embeddings: larger model for better recall**
```python
# Today: bge-small (384-dim, ~90MB, runs on CPU in 50ms)
# Better recall: bge-large (1024-dim, ~400MB, runs on CPU in 200ms)
#   - Only useful if you have 1000+ opportunities indexed
#   - For now, size is fine; quality is held by the Matchmaker's reasoning

# If you move to a GPU, use bge-m3 (multilingual, state-of-the-art)
```

#### 3. **Profiler → Structured extraction (optional, but clean)**
Right now the Profiler outputs a `StudentProfile` JSON. The embedding step (when looking up opportunities) uses `profile.embedding_text()`, which is a hand-coded string. You could:
```python
# Automatically embed each field separately
# { "skills": [vec], "interests": [vec], "education": [vec] }
# Then use field-weighted search (weight "interests" more for matchmaking)
```
This is premature unless matching accuracy is a problem.

#### 4. **Multi-step extraction for complex CVs** (suggested improvement)
A single Profiler call might miss details in a 10-page CV. You could:
```python
# Profiler step 1: Extract summary (name, contact, one-liner)
# Profiler step 2 (parallel): Extract education details
# Profiler step 3 (parallel): Extract work experience
# Profiler step 4 (parallel): Extract projects + publications
# Aggregator: merge all fields into final StudentProfile
```
This is more robust but 3x the API calls. Only do it if CV parsing quality is poor.

### What I'd recommend
**Start with what you have.** The embedding is fine (the bottleneck is the Matchmaker's reasoning, not vector recall). If users complain about missing skills/interests:
1. **Improve the Profiler prompt** — show examples of what you want extracted.
2. **If still bad:** swap `pypdf` for `Unstructured.io` (+1 day).
3. **If you have 1000+ scholarships:** upgrade to `bge-large`.

---

## 6. How to improve the pipeline (ranked by impact)

### High-impact (do these)
1. **Seed the Neo4j with 50–100 real scholarships** you've manually vetted. Right now the Scout searches the web and gets noisy results. A corpus of known-good matches gives the Matchmaker something solid to calibrate against.
   - Impact: 80% better shortlist quality.
   - Effort: 2–4 hours of data entry (name, stipend, eligibility, skills, URL).

2. **Add a "feedback loop"** — when a user says "that match was garbage," store it in the graph and use it to re-weight future scores.
   - Impact: continuous improvement, gets better with every user.
   - Effort: ~200 LOC (add a `feedback()` endpoint, store in Neo4j, adjust Matchmaker weights).

3. **Improve the Scout's query planning** — right now it's generic (e.g., "machine learning funded PhD"). You could add domain knowledge:
   - "If research_interest contains 'drug discovery', also search 'pharmaceutical' and 'biotech'."
   - "If geographic_constraint is 'EU', add 'Marie Curie' and 'Horizon Europe'."
   - Impact: find 50% more relevant opportunities.
   - Effort: ~300 LOC in the Scout node.

4. **Add professor-fit scoring** — right now you match skills. You could also match the *style* of the professor's papers to the applicant's interests (e.g., "this prof publishes on drug screening using ML"; "the applicant is interested in drug discovery").
   - Effort: ~400 LOC (OpenAlex → extract research concepts → embed → compare).

### Medium-impact (nice to have)
5. **Cache opportunity embeddings** so you don't re-embed 1000 scholarships every run.
   - Effort: ~100 LOC (Redis or Postgres cache layer).

6. **Parallel Scout execution** — right now the Scout is serial (search → scrape → extract). Run search and OpenAlex in parallel, then merge.
   - Effort: already mostly parallel (asyncio); add `asyncio.gather()` in a few more places.

7. **Add a "draft critique agent"** between Scribe and Quality Gate that doesn't fact-check, but improves tone/clarity.
   - Effort: ~150 LOC + one more LLM call per opportunity.

### Low-impact (skip unless you hit them)
8. Finer-grained reflection loop (e.g., "revise only the hallucinated paragraph, keep the rest").
9. Caching LLM responses (same query → same answer).
10. A/B testing different prompts (e.g., two Scribes with different styles).

### What I'd actually build first
**Not more agents or models.** Instead: **get real data.** Add 50 scholarships to Neo4j, ask 3 students to run the pipeline, collect their feedback ("this was a real match!" / "garbage"), and use that to tune the weights. You'll learn more from one real user's feedback than from a dozen theoretical improvements.

---

## 7. How to actually add agents and models

### Adding a new agent (5 steps, ~1 hour)

**Scenario:** You want to add an "Interview Prep" agent that generates mock interview questions based on the applicant + the professor's research.

**Step 1: Define the input/output contracts** (Pydantic models)
```python
# src/scholar/schemas/interview.py
from pydantic import BaseModel

class MockQuestion(BaseModel):
    question: str
    context: str  # why we ask this (based on the prof's work)
    suggested_answer: str

class InterviewPrepBundle(BaseModel):
    opportunity_id: str
    questions: list[MockQuestion]
```

**Step 2: Add to the state** ([state.py](../src/scholar/state.py))
```python
class PipelineState(TypedDict, total=False):
    # ... existing fields ...
    interview_bundles: Annotated[list[InterviewPrepBundle], operator.add]
```

**Step 3: Write the agent** (pure async function)
```python
# src/scholar/agents/interview_prep.py
from ..llm import Role, get_llm
from ..schemas.interview import InterviewPrepBundle, MockQuestion
from ..state import PipelineState

async def interview_prep_node(state: PipelineState) -> dict:
    """Generate 5 mock interview questions for each synthesized bundle."""
    bundles = state.get("bundles", [])
    if not bundles:
        return {}
    
    interview_bundles = []
    for bundle in bundles:
        opp = next((o for o in state.get("opportunities", []) 
                    if o.id == bundle.opportunity_id), None)
        if not opp:
            continue
        
        prompt = f"""Generate 5 tough interview questions for a PhD candidate interviewing with 
{opp.professor.name or 'unknown professor'} on {opp.professor.research_summary or 'unknown research'}.
The candidate's interests: {state['profile'].research_interests}.
Make questions that test both domain knowledge and research vision."""
        
        result = await get_llm().structured(
            Role.HEAVY, 
            "You are an interview coach specializing in PhD admissions.",
            prompt,
            InterviewPrepBundle
        )
        interview_bundles.append(result)
    
    return {"interview_bundles": interview_bundles}
```

**Step 4: Wire into the graph** ([graph_app.py](../src/scholar/graph_app.py))
```python
from .agents.interview_prep import interview_prep_node

def build_graph():
    g = StateGraph(PipelineState)
    # ... existing nodes ...
    g.add_node("interview_prep", interview_prep_node)
    
    # Add after synthesis is done
    g.add_edge("commit", "interview_prep")
    g.add_edge("interview_prep", END)
    
    return g.compile()
```

**Step 5: Test it**
```python
# tests/test_interview_prep.py
@pytest.mark.asyncio
async def test_interview_prep_node():
    from scholar.agents.interview_prep import interview_prep_node
    state = {
        "profile": StudentProfile(...),
        "bundles": [SynthesisBundle(...)]
    }
    result = await interview_prep_node(state)
    assert "interview_bundles" in result
```

Done. That's a full agent. The state machine automatically runs it, the structured output validates the response, and the reflection pattern (if you wanted it) is already there.

### Swapping models (1 minute)

Just edit [llm/router.py](../src/scholar/llm/router.py) and `.env`:

```python
# llm/router.py — change the Role enum
class Role(str, Enum):
    HEAVY = "heavy"
    FAST = "fast"
    SCRIBE = "scribe"
    MATH = "math"      # ← NEW

_TEMPERATURE = {
    Role.MATH: 0.0,    # ← math needs determinism
}

def route(role: Role) -> tuple[str, float]:
    model = {
        Role.MATH: s.model_math,  # ← read from config
    }[role]
    return model, _TEMPERATURE.get(role, 0.1)
```

```python
# config.py
class Settings(BaseSettings):
    model_math: str = Field("specialized-math-model", alias="MODEL_MATH")
```

```bash
# .env
MODEL_MATH=Qwen2.5-Math-7B-Instruct
```

Use it in an agent:
```python
await get_llm().complete(Role.MATH, system, user)
```

That's it. You've added a specialized math model for a hypothetical agent that needs symbolic reasoning.

---

## 8. Adding a new data source (tools layer)

**Scenario:** You want the Scout to also check company job boards (LinkedIn, Levels.fyi) for industry roles alongside scholarships.

```python
# src/scholar/tools/job_search.py
async def search_linkedin(keyword: str, salary_min: int = 0) -> list[dict]:
    """Search LinkedIn (or LinkedIn API, or a scraper).
    Return [{"title", "company", "url", "salary_range"}]
    """
    # Option A: LinkedIn official API (requires approval)
    # Option B: Scrape Indeed / levels.fyi (no API, just HTML)
    # Option C: Use a 3rd-party job API (API Layer, RapidAPI, etc.)
    pass

# Register it
# src/scholar/tools/__init__.py
from .job_search import search_linkedin
TOOL_REGISTRY["search_linkedin"] = search_linkedin
```

Use it in the Scout:
```python
# src/scholar/agents/scout.py
jobs = await search_linkedin(primary[0], salary_min=80000)
context += f"\nLINKEDIN JOBS:\n{jobs}"
```

The new results become part of the Scout's extraction corpus, so the same extraction+indexing pipeline applies. One agent, multiple tool sources.

---

## 9. Real-world deployment checklist

When you go from "running on my laptop" to "real users":

- [ ] **Database backups** — set up daily Neo4j + Qdrant snapshots.
- [ ] **Rate limiting** — add to the FastAPI app so one user can't spam 10K requests.
- [ ] **Auth** — users should only see their own results. Add `FastAPI-Users` or similar.
- [ ] **Frontend** — a simple Next.js/React UI that uploads CV, streams results via Server-Sent Events.
- [ ] **Monitoring** — track agent latencies, model errors, hallucination rates. Add structured logging to every agent output.
- [ ] **CI/CD** — run tests on every commit; auto-deploy to a staging env; require code review.
- [ ] **Cost tracking** — log every LLM API call with cost; budget-alert if monthly spend is high.
- [ ] **Data privacy** — EU? GDPR compliance (data retention, user deletion, audit logs).

Most of these are 1–2 days of work each. Start with backups and rate limiting; add auth and a frontend before releasing to users.

---

## Summary

| Question | Answer |
|----------|--------|
| **Complete agentic solution?** | Yes for one use case (scholarship matching). Deterministic, looping, fact-checked. |
| **Which models?** | Qwen2.5-72B (heavy), Llama-3.3-70B (alternative), Nemo-12B (fast), Qwen2.5-32B (scribe). All open, no training. |
| **Where to host?** | Groq free (now), Together.ai ($$/month, later), RunPod (burst), your own Proxmox (scale). Swap via `.env`. |
| **Train the models?** | No. Fine-tune only if you have 10K+ domain examples. |
| **Optimize CV embeddings?** | Current setup is good. Improve Profiler prompt, then add Unstructured.io parser if quality is still bad. |
| **How to improve?** | Seed real data (1st priority), add feedback loop (2nd), tune Scout queries (3rd). Not more agents. |
| **Add agents?** | 5 steps: define schema → add to state → write agent function → wire into graph → test. ~1 hour per agent. |
| **Swap models?** | 1 minute: edit `router.py`, add to config, set `.env`. The client handles the rest. |

---

## Next steps (your choices)

1. **Get Groq working** (already provided the steps).
2. **Seed 20–50 real scholarships** into Neo4j (a spreadsheet + a quick import script).
3. **Run 3 test users** through the pipeline, collect feedback, measure match quality.
4. **If accuracy is weak:** improve Profiler prompt, then add Unstructured.io parser.
5. **If you like what you see:** add the feedback loop agent and open it to 10 real users.
6. **Scale:** move from Groq to Together.ai, add a React frontend, set up auth.

That's the path. Good luck!
