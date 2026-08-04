# M3 — RAG knowledge base

[← back to overview](00-overview.md)

## Objective

Give the agent graph grounded retrieval: a pgvector-backed search over **approved** facility documents, feeding the `response` agent so it can cite sources instead of guessing. Framed as a *tool the agents use*, not a standalone search feature.

## Scope

Build:
- `knowledge_documents` + `knowledge_chunks` tables (Postgres + `pgvector` extension — already available via the `pgvector/pgvector` image from M0).
- Ingestion: PDF/Markdown/text → heading-aware chunking (~400–800 tokens, ~10–15% overlap) → embedding → stored with metadata (document version, effective date, access scope).
- Retriever: query embedding → vector + full-text search → filter by approval/effective-date/access scope → top-5 chunks.
- Citation validator: every response citing a chunk must reference a chunk ID that actually exists and actually supports the claim; if evidence is insufficient, the agent must say so explicitly rather than answer.
- Wire the retriever into the `incident_retrieval`/`faq_retrieval` graph nodes from M2 as a typed tool call, not a free-form function.

For ingestion, use a **CLI script**, not an admin UI — keeps this milestone's full-stack footprint minimal and in line with the agentic-AI focus. A document-approval UI is optional stretch, not required.

## Folders touched

```
apps/api/app/rag/ingestion.py, parsing.py, chunking.py, embeddings.py, retriever.py, citation_validator.py
apps/api/app/repositories/postgres/knowledge.py
apps/api/migrations/versions/000X_knowledge_tables.py
apps/api/app/scripts/ingest_document.py   # CLI: python -m app.scripts.ingest_document <file>
```

## Deployment artifact

None new — `pgvector` extension enabled via a migration (`CREATE EXTENSION IF NOT EXISTS vector;`) on the existing `postgres` service. No separate vector database, per the architecture decision in the original spec.

## Setup & run

```bash
cd apps/api
alembic revision --autogenerate -m "knowledge documents and chunks"
alembic upgrade head

# ingest an approved document
python -m app.scripts.ingest_document ./docs/source-material/building-hours.pdf --approve
```

Embeddings: use the same provider as the chat models (OpenAI/OpenRouter `text-embedding-3-small` or equivalent) — no extra local ML dependency needed, and it stays consistent with the M2 provider swap mechanism.

## Manual tasks (things only you can do)

- [ ] Supply the actual approved facility documents to ingest — operating hours, building access rules, emergency contacts, maintenance-team responsibilities, troubleshooting SOPs. This is real content only you (or your organization) has; I can't fabricate authoritative facility data.
- [ ] Decide which documents count as "approved" before running `--approve` on them.

## Exit criteria

- Asking the assistant a factual question covered by an ingested document returns an answer with a valid citation to that document.
- Asking something not covered returns the explicit "I do not have enough approved information" fallback — never a fabricated answer.
- A document you don't mark approved is never retrievable or cited.
