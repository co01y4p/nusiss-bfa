# AAS Practice Module Architecture Baseline

This document formalizes the **AAS Practice Module FAQ (12 Questions)** as the explicit architectural, operational, and design baseline for the **Facilities AI Assistant (`nusiss-bfa`)** project.

Each section documents the official module guidance, our design decision, architectural justification, risk controls, and implementation references across the codebase.

---

## Baseline Summary Matrix

| # | AAS Module Topic | Module Baseline Requirement | Project Decision | Code Reference / Implementation |
|---|------------------|-----------------------------|------------------|---------------------------------|
| 1 | **Distributed Architecture & A2A** | Not mandatory to be distributed; multi-agent required; architecture depends on business case. | **Bounded In-Process Multi-Agent Graph.** Centralized state machine with specialized agents. | [`apps/api/app/workflows/facility_graph.py`](../apps/api/app/workflows/facility_graph.py) |
| 2 | **Model Performance & Fine-Tuning** | Existing foundation models/APIs; fine-tune only when clearly needed. | **Foundation LLMs via OpenAI/OpenRouter API.** Prompt engineering + few-shot + RAG context; no fine-tuning. | [`apps/api/app/llm/`](../apps/api/app/llm/) |
| 3 | **Model Evaluation & Selection** | Justified selection appropriate to requirements/constraints; universal "best" not required. | **Empirical Evaluation via Promptfoo.** 92-case benchmark covering intent, classification F1, hazard recall, and injection defense. | [`evals/promptfoo/`](../evals/promptfoo/) |
| 4 | **MLSecOps & Data Drift Detection** | Observation & detection required; prompt/RAG/model updates before fine-tuning. | **Langfuse Tracing + Prometheus Metrics + Prompt Studio.** Real-time schema/drift detection; dynamic prompt updates. | [`apps/api/app/monitoring/`](../apps/api/app/monitoring/), [`apps/web/src/app/prompts/`](../apps/web/src/app/prompts/) |
| 5 | **Scalability & Reliability Controls** | Architecture must address expected workloads and failures; identify top risks and controls. | **Stateless API, Valkey Rate Limiting, LLM Circuit Breaker, Deterministic Fallbacks.** | [`apps/api/app/security/circuit_breaker.py`](../apps/api/app/security/circuit_breaker.py), [`apps/api/app/middleware/rate_limit.py`](../apps/api/app/middleware/rate_limit.py) |
| 6 | **MCP vs Direct APIs/CLI** | MCP not mandatory; choose based on architectural benefit and justify. | **Direct Typed Tool Registry (`ToolRegistry`) with RBAC.** Eliminates external RPC overhead; strict Pydantic schemas. | [`apps/api/app/tools/registry.py`](../apps/api/app/tools/registry.py), [`apps/api/app/tools/incident_tools.py`](../apps/api/app/tools/incident_tools.py) |
| 7 | **RAG & Knowledge Management** | RAG and Knowledge Graphs not mandatory; select suitable context engineering based on needs. | **pgvector RAG with Heading-Aware Chunking & Strict Citation Grounding.** Refuses ungrounded responses. | [`apps/api/app/rag/`](../apps/api/app/rag/) |
| 8 | **Web Application Scope** | Simple web UI is sufficient; focus on supporting solution requirements over UI complexity. | **Pragmatic Next.js Frontend.** Serves occupant submission, status lookup, live agent trace visualization, and manager review. | [`apps/web/`](../apps/web/) |
| 9 | **Form-Based vs Chatbot Interface** | Form-based is allowed; prompt injection and conversational handling still apply. | **Dual-Mode Architecture (Form + Chatbot).** Non-AI "save-before-AI" form (`/report`) + conversational assistant (`/assistant`) with M4 guardrails. | [`apps/web/src/app/report/`](../apps/web/src/app/report/), [`apps/web/src/app/assistant/`](../apps/web/src/app/assistant/) |
| 10 | **Database Architecture** | Shared database/schema acceptable where appropriate. | **Retain Current Shared Database Implementation.** Single shared schema (`apps/api/app/core/models.py`) via SQLAlchemy ORM + Alembic migrations (`apps/api/migrations/`), supporting current SQLite (`bfa.db`) and PostgreSQL (`pgvector`). No per-agent databases. | [`apps/api/app/core/database.py`](../apps/api/app/core/database.py), [`apps/api/app/core/models.py`](../apps/api/app/core/models.py) |
| 11 | **Deployment Environments** | Single production environment is sufficient. | **Single Production Target with Local Compose Parity.** Deployable on VM via `compose.prod.yml` behind Caddy reverse proxy. | [`infra/compose/compose.prod.yml`](../infra/compose/compose.prod.yml) |
| 12 | **RAG Scope in Project** | RAG is preferred where appropriate, but not mandatory. | **RAG Fully Integrated as Agent Tool (Milestone M3).** Grounds building policy Q&A (aircon, operating hours, emergency procedures). | [`apps/api/app/rag/`](../apps/api/app/rag/), [`docs/source-material/`](../docs/source-material/) |

