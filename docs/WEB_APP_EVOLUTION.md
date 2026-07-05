# Scholar-Agent → Application Command Center: Systems Analysis

**Author:** (systems analysis)
**Status:** Proposal / for review
**Purpose:** Define the evolution of scholar-agent from a single-page *discovery
tool* into a multi-page *application-management platform* that a scholarship /
PhD aspirant uses to run their entire journey — from finding opportunities to
tracking applications, emailing professors, and hitting deadlines.

---

## 1. Executive summary

Today, scholar-agent is a **stateless one-shot tool**: upload a CV → it finds
scholarships and drafts an email + SOP → the results vanish when you close the
tab. Nothing is saved, there are no accounts, and there is no notion of "my
applications", "professors I've contacted", or "deadlines coming up".

The target is a **personal application command center**: a persistent,
account-based web app where the AI discovery engine is one feature among several,
and the core value is *tracking and driving the whole application process over
months*. Think "CRM + Kanban + deadline calendar + AI assistant" for the
scholarship/PhD hunt.

This is a shift from **tool** to **product**. It requires three things the current
system lacks: **user accounts**, **persistent per-user data**, and a
**multi-view UI**. The good news: the domain model (Opportunity, Professor,
University, Funding) and the AI engine already exist and are reusable — we are
adding a *system of record* around them, not rebuilding the core.

---

## 2. Current state assessment

| Capability | Status today |
|---|---|
| CV ingestion + profiling | ✅ Exists (`/ingest`, Profiler agent) |
| Opportunity discovery (deep web research) | ✅ Exists (Scout/Deep Scout + Critic) |
| Matching & scoring | ✅ Exists (Matchmaker, GraphRAG) |
| Draft email + SOP + kit | ✅ Exists (Scribe, `/draft`) |
| Data model for Professor / University / Funding | ✅ In Neo4j schema (not surfaced in UI) |
| **User accounts / auth** | ❌ None |
| **Persistence of user's saved items / actions** | ❌ None (results are ephemeral) |
| **Application tracking (status, checklist)** | ❌ None |
| **Professor outreach tracking (CRM)** | ❌ None |
| **Deadline calendar / reminders** | ❌ None (deadlines exist per-opp, not aggregated) |
| **Document/version management (SOP/CV/LOR)** | ❌ None |
| **Dashboard / progress overview** | ❌ None |
| **Multi-page navigation** | ❌ Single view (intake → running → results) |

**Conclusion:** the *intelligence* is built; the *system of record* and the
*workflow* around it are missing.

---

## 3. Target users & jobs-to-be-done

### Primary persona — "The Aspirant"
A final-year/graduate student applying, over 3–12 months, to a mix of:
- **Scholarships** (Erasmus Mundus, DAAD, Chevening, Fulbright, country schemes)
- **PhD / Master's positions** (university portals, lab openings)
- **Direct professor outreach** (cold emails, follow-ups, interviews)

They juggle **many parallel applications**, each with its own deadline,
document set, and status — today typically in a messy spreadsheet.

### Jobs-to-be-done (what they actually need)
1. *"Keep my profile in one place"* — CV, interests, target countries/degrees, test scores.
2. *"Find opportunities and save the good ones"* — not re-run search every time.
3. *"See everything I'm working on at a glance"* — a dashboard/pipeline.
4. *"Track each application's status and requirements"* — checklist, deadline, documents.
5. *"Manage professors I'm emailing"* — who, when, replied?, follow-up due.
6. *"Never miss a deadline"* — a unified calendar with reminders.
7. *"Draft and reuse my materials"* — versioned SOPs/emails per target.
8. *"Know what to do next"* — prioritized tasks.

Items 3–8 are **entirely new**. This is the heart of the product.

---

## 4. Gap analysis → feature modules

| Module | Description | Priority |
|---|---|---|
| **Accounts & Profile** | Sign up / log in; editable, persistent StudentProfile; upload CV once | P0 (foundation) |
| **Opportunity Pipeline** | Save discovered opportunities; Kanban board (Interested → Applying → Applied → Result) | P0 |
| **Application Tracker** | Per-application: status, deadline, requirement checklist, notes, attached docs | P1 |
| **Professor CRM** | Track professors: research fit, email status, replies, follow-up reminders | P1 |
| **Deadline Calendar** | Aggregate all deadlines + tasks; reminders (email/in-app) | P1 |
| **Document Manager** | Versioned SOPs, CVs, motivation letters, LORs; link to applications | P2 |
| **Dashboard** | At-a-glance: active apps, deadlines this week, professors awaiting reply, tasks | P1 |
| **AI Assistant (existing)** | Discovery + drafting, now *attached* to saved opportunities/professors | P0 (reuse) |
| **Notifications** | Deadline alerts, "Prof X hasn't replied in 10 days" | P2 |

