"""Typed application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by the API and worker processes."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="MCP_AUDIT_",
        extra="ignore",
    )

    app_name: str = "MCP Audit"
    environment: str = "development"
    debug: bool = False
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/mcp_audit"
    )
    redis_broker_url: str = "redis://localhost:6379/0"
    redis_result_url: str = "redis://localhost:6379/1"
    timezone: str = "Asia/Shanghai"
    task_time_limit_seconds: int = 900
    clone_timeout_seconds: int = 180
    task_retry_delay_seconds: int = 15


def get_settings() -> Settings:
    """Return the process-local cached settings instance."""

    return Settings.settings_cached()


settings = get_settings()

