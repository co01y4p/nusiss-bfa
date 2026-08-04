# M6 — Observability (light)

[← back to overview](00-overview.md)

## Objective

Instrument what actually matters for an agentic system — agent/LLM behavior — plus basic system/API health. Deliberately **not** the original spec's full 5-dashboard enterprise suite; one focused Grafana dashboard is enough to demonstrate the concept.

## Scope

Build:
- Prometheus metrics from `apps/api`: `agent_runs_total{agent,status}`, `agent_duration_seconds{agent}`, `agent_retries_total{agent,reason}`, `llm_tokens_total{provider,model,type}`, `llm_schema_validation_failures_total{agent}`, `tool_invocations_total{tool,status}`, plus basic `http_requests_total`/`http_request_duration_seconds`.
- One Grafana dashboard, provisioned from JSON in Git (not hand-built in the UI): "Agent & LLM Ops" — agent duration, token usage, retries, schema failures, human-escalation rate.
- Structured JSON logging (no chain-of-thought, no secrets — reason codes and rule hits only, per the M4 security constraints).

Explicitly deferred: the security dashboard, facility-operations analytics dashboard, and full system dashboard from the original spec — add only if there's time after M2–M5 are solid.

## Folders touched

```
apps/api/app/monitoring/metrics.py, logging.py
infra/monitoring/prometheus/prometheus.yml
infra/monitoring/grafana/dashboards/agent-llm-ops.json
infra/monitoring/grafana/provisioning/
infra/compose/compose.yml   # add prometheus + grafana under an `observability` profile
```

## Deployment artifact

`infra/compose/compose.yml`, `prometheus` and `grafana` services gated behind `--profile observability` — not started by default, so normal dev work doesn't need them running.

## Setup & run

```bash
docker compose -f infra/compose/compose.yml --profile observability up -d prometheus grafana
# api must expose /metrics (added this milestone)
open http://localhost:3001   # Grafana, default admin/admin on first run — change immediately
```

## Manual tasks (things only you can do)

- [ ] Choose a real Grafana admin password on first login (don't leave the default).
- [ ] Decide whether Grafana/Prometheus stay bound to localhost/SSH-tunnel-only (recommended, especially before M7) or get exposed — this becomes a real decision once there's a production server in M7.

## Exit criteria

- Submitting an incident through the assistant produces visible movement in the "Agent & LLM Ops" dashboard within the same session (agent duration, token count for that run).
- A forced LLM failure (e.g. temporarily wrong `LLM_API_KEY`) shows up as a retry/failure metric, not silent failure.
