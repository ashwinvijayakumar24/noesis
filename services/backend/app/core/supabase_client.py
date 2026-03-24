from supabase import create_client
from app.core.config import settings
from postgrest import SyncPostgrestClient
from postgrest._sync.client import SyncClient
from typing import Dict, Union, Optional
from httpx import Timeout


# Monkey-patch postgrest to disable HTTP/2.
# postgrest-py hardcodes http2=True in create_session, but EC2 drops HTTP/2
# connections to Supabase mid-request (RemoteProtocolError: Server disconnected).
def _create_session_http1(
    self,
    base_url: str,
    headers: Dict[str, str],
    timeout: Union[int, float, Timeout],
    verify: bool = True,
    proxy: Optional[str] = None,
) -> SyncClient:
    return SyncClient(
        base_url=base_url,
        headers=headers,
        timeout=timeout,
        verify=verify,
        proxy=proxy,
        follow_redirects=True,
        http2=False,
    )

SyncPostgrestClient.create_session = _create_session_http1

# Only create client if Supabase credentials are provided
supabase = None
if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def get_supabase_client():
    """
    Get the Supabase client instance.

    Returns the global supabase client.
    """
    return supabase
