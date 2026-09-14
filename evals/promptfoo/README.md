# M5 evaluation harness

This directory contains the reviewed regression evidence for the Facilities AI Assistant. The suite
uses the configured real LLM through the protected evaluation API. The endpoint rejects the fake
provider and never falls back to it. Local and CI runs require valid external model credentials.

## Dataset

The suite contains 92 hand-authored cases:

- 20 intent cases, including 10 status queries and 10 ambiguous, out-of-scope, or feedback cases.
- 30 non-critical incident classification cases balanced across all six categories.
- 12 safety-critical incident cases covering fire, smoke, gas, electrical, lift entrapment, and
  active flooding.
- 20 grounded facility questions with approved context and expected citations.
- 10 prompt-injection cases split evenly between direct and indirect attacks.

## Local run

Start the API from the repository root in one terminal:

```powershell
$env:APP_ENV = "development"
$env:EVALUATION_ENABLED = "true"
$env:EVALUATION_KEY = "local-evaluation-key"
$env:LLM_PROVIDER = "openai"
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_API_KEY = "your-evaluation-api-key"
$env:CLASSIFIER_MODEL = "gpt-5-nano"
$env:GENERATOR_MODEL = "gpt-5-nano"
apps/api/.venv/Scripts/python.exe -m uvicorn app.main:app --app-dir apps/api --port 8011
```

Run the full evaluation in another terminal:

```powershell
cd evals/promptfoo
$env:EVALUATION_KEY = "local-evaluation-key"
$env:EVALUATION_BASE_URL = "http://127.0.0.1:8011"
pnpm install --frozen-lockfile
pnpm eval:full
pnpm metrics:full
```

Use `pnpm eval:critical` and `pnpm metrics:critical` for the PR safety gate. Result JSON files are
ignored and may be inspected with `pnpm exec promptfoo view`.

## Quality gates

| Metric                       |      Required |
| ---------------------------- | ------------: |
| Classification macro F1      | 85% or higher |
| Intent accuracy              | 90% or higher |
| Critical-hazard recall       |          100% |
| Prompt-injection pass rate   | 95% or higher |
| Citation validity            |          100% |
| Temperature-zero consistency |          100% |
| Real LLM provider usage      |          100% |
| Real LLM completion rate     |          100% |

Every case also asserts a strict JSON schema with no extra fields and valid enum values. Promptfoo
runs every case twice at temperature zero and the aggregate gate compares the repeated structured
decisions. Intent and category quality use aggregate accuracy and macro-F1 thresholds instead of
requiring every individual probabilistic classification to match. Safety priority, injection
quarantine, and citations remain hard per-case assertions. Free-form wording and diagnostic reason
codes are excluded from the consistency comparison.

The HTTP provider retries transient model failures up to two times. Persistent failures still return
an invalid result and fail both the per-case schema check and the real-completion gate.
Removing a critical hazard from the deterministic policy, weakening injection detection, breaking
an agent prompt, emitting an unknown schema field, or returning an invalid citation causes the
relevant Promptfoo assertion or aggregate quality gate to fail.
