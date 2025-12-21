from supabase import create_client
from app.core.config import settings

# Only create client if Supabase credentials are provided
supabase = None
if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
