"""
RAG API Endpoints

Provides endpoints for document ingestion and RAG-based querying.
"""

from fastapi import APIRouter, HTTPException, Depends, Header, BackgroundTasks
from app.services.rag_ingest import ingest_document
from app.services.rag_retrieval import retrieve_relevant_chunks, generate_rag_answer
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator
from typing import Optional
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"  # Don't expose environment details
        )

    # Use secure token validator
    token = SecureAuthValidator.validate_bearer_token(authorization)

    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        logger.error(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"  # Don't expose error details
        )


@router.post("/ingest/{document_id}")
async def ingest_document_endpoint(
    document_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user)
):
    """
    Trigger RAG ingestion for a specific document.

    This endpoint:
    1. Verifies the document belongs to the user
    2. Extracts text from the PDF
    3. Chunks the text
    4. Generates embeddings
    5. Stores in pgvector table

    The ingestion happens in the background.
    """
    import traceback
    print(f"[RAG-ENDPOINT] ========== RAG INGESTION REQUEST ==========")
    print(f"[RAG-ENDPOINT] document_id={document_id}, user_id={user_id}")

    try:
        # Verify document exists and belongs to user
        print(f"[RAG-ENDPOINT] Verifying document exists and belongs to user...")
        doc_response = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()

        if not doc_response.data:
            print(f"[RAG-ENDPOINT] ✗ Document not found: {document_id}")
            raise HTTPException(status_code=404, detail="Document not found")

        document = doc_response.data[0]
        project_id = document.get("project_id")
        print(f"[RAG-ENDPOINT] ✓ Found document: title={document.get('title')}, project_id={project_id}")

        if not project_id:
            print(f"[RAG-ENDPOINT] ✗ Document not attached to project")
            raise HTTPException(
                status_code=400,
                detail="Document must be attached to a project before ingestion"
            )

        # Update document status to 'processing' immediately
        print(f"[RAG-ENDPOINT] Updating document status to 'processing'...")
        supabase.table("documents").update({
            "status": "processing",
            "updated_at": "now()"
        }).eq("id", document_id).execute()
        print(f"[RAG-ENDPOINT] ✓ Status updated to 'processing'")

        # Trigger background ingestion
        print(f"[RAG-ENDPOINT] Adding background task for RAG ingestion...")
        background_tasks.add_task(ingest_document, document_id, project_id)
        print(f"[RAG-ENDPOINT] ✓ Background task added successfully")

        return {
            "message": "Document ingestion started in background",
            "document_id": document_id,
            "status": "processing"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[RAG-ENDPOINT] ✗ ERROR: {type(e).__name__}: {str(e)}")
        print(f"[RAG-ENDPOINT] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/ingest-sync/{document_id}")
async def ingest_document_sync_endpoint(
    document_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Synchronously ingest a document (waits for completion).

    Useful for testing or when you need to wait for ingestion to complete.
    """
    try:
        # Verify document exists and belongs to user
        doc_response = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()

        if not doc_response.data:
            raise HTTPException(status_code=404, detail="Document not found")

        document = doc_response.data[0]
        project_id = document.get("project_id")

        if not project_id:
            raise HTTPException(
                status_code=400,
                detail="Document must be attached to a project before ingestion"
            )

        # Run ingestion synchronously
        result = await ingest_document(document_id, project_id)

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")


@router.post("/retrieve")
async def retrieve_endpoint(
    project_id: str,
    query: str,
    limit: Optional[int] = 5,
    user_id: str = Depends(get_current_user)
):
    """
    Retrieve relevant document chunks for a query.

    This endpoint performs semantic search without generating an answer.
    Useful for seeing what context would be used for a query.
    """
    try:
        # Verify project belongs to user
        project_response = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()

        if not project_response.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Retrieve chunks
        chunks = retrieve_relevant_chunks(project_id, query, limit=limit)

        return {
            "query": query,
            "project_id": project_id,
            "chunks": chunks,
            "num_chunks": len(chunks)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")


@router.post("/query")
async def rag_query_endpoint(
    project_id: str,
    query: str,
    model: Optional[str] = "gpt-5.2-chat-latest",
    max_chunks: Optional[int] = 5,
    user_id: str = Depends(get_current_user)
):
    """
    Ask a question about project documents using RAG.

    This endpoint:
    1. Retrieves relevant chunks using vector search
    2. Builds context from chunks
    3. Generates answer using OpenAI chat completion

    Perfect for frontend chat UI.
    """
    try:
        # Verify project belongs to user
        project_response = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()

        if not project_response.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Generate RAG answer
        result = generate_rag_answer(
            project_id=project_id,
            query=query,
            model=model,
            max_chunks=max_chunks
        )

        return {
            "query": query,
            "project_id": project_id,
            **result
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG query failed: {str(e)}")


@router.get("/status/{document_id}")
async def get_ingestion_status(
    document_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get the ingestion status of a document.

    Returns the document status and metadata including chunk count.
    """
    try:
        # Get document
        doc_response = supabase.table("documents").select("*").eq("id", document_id).eq("user_id", user_id).execute()

        if not doc_response.data:
            raise HTTPException(status_code=404, detail="Document not found")

        document = doc_response.data[0]

        # Get chunk count
        chunk_response = supabase.table("document_chunks").select("id", count="exact").eq("document_id", document_id).execute()

        chunk_count = chunk_response.count if hasattr(chunk_response, 'count') else 0

        return {
            "document_id": document_id,
            "status": document.get("status"),
            "metadata": document.get("metadata", {}),
            "chunk_count": chunk_count,
            "created_at": document.get("created_at"),
            "updated_at": document.get("updated_at")
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status check failed: {str(e)}")
