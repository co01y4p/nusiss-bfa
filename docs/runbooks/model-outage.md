# Runbook — LLM provider outage

## Symptoms

- Occupants get "A facility manager will review this request." for most messages.
- `HUMAN_REVIEW` dominates the workflow outcomes (Grafana: "Human Escalation Rate").
- API logs show `Agent '…' failed … executing fallback` or `LLM provider circuit breaker is OPEN`.
- Prometheus metric `bfa_llm_circuit_breaker_state` is `2` (after the observability work in G5).

## What the system does on its own

| Layer | Behaviour |
|---|---|
| Per-attempt timeout | Each HTTP attempt stops after `LLM_ATTEMPT_TIMEOUT_SECONDS` (12s) and is retried up to twice. |
| Agent fallbacks | Every agent has a deterministic fallback; none of them crash the request. |
| Circuit breaker | After 3 consecutive failures the breaker opens for 30s and calls fail fast. |
| Safety rules | Critical hazards (fire, gas, smoke, live wire, lift entrapment, flooding) are still forced to P1 by the keyword rules, with no model involved. |
| Save-before-AI | `POST /api/v1/incidents` (the report form) and manager tools do not use the model at all. |

Reports sent through the assistant during an outage are stored with `requires_human_review` and appear in the manager queue.

## Operator steps

1. **Confirm it is the provider.** Check the provider status page, then test the key directly:
   ```bash
   curl -s -o /dev/null -w "%{http_code}\n" https://api.openai.com/v1/models \
     -H "Authorization: Bearer $LLM_API_KEY"
   ```
   `401` means a bad or expired key, `429` means quota or rate limit, `5xx` or a timeout means a provider outage.
2. **Tell occupants** (if the outage will last): ask them to use the report form at `/report`, which works without the model.
3. **Switch provider** (optional). The gateway is provider-neutral. Edit `.env`:
   ```env
   LLM_PROVIDER=openrouter
   LLM_BASE_URL=https://openrouter.ai/api/v1
   LLM_API_KEY=<openrouter key>
   CLASSIFIER_MODEL=<model id>
   GENERATOR_MODEL=<model id>
   ```
   then restart only the API: `docker compose … up -d api`. OpenRouter uses the chat-completions style, which has no `reasoning` field; quality can differ, so run the Promptfoo suite before relying on it.
4. **Restart the API** to reset the circuit breaker once the provider is back.

## Confirm recovery

- `curl -s localhost:8000/api/v1/health/live` returns ok.
- Send a known question (for example "What are the building hours?"); the outcome should be `FINALIZED` with a cited answer.
- Review the incidents flagged `requires_human_review` during the outage and clear them.

## After the incident

Record the start and end time, cause, how many reports needed manual review, and any change to this runbook.
