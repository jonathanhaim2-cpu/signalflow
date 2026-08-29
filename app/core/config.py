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
    BASE_URL: str = "http://localhost:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
