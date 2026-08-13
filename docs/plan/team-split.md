# Team split — 5 people, M1 + M2

[← back to overview](00-overview.md)

## Why we split M1+M2 into lanes, not the whole project into 5 milestones

The milestones are **sequential**: M2 builds on M1, M3–M5 all extend the M2 graph. If each person "owns a milestone," persons 3–5 are blocked until the graph exists. Instead:

- **Now:** everyone works in parallel on M1+M2, split by *component* with agreed interfaces.
- **Later:** each person carries a pre-assigned "future track" (M3–M8), so when M2 lands, nobody has to renegotiate who does what.

## Day 0 — do together, before splitting (half a day, one shared session)

M0 doesn't exist yet (there is no `apps/` folder). Don't parallelize scaffolding — merge conflicts on an empty repo are pure waste. As a group:

1. Build the M0 skeleton per [m0-harness-scaffold.md](m0-harness-scaffold.md): `apps/web`, `apps/api`, compose (Postgres + Valkey), CI.
2. Agree the **contracts** everyone codes against, and commit them as stubs:
   - `apps/api/app/workflows/state.py` — the shared `WorkflowState` model
   - `apps/api/app/agents/base.py` — agent interface + per-agent Pydantic input/output schemas (`extra="forbid"`)
   - `apps/api/app/llm/gateway.py` — the `StructuredLLM` protocol
   - `apps/api/app/repositories/interfaces/incidents.py` — repository interface (so agent code can stub persistence before the real DB layer lands)
3. Agree branch/PR rules (one lane = one folder set = few conflicts).

Once those stub files are merged, everyone works independently.

## The 5 lanes

| # | Lane | M1/M2 scope | Folders owned | Future track |
|---|------|-------------|---------------|--------------|
| P1 | **Platform + M1 backend** | Auth (JWT + Argon2id), `incidents` table + Alembic migration, incident routers, Postgres repository, seed script | `domain/incidents/`, `repositories/`, `api/v1/routers/`, `security/authentication.py`, `migrations/` | M7 deployment |
| P2 | **Frontend** | M1: report form, tracking page, bare manager list. M2: the manager-only agent **trace view** | `apps/web/src/app/report/`, `track/`, `(manager)/` | M8 demo + responsible-AI |
| P3 | **LLM gateway** | `StructuredLLM` gateway, `FakeStructuredLLM` for tests, retry/timeout/bounds enforcement, `providers/openai_compatible.py` (httpx), prompt-file loading | `llm/`, `prompts/` (loader) | M3 RAG |
| P4 | **Agents A — understanding** | `security`, `intent`, `extraction`, `classification` agents: schema + prompt (`v1.yaml`) + unit tests against the fake LLM, each with its fallback path | `agents/security.py, intent.py, extraction.py, classification.py`, matching `prompts/*/v1.yaml` | M4 agent security |
| P5 | **Graph + Agents B — decisions** | `facility_graph.py` state machine (routing, bounds, fault isolation), `determine_priority` in `domain/incidents/policies.py` (deterministic — code, not prompt), `assignment`, `response`, `review` agents; end-to-end fake-LLM tests hitting every node incl. `human_review`/`quarantine` | `workflows/`, `agents/priority.py, assignment.py, response.py, review.py`, `domain/incidents/policies.py` | M5 evaluation (Promptfoo) |

M6 (observability) is light and shared — whoever finishes their lane first picks it up.

## Dependency map (what actually blocks what)

```
Day 0 contracts (all together)
├── P1: M1 backend ──────────────┐
├── P2: M1 frontend ─── needs P1's API routes (use the plan's exact endpoints as the contract)
├── P3: gateway + FakeStructuredLLM ──┐
├── P4: agents A ── needs P3's fake LLM + gateway protocol (stub is enough to start)
└── P5: graph + agents B ── needs P3's fake LLM; needs P1's repo *interface* only (persist node
                            calls the interface — real Postgres impl plugs in at integration)
```

Key points that keep everyone unblocked:

- **P4/P5 never wait for a real API key.** The plan mandates fake-LLM-first: the whole graph must pass tests with `FakeStructuredLLM` before `openai_compatible.py` is even wired.
- **P5 doesn't wait for P1's database.** The `persist_incident` node calls the repository *interface*; P1's Postgres implementation is swapped in at integration. Same for P2's trace view — build it against a hand-written sample trace JSON first.
- **P3 is the shared dependency** — the gateway protocol + fake should be the first thing merged after Day 0 (it's small: one protocol, one fake class).

## Integration checkpoints

1. **Checkpoint 1 (end of M1):** P1+P2 demo the AI-free slice — report → DB → manager list → tracking with `LLM_API_KEY` blank. This is M1's exit criterion and the permanent fallback path.
2. **Checkpoint 2 (graph green on fakes):** P3+P4+P5 — full graph runs end-to-end in `pytest` with `FakeStructuredLLM`, every node hit at least once. No network needed; can happen before or in parallel with Checkpoint 1.
3. **Checkpoint 3 (real wiring):** one person creates the OpenAI/OpenRouter key (see M2 manual tasks), fill `.env`, run the real thing; P2's trace view shows intent → extraction → classification → priority → assignment with reason codes. Verify the "gas smell → always P1" rule beats the model, and that swapping `.env` between providers needs zero code changes.

Checkpoint 3 met = M2 exit criteria met.
