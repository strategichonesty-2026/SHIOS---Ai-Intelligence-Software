"""Environment-based configuration for SHIOS.

Every tunable lives here. Nothing else in the codebase reads os.environ directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_prefix=""
    )

    # --- Core -------------------------------------------------------------
    app_name: str = "SHIOS"
    app_version: str = "1.0.0"
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")

    # --- Data layer -------------------------------------------------------
    # SQLite is supported for tests/local demo; PostgreSQL + pgvector for real deployments.
    database_url: str = Field(default="sqlite+pysqlite:///./shios.db")
    db_echo: bool = False
    embedding_dim: int = 384

    # --- Event transport --------------------------------------------------
    redis_url: str | None = Field(default=None)
    event_channel: str = "shios.events"

    # --- Security ---------------------------------------------------------
    api_key: str | None = Field(default=None, description="If set, all /api/v1 calls require x-api-key")
    cors_origins: str = "http://localhost:3000"

    # --- AI providers -----------------------------------------------------
    # 'rule' is the default deterministic provider: zero external calls, fully offline.
    llm_provider: str = Field(default="rule")  # rule | anthropic | openai | google
    llm_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    google_api_key: str | None = None
    llm_timeout_seconds: float = 45.0

    # --- Collection sources ----------------------------------------------
    enabled_sources: str = "sample_jobs,rss,github"
    rss_feeds: str = "https://hnrss.org/frontpage"
    github_topics: str = "agile,project-management,llm"
    github_token: str | None = None
    gmail_credentials_json: str | None = None
    gmail_query: str = "from:jobalerts-noreply@linkedin.com newer_than:7d"

    # --- Source retry / resilience ----------------------------------------
    source_max_retries: int = Field(default=3, description="Max attempts per source before giving up")
    source_backoff_seconds: float = Field(default=5.0, description="Base wait between retries (exponential)")
    source_timeout_seconds: float = Field(default=20.0, description="HTTP timeout per source request")

    # --- Governance -------------------------------------------------------
    min_evidence_per_recommendation: int = 2
    max_prediction_review_days: int = 90
    min_confidence: float = 0.05
    max_confidence: float = 0.95
    min_periods_for_prediction: int = 3

    # --- Scheduler --------------------------------------------------------
    scheduler_enabled: bool = False
    collect_interval_minutes: int = 360
    analyze_interval_minutes: int = 720

    @property
    def source_list(self) -> list[str]:
        return [s.strip() for s in self.enabled_sources.split(",") if s.strip()]

    @property
    def rss_feed_list(self) -> list[str]:
        return [s.strip() for s in self.rss_feeds.split(",") if s.strip()]

    @property
    def github_topic_list(self) -> list[str]:
        return [s.strip() for s in self.github_topics.split(",") if s.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]

    @property
    def is_postgres(self) -> bool:
        return self.database_url.startswith("postgres")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
