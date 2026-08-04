# M2 — Multi-agent workflow (centerpiece)

[← back to overview](00-overview.md)

## Objective

Implement the bounded, deterministic multi-agent graph that turns free-text occupant input into a triaged, prioritized, routed incident (or a grounded answer). **This is the core deliverable of the whole project** — the milestone with the most design weight.

## Why this is the centerpiece

Everything before this (M0, M1) is scaffolding. Everything after (M3–M5) extends this graph (retrieval, security, evaluation). The agentic-AI course themes this milestone directly demonstrates:

- **Specialized roles** — one agent, one responsibility, one prompt, one strict schema (no generalist "do everything" prompt).
- **Planning/routing without autonomy** — a supervisor implemented in *code* (not an LLM deciding what to call next) routes between nodes. The LLM influences classification/content; it never controls program execution.
- **Tool use** — retrieval (M3) and later, tool invocation, are explicit, typed, allow-listed calls — never free-form.
- **Fault isolation** — each node has its own timeout, retry policy, and fallback; one agent failing degrades gracefully rather than crashing the workflow.

## Scope

Build the graph as a directed, bounded state machine (LangGraph or a hand-rolled equivalent behind a `WorkflowEngine` interface — implementation detail, the *contract* matters more than the library):

```
security → intent → [faq_retrieval | persist_incident | human_review]
persist_incident → extract → classify → priority → [notify_critical] → assign
                 → incident_retrieval → incident_response → review → [finalize | human_review]
faq_retrieval → faq_response → review → [finalize | human_review]
```

Agents to implement, each with a strict Pydantic input/output schema (`extra="forbid"`) and its own prompt file/version:

| Agent | Responsibility | Fallback on failure |
|---|---|---|
| security | Injection/abuse risk scoring | quarantine or restricted path |
| intent | INCIDENT_REPORT / FACILITY_QA / STATUS_QUERY / FEEDBACK / OTHER | manual triage |
| extraction | Summary, location, hazards, missing fields | preserve raw text, ask for clarification |
| classification | HVAC/ELECTRICAL/PLUMBING/... category | GENERAL + manual review |
| priority | **Deterministic policy layer**, AI is a signal not the decision (hazard-keyword rules always win; see below) | rule-engine result wins |
| assignment | Pick a team from an allow-listed map | unassigned manager queue |
| response | Safe acknowledgement / grounded answer | controlled template |
| review | Schema/policy/citation validation | human review |

Implement the **deterministic priority policy** exactly as a code function, not a prompt:

```python
CRITICAL_HAZARDS = {"FIRE", "SMOKE", "GAS_SMELL", "EXPOSED_LIVE_WIRE", "LIFT_ENTRAPMENT", "ACTIVE_FLOODING"}

def determine_priority(hazard_codes, ai_priority, ai_confidence):
    rule_hits = hazard_codes & CRITICAL_HAZARDS
    if rule_hits:
        return "P1", [f"CRITICAL_HAZARD:{h}" for h in rule_hits], True
    if ai_confidence < 0.75:
        return "P3", ["LOW_CONFIDENCE_MANUAL_REVIEW"], True
    return ai_priority, ["AI_RECOMMENDATION"], ai_priority in {"P1", "P2"}
```

Build the provider-neutral gateway first, with a `FakeStructuredLLM` for tests, before touching the real API:

```python
class StructuredLLM(Protocol):
    async def generate(self, *, system_prompt, user_payload, output_schema, model, temperature=0.0, timeout_seconds=20.0): ...
```

Only after the graph works end-to-end with fake responses, wire `providers/openai_compatible.py` — a thin `httpx` client (not a vendor SDK, to keep both OpenAI and OpenRouter reachable through one code path) pointed at `LLM_BASE_URL`.

Bounds to enforce from the start: max agent steps per request, max model calls, max input chars, per-agent timeout, whole-workflow timeout, at most one schema-repair retry, at most two transient-error retries.

Add a minimal trace view in `apps/web` (manager-only) showing each completed node's output and reason codes for a given incident — this is your primary way to *see* the agent working, and doubles as the demo artifact for M8.

## Folders touched

```
apps/api/app/agents/base.py, intent.py, extraction.py, classification.py, priority.py, assignment.py, response.py, review.py
apps/api/app/workflows/facility_graph.py
apps/api/app/llm/gateway.py, retry.py, providers/openai_compatible.py
apps/api/app/prompts/intent/v1.yaml, classification/v1.yaml, priority/v1.yaml, ...
apps/api/app/domain/incidents/policies.py   # determine_priority lives here
apps/web/src/app/(manager)/incidents/[id]/trace/
```

## Deployment artifact

None new. The `api` container makes outbound HTTPS calls to `LLM_BASE_URL` — no container, no compose service, purely `.env`-driven.

## Setup & run

```bash
cd apps/api
pip install httpx pydantic langgraph   # or drop langgraph if hand-rolling the graph
pytest app/tests/workflow -k fake_llm   # graph tests with FakeStructuredLLM, no network needed
# once real provider is wired:
uvicorn app.main:app --reload
```

## Manual tasks (things only you can do)

- [ ] Create an **OpenAI** API key ([platform.openai.com](https://platform.openai.com)) **or** an **OpenRouter** API key ([openrouter.ai](https://openrouter.ai)) — your call, both work through the same gateway.
- [ ] Add billing/credit to whichever account you choose (both require a funded account for non-trial use).
- [ ] Paste the key into `.env` as `LLM_API_KEY`, and set `LLM_BASE_URL` + model ids per the [overview's swap block](00-overview.md#llm-provider--openai--openrouter-swappable-via-env-only).
- [ ] Pick a starting model per provider (e.g. `gpt-4o-mini` for OpenAI, or any OpenRouter-listed model) — cheap/fast models are fine for classification agents; you can use a stronger one for the response generator only.

## Exit criteria

- With `FakeStructuredLLM`, the full graph runs end-to-end in tests, hitting every node at least once (including `human_review` and `quarantine` paths).
- With a real provider configured, submitting a report through the assistant chat produces a visible agent trace: intent → extraction → classification → priority → assignment, each with reason codes.
- Switching `.env` between OpenAI and OpenRouter (and changing model ids) works with zero code changes.
- A hazard keyword (e.g. "gas smell") always produces P1 regardless of what the model returns — the rule engine provably wins.
