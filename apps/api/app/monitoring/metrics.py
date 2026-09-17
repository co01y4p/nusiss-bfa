from collections.abc import Sequence

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

DEFAULT_DURATION_BUCKETS: Sequence[float] = (
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    20.0,
    30.0,
)

HTTP_DURATION_BUCKETS: Sequence[float] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

# Agent metrics
AGENT_RUNS_TOTAL = Counter(
    "agent_runs_total",
    "Total invocations of agents by agent name and status",
    labelnames=["agent", "status"],
)

AGENT_DURATION_SECONDS = Histogram(
    "agent_duration_seconds",
    "Execution duration of agents in seconds",
    labelnames=["agent"],
    buckets=DEFAULT_DURATION_BUCKETS,
)

AGENT_RETRIES_TOTAL = Counter(
    "agent_retries_total",
    "Total retries triggered for agents by agent name and reason",
    labelnames=["agent", "reason"],
)

# LLM metrics
LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total tokens consumed across LLM providers and models",
    labelnames=["provider", "model", "type"],
)

LLM_SCHEMA_VALIDATION_FAILURES_TOTAL = Counter(
    "llm_schema_validation_failures_total",
    "Total schema validation failures returned from LLM by agent",
    labelnames=["agent"],
)

# Tool metrics
TOOL_INVOCATIONS_TOTAL = Counter(
    "tool_invocations_total",
    "Total tool invocations by tool name and execution status",
    labelnames=["tool", "status"],
)

# Workflow metrics
WORKFLOW_RUNS_TOTAL = Counter(
    "workflow_runs_total",
    "Total workflow executions partitioned by final outcome",
    labelnames=["outcome"],
)

# HTTP metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests received by API",
    labelnames=["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request processing duration in seconds",
    labelnames=["method", "path"],
    buckets=HTTP_DURATION_BUCKETS,
)


def record_agent_run(agent: str, status: str, duration_seconds: float | None = None) -> None:
    AGENT_RUNS_TOTAL.labels(agent=agent, status=status).inc()
    if duration_seconds is not None and duration_seconds >= 0:
        AGENT_DURATION_SECONDS.labels(agent=agent).observe(duration_seconds)


def record_agent_retry(agent: str, reason: str, count: int = 1) -> None:
    if count > 0:
        AGENT_RETRIES_TOTAL.labels(agent=agent, reason=reason).inc(count)


def record_llm_tokens(
    *,
    provider: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> None:
    if prompt_tokens > 0:
        LLM_TOKENS_TOTAL.labels(provider=provider, model=model, type="prompt").inc(prompt_tokens)
    if completion_tokens > 0:
        LLM_TOKENS_TOTAL.labels(provider=provider, model=model, type="completion").inc(
            completion_tokens
        )


def record_schema_validation_failure(agent: str) -> None:
    LLM_SCHEMA_VALIDATION_FAILURES_TOTAL.labels(agent=agent).inc()


def record_tool_invocation(tool: str, status: str) -> None:
    TOOL_INVOCATIONS_TOTAL.labels(tool=tool, status=status).inc()


def record_workflow_run(outcome: str) -> None:
    WORKFLOW_RUNS_TOTAL.labels(outcome=outcome).inc()


def record_http_request(
    *, method: str, path: str, status_code: int, duration_seconds: float
) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=str(status_code)).inc()
    if duration_seconds >= 0:
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_seconds)


def generate_metrics_exposition(registry: CollectorRegistry = REGISTRY) -> tuple[bytes, str]:
    return generate_latest(registry), CONTENT_TYPE_LATEST
