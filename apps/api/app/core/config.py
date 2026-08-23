from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    llm_provider: str = "fake"
    llm_base_url: str = ""
    llm_api_key: str = ""
    classifier_model: str = "fake-classifier"
    generator_model: str = "fake-generator"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    rag_top_k: int = 5
    rag_similarity_threshold: float = 0.25

    max_agent_steps: int = 16
    max_model_calls: int = 10
    max_input_chars: int = 8000
    agent_timeout_seconds: float = 5.0
    workflow_timeout_seconds: float = 30.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
