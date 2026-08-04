# Facilities AI Assistant — Project Plan (Overview)

> Working title only — "Facilities AI Assistant" is a placeholder name (single config constant, trivial to rename later).

## What this is

A **generic building facilities management AI assistant**: occupants report issues (leaks, electrical faults, broken lifts, etc.) or ask facility questions; a bounded multi-agent workflow triages, classifies, prioritizes, and routes reports, and answers questions grounded in approved facility documents. A facility manager reviews, overrides, and operates the system.

Not tied to any specific university or organization — language throughout uses "occupant," "building," "facility manager," not campus-specific terms.

## What this is — and is not — focused on

**This is an agentic-AI capstone, not a full-stack product build.** The full-stack app (Next.js + FastAPI) exists to give the agents something to operate on and a way to see what they decided — it is a *harness*, not a product to polish. The actual substance and grading weight is:

- a bounded multi-agent workflow (reasoning/planning, specialized roles, tool use)
- retrieval-augmented grounding (RAG) as a tool the agents use
- agent-specific security (prompt injection, tool allow-listing, excessive-agency controls)
- evaluation (Promptfoo) proving the agent design actually works

Consequently, the frontend is deliberately thin (a report form, an assistant chat, a simple trace/queue view) rather than the multi-dashboard, admin-panel, analytics-suite version of this idea. Those product features are optional stretch goals, not core deliverables.

## Milestones

Each milestone has its own self-contained file: objective, folders touched, deployment artifact, setup/run commands, manual tasks only you can do, and exit criteria.

| # | File | Objective |
|---|------|-----------|
| M0 | [m0-harness-scaffold.md](m0-harness-scaffold.md) | Thin `apps/web` + `apps/api` skeleton, Postgres + Valkey via Compose, health checks, CI lint/test |
| M1 | [m1-non-agentic-baseline.md](m1-non-agentic-baseline.md) | Non-AI vertical slice: report → DB → manager list → tracking (save-before-AI principle) + minimal auth |
| M2 | [m2-multi-agent-workflow.md](m2-multi-agent-workflow.md) | **Centerpiece.** Bounded agent graph, fake LLM first, then real OpenAI/OpenRouter |
| M3 | [m3-rag-knowledge-base.md](m3-rag-knowledge-base.md) | pgvector RAG as an agent tool, with citations |
| M4 | [m4-agent-security.md](m4-agent-security.md) | Prompt-injection defense, tool allow-list, PII redaction, bounded loops |
| M5 | [m5-evaluation.md](m5-evaluation.md) | Promptfoo suites: accuracy, hazard recall, injection resistance, grounding, consistency |
| M6 | [m6-observability.md](m6-observability.md) | Agent/LLM-focused Prometheus + Grafana (light, not the full enterprise suite) |
| M7 | [m7-deployment.md](m7-deployment.md) | Hardened Compose deployment; production plan documented, not yet provisioned |
| M8 | [m8-responsible-ai-demo.md](m8-responsible-ai-demo.md) | Responsible-AI review, grading-evidence demo pass |

Work through them roughly in order — M2–M5 are where most of the effort belongs.

## Repository structure

```
nusiss-bfa/
├── apps/
│   ├── web/                 # Next.js — frontend, separate from backend
│   │   └── src/app/         # report form, assistant chat, minimal manager/trace view
│   └── api/                 # FastAPI — backend
│       └── app/
│           ├── agents/      # one specialized agent per file — the core of this project
│           ├── workflows/   # bounded graph: state, nodes, routing
│           ├── llm/         # provider-neutral gateway (OpenAI/OpenRouter behind one interface)
│           ├── rag/         # ingestion, chunking, retrieval, citation validation
│           ├── security/    # prompt-injection, PII redaction, output policy, tool allow-list
│           ├── domain/      # entities, policies (e.g. deterministic priority rules)
│           ├── repositories/ # Postgres persistence, interfaces + implementations
│           ├── api/v1/routers/  # thin FastAPI routers only — no business logic
│           └── monitoring/  # Prometheus metrics, structured logging
├── infra/
│   ├── compose/              # compose.yml + compose.prod.yml + Caddyfile
│   └── monitoring/           # prometheus.yml, Grafana dashboard JSON
├── evals/
│   └── promptfoo/            # datasets, promptfooconfig.yaml, redteam.yaml
├── docs/
│   └── plan/                 # this plan
└── .github/workflows/        # CI (and later, deploy)
```

`infra/kubernetes/` is intentionally **not** created — Kubernetes is out of scope unless explicitly requested later.

## Deployment-mechanism matrix

| Component | Dev mechanism | Production mechanism |
|---|---|---|
| `web` (Next.js) | `docker compose up web` (`apps/web/Dockerfile`) | same image, `compose.yml` + `compose.prod.yml` on a VM behind Caddy |
| `api` (FastAPI) | `docker compose up api` | same image on VM; only env values differ |
| `postgres` (+pgvector) | Compose service, local volume | Compose service on VM, persistent volume + backup cron |
| `valkey` | Compose service | Compose service on VM (cache only, no persistence needed) |
| LLM (OpenAI/OpenRouter) | **No container.** Outbound HTTPS from `api`, selected entirely by `.env` | Same — only the `.env` file on the server differs |
| `prometheus` / `grafana` | Optional Compose profile (`--profile observability`) | Same profile on VM, bound to localhost/SSH tunnel initially |
| CI | `.github/workflows/ci.yml` — format, lint, unit tests | Same workflow; a deploy workflow is added at M7 |
| Kubernetes | — | Out of scope until explicitly requested |

## LLM provider — OpenAI / OpenRouter, swappable via `.env` only

Both are OpenAI-compatible chat + embeddings APIs, so the same `openai_compatible.py` provider adapter behind the `StructuredLLM` gateway interface works for either — switching is a `.env` edit, never a code change:

```dotenv
# --- Option A: OpenAI ---
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
CLASSIFIER_MODEL=gpt-4o-mini
GENERATOR_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

# --- Option B: OpenRouter (swap in by commenting out Option A) ---
# LLM_BASE_URL=https://openrouter.ai/api/v1
# LLM_API_KEY=sk-or-...
# CLASSIFIER_MODEL=openai/gpt-4o-mini
# GENERATOR_MODEL=anthropic/claude-3.5-haiku
# EMBEDDING_MODEL=openai/text-embedding-3-small
```

Changing `GENERATOR_MODEL`/`CLASSIFIER_MODEL` alone (e.g. trying a different OpenRouter model) never touches application code.

## Local dev quickstart (placeholder — finalized at M0)

```bash
cp .env.example .env               # fill in secrets per each milestone's manual-tasks section
docker compose up -d postgres valkey
cd apps/api && alembic upgrade head && uvicorn app.main:app --reload
cd apps/web && npm run dev
```

## How to use these docs

Read a milestone file before starting that milestone. Each one is self-contained: you shouldn't need to jump between files to know what to build or what to do yourself first.
