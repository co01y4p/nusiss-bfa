# M1 — Non-agentic baseline slice

[← back to overview](00-overview.md)

## Objective

Prove the **save-before-AI principle**: a report must be persisted and manageable even if the LLM is completely absent. Build the full vertical slice with zero AI involvement — public report → API → Postgres → manager list → public tracking — plus just enough auth to gate the manager view.

## Why this milestone exists

Later, when agents fail, time out, or are disabled, the system must still work exactly like this milestone. Building it AI-free first makes that fallback path real and tested, not theoretical.

## Scope

Build:
- Minimal auth: JWT access token + Argon2id password hashing, two roles only (`PUBLIC` implicit, `MANAGER`). Skip `ADMIN`/refresh-token rotation/full RBAC matrix for now — add if needed later.
- `incidents` table + Alembic migration: id (UUID), reference_code (opaque, unique), description, location, status, timestamps.
- `POST /api/v1/incidents` (public) — creates a `RECEIVED` incident, returns `reference_code`.
- `GET /api/v1/incidents/track/{reference_code}` (public) — status lookup by opaque code, no sequential IDs exposed.
- `GET /api/v1/incidents` + `PATCH /api/v1/incidents/{id}/status` (manager-only).
- `apps/web`: real report form, a bare manager list/status page (no filters, no analytics, no SLA — just a list with a status dropdown), and a tracking page.

Explicitly deferred: SLA tracking, analytics, CSV export, assignment workflow, admin panel — these are optional full-stack polish, not core to the agentic-AI goal.

## Folders touched

```
apps/api/app/domain/incidents/
apps/api/app/repositories/interfaces/incidents.py
apps/api/app/repositories/postgres/incidents.py
apps/api/app/services/incident_service.py
apps/api/app/security/authentication.py
apps/api/app/api/v1/routers/incidents.py
apps/api/app/api/v1/routers/auth.py
apps/api/migrations/versions/0001_initial.py
apps/web/src/app/report/
apps/web/src/app/track/
apps/web/src/app/(manager)/dashboard/
```

## Deployment artifact

No new compose services — same `infra/compose/compose.yml` from M0. New Alembic migration files run via `alembic upgrade head` inside the `api` container/venv.

## Setup & run

```bash
cd apps/api
alembic init migrations   # if not already
alembic revision --autogenerate -m "initial incidents + users"
alembic upgrade head

# seed a manager account (interactive — do not hardcode a password)
python -m app.scripts.seed_manager
```

## Manual tasks (things only you can do)

- [ ] Generate a JWT signing secret and put it in `.env`: `openssl rand -hex 32` → `JWT_SECRET=...`
- [ ] Decide the seed manager account's email; run the seed script yourself and enter a real password when prompted (don't hand it to me).

## Exit criteria

- Submitting the report form creates a `RECEIVED` incident row and returns a reference code.
- The tracking page shows correct status for a valid reference code, and nothing for an invalid one (no ID enumeration).
- Logging in as the seeded manager shows the incident list; changing status updates it.
- All of the above works with `LLM_API_KEY` unset/blank — no AI dependency anywhere in this path.