---

## 5. Proposed data model

New persistent entities (relational — see §6 for why). Existing engine entities
(Opportunity, Professor) are *referenced*, not duplicated.

```
User (id, email, password_hash, created_at)
 └── Profile (1:1)  — the editable StudentProfile + CV file
 └── Application (1:N)
 └── ProfessorContact (1:N)
 └── Document (1:N)
 └── Task (1:N)
 └── SearchRun (1:N)   — history of deep searches

Application
  id, user_id, opportunity_ref, title, institution, country,
  kind (scholarship | phd | masters),
  status (see §7 pipeline), deadline, funding_notes,
  checklist [ChecklistItem], notes, created_at, updated_at

ProfessorContact  (the CRM record — distinct from the engine's Professor node)
  id, user_id, name, university, department, email, research_fit_notes,
  linked_opportunity_ref?, status (see §7),
  last_contacted_at, next_followup_at, thread [OutreachMessage]

OutreachMessage
  id, direction (sent | received), subject, body, sent_at,
  generated_by_ai (bool), approved (bool)

Document
  id, user_id, type (cv | sop | motivation_letter | lor | other),
  title, version, body/file_ref, linked_application_id?, created_at

Task
  id, user_id, title, due_date, done,
  linked_application_id? | linked_professor_id?

ChecklistItem (embedded in Application)
  label (e.g. "SOP", "3x LOR", "IELTS 7.0", "Transcript", "Funding proof"),
  done, due_date?, document_id?
```

**Key relationships:** an `Application` may link to a discovered `Opportunity`
(from the engine) *or* be created manually (e.g. an Erasmus scheme the user
already knows). A `ProfessorContact` may link to an `Application` (emailing a
prof about a specific PhD) or stand alone (speculative outreach).

---

## 6. Proposed architecture

### 6.1 Component view (target)

```
┌───────────────────────── Frontend (multi-page SPA) ─────────────────────────┐
│  Dashboard · Discover · Pipeline · Applications · Professors · Calendar · Docs │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                     │ REST/JSON + SSE (auth: JWT/session cookie)
┌───────────────────────────────────┴──────────────────────────────────────────┐
│  FastAPI backend                                                              │
│   • Auth & users        • Application/Professor/Task/Doc CRUD (new)           │
│   • AI pipeline (existing: discover / draft, now writes to user records)      │
│   • Background jobs (long deep-searches) + notifications                      │
└───────┬───────────────────────────┬───────────────────────────┬──────────────┘
        │                           │                           │
   Postgres (NEW)              Neo4j + Qdrant              Object storage (NEW)
  system of record:          discovery/matching           CV & document files
  users, applications,       engine (unchanged)           (local dir or S3/MinIO)
  professors, tasks, docs
```

### 6.2 Why add Postgres (and keep Neo4j/Qdrant)?

- **Postgres** is the right fit for the *system of record*: users, applications,
  statuses, tasks, documents — highly relational, transactional, needs
  per-user isolation and ACID updates. This is a poor fit for a graph or vector
  DB.
- **Neo4j + Qdrant** stay exactly as they are — the discovery/matching *engine*.
  They answer "what opportunities exist and how well do they fit?"; Postgres
  answers "what is *this user* doing about them?"

### 6.3 Frontend options (trade-offs)

| Option | Pros | Cons | Fit |
|---|---|---|---|
| **Keep Alpine.js, add a client router + views** | No new toolchain; incremental; matches current zero-build ethos | Gets unwieldy for a large multi-page app; limited component reuse | Good for MVP / staying solo-friendly |
| **SvelteKit** | Small, fast, great DX, SSR + routing built in | New toolchain to learn/host | Strong middle ground |
| **React + Vite (or Next.js)** | Ecosystem, hireable skill, component libraries | Heaviest; more boilerplate | Best "portfolio/hireability" signal |

