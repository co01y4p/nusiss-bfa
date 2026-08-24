# Facilities AI Assistant API

FastAPI backend for milestones M0 through M3. Includes bounded multi-agent workflow, pgvector-backed
RAG knowledge base, heading-aware chunking, hybrid search, and citation validation. The default `fake`
LLM provider is fully local and deterministic. It makes the workflow testable without an API key.

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

## Provider selection

Keep `LLM_PROVIDER=fake` for local development and automated tests. A future real-provider run can
set `LLM_PROVIDER=openai` or `LLM_PROVIDER=openrouter` together with `LLM_BASE_URL`, `LLM_API_KEY`,
`EMBEDDING_MODEL`, and chat model names. No agent or workflow code changes are required.


