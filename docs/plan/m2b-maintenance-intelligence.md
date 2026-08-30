# M2b — Maintenance intelligence (recommendations, anomaly explanations, work orders)

[← back to overview](00-overview.md)

## Objective

Add a **proactive**, manager-triggered analysis path alongside the reactive incident graph from M2: given an as-of point in time, detect abnormal maintenance patterns from historical incidents + maintenance logs, explain them in plain language, recommend action, and draft a work order — all subject to the same human-approval discipline as the rest of the system (never auto-dispatched).

## Why this milestone exists

M1/M2 are entirely reactive: an occupant reports something, the graph triages it. Nothing yet looks *backward* across accumulated history to say "this is trending wrong" before it becomes another report. This milestone adds that lens, reusing M2's infrastructure (`StructuredLLM` gateway, strict Pydantic schemas, bounded/fallback agent pattern) rather than inventing a parallel stack.

Kept deliberately **on-demand, not streaming**: a manager picks an as-of date/window and gets a snapshot analysis. No sensor/IoT ingestion, no background scheduler required for the core deliverable — see "Explicitly deferred" below.

## Scope

Build:

- `maintenance_logs` table + Alembic migration: id, optional `incident_id` FK, location, category, description, `performed_by` (team), `performed_at`, `next_due_at` (nullable), timestamps. Represents completed work — the thing M1's `incidents` table doesn't track.
- **Deterministic anomaly detection** — a code function, not a prompt (same philosophy as M2's `determine_priority`): given an as-of timestamp, group `incidents` + `maintenance_logs` by `(location, category)` and flag:
  - `RECURRING_FAILURE` — incident count in a rolling window (e.g. 30/90 days) exceeds a threshold.
  - `OVERDUE_MAINTENANCE` — `next_due_at` from the last maintenance log has passed as-of the analysis date.
  - `MTBF_DROP` — mean time between incidents for that `(location, category)` has shortened materially versus its historical baseline.

  ```python
  def detect_anomaly_signals(incidents, maintenance_logs, as_of: datetime) -> list[AnomalySignal]: ...
  ```

  The AI never invents *whether* something is anomalous — it only explains/acts on signals this function already found, mirroring how `determine_priority` keeps the hazard rule engine authoritative over the model.
- Three specialized agents (strict Pydantic schema, `extra="forbid"`, own prompt file — same pattern as M2's agents), chained per detected signal:

  | Agent | Responsibility | Fallback on failure |
  |---|---|---|
  | anomaly_explanation | Plain-language explanation of *why* the signal fired, grounded only in the supplied incident/log evidence (no speculation beyond it) | template explanation citing the raw counts/dates |
  | maintenance_recommendation | Concrete recommended action(s) given the explanation and signal type | "manual review required" placeholder |
  | work_order_draft | Structured draft: title, description, priority, suggested team (same allow-listed team map as M2's `assignment` agent), suggested due-by | unassigned draft, flagged for manual authoring |
- `maintenance_work_orders` table: one row per analyzed signal, holding the signal reference, all three agent outputs, and a review `status` (`DRAFT` → `APPROVED` / `REJECTED` / `EDITED`, `reviewed_by`, `reviewed_at`). **A work order is never auto-issued** — approval is a required manual step, consistent with M2/M8's human-oversight rules.
- `POST /api/v1/maintenance/analysis` (manager-only) — body: `{ as_of: date, window_days?: int }` → runs detection + the three-agent chain for each signal found, returns draft work orders.
- `PATCH /api/v1/maintenance/work-orders/{id}` (manager-only) — approve/reject/edit a draft.
- Minimal `apps/web` manager page: a date picker + "Analyze" button, a list of resulting draft work orders (anomaly explanation, recommendation, work order fields), each with approve/reject/edit controls. Reuses the M2 trace-view visual pattern where practical rather than inventing new UI.

Explicitly deferred: sensor/IoT ingestion, scheduled/background analysis runs, equipment/asset registry beyond the existing `location`/`category` fields already on `incidents` — all optional stretch goals if there's time after the core deliverables (M2–M5) are solid.

## Folders touched

```
apps/api/app/domain/maintenance/anomaly_detection.py   # detect_anomaly_signals lives here
apps/api/app/agents/anomaly_explanation.py, maintenance_recommendation.py, work_order_draft.py
apps/api/app/prompts/anomaly_explanation/v1.yaml, maintenance_recommendation/v1.yaml, work_order_draft/v1.yaml
apps/api/app/workflows/maintenance_analysis.py          # small bounded chain, not the full M2 graph
apps/api/app/repositories/interfaces/maintenance.py, postgres/maintenance.py
apps/api/app/api/v1/routers/maintenance.py
apps/api/migrations/versions/000X_maintenance_logs_and_work_orders.py
apps/web/src/app/(manager)/maintenance/
```

## Deployment artifact

None new — same `api`/`postgres` services from M0. No new container, no scheduler service (analysis runs synchronously on request).

## Setup & run

```bash
cd apps/api
alembic revision --autogenerate -m "maintenance logs and work orders"
alembic upgrade head

pytest app/tests/maintenance -k fake_llm   # detection + 3-agent chain against FakeStructuredLLM
```

## Manual tasks (things only you can do)

- [ ] Supply (or seed) some realistic historical `maintenance_logs` entries — this milestone's detection quality depends on having real-ish completed-work history to analyze; synthetic data works for tests but a demo benefits from something plausible.
- [ ] Decide the anomaly thresholds (recurrence count/window, MTBF-drop sensitivity) — these are policy calls specific to the type of facility, not something to fabricate.
- [ ] Confirm the allow-listed team map reused from M2's `assignment` agent still covers the teams you want work orders routed to.

## Exit criteria

- Running an analysis with `FakeStructuredLLM` against seeded incidents/logs containing a known recurring pattern produces exactly the expected `AnomalySignal`, and the three-agent chain runs end-to-end for it.
- With a real provider configured, triggering an analysis from the manager UI for a chosen as-of date returns one draft work order per detected signal, each with an anomaly explanation, a recommendation, and structured work-order fields.
- A draft work order is never actionable/dispatched until a manager explicitly approves it — rejecting or editing one is reflected in `maintenance_work_orders.status` and preserves the original AI draft alongside the human decision (never overwritten), consistent with M2/M8's audit-trail rule.
- Analysis over a window with no qualifying patterns returns zero signals, not fabricated ones.