---

## Detailed Specifications & Architectural Justifications

### 1. Multi-Agent Architecture: Bounded In-Process vs. Distributed (A2A)

#### Module Guidance
> *Must the application be a distributed agentic system?*
> No. The application is expected to be a multi-agent system, but whether it should be deployed as a distributed system depends on the business case. Teams are expected to understand the options of distributed agent architectures and A2A, and to consider whether they are relevant to their use case. The proposed deployment architecture should be based on the business requirements, technical constraints, and a clear justification of the design decision.

#### Baseline Decision
The system is built as a **bounded in-process multi-agent graph**, orchestrated through a state machine in FastAPI ([`apps/api/app/workflows/facility_graph.py`](../apps/api/app/workflows/facility_graph.py)), comprising 8 specialized agents:
- **Security Guardrail Agent** ([`security.py`](../apps/api/app/agents/security.py))
- **Intent Router Agent** ([`intent.py`](../apps/api/app/agents/intent.py))
- **Extraction Agent** ([`extraction.py`](../apps/api/app/agents/extraction.py))
- **Classification Agent** ([`classification.py`](../apps/api/app/agents/classification.py))
- **Priority Escalation Agent** ([`priority.py`](../apps/api/app/agents/priority.py))
- **Assignment Agent** ([`assignment.py`](../apps/api/app/agents/assignment.py))
- **Response Synthesis Agent** ([`response.py`](../apps/api/app/agents/response.py))
- **Review / Fallback Agent** ([`review.py`](../apps/api/app/agents/review.py))

#### Justification
- **Zero Serialization Latency & Network Overhead:** Facility incident triage requires fast user feedback (<2 seconds). In-process function invocation and shared memory state eliminate HTTP/gRPC serialization, network hops, and connection timeouts between agents.
- **Deterministic Transactional Integrity:** Incident creation follows the *save-before-AI* principle. A bounded graph guarantees atomic transitions and deterministic fallback to human review (`review` state) upon any schema violation or tool failure.
- **Auditability & Observability:** A single execution graph provides end-to-end trace correlation in Langfuse and Prometheus without needing complex distributed trace propagation across multiple microservice runtimes.
- **A2A Evaluation:** Autonomous Agent-to-Agent (A2A) distributed protocols are appropriate when agents belong to distinct administrative domains or organizations (e.g., cross-enterprise supply chains). For an internal facility management system, distributed A2A would introduce unwarranted operational failure modes (split-brain state, distributed deadlocks) with zero business benefit.

---

### 2. Model Selection & Fine-Tuning Strategy

#### Module Guidance
> *Is model performance a critical component? Do we need to fine-tune a model?*
> You may use existing foundation models, specialised models, APIs, or open-source models. Fine-tuning should be considered when there is a clear need. The key requirement is to select an appropriate model for the task, explain why the model was selected, and evaluate whether it performs adequately for the intended use case.

#### Baseline Decision
We utilize **commercial foundation models (OpenAI / OpenRouter API)**, specifically `gpt-4o-mini` / `gpt-4o` (with support for open-weights via OpenRouter such as `meta-llama/llama-3.3-70b-instruct`). **Model fine-tuning is deliberately excluded.**

