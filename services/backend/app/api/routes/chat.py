from fastapi import APIRouter, HTTPException, Depends, Header, Query, Request
from fastapi.responses import StreamingResponse
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator, limiter
from app.core.openai_client import get_async_openai_client, get_completion_params
from typing import Optional, List, AsyncGenerator
import json
import asyncio
from datetime import datetime
from starlette.background import BackgroundTask
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Initialize OpenAI client
openai_client = get_async_openai_client()

# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

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


@router.get("/projects/{project_id}/messages")
def get_chat_history(
    project_id: str,
    limit: int = Query(50, ge=1, le=100, description="Number of messages to return (max 100)"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    user_id: str = Depends(get_current_user)
):
    """
    Get chat message history for a project with pagination.

    Pagination:
    - limit: Number of messages to return (default: 50, max: 100)
    - offset: Number of messages to skip (default: 0)
    - Returns total count and has_more flag

    Messages are ordered by created_at (oldest first for conversation flow).
    """
    try:
        # Verify project belongs to user
        project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get total count for pagination
        count_query = (supabase.table("chat_messages")
            .select("id", count="exact")
            .eq("project_id", project_id)
            .eq("user_id", user_id))
        count_response = count_query.execute()
        total = count_response.count if hasattr(count_response, 'count') else 0

        # Get paginated messages
        messages_res = (supabase.table("chat_messages")
            .select("*")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .range(offset, offset + limit - 1)
            .execute())

        return {
            "data": messages_res.data,
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CHAT] Error getting chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/messages")
@limiter.limit("30/minute")  # Max 30 chat messages per minute
def save_chat_message(
    request: Request,
    project_id: str,
    role: str,
    content: str,
    sources: Optional[List[dict]] = None,
    model: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """
    Save a chat message to the database
    """
    try:
        # Verify project belongs to user
        project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Save message
        message_data = {
            "project_id": project_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "sources": sources,
            "model": model,
            "created_at": datetime.utcnow().isoformat()
        }

        result = supabase.table("chat_messages").insert(message_data).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to save message")

        return result.data[0]
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CHAT] Error saving message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def stream_chat_response(
    project_id: str,
    query: str,
    user_id: str,
    model: str = "gpt-4o",
    max_chunks: int = 5,
    document_id: str = None,
    include_drafts: bool = False,
    draft_id: str = None
) -> AsyncGenerator[str, None]:
    """
    Stream chat response from OpenAI with RAG context

    Args:
        document_id: Optional UUID to search within a single document only.
                    If None, searches across all documents in the project.
        include_drafts: Whether to include draft content in search (default: False)
        draft_id: Optional UUID to search within a specific draft only

    Validates: Requirements 6.2, 6.4 - Draft-aware chat
    """
    try:
        # Get RAG context from vector search (draft-aware if requested)
        from app.services.rag_retrieval import retrieve_relevant_chunks, retrieve_relevant_chunks_with_drafts

        if include_drafts or draft_id:
            chunks = retrieve_relevant_chunks_with_drafts(
                project_id=project_id,
                query=query,
                limit=max_chunks,
                include_drafts=include_drafts,
                include_literature=True,
                draft_id=draft_id
            )
        else:
            chunks = retrieve_relevant_chunks(project_id, query, limit=max_chunks, document_id=document_id)

        # Build context from chunks with numbered citations (draft-aware)
        context_parts = []
        sources = []
        for idx, chunk in enumerate(chunks, 1):
            source_type = chunk.get("source_type", "literature")
            source_icon = chunk.get("source_icon", "📚")
            source_title = chunk.get("source_title", chunk.get("document_title", "Unknown"))

            if source_type == "draft":
                label = f"[{idx}] {source_icon} FROM YOUR DRAFT: {source_title}"
            else:
                label = f"[{idx}] {source_icon} FROM LITERATURE: {source_title}"

            context_parts.append(f"{label}\\n{chunk['content']}")

            # Enhanced source metadata
            sources.append({
                "citation_number": idx,
                "source_type": source_type,
                "source_title": source_title,
                "document_id": chunk.get("document_id"),
                "draft_id": chunk.get("draft_id"),
                "chunk_id": chunk.get("id"),
                "similarity": chunk.get("similarity"),
                "content_preview": chunk['content'][:200] + "..." if len(chunk['content']) > 200 else chunk['content']
            })

        context = "\\n\\n---\\n\\n".join(context_parts)

        # Get recent chat history for context
        history_res = (supabase.table("chat_messages")
            .select("role, content")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .limit(10)
            .execute())

        # Build messages for OpenAI (draft-aware system prompt if drafts included)
        if include_drafts or draft_id:
            system_content = f"""You are a helpful AI research assistant helping users with their research drafts. You have access to both the user's draft content and their literature database.

Context from sources:
{context}

IMPORTANT DRAFT AWARENESS:
- Sources marked "FROM YOUR DRAFT" are the user's own writing
- Sources marked "FROM LITERATURE" are published research papers
- When citing the user's draft, use language like "In your draft..." or "You wrote..."
- When citing literature, use traditional academic citations with [N]

CITATION REQUIREMENTS:
- When you reference information from ANY source, add a citation using [N] format
- Place citations immediately after the relevant statement or claim
- Distinguish between user's draft and literature when responding
- You can cite the same source multiple times if needed
- If a statement uses information from multiple sources, cite all of them: [1][2]

FORMATTING REQUIREMENTS:
- Use proper formatting: **bold** for emphasis, lists where appropriate
- Keep responses clear and well-structured
- Always cite your sources when making specific claims
- Be helpful and specific when referencing the user's draft

If the context doesn't contain enough information to answer the question, say so clearly.

Example response format:
In your draft, you mention X [1]. This aligns with recent research showing Y [2]. Multiple studies confirm this relationship [2][3]."""
        else:
            system_content = f"""You are a helpful AI research assistant. Answer questions based on the provided context from research documents.

Context from documents:
{context}

CITATION REQUIREMENTS:
- When you reference information from a source, add a citation using the format [N] where N is the source number shown in the context above.
- Place citations immediately after the relevant statement or claim.
- You can cite the same source multiple times if needed.
- If a statement uses information from multiple sources, cite all of them: [1][2]

FORMATTING REQUIREMENTS:
- Use proper formatting: **bold** for emphasis, lists where appropriate
- Keep responses clear and well-structured
- Always cite your sources when making specific claims

If the context doesn't contain enough information to answer the question, say so clearly.

Example response format:
The study found that caffeine improves cognitive performance [1] and increases alertness [2]. Multiple sources confirm these effects [1][3]."""

        messages = [
            {
                "role": "system",
                "content": system_content
            }
        ]

        # Add conversation history
        if history_res.data:
            for msg in history_res.data:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })

        # Add current query
        messages.append({
            "role": "user",
            "content": query
        })

        # Stream response from OpenAI
        full_response = ""

        stream = await openai_client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            temperature=0.7,
            max_tokens=1000,
            **get_completion_params()  # Enable zero data retention
        )

        # Send sources first
        yield json.dumps({"type": "sources", "data": sources}) + "\n"

        # Stream tokens
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_response += token
                yield json.dumps({"type": "token", "data": token}) + "\n"

        # Send completion signal
        yield json.dumps({"type": "done", "data": full_response}) + "\n"

        # Save assistant message to database
        save_chat_message(
            project_id=project_id,
            role="assistant",
            content=full_response,
            sources=sources,
            model=model,
            user_id=user_id
        )

        # Track quota usage and OpenAI costs
        try:
            from app.services.quota_management import increment_quota_usage, track_openai_usage

            # Increment quota counter
            await increment_quota_usage(user_id, "chat")
            print(f"[CHAT] Quota incremented for user_id={user_id}")

            # Estimate token usage for streaming responses
            # Note: OpenAI streaming doesn't return exact token counts in the response.
            # We use rough estimation based on character count:
            # ~4 characters per token (average for English text)
            # Future improvement: Use tiktoken library for accurate token counting

            # Estimate prompt tokens (system prompt + history + query + context)
            prompt_chars = len(system_content) + len(query) + sum(len(msg.get("content", "")) for msg in messages)
            estimated_prompt_tokens = prompt_chars // 4

            # Estimate completion tokens from response
            completion_chars = len(full_response)
            estimated_completion_tokens = completion_chars // 4

            await track_openai_usage(
                user_id=user_id,
                operation_type="chat",
                model=model,
                prompt_tokens=estimated_prompt_tokens,
                completion_tokens=estimated_completion_tokens,
                project_id=project_id
            )
            print(f"[CHAT] OpenAI usage tracked: ~{estimated_prompt_tokens + estimated_completion_tokens} tokens (estimated)")

        except Exception as tracking_error:
            # Don't fail the chat if tracking fails
            print(f"[CHAT] WARNING: Failed to track quota/usage: {tracking_error}")

    except Exception as e:
        print(f"[CHAT] Stream error: {e}")
        yield json.dumps({"type": "error", "data": str(e)}) + "\n"


