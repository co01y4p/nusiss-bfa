# AAS Practice Module Baseline Agent Rules

These rules govern all autonomous agents, code generation, and architectural refactoring in the `nusiss-bfa` repository. They codify the 12 requirements from the AAS Practice Module FAQ into immutable engineering constraints.

See the complete architectural justification in [docs/aas-baseline.md](../../docs/aas-baseline.md).

---

## 1. Multi-Agent Graph (Bounded In-Process)
- Maintain an **in-process bounded graph architecture** (`apps/api/app/workflows/facility_graph.py`).
- Do NOT introduce uncoordinated distributed Agent-to-Agent (A2A) network topologies or microservice agent runtimes without explicit architectural approval.
- All agent interactions must proceed through typed Pydantic payloads and the central workflow state machine.

## 2. Foundation Models & No Fine-Tuning
- Rely on foundation LLMs (`gpt-4o-mini`, `gpt-4o`, or OpenRouter equivalents) accessed through the provider-neutral gateway (`apps/api/app/llm/`).
- Do NOT add fine-tuning pipelines or weights training scripts. Improve performance via structured prompt engineering, few-shot updates in `apps/api/app/prompts/`, or knowledge base additions in `apps/api/app/rag/`.

## 3. Evaluation-Driven Justification
- Any model change or critical prompt update must be validated against the 92-case Promptfoo suite (`evals/promptfoo/`).
- Enforce strict adherence to:
  - 100% critical hazard recall (gas leaks, exposed live wires, active floods).
  - >= 95% prompt injection resistance.
  - 100% JSON schema validity.

## 4. MLSecOps & Drift Detection
- Retain continuous metric collection (`prometheus-client`) and Langfuse tracing (`apps/api/app/monitoring/`).
- Address data or schema drift via prompt adjustments (`/prompts`), RAG document ingestion, or model configuration changes before considering fine-tuning.

## 5. Scalability & Reliability Controls
- Maintain stateless API design in FastAPI (`apps/api/app/`).
- All external LLM provider calls must pass through the LLM Circuit Breaker (`apps/api/app/security/circuit_breaker.py`).
- Public endpoints must remain protected by the sliding-window rate limiter (`apps/api/app/middleware/rate_limit.py`).
- Maintain bounded retries and deterministic fallback to the `review` queue node when agents fail.

## 6. Tool Integration & Model Context Protocol (MCP)
- Tools must be registered in the in-process `ToolRegistry` (`apps/api/app/tools/registry.py`) with strict Pydantic schemas and Role-Based Access Control (`PUBLIC`, `MANAGER`, `SYSTEM`).
- Do NOT replace in-process tool registry operations with external MCP processes unless an explicit requirement for external IDE/desktop tooling arises.

## 7. Context Engineering & RAG
- Use pgvector-backed retrieval over approved facility markdown/PDF documents in `docs/source-material/`.
- Maintain strict citation validation: any factual claim regarding facility policies must cite valid chunk IDs. Never allow the LLM to invent ungrounded answers; enforce refusal fallback.

## 8. Web Application Harness
- Maintain the Next.js frontend (`apps/web/`) as an operational harness for the agent workflow.
- Prioritize workflow transparency, live graph traversal visualization, incident management, and prompt/knowledge administration over complex decorative features.

## 9. Interface Modalities (Form + Chatbot)
- Preserve the non-AI form submission (`/report`) to guarantee the "save-before-AI" principle.
- All free-text inputs across both the form and chatbot (`/assistant`) must undergo M4 security filtering: prompt injection detection, PII redaction, and output policy validation.

## 10. Database Architecture (Stick with Current Implementation)
- Stick with the current database implementation: single shared schema (`apps/api/app/core/models.py`) accessed via SQLAlchemy ORM (`app/core/database.py`) and Alembic migrations (`apps/api/migrations/`).
- Preserve the existing dual-dialect support: SQLite (`bfa.db`) for lightweight local dev/testing and PostgreSQL (`pgvector`) for containerized production.
- Do NOT introduce separate per-agent databases, extra database engines, or schema partitioning.

## 11. Environment Parity
- Target a single production environment using Docker Compose (`infra/compose/compose.prod.yml`) behind Caddy reverse proxy, mirroring local development (`compose.yml`).
- Keep configuration differences strictly confined to `.env` / environment variables.

## 12. RAG Scope & Truth Grounding
- RAG is an active, first-class tool within Milestone M3. Keep knowledge documents synchronized with real building operations policies.
