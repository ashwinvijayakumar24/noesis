"""
Zotero API Routes

Endpoints for integrating with the Zotero reference manager.

Zotero users can:
1. Validate their API key
2. Browse their Zotero libraries/collections
3. Import a selected collection into a Noesis project
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator, limiter
from app.core.logging_config import get_logger
from app.services.zotero_service import (
    validate_api_key,
    list_collections,
    import_collection,
)

router = APIRouter()
logger = get_logger(__name__)


# ── Auth helper ───────────────────────────────────────────────────────────────

def get_current_user(authorization: str = Header(None)) -> str:
    token = SecureAuthValidator.validate_bearer_token(authorization)
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Request/Response models ───────────────────────────────────────────────────

class ZoteroValidateRequest(BaseModel):
    api_key: str = Field(..., min_length=24, max_length=64, description="Zotero API key")


class ZoteroValidateResponse(BaseModel):
    valid: bool
    user_id: Optional[int] = None
    username: Optional[str] = None
    name: Optional[str] = None


class ZoteroImportRequest(BaseModel):
    api_key: str = Field(..., min_length=24, max_length=64)
    zotero_user_id: int
    project_id: str
    collection_key: Optional[str] = None  # None = entire library
    max_items: int = Field(default=200, ge=1, le=500)


class ZoteroImportResponse(BaseModel):
    imported: int
    skipped: int
    total_found: int
    errors: List[str] = []
    message: str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/zotero/validate-key", response_model=ZoteroValidateResponse)
@limiter.limit("20/minute")
async def validate_zotero_key(
    request: Request,
    body: ZoteroValidateRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Validate a Zotero API key and return user info.

    The API key can be created at: https://www.zotero.org/settings/keys
    Select "Allow library access" and optionally "Allow notes access".
    """
    user_info = await validate_api_key(body.api_key)

    if not user_info:
        return ZoteroValidateResponse(valid=False)

    return ZoteroValidateResponse(
        valid=True,
        user_id=user_info.get("user_id"),
        username=user_info.get("username"),
        name=user_info.get("name"),
    )


@router.post("/zotero/libraries")
@limiter.limit("20/minute")
async def get_zotero_libraries(
    request: Request,
    body: ZoteroValidateRequest,
    user_id: str = Depends(get_current_user),
):
    """
    List Zotero collections for a user.

    Pass both api_key and zotero_user_id (from validate-key response).
    Returns collections with item counts.
    """
    # Validate key first
    user_info = await validate_api_key(body.api_key)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid Zotero API key")

    zotero_user_id = user_info.get("user_id")
    if not zotero_user_id:
        raise HTTPException(status_code=400, detail="Could not determine Zotero user ID")

    collections = await list_collections(
        api_key=body.api_key,
        zotero_user_id=zotero_user_id,
    )

    return {
        "user_id": zotero_user_id,
        "username": user_info.get("username"),
        "collections": collections,
        "total_collections": len(collections),
    }


@router.post("/zotero/import", response_model=ZoteroImportResponse)
@limiter.limit("5/minute")
async def import_zotero_collection(
    request: Request,
    body: ZoteroImportRequest,
    user_id: str = Depends(get_current_user),
):
    """
    Import a Zotero collection (or entire library) into a Noesis project.

    - Each paper becomes a document record with status='imported'
    - Papers with a DOI will have their open-access PDF URL fetched via Unpaywall (async)
    - Max 500 items per import request

    Example request:
    ```json
    {
        "api_key": "your_zotero_key",
        "zotero_user_id": 123456,
        "project_id": "uuid-of-project",
        "collection_key": "ABC12345",
        "max_items": 100
    }
    ```
    """
    # Verify the project exists and belongs to this user
    project_res = supabase.table("projects")\
        .select("id")\
        .eq("id", body.project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Validate Zotero key before importing
    user_info = await validate_api_key(body.api_key)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid Zotero API key")

    if user_info.get("user_id") != body.zotero_user_id:
        raise HTTPException(
            status_code=403,
            detail="Zotero user ID does not match the provided API key"
        )

    # Run import
    result = await import_collection(
        api_key=body.api_key,
        zotero_user_id=body.zotero_user_id,
        project_id=body.project_id,
        user_id=user_id,
        collection_key=body.collection_key,
        max_items=body.max_items,
    )

    message = f"Imported {result['imported']} references"
    if result.get("collection_key"):
        message += f" from collection"
    else:
        message += " from Zotero library"

    if result["skipped"] > 0:
        message += f" ({result['skipped']} skipped)"

    return ZoteroImportResponse(
        imported=result["imported"],
        skipped=result["skipped"],
        total_found=result["total_found"],
        errors=result.get("errors", []),
        message=message,
    )