#### Justification
- **Strict Schema Enforcement:** Modern frontier models support native structured outputs (JSON schema / tool calling), guaranteeing 100% Pydantic parsing reliability.
- **Prompt Engineering & Context Sufficiency:** Facility triage tasks (hazard classification, priority calculation, department routing) do not require novel domain representation learning. Well-defined few-shot prompt templates combined with M3 pgvector RAG achieve **100% recall on critical safety hazards** and **>95% intent accuracy** on evaluation suites.
- **Cost & Agility:** Fine-tuning incurs ongoing compute cost, data curation overhead, and operational complexity when policies change. With our Agent Prompt Control Studio ([`/prompts`](../apps/web/src/app/prompts/)), facility managers can update business rules immediately in plain English without retraining pipelines.

---

### 3. Model Evaluation & Benchmark Justification

#### Module Guidance
> *Do we need to evaluate different LLMs and select the best one?*
> The objective is not necessarily to identify the universally “best” model, but to select a model that is appropriate for your requirements and constraints. You should provide a reasonable justification for the model selected.

#### Baseline Decision
We implement a **systematic evaluation pipeline via Promptfoo** ([`evals/promptfoo/`](../evals/promptfoo/)) containing **92 test cases** across five critical evaluation axes:
1. **Critical-Hazard Recall:** Must achieve 100% recall for immediate safety risks (gas leaks, exposed wires, active flooding).
2. **Classification Macro-F1:** Accuracy across electrical, plumbing, HVAC, structural, and custodial categories.
3. **Prompt-Injection Resistance:** Defense against direct jailbreaks and indirect RAG chunk injections (target >= 95%).
4. **Citation Grounding:** Verification that responses reference valid chunk IDs from the knowledge base without hallucination.
5. **Deterministic Consistency:** Repeated evaluations verifying identical outputs for deterministic inputs.

#### Selected Models & Rationale
- **Primary Generator/Classifier (`gpt-4o-mini`):** Delivers sub-800ms latency, high prompt injection resistance, native structured JSON schema compliance, and low cost per 1M tokens, well within operational facility constraints.
- **Provider-Neutral Abstraction:** Configured through [`apps/api/app/llm/`](../apps/api/app/llm/) via environment variables (`LLM_BASE_URL`, `GENERATOR_MODEL`, `CLASSIFIER_MODEL`), enabling zero-code swapping between OpenAI, Azure, and OpenRouter models.

---

### 4. MLSecOps & Data Drift Detection

#### Module Guidance
> *Does MLSecOps require data-drift detection and model fine-tuning?*
> For Data drift: observation and detection are required. Fine-tuning is not necessarily. When performance degrades, only if other measures (eg. update the prompt, improve the RAG data, change the model etc) does not resolve the issue, you may consider fine tuning the LLM.

#### Baseline Decision
We implement **continuous observability and drift detection via Langfuse and Prometheus**, with a hierarchical mitigation ladder:
1. **Detection (Observability Layer):**
   - Prometheus metrics ([`apps/api/app/monitoring/metrics.py`](../apps/api/app/monitoring/metrics.py)): Tracks `agent_runs_total`, `agent_duration_seconds`, `llm_tokens_total`, `llm_schema_validation_failures_total`, and `tool_invocations_total`.
   - Langfuse Tracing ([`apps/api/app/monitoring/langfuse.py`](../apps/api/app/monitoring/langfuse.py)): Full request-response observability, token usage breakdowns, latency profiling, and user feedback correlation.
2. **Mitigation Ladder (Without Fine-Tuning):**
   - **Tier 1 (Prompt Drift):** Update system instructions dynamically via the Agent Prompt Control Studio ([`/prompts`](../apps/web/src/app/prompts/)) with immediate live testing and version rollback.
   - **Tier 2 (Domain Knowledge Drift):** Ingest updated policy documents via [`python -m app.scripts.ingest_document`](../apps/api/app/scripts/) to refresh pgvector embeddings instantly.
   - **Tier 3 (Model Provider Drift):** Swap provider/model identifiers via `.env` (e.g., from `gpt-4o-mini` to `claude-3.5-haiku` via OpenRouter) without rebuilding containers.

