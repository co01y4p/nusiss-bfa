# Facilities AI Assistant API

FastAPI backend for milestones M0 through M3. Includes bounded multi-agent workflow, pgvector-backed
RAG knowledge base, heading-aware chunking, hybrid search, and citation validation. The application
uses the OpenAI Responses API with `gpt-5-nano` by default. Deterministic fake providers remain
available only for automated tests.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
python -m app.scripts.seed_manager

# Ingest sample approved documents for RAG
python -m app.scripts.ingest_document ../../docs/source-material/building-hours.md --approve
python -m app.scripts.ingest_document ../../docs/source-material/aircon-policy.md --approve
python -m app.scripts.ingest_document ../../docs/source-material/emergency-contacts.md --approve

uvicorn app.main:app --reload --port 8000
```

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
- `GET /api/v1/knowledge/documents`
- `POST /api/v1/knowledge/documents`
- `PATCH /api/v1/knowledge/documents/{id}/approval`
- `DELETE /api/v1/knowledge/documents/{id}`
- `POST /api/v1/knowledge/search`

- `GET /api/v1/prompts`
- `GET /api/v1/prompts/{agent_name}`
- `PATCH /api/v1/prompts/{agent_name}`
- `POST /api/v1/prompts/{agent_name}/reset`
- `POST /api/v1/prompts/{agent_name}/test`

## Prompt management and governance

System prompts for each of the 8 bounded workflow agents are configured with defaults and dynamic overrides:
- **Factory defaults**: stored as versioned YAML files on disk under `app/prompts/<agent_name>/v1.yaml`.
- **Database persistence**: runtime prompt customizations are persisted in the `agent_prompts` table with version notes.
- **Dynamic resolution**: workflow agents load active prompt overrides at request time with automatic fallback to `v1.yaml`.
- **Live playground**: prompts can be evaluated against sample payloads with execution latency and schema validation via `POST /api/v1/prompts/{agent_name}/test`.

## OpenAI configuration


Set `LLM_API_KEY` in the repository-level `.env` file. The default production-like configuration
uses `LLM_PROVIDER=openai`, `LLM_BASE_URL=https://api.openai.com/v1`, and `gpt-5-nano` for both
classification and response generation. `LLM_REASONING_EFFORT=minimal` keeps reasoning cost and
latency low. Never commit the `.env` file.

The OpenAI provider uses the Responses API with strict JSON-schema output. OpenRouter and Gemini
remain available through the OpenAI-compatible Chat Completions adapter by changing environment
variables only.


