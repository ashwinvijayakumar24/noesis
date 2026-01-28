"""
RAG Ingestion Service

Handles document ingestion, text extraction, chunking, and embedding generation
for the RAG pipeline.

Uses GROBID for scientific PDF processing to extract structured information
including sections, references, and metadata.
"""

import fitz  # pymupdf (fallback only)
from openai import OpenAI
import tiktoken
from app.core.supabase_client import supabase
from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.grobid_client import get_grobid_client
from app.services.rag_chunking import get_chunking_strategy, get_section_aware_chunking_strategy
import datetime
from typing import List, Dict, Any

logger = get_logger(__name__)


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
    tokens = enc.encode(text)

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


def embed_chunks(chunks: List[str], model: str = "text-embedding-3-small") -> List:
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

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    embeddings = client.embeddings.create(
        model=model,
        input=chunks,
        dimensions=1536  # Fixed at 1536 for pgvector index compatibility
    )

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
        logger.info(f"[RAG-INGEST] file_url={file_url}, user_id={user_id}")

        # 2. Download file bytes from Supabase Storage
        logger.info(f"[RAG-INGEST] Step 2: Downloading file from Supabase Storage...")
        # Extract storage path from URL
        # URL format: https://.../storage/v1/object/public/documents/{user_id}/{filename}
        # or: https://.../storage/v1/object/documents/{user_id}/{filename}
        try:
            # Extract the path after "/documents/"
            path_parts = file_url.split("/documents/")
            if len(path_parts) < 2:
                logger.error(f"[RAG-INGEST] ✗ Invalid file URL format: {file_url}")
                raise ValueError(f"Invalid file URL format: {file_url}")

            storage_path = path_parts[1]  # This will be "{user_id}/{actual_filename}"
            logger.info(f"[RAG-INGEST] Extracted storage path: {storage_path}")

            file_bytes = supabase.storage.from_("documents").download(storage_path)
            logger.info(f"[RAG-INGEST] ✓ Downloaded {len(file_bytes)} bytes")
        except Exception as e:
            logger.error(f"[RAG-INGEST] ✗ Failed to download file: {type(e).__name__}: {str(e)}")
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
        total_tokens = len(enc.encode(full_text))
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
        embedding_model = "text-embedding-3-small"
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

        # First, get current document status to avoid race condition with analysis
        current_doc = supabase.table("documents").select("status").eq("id", document_id).execute()
        current_status = current_doc.data[0].get("status") if current_doc.data else "uploaded"

        # Prepare metadata update
        metadata_update = {
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "metadata": {
                **record.data.get("metadata", {}),
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

        # Only update status to 'ready' if analysis hasn't started yet
        # If status is 'analyzing' or 'analyzed', don't overwrite it
        if current_status not in ["analyzing", "analyzed"]:
            metadata_update["status"] = "ready"
            logger.info(f"[RAG-INGEST] Setting status to 'ready' (current: {current_status})")
        else:
            logger.info(f"[RAG-INGEST] Preserving status '{current_status}' (analysis in progress or complete)")

        supabase.table("documents").update(metadata_update).eq("id", document_id).execute()

        logger.info(f"[RAG-INGEST] ✓ Document metadata updated")
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
        error_metadata = {
            "error": str(e),
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
