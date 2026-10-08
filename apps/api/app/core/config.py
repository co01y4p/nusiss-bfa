from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AGENT_NAMES = (
    "security",
    "intent",
    "extraction",
    "classification",
    "priority",
    "assignment",
    "response",
    "review",
)
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high")


def parse_reasoning_effort_overrides(value: str) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for item in value.split(","):
        if not item.strip():
            continue
        agent, separator, effort = (part.strip().lower() for part in item.partition("="))
        if not separator or agent not in AGENT_NAMES or effort not in REASONING_EFFORTS:
            raise ValueError(
                f"Invalid LLM_REASONING_EFFORT_OVERRIDES entry {item.strip()!r}: use "
                f"agent=effort with agent in {', '.join(AGENT_NAMES)} and effort in "
                f"{', '.join(REASONING_EFFORTS)}"
            )
        overrides[agent] = effort
    return overrides


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../../.env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "Facilities AI Assistant"
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "sqlite:///./bfa.db"
    valkey_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "development-only-secret-change-before-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:3000"

    llm_provider: str = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    classifier_model: str = "gpt-5-nano"
    generator_model: str = "gpt-5-nano"
    llm_reasoning_effort: str = "minimal"
    llm_max_output_tokens: int = 1024
    # Per-agent overrides of LLM_REASONING_EFFORT, as "agent=effort,agent=effort",
    # e.g. "security=low,intent=low,priority=low". Agents not listed use the default.
    llm_reasoning_effort_overrides: str = ""
    # Per-HTTP-attempt timeout. Kept well below agent_timeout_seconds so a stalled
    # provider request is retried inside the agent budget instead of consuming it.
    llm_attempt_timeout_seconds: float = 12.0
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.25
    incident_similarity_threshold: float = 0.75

    max_agent_steps: int = 16
    max_model_calls: int = 10
    max_input_chars: int = 8000
    agent_timeout_seconds: float = 30.0
    workflow_timeout_seconds: float = 120.0

    rate_limit_enabled: bool = True
    # "valkey" shares limits across API processes and falls back to memory if Valkey is down.
    rate_limit_backend: Literal["valkey", "memory"] = "valkey"
    # Comma-separated IPs/CIDRs of reverse proxies allowed to set X-Forwarded-For.
    trusted_proxy_ips: str = ""
    rate_limit_requests_per_minute: int = 60
    rate_limit_window_seconds: int = 60
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_recovery_seconds: float = 30.0
    redact_pii_in_llm_prompts: bool = True

    evaluation_enabled: bool = False
    evaluation_key: str = ""

    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_sample_rate: float = 1.0
    langfuse_debug: bool = False

    @field_validator("llm_reasoning_effort_overrides")
    @classmethod
    def _validate_effort_overrides(cls, value: str) -> str:
        parse_reasoning_effort_overrides(value)
        return value

    def reasoning_effort_for(self, agent_name: str) -> str | None:
        """Effort override for one agent, or None to use the provider default."""
        return parse_reasoning_effort_overrides(self.llm_reasoning_effort_overrides).get(agent_name)

    @property
    def trusted_proxy_networks(self) -> list[IPv4Network | IPv6Network]:
        return [
            ip_network(item.strip(), strict=False)
            for item in self.trusted_proxy_ips.split(",")
            if item.strip()
        ]

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