**Recommendation:** start MVP by **extending the current Alpine app into a few
routed views** (fastest path to a working product), and migrate to **SvelteKit
or React** at Phase 3 if/when complexity justifies it. Don't rewrite the
frontend before the data model and API exist.

### 6.4 Background jobs

Deep search takes minutes. Today it blocks an SSE request. For a real app, move
long runs to a **task queue** (`arq`/RQ/Celery) so the user can navigate away and
get notified when results land. MVP can keep SSE; Phase 2 adds the queue.

---

## 7. Workflow state machines

### 7.1 Application pipeline (Kanban columns)
```
Discovered → Interested → Preparing → Applied → Interview → Decision
                                                              ├─ Offer
                                                              ├─ Rejected
                                                              └─ Waitlisted
```

### 7.2 Professor outreach pipeline
```
To Contact → Emailed → Replied → In Conversation → Meeting → Outcome
                   └──(no reply, N days)──► Follow-up Due
```
The "Follow-up Due" transition is what powers the *"Prof X hasn't replied in 10
days"* reminder — a background job scans `next_followup_at`.

---

## 8. Non-functional requirements

- **Authentication & isolation (critical):** every query is scoped to the
  logged-in `user_id`; no user can read another's data. This is the #1 new
  security surface — it did not exist before.
- **Privacy / data protection:** CVs and application data are sensitive personal
  data. If serving EU users (Erasmus!), GDPR applies — encryption at rest,
  export/delete-my-data, clear retention. Documents stored outside the repo.
- **Secrets:** unchanged discipline (`.env`, rotate keys) + now password hashing
  (argon2/bcrypt) and signed session tokens.
- **Reliability:** long jobs must survive a page reload (background queue + job
  status), and DB writes must be transactional.
- **Cost:** stays ~$0 self-hosted (Postgres + Neo4j + Qdrant in Docker, local
  file storage). Multi-tenant SaaS would add hosting/DB/storage cost.

---

## 9. Phased roadmap

Each phase is independently useful and shippable.

**Phase 0 — Foundation (accounts + persistence)** ⟶ *turns the demo into an app*
- Add Postgres + a migration tool (Alembic).
- User signup/login (email + password, hashed; JWT or session cookie).
- Persistent, editable Profile; store the uploaded CV.
- "Save opportunity" from search results → an `Application` in status *Interested*.

**Phase 1 — Track the work** ⟶ *the core value*
- Opportunity Pipeline (Kanban board) + Application detail (status, deadline,
  checklist, notes).
- Dashboard (active apps, upcoming deadlines, tasks).
- Deadline Calendar (aggregated) with in-app reminders.

**Phase 2 — Professors & documents**
- Professor CRM: add/track professors, outreach status, drafted emails saved to
  the thread, follow-up reminders. (Reuse the existing `/draft` engine, but
  persist the output against the professor.)
- Document Manager: versioned SOPs/CVs/letters linked to applications.

**Phase 3 — Automation & polish**
- Background job queue for deep searches + email notifications (deadlines,
  follow-ups).
- Optional frontend migration to SvelteKit/React.
- Multi-tenant hardening (if going SaaS).

---

## 10. Key decisions to make (before building)

1. **Deployment model:** *single-user self-hosted* (simplest — the user runs it
   for themselves) **vs** *multi-tenant SaaS* (accounts for many users, needed if
   monetizing). This changes auth, privacy scope, and scaling. **Biggest fork.**
2. **Frontend path:** extend Alpine (fast) vs adopt SvelteKit/React (scalable,
   more portfolio value).
3. **Auth mechanism:** simple email+password vs OAuth ("Sign in with Google").
4. **Scope of MVP:** how much of Phase 1 ships first.

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Scope explosion (this is a big build) | Strict phasing; Phase 0+1 is a usable product on its own |
| Auth/data-isolation bugs leak user data | Enforce `user_id` scoping in a single data-access layer; tests for cross-user access |
| Frontend rewrite stalls momentum | Keep Alpine for MVP; migrate only when justified |
| AI engine changes break the app | Keep the engine behind a stable internal API; app depends on contracts, not internals |

---

## 12. Recommendation

