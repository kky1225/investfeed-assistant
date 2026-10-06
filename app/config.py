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

    # 5단계 Q&A (2026-09-30 확정)
    assistant_model: str = "claude-sonnet-5-5"
    assistant_effort: str = "low"  # 질문 해석(분류)만 하므로 low 부터
    assistant_max_tokens: int = 4096
    llm_timeout_seconds: float = 15.0
    chat_timeout_seconds: float = 20.0  # 턴 전체. 넘으면 끝난 카드만
    rate_per_minute: int = 10  # 회원별 LLM 호출
    monthly_cost_cap_usd: float = 30.0  # 서비스 전체 (API 키 1개)
    session_ttl_seconds: int = 1800  # 30분 무활동이면 세션 초기화
    history_token_budget: int = 4000  # 턴 이력 compact 발동 기준


@lru_cache
def get_settings() -> Settings:
    return Settings()
