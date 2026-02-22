from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Supabase Configuration
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None

    # OpenAI Configuration
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_ZERO_DATA_RETENTION: bool = True  # Privacy-first default
    OPENAI_ORGANIZATION_ID: Optional[str] = None

    # Cohere Configuration (for reranking in RAG optimization)
    COHERE_API_KEY: Optional[str] = None

    # Sentry Configuration (Error Tracking)
    SENTRY_DSN: Optional[str] = None

    # Database Configuration
    DATABASE_URL: Optional[str] = None

    # Redis Configuration
    REDIS_URL: Optional[str] = None

    # GROBID Configuration
    GROBID_URL: Optional[str] = None

    # Application Configuration
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # File Upload Configuration
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: str = ".pdf"

    # API Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100

    class Config:
        env_file = ".env"


settings = Settings()
