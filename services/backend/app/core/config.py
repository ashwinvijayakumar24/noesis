from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    class Config:
        env_file = ".env"


settings = Settings()
