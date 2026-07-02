# Ops layer — n8n (free, self-hosted)

n8n is the **ops/automation layer** (not the reasoning core): scheduled freshness
sweeps, deep-research refreshes, and "new match / deadline soon" alerts.

## Run it (free Community edition)
```bash
docker run -d --name n8n -p 5678:5678 \
  -v n8n_data:/home/node/.n8n \
  --network cse412_hands \           # same docker network as the orchestrator
  n8nio/n8n
# open http://localhost:5678  -> Import workflow -> nightly_refresh.json
```

## What the sample workflow does
`nightly_refresh.json`: every night at 03:00 it calls the orchestrator's
`POST /maintenance/sweep` (expire past-deadline opps, mark stale ones) and emails
the summary.

## Extending it (the useful automations)
- **Deep-research refresh:** add an HTTP node → `POST /pipeline/run` with
  `{"documents": ["<stored CV>"], "mode": "deep"}` to re-hunt and write back fresh
  opportunities before the sweep.
- **Deadline alerts:** query opportunities with a deadline within 7 days and send a
  Telegram/email reminder.
- **Approve-and-send:** when you approve a drafted cold email, an n8n "Gmail: Create
  Draft" node puts it in your outbox for a final human click.

The orchestrator exposes the endpoints; n8n provides the triggers, scheduling and
365-integration glue — no orchestration code needed for any of this.
