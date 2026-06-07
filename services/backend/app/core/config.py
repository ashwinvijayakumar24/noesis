from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

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

    # Stripe Configuration
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRICE_ID_PRO: Optional[str] = None  # Monthly Pro plan
    STRIPE_PRICE_ID_TEAM: Optional[str] = None  # Monthly Team plan

    # Figma Configuration (for MCP integration)
    FIGMA_PAT: Optional[str] = None

    # Database Configuration
    DATABASE_URL: Optional[str] = None

    # Redis Configuration
    REDIS_URL: Optional[str] = None

    # GROBID Configuration
    GROBID_URL: Optional[str] = None
    # PDF body parser: "grobid" (default) or "docling". Docling gives per-block
    # coordinates (fixes anchoring); GROBID stays as automatic fallback + references.
    PDF_PARSER: str = "grobid"
    DOCLING_URL: Optional[str] = None

    # Application Configuration
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # File Upload Configuration
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: str = ".pdf"

    # API Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100

settings = Settings()
