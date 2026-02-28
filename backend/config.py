"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    DB_HOST: str = "192.168.224.171"
    DB_PORT: int = 3326
    DB_USER: str = "root"
    DB_PASSWORD: str = "unionman#2025"
    DB_NAME: str = "fund_tracker"

    # App
    APP_ENV: str = "development"
    APP_PORT: int = 8000

    # NAV Fetch
    NAV_FETCH_CONCURRENCY: int = 5
    NAV_FETCH_INTERVAL: float = 0.5

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )

    @property
    def ASYNC_DATABASE_URL(self) -> str:
        return self.DATABASE_URL

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