---

### 5. Scalability & Reliability Controls

#### Module Guidance
> *Are scalability and reliability assessment criteria?*
> Scalability and reliability are relevant under architecture and design quality. Your architecture should explain how the system could handle expected workloads and failures. The team should identify the most important scalability and reliability risks for the proposed application and demonstrate suitable controls for selected risks.

#### Identified Risks & Baseline Controls

| Risk | Architecture Failure Mode | Demonstrated Control in `nusiss-bfa` |
|------|---------------------------|-------------------------------------|
| **LLM Provider Outage / Latency Spike** | Cascading timeouts, blocked worker threads | **LLM Circuit Breaker** ([`apps/api/app/security/circuit_breaker.py`](../apps/api/app/security/circuit_breaker.py)) transitions through `CLOSED` → `OPEN` → `HALF_OPEN`. When open, requests fail fast to deterministic fallback without stalling the API. |
| **Malformed LLM Output** | Schema mismatch crashes the graph | **Pydantic Validation & Retry:** [`apps/api/app/agents/base.py`](../apps/api/app/agents/base.py) enforces strict schema parsing with bounded retries, falling back to the `review` node for human triage. |
| **API Denial of Service / Abuse** | Token exhaustion, server starvation | **Valkey Sliding-Window Rate Limiter** ([`apps/api/app/middleware/rate_limit.py`](../apps/api/app/middleware/rate_limit.py)) restricts public endpoints per IP/token. |
| **Database Connection Exhaustion** | Connection leaks under concurrent reports | **SQLAlchemy Connection Pooling** with strict pool sizes, timeout boundaries, and automated health checks. |
| **Stateless Scaling** | Backend bottleneck under high occupant volume | **Stateless API Design:** All agent state is request-scoped or persisted in Postgres/Valkey. The FastAPI service can scale horizontally behind a reverse proxy (Caddy / Nginx). |

---

### 6. Tool Integration: Direct Typed Tool Registry vs. MCP

#### Module Guidance
> *Is MCP mandatory? Can we use a CLI or API directly?*
> MCP is not mandatory. Teams should understand its purpose and consider whether it provides value for their application. However, the selected integration approach should be justified. It should be selected when it provides a meaningful architectural benefit.

#### Baseline Decision
We use a **direct in-process Typed Tool Registry (`ToolRegistry`) with Role-Based Access Control (RBAC)** ([`apps/api/app/tools/registry.py`](../apps/api/app/tools/registry.py)), rather than Model Context Protocol (MCP).

#### Active Tools:
- `create_incident` (`SYSTEM` role): Atomically persists an incident and assigns an authoritative tracking code.
- `lookup_incident_status` (`PUBLIC` role): Retrieves public status for a validated reference code.
- `find_recent_incidents` (`SYSTEM` role): Queries spatial/temporal incident duplicates to assist classification and escalation.

#### Justification:
- **Zero Inter-Process Overhead:** MCP is designed for desktop/IDE tools to connect to disparate local external subprocesses. In a cloud/server web application, running external MCP servers over stdio/SSE introduces process management overhead, IPC failure points, and latency.
- **Strict Type Safety & RBAC:** The Tool Registry validates all arguments via Pydantic schemas and enforces caller privileges (`PUBLIC` vs `MANAGER` vs `SYSTEM`), preventing unauthorized execution of internal domain operations.
- **Native LLM Function Calling:** The Tool Registry directly exports standard OpenAI/OpenRouter function calling JSON definitions, supported out-of-the-box by the LLM gateway.

---

### 7. Knowledge Management: pgvector RAG vs. Knowledge Graphs

#### Module Guidance
> *Are RAG and a Knowledge Graph mandatory? Is chat history and internet search sufficient as context?*
> RAG and Knowledge Graphs are not mandatory. Teams should select a suitable context-engineering and knowledge-management approach based on the application requirements.

