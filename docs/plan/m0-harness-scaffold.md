# M0 — Minimal harness scaffold

[← back to overview](00-overview.md)

## Objective

Stand up the thinnest possible working skeleton: separate frontend/backend folders, a database and cache, health checks, and a CI quality gate. **No business logic, no agents yet** — this milestone only proves the plumbing works.

## Scope

Build:
- `apps/api` — FastAPI app with `/api/v1/health/live` and `/api/v1/health/ready` (readiness checks Postgres + Valkey connectivity).
- `apps/web` — Next.js app with three placeholder pages/routes: report form, assistant chat, and a manager list — all static/non-functional stubs at this stage.
- `infra/compose/compose.yml` — `postgres` (pgvector image) and `valkey` services, plus `api` and `web` services with Dockerfiles.
- Lint/format/type tooling: Ruff + mypy (Python), ESLint + TypeScript + Prettier (Node).
- `.github/workflows/ci.yml` — format check, lint, unit tests (empty test suites are fine for now, just wire the job).

Explicitly **not** built yet: auth, database schema, agents, RAG, monitoring stack, production config.

## Folders touched

```
apps/api/app/main.py
apps/api/app/api/v1/routers/health.py
apps/api/app/core/config.py
apps/api/Dockerfile
apps/api/pyproject.toml
apps/web/src/app/...
apps/web/Dockerfile
apps/web/package.json
infra/compose/compose.yml
.github/workflows/ci.yml
.env.example
```

## Deployment artifact

`infra/compose/compose.yml` with services `postgres`, `valkey`, `api`, `web`. This is the **only** deployment mechanism for the whole project (see [00-overview.md](00-overview.md) matrix) — the same file gets a production overlay at M7.

## Setup & run

```bash
# Backend
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn[standard] pydantic-settings sqlalchemy alembic
uvicorn app.main:app --reload --port 8000

# Frontend
cd apps/web
npx create-next-app@latest . --typescript --tailwind --app --eslint
npm run dev

# Infra
cp .env.example .env
docker compose -f infra/compose/compose.yml up -d postgres valkey
```

## Manual tasks (things only you can do)

- [ ] Install Docker Desktop (macOS) or Docker Engine + Compose plugin.
- [ ] Install Node.js LTS (≥20) and Python 3.13 locally, for running lint/tests outside containers.
- [ ] Confirm this repo's GitHub remote is set up the way you want (already has commits `f85cf24`, `62d6013` — confirm you want to keep building on this history).
- [ ] Decide package managers if you have a preference (npm vs pnpm; pip vs uv/poetry) — default plan uses npm and plain pip/venv unless you say otherwise.

## Exit criteria

- `docker compose up -d postgres valkey` starts cleanly.
- `GET /api/v1/health/live` and `/api/v1/health/ready` both return 200 locally.
- `npm run dev` renders the three placeholder pages.
- CI workflow runs and passes on a push (even with minimal/empty test suites).
