# Portal — vanilla demo app (Cloudflare Workers + D1)

Live at **https://nusiss-bfa.co01y4p.workers.dev**

A vanilla HTML/JS deployment of the M1 non-agentic slice ([plan](../../docs/plan/m1-non-agentic-baseline.md)): report form → D1 → manager queue → public tracking. No AI in this path by design (save-before-AI). D1 stands in for the plan's Postgres, since Workers can't host Postgres/FastAPI — same table shape, same API contract.

## Layout

```
public/          static pages (login, report, track, manager) — vanilla HTML/CSS/JS
src/worker.js    site-wide Google sign-in gate + API:
                 POST /api/v1/auth/google, GET .../me, POST .../logout,
                 POST /api/v1/incidents, GET .../track/{code},
                 GET /api/v1/incidents + PATCH .../{id}/status (manager role only)
schema.sql       D1 schema — keep it idempotent (CREATE TABLE IF NOT EXISTS ...)
wrangler.jsonc   Worker config, pinned to the shared Cloudflare account
package.json     one dependency: `jose`, used to verify/sign JWTs
```

**Auth:** every page and API route requires a signed-in Google account (Sign In With Google, ID-token flow — see `/login.html`). Sign-in itself is restricted to the `MANAGER_EMAILS` allow-list — any other Google account is rejected at sign-in, before a session is ever created. `GOOGLE_CLIENT_ID` is a public identifier, committed directly in `wrangler.jsonc`. `SESSION_SECRET` and `MANAGER_EMAILS` are real Cloudflare secrets (`wrangler secret put <NAME>`) — not committed anywhere in this repo.

## How to work on it (collaborators)

You do **not** need Cloudflare access to contribute:

1. Branch, edit files under `apps/web-vanilla/`, open a PR → CI runs a `wrangler deploy --dry-run` check.
2. Merge to `master` → GitHub Actions ([deploy-portal.yml](../../.github/workflows/deploy-portal.yml)) applies `schema.sql` and deploys automatically. The live URL updates in ~1 minute.

Schema changes: only add idempotent statements to `schema.sql` (`IF NOT EXISTS`, `ALTER TABLE ... ADD COLUMN` guarded appropriately) — it re-runs on every deploy.

## Local development

```bash
cd apps/web-vanilla
npm install
```

Create `apps/web-vanilla/.dev.vars` (gitignored, never committed) with just the two real secrets — `GOOGLE_CLIENT_ID` already comes from the committed `wrangler.jsonc`, no need to set it here:

```dotenv
SESSION_SECRET=<any random string, e.g. `openssl rand -hex 32`>
MANAGER_EMAILS=<comma-separated emails that should get manager access>
```

Then:

```bash
npx wrangler d1 execute nusiss-bfa-db --local --file schema.sql -y   # once, to init local DB
npx wrangler dev          # local Worker + local D1 at http://localhost:8787
```

Signing in locally requires `http://localhost:8787` to be registered as an authorized JavaScript origin on the Google OAuth client, and your Google account to be added as a test user on the consent screen (while it's in Testing status).

Manual deploy (needs Cloudflare access): `npx wrangler deploy`.
