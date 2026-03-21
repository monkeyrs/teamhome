from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    PROJECT_NAME: str = "TeamHome"
    VERSION: str = "0.1.0"
    DATABASE_URL: str = "postgresql+psycopg2://admin:admin@db:5432/teamhome"
    DB_AUTO_CREATE: bool = False
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALG: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 60 * 24 * 7
    CORS_ALLOW_ORIGINS: list[str] = ["*"]

    WECHAT_APPID: str | None = None
    WECHAT_SECRET: str | None = None

    LLM_PROVIDER: str | None = None
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None
    OPENAI_MODEL: str = "gpt-4.1-mini"
    OPENAI_AUDIO_MODEL: str = "gpt-4o-mini-transcribe"
    OPENAI_SSL_VERIFY: bool = True
    OPENAI_MODEL_FALLBACKS: str | None = None
    OPENAI_AUTO_SWITCH_MODELS: bool = True
    OPENAI_MODEL_MAX_ATTEMPTS: int = 6
    OPENROUTER_SITE_URL: str = "http://localhost"
    OPENROUTER_APP_NAME: str = "TeamHome"


@lru_cache
def get_settings() -> Settings:
    return Settings()