@router.post("/projects/{project_id}/query-stream")
async def query_stream(
    project_id: str,
    query: str,
    model: str = "gpt-4o",
    max_chunks: int = 5,
    document_id: Optional[str] = None,
    include_drafts: bool = False,
    draft_id: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """
    Stream RAG query response with real-time tokens (draft-aware)

    Args:
        document_id: Optional UUID to search within a single document only.
                    If None, searches across all documents in the project.
        include_drafts: Whether to include draft content in search (default: False)
        draft_id: Optional UUID to search within a specific draft only

    Validates: Requirements 6.2, 6.4 - Draft-aware chat API
    """
    from app.services.quota_management import check_quota, QuotaExceededError

    try:
        # CHECK QUOTA BEFORE PROCESSING
        try:
            await check_quota(user_id, "chat")
            print(f"[CHAT] Quota check passed for user_id={user_id}")
        except QuotaExceededError as qe:
            print(f"[CHAT] Quota exceeded for user_id={user_id}: {qe}")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "quota_exceeded",
                    "message": str(qe),
                    "quota_type": qe.quota_type,
                    "limit": qe.limit,
                    "current": qe.current
                }
            )

        # Verify project belongs to user
        project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Save user message first
        save_chat_message(
            project_id=project_id,
            role="user",
            content=query,
            user_id=user_id
        )

        # Return streaming response with proper headers to prevent buffering
        return StreamingResponse(
            stream_chat_response(project_id, query, user_id, model, max_chunks, document_id, include_drafts, draft_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[CHAT] Error in query stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/projects/{project_id}/messages")
def clear_chat_history(project_id: str, user_id: str = Depends(get_current_user)):
    """
    Clear all chat messages for a project
    """
    try:
        # Verify project belongs to user
        project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Delete all messages
        (supabase.table("chat_messages")
            .delete()
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .execute())

        return {"message": "Chat history cleared"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CHAT] Error clearing chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