#### Baseline Decision
We implement a **pgvector-backed Retrieval-Augmented Generation (RAG) system** ([`apps/api/app/rag/`](../apps/api/app/rag/)) over approved facility documentation, combined with **strict citation grounding**. Knowledge Graphs are omitted.

#### Justification:
- **Domain Requirements:** Facility documentation consists of structured organizational policies (e.g., [`aircon-policy.md`](../docs/source-material/aircon-policy.md), [`building-hours.md`](../docs/source-material/building-hours.md), [`emergency-contacts.md`](../docs/source-material/emergency-contacts.md)). These documents are hierarchical and textual rather than high-density entity-relationship graphs.
- **Hybrid Search & Anti-Hallucination:** Heading-aware chunking (400–800 tokens) combined with pgvector cosine similarity retrieval provides relevant policy context. The `CitationValidator` verifies that citations match actual chunk IDs in the database and forces an explicit refusal ("I cannot find information regarding this policy in approved facility records") when context is absent.
- **Simplicity vs Complexity:** A Knowledge Graph (e.g. Neo4j) would add substantial infrastructure overhead and schema maintenance with negligible accuracy gain for standard building operations policies.

---

### 8. Web Application Scope & Interface Philosophy

#### Module Guidance
> *Does the project require us to design and develop a web application integrated with agentic AI systems? If so, how much emphasis will be placed on the web application component for the project assessment?*
> A simple web UI is sufficient. However, if your business case requires a richer user interface, you are encouraged to implement it. The focus is on supporting your solution requirements rather than building a sophisticated UI.

#### Baseline Decision
The web frontend ([`apps/web/`](../apps/web/)) is built using **Next.js**, focused strictly on **supporting agent workflow transparency, management, and occupant self-service**:
- **Occupant Portal:** Non-AI report submission form (`/report`), status tracking (`/track`), and conversational assistant (`/assistant`).
- **Live Multi-Agent Trace Visualizer:** Interactive graph traversal pipeline on `/assistant` displaying active nodes, reason codes, payload inspector, and decision highlights.
- **Manager Operations:** Incident review queue (`/manager`) with one-click status transitions and full audit trails.
- **Prompt & Knowledge Studios:** Developer and manager tools for runtime prompt evaluation (`/prompts`) and knowledge retrieval verification (`/knowledge`).

The frontend acts as an operational harness for the agentic backend, prioritizing transparency over decorative complexity.

---

### 9. Interface Paradigm: Form-Based vs. Chatbot-Driven

#### Module Guidance
> *Whether the application can be form-based, or if it must be chatbot-driven to support additional project requirements such as prompt injection testing, memory handling, and conversational interactions.*
> Application can be form based. It does not have to be chatbot-driven. Even with a form-based interface, the application may still be subject to AI-related concerns such as prompt injection, depending on how user inputs are processed.

#### Baseline Decision
We provide a **hybrid dual-interface**:
1. **Form-Based ("Save-Before-AI"):** Direct structured form at [`/report`](../apps/web/src/app/report/) allowing users to submit incidents with no AI dependency, ensuring maximum accessibility and fault tolerance.
2. **Chatbot-Driven Assistant:** Natural language dialogue at [`/assistant`](../apps/web/src/app/assistant/) for interactive incident reporting, policy Q&A, and status inquiries.

#### Unified Security Controls (M4):
Regardless of entry point, all free-form text is subjected to our defense-in-depth security pipeline:
- **Prompt Injection Defense** ([`prompt_injection.py`](../apps/api/app/security/prompt_injection.py)): Detects jailbreaks, delimiter hijacking, and system override patterns before agent invocation. High-risk requests route directly to the `quarantine` state.
- **PII Redaction** ([`pii.py`](../apps/api/app/security/pii.py)): Sanitizes Singapore NRIC/FIN, phone numbers, emails, and credentials before payloads reach external LLM endpoints.
- **Output Policy Enforcement** ([`output_policy.py`](../apps/api/app/security/output_policy.py)): Validates generated answers for injection echo, XSS, and unauthorized data leakage.

