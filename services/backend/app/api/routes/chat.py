from fastapi import APIRouter, HTTPException, Depends, Header
from fastapi.responses import StreamingResponse
from app.core.supabase_client import supabase
from typing import Optional, List, AsyncGenerator
import json
import asyncio
from openai import AsyncOpenAI
import os
from datetime import datetime
from starlette.background import BackgroundTask

router = APIRouter()

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.split("Bearer ")[-1]
    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")


@router.get("/projects/{project_id}/messages")
def get_chat_history(project_id: str, limit: int = 50, user_id: str = Depends(get_current_user)):
    """
    Get chat message history for a project
    """
    try:
        # Verify project belongs to user
        project_res = supabase.table("projects").select("*").eq("id", project_id).eq("user_id", user_id).execute()
        if not project_res.data:
            raise HTTPException(status_code=404, detail="Project not found")

        # Get messages
        messages_res = (supabase.table("chat_messages")
            .select("*")
            .eq("project_id", project_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .limit(limit)
            .execute())

        return messages_res.data
    except HTTPException:
        raise
    except Exception as e:
        print(f"[CHAT] Error getting chat history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/messages")
def save_chat_message(
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
    document_id: str = None
) -> AsyncGenerator[str, None]:
    """
    Stream chat response from OpenAI with RAG context

    Args:
        document_id: Optional UUID to search within a single document only.
                    If None, searches across all documents in the project.
    """
    try:
        # Get RAG context from vector search
        from app.services.rag_retrieval import retrieve_relevant_chunks

        chunks = retrieve_relevant_chunks(project_id, query, limit=max_chunks, document_id=document_id)

        # Build context from chunks with numbered citations
        context_parts = []
        sources = []
        for idx, chunk in enumerate(chunks, 1):
            context_parts.append(f"[{idx}] Document: {chunk.get('document_title', 'Unknown')}\\n{chunk['content']}")
            sources.append({
                "citation_number": idx,
                "document_id": chunk.get("document_id"),
                "document_title": chunk.get("document_title"),
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

        # Build messages for OpenAI
        messages = [
            {
                "role": "system",
                "content": f"""You are a helpful AI research assistant. Answer questions based on the provided context from research documents.

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
            max_tokens=1000
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
    user_id: str = Depends(get_current_user)
):
    """
    Stream RAG query response with real-time tokens

    Args:
        document_id: Optional UUID to search within a single document only.
                    If None, searches across all documents in the project.
    """
    try:
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
            stream_chat_response(project_id, query, user_id, model, max_chunks, document_id),
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
