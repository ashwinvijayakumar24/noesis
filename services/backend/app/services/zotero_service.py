"""
Zotero Integration Service

Connects to the Zotero REST API to import a user's library into Noesis.

Zotero API docs: https://www.zotero.org/support/dev/web_api/v3/start
Rate limits: 100 requests/second (polite: stay under 10/s for web API)
Auth: Zotero-API-Key header

Typical flow:
    1. validate_api_key() — verify key + get userID
    2. list_collections() — show user their libraries
    3. import_collection() — pull items, create document records
"""

import asyncio
import datetime
from typing import Dict, Any, List, Optional, Tuple
import aiohttp

from app.core.supabase_client import supabase
from app.core.logging_config import get_logger

logger = get_logger(__name__)

ZOTERO_API_BASE = "https://api.zotero.org"


def _zotero_headers(api_key: str) -> Dict[str, str]:
    return {
        "Zotero-API-Key": api_key,
        "Zotero-API-Version": "3",
        "User-Agent": "Noesis/1.0 (contact@noesis.is)",
    }


async def validate_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """
    Validate a Zotero API key and return user info.

    Args:
        api_key: Zotero API key from zotero.org/settings/keys

    Returns:
        { user_id: int, username: str, name: str } or None if invalid
    """
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{ZOTERO_API_BASE}/keys/{api_key}"
            async with session.get(
                url,
                headers=_zotero_headers(api_key),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    user = data.get("user", {})
                    return {
                        "user_id": user.get("id"),
                        "username": user.get("username", ""),
                        "name": user.get("name", ""),
                        "access": data.get("access", {}),
                    }
                elif resp.status == 404:
                    logger.warning("[Zotero] Invalid API key")
                    return None
                else:
                    logger.warning(f"[Zotero] Key validation returned {resp.status}")
                    return None
    except Exception as e:
        logger.error(f"[Zotero] validate_api_key error: {e}")
        return None


async def list_collections(
    api_key: str,
    zotero_user_id: int,
) -> List[Dict[str, Any]]:
    """
    List all collections in a user's Zotero library.

    Args:
        api_key: Zotero API key
        zotero_user_id: Zotero user ID (from validate_api_key)

    Returns:
        List of collection dicts: { key, name, num_items, parent_collection }
    """
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{ZOTERO_API_BASE}/users/{zotero_user_id}/collections"
            params = {"limit": 100, "format": "json"}
            async with session.get(
                url,
                params=params,
                headers=_zotero_headers(api_key),
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()

                collections = []
                for col in data:
                    meta = col.get("meta", {})
                    col_data = col.get("data", {})
                    collections.append({
                        "key": col.get("key", ""),
                        "name": col_data.get("name", "Untitled Collection"),
                        "num_items": meta.get("numItems", 0),
                        "parent_collection": col_data.get("parentCollection"),
                        "version": col.get("version", 0),
                    })

                logger.info(f"[Zotero] Found {len(collections)} collections for user {zotero_user_id}")
                return collections

    except Exception as e:
        logger.error(f"[Zotero] list_collections error: {e}")
        return []


async def fetch_collection_items(
    api_key: str,
    zotero_user_id: int,
    collection_key: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """
    Fetch items from a Zotero library collection (or the whole library).

    Args:
        api_key: Zotero API key
        zotero_user_id: Zotero user ID
        collection_key: Collection key (None = entire library)
        limit: Max items to fetch (cap at 100 per request, paginates up to 500)

    Returns:
        List of raw Zotero item dicts
    """
    items = []
    start = 0
    max_total = min(limit, 500)  # Don't import more than 500 at once

    try:
        async with aiohttp.ClientSession() as session:
            while len(items) < max_total:
                if collection_key:
                    url = f"{ZOTERO_API_BASE}/users/{zotero_user_id}/collections/{collection_key}/items"
                else:
                    url = f"{ZOTERO_API_BASE}/users/{zotero_user_id}/items"

                params = {
                    "limit": min(100, max_total - len(items)),
                    "start": start,
                    "format": "json",
                    "itemType": "-attachment",  # Exclude attachments
                }

                async with session.get(
                    url,
                    params=params,
                    headers=_zotero_headers(api_key),
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status != 200:
                        break

                    batch = await resp.json()
                    if not batch:
                        break

                    items.extend(batch)
                    start += len(batch)

                    # Check Total-Results header
                    total = int(resp.headers.get("Total-Results", len(items)))
                    if len(items) >= total or len(items) >= max_total:
                        break

    except Exception as e:
        logger.error(f"[Zotero] fetch_collection_items error: {e}")

    logger.info(f"[Zotero] Fetched {len(items)} items from collection {collection_key or 'library'}")
    return items


def _zotero_item_to_document_record(
    item: Dict[str, Any],
    user_id: str,
    project_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Convert a Zotero item JSON into a Noesis document record.

    Skips non-paper types (notes, attachments, webpages without meaningful metadata).
    """
    data = item.get("data", {})
    item_type = data.get("itemType", "")

    # Only import paper-like types
    importable_types = {
        "journalArticle", "conferencePaper", "book", "bookSection",
        "thesis", "report", "preprint", "patent"
    }
    if item_type not in importable_types:
        return None

    title = data.get("title", "").strip()
    if not title:
        return None

    # Authors
    authors = []
    for creator in data.get("creators", []):
        if creator.get("creatorType") in ("author", "editor"):
            last = creator.get("lastName", "")
            first = creator.get("firstName", "")
            name = f"{first} {last}".strip() if first else last
            if name:
                authors.append(name)

    # Date/year
    date_str = data.get("date", "")
    year = ""
    if date_str:
        for part in date_str.split("-"):
            if part.strip().isdigit() and len(part.strip()) == 4:
                year = part.strip()
                break

    now = datetime.datetime.utcnow().isoformat()

    return {
        "user_id": user_id,
        "project_id": project_id,
        "title": title,
        "description": None,
        "file_url": "",
        "file_type": "bibtex_import",
        "file_size": 0,
        "status": "imported",
        "metadata": {
            "import_source": "zotero",
            "zotero_key": item.get("key", ""),
            "item_type": item_type,
            "authors": authors,
            "year": year,
            "abstract": data.get("abstractNote", ""),
            "doi": data.get("DOI", ""),
            "url": data.get("url", ""),
            "journal": data.get("publicationTitle", "") or data.get("bookTitle", ""),
            "volume": data.get("volume", ""),
            "issue": data.get("issue", ""),
            "pages": data.get("pages", ""),
            "publisher": data.get("publisher", ""),
            "isbn": data.get("ISBN", ""),
            "issn": data.get("ISSN", ""),
            "import_timestamp": now,
        },
        "created_at": now,
        "updated_at": now,
    }


async def import_collection(
    api_key: str,
    zotero_user_id: int,
    project_id: str,
    user_id: str,
    collection_key: Optional[str] = None,
    max_items: int = 200,
) -> Dict[str, Any]:
    """
    Import a Zotero collection (or entire library) into a Noesis project.

    Steps:
    1. Fetch items from Zotero API
    2. Convert to document records
    3. Batch insert into Supabase documents table
    4. For items with DOI, attempt Unpaywall PDF lookup (fire-and-forget)

    Args:
        api_key: Zotero API key
        zotero_user_id: Zotero user ID
        project_id: Target Noesis project ID
        user_id: Authenticated user ID
        collection_key: Zotero collection key (None = entire library)
        max_items: Max items to import per request

    Returns:
        { imported, skipped, total_found, errors }
    """
    # Fetch raw items
    raw_items = await fetch_collection_items(
        api_key=api_key,
        zotero_user_id=zotero_user_id,
        collection_key=collection_key,
        limit=max_items,
    )

    imported = 0
    skipped = 0
    errors = []

    for item in raw_items:
        record = _zotero_item_to_document_record(item, user_id, project_id)
        if not record:
            skipped += 1
            continue

        try:
            res = supabase.table("documents").insert(record).execute()
            if res.data:
                imported += 1
                doc_id = res.data[0]["id"]
                # If DOI present, schedule PDF fetch via Unpaywall (non-blocking)
                doi = record["metadata"].get("doi", "")
                if doi:
                    asyncio.create_task(_fetch_oa_pdf_for_document(doi, doc_id))
                try:
                    from app.services.rag_ingest import embed_imported_document
                    embed_imported_document(
                        document_id=doc_id,
                        project_id=project_id,
                        title=record["title"],
                        abstract=record["metadata"].get("abstract", ""),
                    )
                except Exception:
                    pass  # Non-fatal — document still imported without embedding
            else:
                skipped += 1
        except Exception as e:
            logger.warning(f"[Zotero] Failed to import '{record['title'][:50]}': {e}")
            errors.append(record["title"][:50])
            skipped += 1

    logger.info(f"[Zotero] Import complete: imported={imported}, skipped={skipped}, errors={len(errors)}")

    return {
        "imported": imported,
        "skipped": skipped,
        "total_found": len(raw_items),
        "errors": errors[:10],
    }


async def _fetch_oa_pdf_for_document(doi: str, document_id: str) -> None:
    """
    Background task: check Unpaywall for an open-access PDF for this DOI.
    If found, update the document record with the PDF URL.

    Unpaywall API: https://unpaywall.org/products/api
    Rate limit: 100K requests/day (polite: include email)
    """
    email = "contact@noesis.is"
    doi_clean = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()

    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.unpaywall.org/v2/{doi_clean}?email={email}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return

                data = await resp.json()

                # Get best OA location
                best_oa = data.get("best_oa_location", {})
                pdf_url = (
                    best_oa.get("url_for_pdf")
                    or best_oa.get("url")
                    if best_oa else None
                )

                if pdf_url:
                    # Update document with OA PDF URL
                    supabase.table("documents").update({
                        "metadata": supabase.table("documents")
                            .select("metadata")
                            .eq("id", document_id)
                            .single()
                            .execute()
                            .data["metadata"] | {"oa_pdf_url": pdf_url}
                    }).eq("id", document_id).execute()

                    logger.info(f"[Zotero/Unpaywall] Found OA PDF for doc {document_id}: {pdf_url[:60]}")

    except Exception as e:
        logger.debug(f"[Zotero/Unpaywall] PDF fetch failed for doc {document_id}: {e}")
