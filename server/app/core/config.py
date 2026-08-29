"""Application configuration using Pydantic Settings."""

import logging
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("meetingmind.config")


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    # Project metadata
    PROJECT_NAME: str = "MeetingMind API"
    VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/meetingmind"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # AI API Keys
    DEEPGRAM_API_KEY: str = ""
    GEMINI_API_KEY: str = ""

    # Cloud Storage (S3 / Cloudflare R2)
    S3_ENDPOINT_URL: str | None = None
    S3_BUCKET_NAME: str = "meetingmind-uploads"
    S3_REGION: str = "us-east-1"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    STORAGE_DRIVER: str = "s3"  # "s3" or "local" / "mock"
    LOCAL_STORAGE_PATH: str = "storage_uploads"

    # JWT Authentication
    JWT_SECRET: str = "default_development_secret_key_meetingmind_at_least_32_chars_long"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_EXPIRES_MINUTES: int = 15
    JWT_REFRESH_EXPIRES_DAYS: int = 7
    BCRYPT_ROUNDS: int = 12

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"
    # TODO: Replace with your actual production frontend domain before production deployment
    PRODUCTION_FRONTEND_URL: str = "https://app.meetingmind.ai"

    # Rate Limiting
    GENERAL_RATE_LIMIT: str = "100/minute"
    AI_RATE_LIMIT: str = "10/minute"

    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parent.parent.parent / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def async_database_url(self) -> str:
        """Returns the PostgreSQL connection URL formatted for asyncpg."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    @property
    def sync_database_url(self) -> str:
        """Returns the PostgreSQL connection URL formatted for psycopg2 sync operations."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg2://", 1)
        return url

    def validate_required_keys(self) -> None:
        """Validates that all critical configuration keys are present and valid."""
        missing = []
        if not self.DEEPGRAM_API_KEY:
            missing.append("DEEPGRAM_API_KEY")
        if not self.GEMINI_API_KEY:
            missing.append("GEMINI_API_KEY")
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        if not self.REDIS_URL:
            missing.append("REDIS_URL")
        if not self.JWT_SECRET or (
            self.ENVIRONMENT == "production"
            and self.JWT_SECRET.startswith("default_development_secret")
        ):
            missing.append("JWT_SECRET (secure non-default value required in production)")

        if missing:
            msg = f"Critical configuration keys missing or insecure: {', '.join(missing)}"
            if self.ENVIRONMENT == "production":
                logger.critical(msg)
                raise ValueError(f"Production Startup Failed: {msg}")
            else:
                logger.warning(msg)


@lru_cache
def get_settings() -> Settings:
    """Cached settings getter."""
    return Settings()


settings: Settings = get_settings()
