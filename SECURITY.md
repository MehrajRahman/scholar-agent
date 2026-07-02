# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Email the maintainer
at **rahmanmehraj627@gmail.com** with details and steps to reproduce. You'll get
an acknowledgement within a few days.

## Secrets & configuration

- **Never commit real secrets.** `.env` and `providers.json` are git-ignored on
  purpose. Copy the templates instead:
  ```bash
  cp .env.example .env
  cp providers.json.example providers.json   # optional multi-provider pool
  ```
- API keys are referenced **by env-var name** in `providers.json`
  (`"api_key_env": "GROQ_API_KEY"`), and resolved from the environment — keys
  never live in that file.
- If a key has ever appeared in a commit, a shared file, or a chat, treat it as
  **compromised and rotate it** (Groq: <https://console.groq.com/keys>, Tavily:
  <https://app.tavily.com>). Rotating is cheaper than a leak.
- Before your first push, scan history for accidental secrets, e.g.
  [`gitleaks detect`](https://github.com/gitleaks/gitleaks) or
  `git grep -nE 'gsk_|tvly-|sk-'`.

## Design safeguards

- **Grounded, human-in-the-loop output.** Generated emails and Statements of
  Purpose are drafts for **your review** — the system never auto-sends anything.
  The Quality Gate fact-checks claims against your CV and the professor's real
  public record to reduce hallucination.
- **Air-gapped model tier.** In the production Docker topology, the model + DB
  containers run on an `internal: true` network with no internet route; only the
  orchestrator bridges to the outside. See `docker-compose.yml`.
- **No credentials in logs.** Structured logs record events and counts, not keys.

## Scope & data

- This is a personal research/portfolio tool. When you upload a CV, it is
  processed locally by your own stack (your Ollama/DB containers or your chosen
  API provider) — review each provider's data policy before sending real
  personal data to a hosted LLM.

## Supported versions

The `main` branch is the only supported version.