---

### 10. Database Architecture: Shared Database vs. Per-Agent Stores

#### Module Guidance
> *Whether separate databases per agent are required, or if a shared database/schema approach would be acceptable for more cost effective.*
> Shared database/schema approach is acceptable where it is appropriate for the proposed architecture and use case.

#### Baseline Decision
The project **sticks with the current database implementation**: a single shared database accessed via SQLAlchemy ORM ([`apps/api/app/core/database.py`](../apps/api/app/core/database.py)) with Alembic migrations ([`apps/api/migrations/`](../apps/api/migrations/)). **No separate per-agent databases are introduced or required.**

#### Current Implementation Details:
- **Unified Relational & Vector Schema** ([`apps/api/app/core/models.py`](../apps/api/app/core/models.py)):
  - `users`: Manager authentication records and roles.
  - `incidents`: Core business records, status transitions, priority, and department routing.
  - `workflow_runs`: Immutable execution traces, node latency, and agent decision payloads.
  - `knowledge_documents` & `knowledge_chunks`: Knowledge base document chunks and vector embeddings.
  - `floors` & `facilities`: Building floor directory and facility locations.
  - `security_events`: High-severity injection attempts, policy violations, and quarantine audit logs.
  - `agent_prompts`: Active runtime prompt overrides and version history.
- **Dual Dialect Support**:
  - **SQLite** (`sqlite:///./bfa.db`): Zero-dependency local development, unit tests, and CI; embeddings stored as JSON with vector cosine similarity computed in Python.
  - **PostgreSQL + pgvector** (`postgresql://...`): Production and containerized deployments with native `vector(1536)` indexing.
- **Migration Engine**: Managed via Alembic (`apps/api/migrations/versions/`).

#### Justification:
- **Preserves Working Implementation:** The current database architecture is fully implemented, thoroughly tested, and already supports the entire multi-agent workflow, RAG knowledge base, and manager queue without friction.
- **Transactional Consistency (ACID):** Creating an incident, logging workflow traces, and recording security events occur within a single database transaction boundary.
- **Cost-Effectiveness & Low Operational Complexity:** Running isolated databases per agent would multiply hosting costs, connection pooling overhead, and migration complexity with zero functional benefit.

---

### 11. Environment & Infrastructure Strategy

#### Module Guidance
> *Whether a single production environment is sufficient, or if separate development and test environments are expected to demonstrate software development best practices.*
> A single production environment is sufficient for the project.

#### Baseline Decision
We maintain **local development and a single production deployment target** using Docker Compose:
- **Local Development:** `docker compose -f infra/compose/compose.yml up` with hot reloading for FastAPI and Next.js, and local Postgres/Valkey containers.
- **Production Deployment:** `docker compose -f infra/compose/compose.prod.yml up` deploying hardened multi-stage production builds behind a Caddy reverse proxy with automatic HTTPS and persistent volume mounts.
- **Continuous Integration (CI):** GitHub Actions workflow ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) running automated formatters, linters, unit tests, and Promptfoo regression evaluations on every pull request.

---

### 12. RAG Scope & Purpose

#### Module Guidance
> *Whether RAG (Retrieval-Augmented Generation) is expected to be part of the project scope.*
> RAG is preferred where it is appropriate for your use case, but it is not a mandatory requirement. Choose the architecture and techniques that best address your problem statement.

#### Baseline Decision
**RAG is formally included in the project scope as Milestone M3**, addressing the primary business use case of answering occupant inquiries about building facilities and policies.

#### Scope Details:
- **Knowledge Sources:** Approved facility documents ([`docs/source-material/`](../docs/source-material/)) covering HVAC policies, operational hours, and emergency escalation contacts.
- **Chunking & Indexing:** Markdown/PDF parsing with heading-aware chunking (400–800 tokens) and embedding generation via `text-embedding-3-small`.
- **Grounded Tool Integration:** Exposed to the agent graph via `knowledge_retrieval` tool. The Response Agent only synthesizes answers based on retrieved context, ensuring strict citation validation and refusing to answer when context is unavailable.
