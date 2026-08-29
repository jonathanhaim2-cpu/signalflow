from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str = "dev-secret-key-change-me"
    DATABASE_URL: str = "sqlite+aiosqlite:///./signalflow.db"
    TELEGRAM_DEFAULT_BOT_TOKEN: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    ALGORITHM: str = "HS256"
    ENVIRONMENT: str = "development"
    # Legacy fallback. Prefer APP_BASE_URL; otherwise the public host is taken from the request.
    BASE_URL: str = "http://localhost:8000"
    APP_BASE_URL: str = ""
    ALLOW_PRO_EMAILS: str = ""
    # Comma-separated owner emails. jonathanhaim2@gmail.com is always treated as owner.
    ADMIN_EMAILS: str = "jonathanhaim2@gmail.com"
    # PayPlus (Israeli clearing). Never commit live keys.
    PAYPLUS_API_KEY: str = ""
    PAYPLUS_SECRET_KEY: str = ""
    PAYPLUS_PAYMENT_PAGE_UID: str = ""
    PAYPLUS_TERMINAL_UID: str = ""
    PAYPLUS_USE_STAGING: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
