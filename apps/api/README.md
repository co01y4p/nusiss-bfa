# Facilities AI Assistant API

FastAPI backend for milestones M0 through M2. The default `fake` LLM provider is fully local and
deterministic. It makes the workflow testable without an API key.

## Local setup

```bash
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.scripts.seed_manager
uvicorn app.main:app --reload --port 8000
```

On macOS or Linux, activate the environment with `source .venv/bin/activate`.

## Main endpoints

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- `POST /api/v1/auth/token`
- `POST /api/v1/incidents`
- `GET /api/v1/incidents/track/{reference_code}`
- `GET /api/v1/incidents`
- `PATCH /api/v1/incidents/{id}/status`
- `POST /api/v1/assistant/messages`
- `GET /api/v1/incidents/{id}/trace`

The last two manager endpoints require `Authorization: Bearer <token>`.

## Provider selection

Keep `LLM_PROVIDER=fake` for local development and automated tests. A future real-provider run can
set `LLM_PROVIDER=openai` or `LLM_PROVIDER=openrouter` together with `LLM_BASE_URL`, `LLM_API_KEY`,
and model names. No agent or workflow code changes are required.

