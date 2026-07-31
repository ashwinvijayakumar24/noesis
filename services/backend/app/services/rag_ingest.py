"""
RAG Ingestion Service

Handles document ingestion, text extraction, chunking, and embedding generation
for the RAG pipeline.

Uses GROBID for scientific PDF processing to extract structured information
including sections, references, and metadata.
"""

import fitz  # pymupdf (fallback only)
import tiktoken
from app.core.supabase_client import supabase
from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_completion_params
from app.services.grobid_client import get_grobid_client
from app.services.retry_utils import retry_openai
from app.services.rag_chunking import (
    count_and_encode,
    get_chunking_strategy,
    get_section_aware_chunking_strategy,
)
import datetime
from typing import Any, Dict, List, Tuple

logger = get_logger(__name__)


# The ONLY character PostgreSQL refuses to store in a `text` value is U+0000.
# Verified against the local pgvector Postgres: `SELECT chr(0)` errors with
# "null character not permitted", every other C0 control (U+0001..U+001F,
# including \t \n \r and the form feed U+000C that PDF extraction emits at page
# breaks), U+007F, the Unicode line/paragraph separators U+2028/U+2029 and the
# BOM U+FEFF all round-trip fine. psycopg2 rejects NUL client-side too
# ("A string literal cannot contain NUL (0x00) bytes"), and PostgREST -- the path
# production actually uses -- fails on the JSON side with "unsupported Unicode
# escape sequence" for the escaped NUL. So NUL is the whole problem and nothing else here
# needs touching: stripping legal control characters would silently mangle
# legitimate extracted text (form feeds carry page structure, tabs carry table
# structure) for no database-level benefit.
_POSTGRES_ILLEGAL_TEXT_CHAR = "\x00"


def sanitize_for_postgres_text(text: str) -> Tuple[str, int]:
    """Remove characters PostgreSQL `text` columns cannot store.

    Returns ``(sanitised_text, removed_count)``. The count is returned rather
    than logged here so the caller can report it once per document instead of
    once per chunk.

    STRIP, not replace-with-space. PDF text extraction emits NUL as an artefact
    of a broken glyph-to-Unicode mapping -- it stands in for a character that
    was *supposed* to be there, not for a word boundary. Replacing with a space
    would turn ``"Smith et\\x00al."`` into ``"Smith et al."``, which reads fine,
    but would equally turn ``"tempera\\x00ture"`` into ``"tempera ture"``,
    splitting a word that was whole and breaking both tokenisation and keyword
    search on it. Stripping gives ``"Smith etal."`` and ``"temperature"``:
    the mid-word case (the common one, since NUL replaces a real glyph) comes
    out correct, and the between-words case merely loses a space that the
    surrounding whitespace usually still provides. One damaged token beats a
    damaged token *plus* a spurious word break.
    """
    if _POSTGRES_ILLEGAL_TEXT_CHAR not in text:
        return text, 0
    removed = text.count(_POSTGRES_ILLEGAL_TEXT_CHAR)
    return text.replace(_POSTGRES_ILLEGAL_TEXT_CHAR, ""), removed


def sanitize_chunks_for_postgres(chunks: List[str]) -> Tuple[List[str], int]:
    """Sanitise a list of chunks, returning the cleaned list and the total removed."""
    cleaned: List[str] = []
    total = 0
    for chunk in chunks:
        text, removed = sanitize_for_postgres_text(chunk)
        cleaned.append(text)
        total += removed
    return cleaned, total


def sanitize_json_for_postgres(value: Any) -> Tuple[Any, int]:
    """Sanitise every string inside a nested JSON-able value bound for a jsonb column.

    Document-derived strings (GROBID title/abstract/section titles/references) are
    written to ``documents.metadata``. jsonb rejects U+0000 exactly like text does
    -- PostgREST reports "unsupported Unicode escape sequence" -- so the metadata
    write fails for the same PDFs the chunk write does.
    """
    if isinstance(value, str):
        return sanitize_for_postgres_text(value)
    if isinstance(value, dict):
        out_d: Dict[Any, Any] = {}
        total = 0
        for k, v in value.items():
            out_d[k], removed = sanitize_json_for_postgres(v)
            total += removed
        return out_d, total
    if isinstance(value, list):
        out_l: List[Any] = []
        total = 0
        for v in value:
            cleaned, removed = sanitize_json_for_postgres(v)
            out_l.append(cleaned)
            total += removed
        return out_l, total
    return value, 0


