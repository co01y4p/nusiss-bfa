# M8 — Responsible-AI review & demo packaging

[← back to overview](00-overview.md)

## Objective

Close the loop: confirm the human-oversight rules actually hold up end-to-end, the audit trail is complete, and prepare a demonstration that maps directly to what was built (not an aspirational checklist).

## Scope

Build/do:
- `docs/responsible-ai/impact-assessment.md` — the harms/mitigations table from the original spec, trimmed to what was actually implemented (fire/hazard under-prioritization, wrong assignment, hallucinated answers, PII disclosure, injection-caused unauthorized action, AI outage).
- Walk through the human-involvement rules from M2/M4 and confirm each one fires in practice:
  - P1 → mandatory human acknowledgement
  - confidence < 0.75 → manual triage
  - no RAG evidence → no factual claim, explicit fallback
  - manual override → reason required, both AI and human decisions preserved (never overwritten)
- A short demo script: sequence of actions to run live (submit a routine report, submit a hazard report, ask a grounded question, ask an unsupported question, attempt an injection, kill the LLM API key and show the incident still saves).

## Folders touched

```
docs/responsible-ai/impact-assessment.md
docs/responsible-ai/demo-script.md
```

## Deployment artifact

None — this is a review and documentation pass over the system built in M0–M7.

## Setup & run

No new setup. Run through `demo-script.md` against your local (or, if M7 is done, production) deployment and record the actual results next to each expected outcome.

## Manual tasks (things only you can do)

- [ ] Review and personally sign off on the responsible-AI docs — this is a judgment call about your own project, not something to delegate.
- [ ] Decide what gets recorded (screenshots/screen recording) for submission or presentation.

## Exit criteria

- Every human-oversight rule listed above has been triggered at least once and behaved correctly.
- The demo script runs cleanly start to finish against a real deployment.
- The harms/mitigations doc reflects what was actually built, not the full original spec's aspirational scope.
