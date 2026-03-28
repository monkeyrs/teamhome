import json
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    PROJECT_NAME: str = "TeamHome"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+psycopg2://admin:admin@db:5432/teamhome"
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALG: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 60 * 24 * 7
    CORS_ALLOW_ORIGINS: list[str] = ["*"]
    ALLOW_INSECURE_DEV_AUTH: bool = True
    ENABLE_DEBUG_ENDPOINTS: bool | None = None
    DEMO_SEED_MODE: str | None = None
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024
    ALLOWED_AUDIO_EXTENSIONS: list[str] = [".wav", ".mp3", ".m4a", ".aac", ".ogg", ".webm", ".mp4"]
    ALLOWED_AUDIO_CONTENT_TYPES: list[str] = [
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/mp4",
        "audio/aac",
        "audio/ogg",
        "audio/webm",
        "video/webm",
        "application/octet-stream",
    ]

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
    ASSISTANT_ENGINE: str = "legacy"
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_ENDPOINT: str | None = "https://api.smith.langchain.com"
    LANGSMITH_PROJECT: str | None = "teamhome-assistant"
    LANGSMITH_WORKSPACE_ID: str | None = None
    LANGGRAPH_API_URL: str | None = None
    LANGGRAPH_ASSISTANT_ID: str = "assistant_orchestrator"
    LANGGRAPH_REQUEST_TIMEOUT_SECONDS: float = 45.0

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def normalize_environment(cls, value: str | None) -> str:
        return (value or "development").strip().lower()

    @field_validator("DEMO_SEED_MODE", mode="before")
    @classmethod
    def normalize_demo_seed_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip().lower()
        if not normalized:
            return None
        if normalized not in {"auto", "manual", "off"}:
            raise ValueError("DEMO_SEED_MODE must be one of: auto, manual, off")
        return normalized

    @field_validator("CORS_ALLOW_ORIGINS", "ALLOWED_AUDIO_EXTENSIONS", "ALLOWED_AUDIO_CONTENT_TYPES", mode="before")
    @classmethod
    def parse_list_settings(cls, value):
        if value is None:
            return value
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return []
            if normalized.startswith("["):
                parsed = json.loads(normalized)
                if isinstance(parsed, list):
                    return parsed
                return []
            return [item.strip() for item in normalized.split(",") if item.strip()]
        return value

    @field_validator("ALLOWED_AUDIO_EXTENSIONS")
    @classmethod
    def normalize_audio_extensions(cls, value: list[str]) -> list[str]:
        normalized = []
        for item in value:
            token = str(item or "").strip().lower()
            if not token:
                continue
            normalized.append(token if token.startswith(".") else f".{token}")
        return normalized

    @field_validator("ALLOWED_AUDIO_CONTENT_TYPES")
    @classmethod
    def normalize_audio_content_types(cls, value: list[str]) -> list[str]:
        return [str(item or "").strip().lower() for item in value if str(item or "").strip()]

    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    def debug_endpoints_enabled(self) -> bool:
        if self.ENABLE_DEBUG_ENDPOINTS is not None:
            return self.ENABLE_DEBUG_ENDPOINTS
        return not self.is_production()

    def demo_seed_auto_enabled(self) -> bool:
        if self.DEMO_SEED_MODE is not None:
            return self.DEMO_SEED_MODE == "auto"
        return True

    def uses_default_database_credentials(self) -> bool:
        parsed = urlsplit(self.DATABASE_URL)
        username = parsed.username or ""
        password = parsed.password or ""
        return username == "admin" and password == "admin"

    def validate_runtime_security(self) -> list[str]:
        issues: list[str] = []

        if self.is_production():
            if self.uses_default_database_credentials():
                issues.append("DATABASE_URL must not use default admin/admin credentials in production.")
            if self.JWT_SECRET == "dev-secret-change-me" or len(self.JWT_SECRET) < 32:
                issues.append("JWT_SECRET must be set to a strong non-default value of at least 32 characters in production.")
            if "*" in self.CORS_ALLOW_ORIGINS:
                issues.append("CORS_ALLOW_ORIGINS must not contain '*' in production.")
            if not (self.WECHAT_APPID and self.WECHAT_SECRET):
                issues.append("WECHAT_APPID and WECHAT_SECRET are required in production.")
            if self.ALLOW_INSECURE_DEV_AUTH:
                issues.append("ALLOW_INSECURE_DEV_AUTH must be false in production.")
            if self.debug_endpoints_enabled():
                issues.append("ENABLE_DEBUG_ENDPOINTS must be disabled in production.")

        if self.MAX_UPLOAD_BYTES <= 0:
            issues.append("MAX_UPLOAD_BYTES must be greater than 0.")

        return issues


@lru_cache
def get_settings() -> Settings:
    return Settings()