def report_nul_removal(document_id: str, removed: int, where: str) -> None:
    """Log, once per document per surface, how much text sanitisation altered.

    Sanitising silently is how the next data-quality problem hides: a chunk that
    lost characters embeds and retrieves differently, and with no log there is
    nothing to correlate a bad retrieval number against. No-ops when nothing was
    removed, so clean documents stay quiet.
    """
    if not removed:
        return
    logger.warning(
        "[RAG-INGEST] Removed %d NUL character(s) from %s of document_id=%s "
        "(PostgreSQL cannot store U+0000); extracted text was altered",
        removed,
        where,
        document_id,
    )


async def extract_structured_data_from_pdf(file_bytes: bytes) -> Dict[str, Any]:
    """
    Extract structured data from scientific PDF using GROBID.

    Args:
        file_bytes: PDF file as bytes

    Returns:
        Dictionary with structured data including:
        - full_text: Complete document text
        - title: Paper title
        - authors: List of authors
        - abstract: Abstract text
        - sections: List of sections with titles and content
        - references: List of bibliography entries
        - metadata: Additional metadata

    Raises:
        Exception: If GROBID processing fails, falls back to PyMuPDF
    """
    try:
        grobid = get_grobid_client()
        structured_data = await grobid.process_pdf(file_bytes)
        logger.info("Successfully extracted structured data using GROBID")
        return structured_data
    except Exception as e:
        logger.warning(f"GROBID extraction failed: {e}. Falling back to PyMuPDF")
        # Fallback to basic extraction
        return {
            "full_text": extract_text_from_pdf_fallback(file_bytes),
            "title": "",
            "authors": [],
            "abstract": "",
            "sections": [],
            "references": [],
            "metadata": {}
        }


