from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수(.env). 값은 README 환경변수 표 참고."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
    core_jwks_url: str = "http://localhost:8080/api/assistant/.well-known/jwks.json"
    core_internal_base_url: str = "http://localhost:8080"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = ""
    host: str = "127.0.0.1"
    port: int = 8000

    token_issuer: str = "investfeed-core"
    token_audience: str = "assistant"
    jwks_cache_seconds: int = 3600
    core_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
