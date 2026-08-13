# Portal — vanilla demo app (Cloudflare Workers + D1)

Live at **https://nusiss-bfa.co01y4p.workers.dev**

A vanilla HTML/JS deployment of the M1 non-agentic slice ([plan](../../docs/plan/m1-non-agentic-baseline.md)): report form → D1 → manager queue → public tracking. No AI in this path by design (save-before-AI). D1 stands in for the plan's Postgres, since Workers can't host Postgres/FastAPI — same table shape, same API contract.

## Layout

```
public/          static pages (index/report, track, manager) — vanilla HTML/CSS/JS
src/worker.js    API: POST /api/v1/incidents, GET .../track/{code},
                 GET /api/v1/incidents + PATCH .../{id}/status (manager)
schema.sql       D1 schema — keep it idempotent (CREATE TABLE IF NOT EXISTS ...)
wrangler.jsonc   Worker config, pinned to the shared Cloudflare account
```

Manager passcode for the demo: `bfa-manager-2026` (env var in `wrangler.jsonc`; the real build replaces this with JWT + Argon2id per M1).

## How to work on it (collaborators)

You do **not** need Cloudflare access to contribute:

1. Branch, edit files under `apps/web-vanilla/`, open a PR → CI runs a `wrangler deploy --dry-run` check.
2. Merge to `master` → GitHub Actions ([deploy-portal.yml](../../.github/workflows/deploy-portal.yml)) applies `schema.sql` and deploys automatically. The live URL updates in ~1 minute.

Schema changes: only add idempotent statements to `schema.sql` (`IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN` guarded appropriately) — it re-runs on every deploy.

## Local development

```bash
cd apps/web-vanilla
npx wrangler dev          # local Worker + local D1 at http://localhost:8787
npx wrangler d1 execute nusiss-bfa-db --local --file schema.sql -y   # once, to init local DB
```

Manual deploy (needs Cloudflare access): `npx wrangler deploy`.
