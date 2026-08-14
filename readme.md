# Facilities AI Assistant (nusiss-bfa)

NUS-ISS capstone project: a generic building facilities management AI assistant. Occupants report issues (leaks, electrical faults, broken lifts, etc.) or ask facility questions; a bounded multi-agent workflow will triage, classify, prioritize, and route reports, and answer questions grounded in approved facility documents. A facility manager reviews, overrides, and operates the system.

Full design and milestone breakdown: [docs/plan/00-overview.md](docs/plan/00-overview.md).

## Current state

Only **M1 (non-agentic baseline)** is built so far, as a deliberately minimal vanilla HTML/JS + Cloudflare Workers + D1 app at [apps/web-vanilla/](apps/web-vanilla/) — not yet the full Next.js + FastAPI + Postgres stack the plan describes for later milestones. No AI/agent workflow exists yet (by design — "save-before-AI": the system must work end-to-end with the AI completely absent before any agent logic is added on top).

What works today:
- **Google Sign-In gates the whole site, restricted to an allow-list.** Every page and API route requires a signed-in Google account, and sign-in itself is rejected outright for any email not on the `MANAGER_EMAILS` allow-list — there's no general public access yet, only the team.
- **Report an issue** — creates an incident, returns an opaque tracking code.
- **Track a report** — status lookup by tracking code, no ID enumeration.
- **Manager queue** — list all incidents, update status (`RECEIVED → IN_PROGRESS → RESOLVED → CLOSED`).

Live at **https://nusiss-bfa.co01y4p.workers.dev**.

Not yet built: the multi-agent triage/routing workflow, RAG-grounded Q&A, agent security controls, evaluation suite, observability, and the full Next.js/FastAPI stack — see the milestone table in the plan overview for what's still ahead (M2–M8).

## Repository structure

```
apps/web-vanilla/   the only app built so far — Cloudflare Workers + D1 (see below)
docs/plan/           full capstone plan, one file per milestone
.github/workflows/    CI: PR dry-run check, auto-deploy on merge to master
```

## Running the web app locally

```bash
cd apps/web-vanilla
npm install
```

Create a local secrets file — `apps/web-vanilla/.dev.vars` (gitignored, never committed). It needs two values (`GOOGLE_CLIENT_ID` already comes from the committed `wrangler.jsonc`, no need to set it here):

```dotenv
SESSION_SECRET=<any random string, e.g. output of `openssl rand -hex 32`>
MANAGER_EMAILS=<comma-separated list of emails allowed to sign in at all, e.g. your own>
```

Then initialize the local database (once) and start the dev server:

```bash
npx wrangler d1 execute nusiss-bfa-db --local --file schema.sql -y
npx wrangler dev
```

The app runs at **http://localhost:8787**. To actually sign in locally, `http://localhost:8787` needs to be registered as an authorized JavaScript origin on the Google OAuth client, and your Google account needs to be added as a test user on the consent screen (ask whoever manages the Google Cloud Console project).

Full details, including the auto-deploy pipeline and how to contribute without needing Cloudflare access: [apps/web-vanilla/README.md](apps/web-vanilla/README.md).
