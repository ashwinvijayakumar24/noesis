"""
RAG Ingestion Service

Handles document ingestion, text extraction, chunking, and embedding generation
for the RAG pipeline.
"""

import fitz  # pymupdf
from openai import OpenAI
import tiktoken
from app.core.supabase_client import supabase
from app.core.config import settings
from app.core.logging_config import get_logger
import datetime
from typing import List

logger = get_logger(__name__)


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """
    Extract text from PDF file bytes.

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
    Complete RAG ingestion pipeline for a single document.

    Steps:
    1. Fetch document record and project RAG settings
    2. Download file from Supabase Storage
    3. Extract text from PDF
    4. Chunk text into smaller pieces (using project settings)
    5. Generate embeddings for chunks (using project settings)
    6. Store chunks and embeddings in pgvector table
    7. Update document status to 'ready'

    Args:
        document_id: UUID of the document
        project_id: UUID of the project

    Returns:
        Success message with ingestion statistics
    """
    try:
        # 1. Fetch document record
        record = supabase.table("documents").select("*").eq("id", document_id).single().execute()

        if not record.data:
            raise ValueError(f"Document ID {document_id} not found")

        file_url = record.data["file_url"]
        user_id = record.data["user_id"]

        # Fetch project RAG settings
        project_record = supabase.table("projects").select("rag_settings").eq("id", project_id).single().execute()

        # Get RAG settings with defaults
        rag_settings = project_record.data.get("rag_settings", {}) if project_record.data else {}
        chunk_size = rag_settings.get("chunk_size", 500)
        chunk_overlap = rag_settings.get("chunk_overlap", 100)
        embedding_model = rag_settings.get("embedding_model", "text-embedding-3-small")

        logger.info(f"Using RAG settings - chunk_size: {chunk_size}, overlap: {chunk_overlap}, model: {embedding_model}")

        # 2. Download file bytes from Supabase Storage
        # Extract storage path from URL
        # URL format: https://.../storage/v1/object/public/documents/{user_id}/{filename}
        # or: https://.../storage/v1/object/documents/{user_id}/{filename}
        try:
            # Extract the path after "/documents/"
            path_parts = file_url.split("/documents/")
            if len(path_parts) < 2:
                raise ValueError(f"Invalid file URL format: {file_url}")

            storage_path = path_parts[1]  # This will be "{user_id}/{actual_filename}"

            file_bytes = supabase.storage.from_("documents").download(storage_path)
        except Exception as e:
            raise ValueError(f"Failed to download file from storage: {str(e)}")

        # 3. Extract text from PDF
        full_text = extract_text_from_pdf(file_bytes)

        if not full_text.strip():
            raise ValueError("No text could be extracted from the PDF")

        # 4. Chunk text (using project settings)
        chunks = chunk_text(full_text, max_tokens=chunk_size, overlap_tokens=chunk_overlap)

        if not chunks:
            raise ValueError("Text chunking produced no chunks")

        # 5. Generate embeddings (using project settings)
        embeddings = embed_chunks(chunks, model=embedding_model)

        # 6. Insert chunks + embeddings into pgvector table
        rows = []
        for i, emb in enumerate(embeddings):
            rows.append({
                "document_id": document_id,
                "project_id": project_id,
                "chunk_index": i,
                "content": chunks[i],
                "embedding": emb.embedding
            })

        # Batch insert (insert one at a time for now, could be optimized)
        for row in rows:
            supabase.table("document_chunks").insert(row).execute()

        # 7. Update document status to 'ready'
        supabase.table("documents").update({
            "status": "ready",
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "metadata": {
                **record.data.get("metadata", {}),
                "embedded_at": datetime.datetime.utcnow().isoformat(),
                "num_chunks": len(chunks),
                "total_characters": len(full_text),
                "rag_settings_used": {
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "embedding_model": embedding_model
                }
            }
        }).eq("id", document_id).execute()

        return {
            "message": "Document successfully ingested and embedded",
            "document_id": document_id,
            "num_chunks": len(chunks),
            "total_characters": len(full_text),
            "rag_settings_used": {
                "chunk_size": chunk_size,
                "chunk_overlap": chunk_overlap,
                "embedding_model": embedding_model
            }
        }

    except Exception as e:
        # Update document status to error
        error_metadata = {
            "error": str(e),
            "embedding_status": "failed",
            "failed_at": datetime.datetime.utcnow().isoformat()
        }

        try:
            supabase.table("documents").update({
                "status": "failed",
                "metadata": error_metadata,
                "updated_at": datetime.datetime.utcnow().isoformat()
            }).eq("id", document_id).execute()
        except:
            pass  # If we can't update the DB, at least raise the original error

        raise