Build **Phase 0 + Phase 1** first as a **single-user, self-hosted** app,
extending the current Alpine UI into routed views and adding Postgres as the
system of record. That delivers the thing the user actually asked for — *"track
all my progress in one place"* — with the least risk, while keeping the door
open to SaaS/monetization later. Professors CRM (Phase 2) follows once the
tracking spine exists.

---

## 13. Decisions (locked) & Phase 0 build plan

**Decisions taken:**
- **Deployment:** single-user self-hosted first, but the data model carries a
  `user_id` on every record from day one, so multi-tenant SaaS is a
  configuration/hardening step later — not a rewrite.
- **Frontend:** migrate to **SvelteKit/React** (a real SPA). The existing Alpine
  page is kept working during the transition; the new app is built alongside it
  under `frontend/` and calls the same backend API.
- **Start here:** Phase 0 — accounts + persistence.

**Phase 0 is delivered in small, non-breaking increments:**

| # | Increment | Deliverable |
|---|---|---|
| **0.1** | **DB foundation** | Postgres (Docker) + SQLAlchemy models (`User`, `Profile`, `SavedApplication`) + Alembic migrations + `DATABASE_URL` config. Every record carries `user_id`. Ships behind a `[web]` extra so the pipeline-only tool is unaffected. |
| **0.2** | **Auth** | `POST /auth/signup` + `/auth/login`; argon2 password hashing; JWT; a `current_user` dependency that scopes all app data. |
| **0.3** | **Persistence API** | CRUD for the user's profile + saved applications (`/me/profile`, `/me/applications`), all scoped to `user_id`; "save a discovered opportunity" → an Application in status *Interested*. |
| **0.4** | **SvelteKit scaffold** | New `frontend/` app: signup/login pages + a dashboard shell that authenticates against the API. |
| **0.5** | **Connect discovery → save** | The existing discovery results gain a "Save" action that persists to the user's pipeline. |

Increment 0.1 is additive and does not touch any existing endpoint — the current
one-shot tool keeps working throughout.

---

## 14. Course corrections (product + architecture)

### 14.1 Frontend: reverse the SvelteKit decision → zero-build, FastAPI-served
The earlier choice was SvelteKit/React. Re-evaluated against the stated goals
(*"minimal, more engineered, less resource"*, single-user self-hosted): a SPA
framework adds a **Node toolchain, a build step, a second dev server, and CORS**
— all overhead a personal one-stop tool shouldn't carry.

The *finer* pattern for this context is a **zero-build multi-view app** (Alpine +
Tailwind via CDN) served as static files by the **same FastAPI** process:
- one process, one deploy, no build, no CORS, no Node in production;
- same-origin `fetch` to the `/auth` and `/me` APIs;
- reuses the existing UI's aesthetic and idioms.

It is still a real multi-page app (client-side routed views: Dashboard,
Applications, Profile, Discover). If it ever outgrows this, migrating to SvelteKit
is a clean, later step — but not before it's justified. **Phase 0.4 builds this.**

### 14.2 Data retention: keep it fresh, not fat
Insight from use: a scholarship platform should **not hoard past-years'
opportunities** — expired calls are noise and waste storage. Instead:
- **Prune/expire aggressively.** The `expire_sweep` already marks past-deadline
  opportunities `expired`; retention should *archive or delete* them, keeping
  Neo4j/Qdrant lean (directly serves "less resource").
- **Keep a small, curated "success gallery" instead** — anonymised/consented
  examples of past *successful* candidates + their winning documents (SOP,
  motivation letters). High signal for an aspirant, tiny storage. This is a
  future content module (`SuccessStory`), not opportunity data.

### 14.3 Daily freshness job (scheduled surfing)
Goal: once a day, refresh the knowledge base so it stays current. The mechanism
already exists — `deep_scout` write-back (versioned, dedup) + `/maintenance/sweep`
(`expire_sweep`). What's missing is a **scheduler**. Minimal design:
- A single daily job (system `cron` hitting `/maintenance/sweep`, or a small
  in-process scheduler) that (1) expires stale/past-deadline opps and (2) runs a
  *bounded* deep-research pass over a rotating set of the user's active interests
  to pull in new opportunities and update changed ones (content-hash tells a
  re-discovery from a real change).
- Kept **off the request path** and **bounded** (respects the free-tier call
  budget). This lands in the automation phase (Phase 3), not now — but the data
  model and sweep are already built for it.
