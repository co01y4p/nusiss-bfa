# Failure modes and how the system behaves

Every row is exercised by a test in [`apps/api/tests/test_failure_injection.py`](../apps/api/tests/test_failure_injection.py)
unless another file is named. None of them may produce an HTTP 500 or lose a stored incident.

| Failure | How it is injected | What the occupant gets | What a manager sees |
|---|---|---|---|
| LLM provider down (HTTP 503 on every call), ordinary message | `httpx.MockTransport` behind the real OpenAI provider | "A facility manager will review this request." | Run saved as `HUMAN_REVIEW`, reason `SECURITY_CHECK_UNAVAILABLE`; a MEDIUM `SECURITY_CHECK_UNAVAILABLE` event (not an injection) |
| LLM down, **critical-hazard report** (gas, fire, smoke, live wire, lift entrapment, flooding) | same | Reference code and the emergency hotline, in fixed text | An incident exists, forced to **P1** by the keyword rules, flagged for review; trace shows `HAZARD_LOGGED_WITHOUT_MODEL` |
| LLM down, real prompt injection | same | "This request was quarantined for manager review." | `QUARANTINED` and a HIGH injection event: the keyword rules need no model |
| Model returns invalid JSON or breaks the schema (extra field, out-of-range value, missing fields) | mock transport returns the bad body | As for "provider down" | `llm_schema_validation_failures_total` increments; the output is never trusted |
| Circuit breaker open | breaker opened before the request | As for "provider down" | **No HTTP request is made**; hazards are still logged as P1 |
| Workflow exceeds its time budget | an LLM that sleeps longer than `WORKFLOW_TIMEOUT_SECONDS` | "The automated workflow stopped safely. A manager will review it." | `HUMAN_REVIEW`, reason `WORKFLOW_BOUND_REACHED`, run saved |
| Unexpected error mid-workflow (embedding API or retriever failure, bug) | a retriever that raises | Same safe message, **HTTP 200** | `HUMAN_REVIEW`, reason `WORKFLOW_ERROR`, traceback logged with the request id; an existing incident is kept and flagged |
| Database error while creating the incident | the incident repository raises | "A facility manager will review this request." | `HUMAN_REVIEW`, reason `CREATE_INCIDENT_FAILED` |
| Review step rejects a P1 reply | review agent returns `approved=false` | Reference code plus the emergency hotline, in fixed text | `HUMAN_REVIEW` with the review issues in the trace |
| Valkey (rate limiter) unreachable | unreachable URL; broken limiter (`tests/test_rate_limit.py`) | Request served normally | Limits fall back to per-process memory; one warning logged; `rate_limit_decisions_total{backend="memory"}` |
| Langfuse unreachable | tracer pointed at a closed port | Unaffected | Unaffected; trace upload is dropped |
| Report form during an LLM outage | the assistant's LLM replaced by a failing provider | `POST /incidents` returns 201 and the code is trackable | Normal incident |

## Known limits

- With the model down, the system cannot tell a hazard **question** ("what do I do if there is a fire?")
  from a hazard **report**, so a flagged message is logged as an incident. Safety wins over a possible
  false P1; a manager reviews every P1.
- Non-hazard requests during an outage are not saved as incidents; occupants should use the report form
  (`/report`), which does not depend on the model. See [the outage runbook](runbooks/model-outage.md).
- The unit tests use a mocked transport, not a real provider outage.
