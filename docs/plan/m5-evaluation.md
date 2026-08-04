# M5 — Evaluation (Promptfoo)

[← back to overview](00-overview.md)

## Objective

Build the evaluation harness that is the actual *evidence* the agent design works — not just "it ran once and looked fine," but measured accuracy, hazard recall, and injection resistance against a reviewed dataset, re-run on every change.

## Scope

Build, under `evals/promptfoo/`:
- `datasets/intent.jsonl`, `incidents.jsonl`, `safety_critical.jsonl`, `facility_qa.jsonl`, `prompt_injection.jsonl` — hand-built and reviewed, not bulk-generated. Aim for 50–100 total cases to start:
  - ~20 facility questions, ~40 incident reports, ~10 status queries, ~20 ambiguous/out-of-scope messages
  - a curated safety-critical set (fire/gas/electrical/entrapment phrasings) that must hit P1 100% of the time
  - direct + indirect (RAG-embedded) prompt-injection cases
- `promptfooconfig.yaml` wired against a protected `/api/v1/evals/*` endpoint (guarded by an evaluation key, **disabled outside dev/CI**).
- Assertions for: classification accuracy (macro F1), critical-hazard recall, valid JSON schema (no extra fields, enums respected), citation presence/validity, and consistency across repeated runs at temperature 0.
- Wire `promptfoo eval` into `.github/workflows/ci.yml` as a required job (small critical-regression subset on every PR; full suite before anything you'd call a "release").

## Folders touched

```
evals/promptfoo/promptfooconfig.yaml
evals/promptfoo/redteam.yaml
evals/promptfoo/datasets/*.jsonl
apps/api/app/api/v1/routers/evals.py   # dev/CI-only, guarded by X-Evaluation-Key
.github/workflows/ci.yml               # add promptfoo job
```

## Deployment artifact

None new. Runs via `npx promptfoo eval` locally and as a CI job — not a running service.

## Setup & run

```bash
npm install -D promptfoo
npx promptfoo eval -c evals/promptfoo/promptfooconfig.yaml
npx promptfoo view   # inspect results in a local UI
```

## Manual tasks (things only you can do)

- [ ] None strictly required. Optional: if you have real (anonymized) example reports/questions, contributing a handful adds realism the synthetic cases can't — but the plan works fine with synthetic data alone.

## Exit criteria

- `promptfoo eval` runs clean locally and in CI.
- Targets from the original spec are measured and documented (met, or explicitly flagged as a gap with next steps) — notably: **100% recall on the critical-hazard safety set** and **≥95% prompt-injection pass rate**, since those two are non-negotiable for a system that touches safety-adjacent reports.
- A regression is visible: deliberately breaking a prompt or the priority rule causes the relevant CI job to fail.