def extract_text_from_pdf_fallback(file_bytes: bytes) -> str:
    """
    Fallback: Extract text from PDF using PyMuPDF (basic extraction).
    Used only if GROBID fails.

    Args:
        file_bytes: PDF file as bytes

    Returns:
        Extracted text as string
    """
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def get_pdf_page_count(file_bytes: bytes) -> int:
    """
    Get the number of pages in a PDF document.

    Args:
        file_bytes: PDF file as bytes

    Returns:
        Number of pages in the PDF

    Raises:
        Exception: If unable to open or read the PDF
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        page_count = len(doc)
        doc.close()
        logger.info(f"PDF has {page_count} pages")
        return page_count
    except Exception as e:
        logger.error(f"Failed to get page count: {e}")
        # Return a default value to allow processing to continue
        return 10  # Assume medium-length document as fallback


def chunk_text(text: str, max_tokens: int = 500, overlap_tokens: int = 100) -> List[str]:
    """
    Chunk text into smaller pieces based on token count with optional overlap.

    Args:
        text: Text to chunk
        max_tokens: Maximum tokens per chunk
        overlap_tokens: Number of tokens to overlap between chunks (for context preservation)

    Returns:
        List of text chunks
    """
    enc = tiktoken.get_encoding("cl100k_base")
    # count_and_encode, not enc.encode: a document quoting "<|endoftext|>" (any
    # paper about LLM tokenisation does) otherwise raises here. See the
    # _DISALLOWED_SPECIAL note in rag_chunking for why the literal string is kept
    # as text rather than promoted to a control token.
    tokens = count_and_encode(enc, text)

    chunks = []
    stride = max(1, max_tokens - overlap_tokens)  # Ensure stride is at least 1

    for i in range(0, len(tokens), stride):
        chunk_tokens = tokens[i:i+max_tokens]
        if chunk_tokens:  # Only add non-empty chunks
            chunks.append(enc.decode(chunk_tokens))

        # Stop if we've reached the end
        if i + max_tokens >= len(tokens):
            break

    return chunks


def embed_chunks(chunks: List[str], model: str = "text-embedding-3-large") -> List:
    """
    Generate embeddings for text chunks using OpenAI API.

    Args:
        chunks: List of text chunks
        model: OpenAI embedding model to use (text-embedding-3-small or text-embedding-3-large)

    Returns:
        List of embedding objects (always 1536 dimensions)

    Note:
        Both models return 1536-dimensional embeddings for pgvector compatibility.
        text-embedding-3-large uses dimension reduction from its native 3072 dimensions.
    """
    if not settings.OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not configured in environment variables")

    client = get_openai_client()

    # retry_openai backs off on RateLimitError/APIError/APIConnectionError. This
    # call had no retry at all, while embed_query in rag_retrieval has had one all
    # along -- so a single TPM spike killed an entire ingestion. Reproduced on a
    # 345-document corpus: OpenAI returned
    #   429 ... Limit 1000000, Used 982070, Requested 20872. Please try again in 176ms
    # and the run died 264 documents in, having already paid for them. The retry
    # waits the 176ms instead. Batching keeps requests large, so brushing the
    # per-minute token ceiling is normal operation, not an exceptional condition.
    @retry_openai
    def _create():
        return client.embeddings.create(
            model=model,
            input=chunks,
            dimensions=1536  # Fixed at 1536 for pgvector index compatibility
        )

    embeddings = _create()

    return embeddings.data


async def ingest_document(document_id: str, project_id: str) -> dict:
    """
    Complete RAG ingestion pipeline for a single document with adaptive chunking.

    Steps:
    1. Fetch document record
    2. Download file from Supabase Storage
    3. Get page count from PDF
    4. Extract structured data using GROBID
    5. Calculate total tokens
    6. Determine optimal chunking strategy (adaptive based on page count + cost ceiling)
    7. Chunk text into smaller pieces (using adaptive parameters)
    8. Generate embeddings for chunks (server-controlled model)
    9. Store chunks and embeddings in pgvector table
    10. Update document status to 'ready' with adaptive chunking metadata

    Adaptive Chunking Strategy:
    - SHORT (1-10 pages): chunk_size=1200, overlap=200
    - MEDIUM (11-30 pages): chunk_size=1600, overlap=250
    - LONG (31+ pages): chunk_size=2000, overlap=300
    - Cost ceiling: Max 50 chunks per document (auto-adjusts if needed)

    Args:
        document_id: UUID of the document
        project_id: UUID of the project

    Returns:
        Success message with ingestion statistics including adaptive chunking info
    """
    try:
        logger.info(f"[RAG-INGEST] ========== STARTING RAG INGESTION ==========")
        logger.info(f"[RAG-INGEST] document_id={document_id}, project_id={project_id}")

        # 1. Fetch document record
        logger.info(f"[RAG-INGEST] Step 1: Fetching document record from database...")
        record = supabase.table("documents").select("*").eq("id", document_id).single().execute()
        logger.info(f"[RAG-INGEST] ✓ Found document record")

        if not record.data:
            logger.error(f"[RAG-INGEST] ✗ Document ID {document_id} not found in database")
            raise ValueError(f"Document ID {document_id} not found")

        file_url = record.data["file_url"]
        user_id = record.data["user_id"]
        logger.info(f"[RAG-INGEST] File record retrieved")

        # 2. Download file bytes from Supabase Storage
        logger.info(f"[RAG-INGEST] Step 2: Downloading file from Supabase Storage...")
        # Extract storage path from URL
        # URL format: https://.../storage/v1/object/public/documents/{user_id}/{filename}
        # or: https://.../storage/v1/object/documents/{user_id}/{filename}
        try:
            # Extract the path after "/documents/"
            path_parts = file_url.split("/documents/")
            if len(path_parts) < 2:
                logger.error(f"[RAG-INGEST] ✗ Invalid file URL format")
                raise ValueError(f"Invalid file URL format: {file_url}")

            storage_path = path_parts[1]  # This will be "{user_id}/{actual_filename}"

            file_bytes = supabase.storage.from_("documents").download(storage_path)
            logger.info(f"[RAG-INGEST] ✓ Downloaded {len(file_bytes)} bytes")
        except Exception as e:
            logger.error(f"[RAG-INGEST] ✗ Failed to download file: {type(e).__name__}")
            raise ValueError(f"Failed to download file from storage: {str(e)}")

        # 3. Get page count from PDF for adaptive chunking
        logger.info(f"[RAG-INGEST] Step 3: Getting PDF page count...")
        page_count = get_pdf_page_count(file_bytes)
        logger.info(f"[RAG-INGEST] ✓ PDF has {page_count} pages")

        # 4. Extract structured data from PDF using GROBID
        logger.info(f"[RAG-INGEST] Step 4: Extracting structured data using GROBID...")
        structured_data = await extract_structured_data_from_pdf(file_bytes)
        full_text = structured_data["full_text"]
        logger.info(f"[RAG-INGEST] ✓ Extracted {len(full_text)} characters of text")

        if not full_text.strip():
            logger.error(f"[RAG-INGEST] ✗ No text could be extracted from the PDF")
            raise ValueError("No text could be extracted from the PDF")

        # 5. Calculate total tokens for adaptive chunking
        logger.info(f"[RAG-INGEST] Step 5: Calculating total tokens...")
        enc = tiktoken.get_encoding("cl100k_base")
        total_tokens = len(count_and_encode(enc, full_text))
        logger.info(f"[RAG-INGEST] ✓ Document has {total_tokens} tokens across {page_count} pages")

        # 6. Determine chunking strategy based on GROBID section extraction
        logger.info(f"[RAG-INGEST] Step 6: Determining chunking strategy...")
        sections = structured_data.get("sections", [])
        use_section_aware = len(sections) > 0  # Use section-aware if GROBID extracted sections

        if use_section_aware:
            logger.info(f"[RAG-INGEST] Using section-aware chunking with {len(sections)} sections")

            # Get section-aware chunking strategy
            chunking_params = get_section_aware_chunking_strategy(
                sections=sections,
                page_count=page_count,
                total_tokens=total_tokens,
                doc_type="paper"
            )

            chunk_size = chunking_params["chunk_size"]
            chunk_overlap = chunking_params["overlap"]
            tier = chunking_params["tier"]
            was_adjusted = chunking_params["was_adjusted"]
            estimated_chunks = chunking_params["estimated_chunks"]
            chunking_method = chunking_params["chunking_method"]

            # Get pre-chunked content with section metadata
            section_aware_chunks = chunking_params["chunks"]

            logger.info(
                f"Section-aware chunking - tier: {tier}, chunk_size: {chunk_size}, "
                f"overlap: {chunk_overlap}, chunks: {len(section_aware_chunks)}, "
                f"cost_ceiling_applied: {was_adjusted}"
            )
        else:
            logger.info("[RAG-INGEST] GROBID did not extract sections, using basic adaptive chunking")

            # Fallback to basic adaptive chunking
            chunking_params = get_chunking_strategy(
                page_count=page_count,
                total_tokens=total_tokens,
                doc_type="paper"
            )
            logger.info(f"[RAG-INGEST] ✓ Determined basic chunking strategy")

            chunk_size = chunking_params["chunk_size"]
            chunk_overlap = chunking_params["overlap"]
            tier = chunking_params["tier"]
            was_adjusted = chunking_params["was_adjusted"]
            estimated_chunks = chunking_params["estimated_chunks"]
            chunking_method = "basic"

            logger.info(
                f"Basic adaptive chunking - tier: {tier}, chunk_size: {chunk_size}, "
                f"overlap: {chunk_overlap}, estimated_chunks: {estimated_chunks}, "
                f"cost_ceiling_applied: {was_adjusted}"
            )

        # Use default embedding model (server-controlled, no user config)
        embedding_model = "text-embedding-3-large"
        logger.info(f"[RAG-INGEST] Using embedding model: {embedding_model}")

        # 7. Chunk text (using appropriate strategy)
        logger.info(f"[RAG-INGEST] Step 7: Chunking document text...")
        if use_section_aware:
            # Extract just the content strings from section-aware chunks
            chunks = [chunk["content"] for chunk in section_aware_chunks]
            logger.info(f"[RAG-INGEST] ✓ Created {len(chunks)} section-aware chunks")
        else:
            # Use basic chunking
            chunks = chunk_text(full_text, max_tokens=chunk_size, overlap_tokens=chunk_overlap)
            logger.info(f"[RAG-INGEST] ✓ Created {len(chunks)} basic chunks")

        if not chunks:
            logger.error(f"[RAG-INGEST] ✗ Text chunking produced no chunks")
            raise ValueError("Text chunking produced no chunks")

        # Sanitise BEFORE embedding so the vector matches the text that is stored.
        chunks, nul_in_chunks = sanitize_chunks_for_postgres(chunks)
        report_nul_removal(document_id, nul_in_chunks, "chunk content")

        logger.info(f"[RAG-INGEST] Created {len(chunks)} chunks (estimated: {estimated_chunks})")

        # 8. Generate embeddings (using server-controlled model)
        logger.info(f"[RAG-INGEST] Step 8: Generating embeddings for {len(chunks)} chunks...")
        embeddings = embed_chunks(chunks, model=embedding_model)
        logger.info(f"[RAG-INGEST] ✓ Generated {len(embeddings)} embeddings")

        # 9. Insert chunks + embeddings into pgvector table with section metadata
        logger.info(f"[RAG-INGEST] Step 9: Storing {len(embeddings)} chunks in database...")
        rows = []
        for i, emb in enumerate(embeddings):
            row = {
                "document_id": document_id,
                "project_id": project_id,
                "chunk_index": i,
                "content": chunks[i],
                "embedding": emb.embedding
            }

            # Note: metadata column removed - not present in Supabase schema
            # Section metadata can be added later if column is created

            rows.append(row)

        # Batch insert (insert one at a time for now, could be optimized)
        logger.info(f"[RAG-INGEST] Inserting {len(rows)} rows into document_chunks table...")
        for idx, row in enumerate(rows):
            supabase.table("document_chunks").insert(row).execute()
            if (idx + 1) % 10 == 0 or (idx + 1) == len(rows):
                logger.info(f"[RAG-INGEST] Inserted {idx + 1}/{len(rows)} chunks")

        logger.info(f"[RAG-INGEST] ✓ All chunks stored successfully")

        # 10. Update document metadata and status (only update status if not already analyzing/analyzed)
        logger.info(f"[RAG-INGEST] Step 10: Updating document metadata...")

        # Re-check current document status right before writing metadata.
        # The document may have advanced since ingestion started.
        current_doc = supabase.table("documents").select("status, metadata").eq("id", document_id).execute()
        current_status = current_doc.data[0].get("status") if current_doc.data else "uploaded"
        current_metadata = current_doc.data[0].get("metadata") if current_doc.data else {}

        # Prepare metadata update
        metadata_update = {
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "metadata": {
                **(current_metadata or record.data.get("metadata") or {}),
                "embedded_at": datetime.datetime.utcnow().isoformat(),
                "page_count": page_count,
                "total_tokens": total_tokens,
                "num_chunks": len(chunks),
                "total_characters": len(full_text),
                # Adaptive chunking parameters (server-controlled)
                "adaptive_chunking": {
                    "method": chunking_method,
                    "tier": tier,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "embedding_model": embedding_model,
                    "estimated_chunks": estimated_chunks,
                    "actual_chunks": len(chunks),
                    "cost_ceiling_applied": was_adjusted,
                    "sections_count": len(sections) if use_section_aware else 0
                },
                # GROBID extracted metadata
                "grobid_title": structured_data.get("title", ""),
                "grobid_authors": structured_data.get("authors", []),
                "grobid_abstract": structured_data.get("abstract", ""),
                "grobid_sections_count": len(structured_data.get("sections", [])),
                "grobid_references_count": len(structured_data.get("references", [])),
                "grobid_sections": [
                    {"title": s.get("title"), "type": s.get("type")}
                    for s in structured_data.get("sections", [])
                ],
                "grobid_references": structured_data.get("references", [])[:50]  # Limit to 50 refs to avoid size issues
            }
        }

        metadata_update["metadata"], nul_in_metadata = sanitize_json_for_postgres(
            metadata_update["metadata"]
        )
        report_nul_removal(
            document_id, nul_in_metadata, "GROBID metadata (title/abstract/sections/references)"
        )

        # Only update status to 'ready' if analysis hasn't started yet
        # If status is 'analyzing' or 'analyzed', don't overwrite it
        if current_status not in ["analyzing", "analyzed"]:
            metadata_update["status"] = "ready"
            logger.info(f"[RAG-INGEST] Setting status to 'ready' (current: {current_status})")
        else:
            logger.info(f"[RAG-INGEST] Preserving status '{current_status}' (analysis in progress or complete)")

        supabase.table("documents").update(metadata_update).eq("id", document_id).execute()

        logger.info(f"[RAG-INGEST] ✓ Document metadata updated")

        # Auto-trigger document analysis after RAG completion (if not already analyzing)
        # This prevents race conditions and ensures analysis always runs after RAG
        if current_status not in ["analyzing", "analyzed"]:
            logger.info(f"[RAG-INGEST] Auto-triggering document analysis...")
            try:
                from app.tasks.document_analysis import analyze_document_task

                # Note: user_id is already fetched from record.data at line 210
                task_result = analyze_document_task.delay(document_id, user_id, project_id)
                logger.info(f"[RAG-INGEST] ✓ Analysis task submitted (task_id={task_result.id})")
            except Exception as analysis_error:
                logger.error(f"[RAG-INGEST] ✗ Failed to trigger analysis: {analysis_error}")
                logger.error(f"[RAG-INGEST] Analysis error traceback:", exc_info=True)
                # Don't fail the entire ingestion if analysis trigger fails
        else:
            logger.info(f"[RAG-INGEST] Skipping auto-trigger (status={current_status})")

        logger.info(f"[RAG-INGEST] ========== INGESTION COMPLETE ==========")

        return {
            "message": "Document successfully ingested and embedded",
            "document_id": document_id,
            "page_count": page_count,
            "total_tokens": total_tokens,
            "num_chunks": len(chunks),
            "total_characters": len(full_text),
            "adaptive_chunking": {
                "method": chunking_method,
                "tier": tier,
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "embedding_model": embedding_model,
                "estimated_chunks": estimated_chunks,
                "actual_chunks": len(chunks),
                "cost_ceiling_applied": was_adjusted,
                "sections_count": len(sections) if use_section_aware else 0
            },
            "grobid_extraction": {
                "title": structured_data.get("title", ""),
                "authors_count": len(structured_data.get("authors", [])),
                "sections_count": len(structured_data.get("sections", [])),
                "references_count": len(structured_data.get("references", []))
            }
        }

    except Exception as e:
        # Log the error with full traceback
        import traceback
        logger.error(f"[RAG-INGEST] ✗ INGESTION FAILED for document_id={document_id}")
        logger.error(f"[RAG-INGEST] Error type: {type(e).__name__}")
        logger.error(f"[RAG-INGEST] Error message: {str(e)}")
        logger.error(f"[RAG-INGEST] Full traceback:\n{traceback.format_exc()}")

        # Update document status to error
        # The exception message can quote the offending document text (PostgREST
        # echoes it back), so the failure record is itself a place a NUL reaches
        # the database. Unsanitised, this update throws too and the document is
        # left stuck in its previous status with no error recorded at all.
        error_message, _ = sanitize_for_postgres_text(str(e))
        error_metadata = {
            "error": error_message,
            "error_type": type(e).__name__,
            "embedding_status": "failed",
            "failed_at": datetime.datetime.utcnow().isoformat()
        }

        try:
            logger.info(f"[RAG-INGEST] Updating document status to 'failed'...")
            supabase.table("documents").update({
                "status": "failed",
                "metadata": error_metadata,
                "updated_at": datetime.datetime.utcnow().isoformat()
            }).eq("id", document_id).execute()
            logger.info(f"[RAG-INGEST] ✓ Document status updated to 'failed'")
        except Exception as update_error:
            logger.error(f"[RAG-INGEST] ✗ Failed to update document status: {update_error}")

        logger.error(f"[RAG-INGEST] ========== INGESTION FAILED ==========")
        raise


def embed_imported_document(
    document_id: str,
    project_id: str,
    title: str,
    abstract: str = "",
) -> int:
    """
    Embed title + abstract for a metadata-only imported document and store
    one chunk in document_chunks with metadata.source = "abstract_only".

    Called after BibTeX or Zotero inserts so imported references contribute
    to semantic search, coverage gap detection, and citation suggestions.

    Returns number of chunks stored (0 or 1).
    """
    embed_text = title.strip()
    if abstract and abstract.strip():
        embed_text += f"\n{abstract.strip()[:600]}"

    embed_text, nul_removed = sanitize_for_postgres_text(embed_text)
    report_nul_removal(document_id, nul_removed, "imported title/abstract")

    if not embed_text:
        return 0

    try:
        # Clear any prior chunk for this document (idempotent re-import)
        supabase.table("document_chunks").delete().eq("document_id", document_id).execute()

        embeddings = embed_chunks([embed_text], model="text-embedding-3-large")
        if not embeddings:
            return 0

        supabase.table("document_chunks").insert({
            "document_id": document_id,
            "project_id": project_id,
            "chunk_index": 0,
            "content": embed_text,
            "embedding": embeddings[0].embedding,
        }).execute()

        logger.info(f"[ImportEmbed] Stored abstract chunk for document_id={document_id}")
        return 1

    except Exception as e:
        logger.warning(f"[ImportEmbed] Failed to embed imported document {document_id}: {e}")
        return 0
