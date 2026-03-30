"""
Chat routes for collection-based conversations.
Uses Socket.IO for real-time messaging and HTTP endpoints for REST API.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid
import asyncio

from app import collection_store
from app import vector_store
from app import llm_service
from app.extensions import scrape_single_page
from app.models import (
    WebsiteMessageRequest,
    WebsiteSessionCreateRequest,
    WebsiteSessionSummary,
)
from app.routes.scrape import (
    append_temp_website_message,
    create_temp_website_session,
    delete_temp_website_session,
    extract_scraped_text,
    get_temp_website_session,
    list_temp_website_sessions,
)

router = APIRouter(prefix="/chat", tags=["chat"])
WEBSITE_CONTEXT_LIMIT = 12000

class CreateSessionRequest(BaseModel):
    collection_id: str
    title: Optional[str] = None


class SendMessageRequest(BaseModel):
    message: str
    top_k: int = 3


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    sources: List[dict] = Field(default_factory=list)
    created_at: str


class SessionResponse(BaseModel):
    id: str
    collection_id: str
    title: Optional[str]
    messages: List[dict] = Field(default_factory=list)
    created_at: str
    updated_at: str


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(req: CreateSessionRequest):
    """Create a new chat session for a collection."""
    # Verify collection exists
    collection = await collection_store.get_collection_by_id(req.collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    
    session_id = str(uuid.uuid4())
    session_data = {
        "id": session_id,
        "collection_id": req.collection_id,
        "title": req.title or "New Chat",
        "messages": [],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    await collection_store.create_chat_session(req.collection_id, session_data)
    
    return session_data


@router.get("/sessions/{collection_id}")
async def get_sessions(collection_id: str):
    """Get all chat sessions for a collection."""
    collection = await collection_store.get_collection_by_id(collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    
    sessions = await collection_store.get_all_chat_sessions(collection_id)
    return {"collection_id": collection_id, "sessions": sessions}


@router.get("/session/{collection_id}/{session_id}")
async def get_session(collection_id: str, session_id: str):
    """Get a specific chat session with all messages."""
    session = await collection_store.get_chat_session(collection_id, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return session


@router.delete("/session/{collection_id}/{session_id}")
async def delete_session(collection_id: str, session_id: str):
    """Delete a chat session."""
    deleted = await collection_store.delete_chat_session(collection_id, session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return {"message": "Session deleted", "session_id": session_id}


@router.post("/message/{collection_id}/{session_id}")
async def send_message(
    collection_id: str,
    session_id: str,
    req: SendMessageRequest
):
    """
    Send a message and get AI response (REST API).
    For real-time updates, use Socket.IO instead.
    """
    collection = await collection_store.get_collection_by_id(collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )

    session = await collection_store.get_chat_session(collection_id, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    collection_name = collection.get('name')
    user_message_id = str(uuid.uuid4())
    user_message = {
        "id": user_message_id,
        "role": "user",
        "content": req.message,
        "sources": [],
        "created_at": datetime.utcnow().isoformat()
    }
    await collection_store.add_message_to_session(collection_id, session_id, user_message)
    
    try:
        context, sources = await asyncio.to_thread(
            vector_store.get_context_and_sources,
            req.message,
            req.top_k,
            collection_name,
        )
        answer = await asyncio.to_thread(
            llm_service.generate_chat_response,
            question=req.message,
            context=context,
        )
        

        assistant_message_id = str(uuid.uuid4())
        assistant_message = {
            "id": assistant_message_id,
            "role": "assistant",
            "content": answer,
            "sources": [
                {"url": s["url"], "title": s["title"], "similarity": s["similarity"]}
                for s in sources
            ],
            "created_at": datetime.utcnow().isoformat()
        }
        await collection_store.add_message_to_session(collection_id, session_id, assistant_message)
        
        # Emit via Socket.IO if available
        try:
            from app.socketio_manager import sio
            room = f"chat_{collection_id}_{session_id}"
            await sio.emit('new_message', {
                'session_id': session_id,
                'message': assistant_message
            }, room=room)
        except:
            pass  # Socket.IO not available
        
        return {
            "user_message": user_message,
            "assistant_message": assistant_message
        }
        
    except ValueError as e:
        # AI service not configured
        return {
            "user_message": user_message,
            "assistant_message": None,
            "error": str(e)
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate response: {str(e)}"
        )


@router.get("/history/{collection_id}/{session_id}")
async def get_chat_history(collection_id: str, session_id: str):
    """Get full chat history for a session."""
    session = await collection_store.get_chat_session(collection_id, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    return {
        "session_id": session_id,
        "collection_id": collection_id,
        "messages": session.get("messages", [])
    }



def _website_session_summary(session: dict) -> dict:
    summary = WebsiteSessionSummary(
        id=session["id"],
        website_session_name=session["website_session_name"],
        user_id=session.get("user_id"),
        url=session["url"],
        domain=session.get("domain") or "",
        context_length=len(session.get("context", "")),
        message_count=len(session.get("messages", [])),
        created_at=session["created_at"],
        updated_at=session["updated_at"],
    )
    return summary.model_dump()


@router.post("/website/sessions", status_code=status.HTTP_201_CREATED)
async def create_website_session(req: WebsiteSessionCreateRequest):
    """Create a temporary website chat session by scraping a single URL."""
    try:
        raw = await scrape_single_page(str(req.url))
        context = extract_scraped_text(raw).strip()
        if not context:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract readable context from the URL.",
            )
        session = create_temp_website_session(
            str(req.url),
            context,
            website_session_name=req.website_session_name,
            user_id=req.user_id,
        )
        return {"session": _website_session_summary(session)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create website session: {str(e)}",
        )


@router.get("/website/sessions")
async def get_website_sessions():
    sessions = list_temp_website_sessions()
    return {"sessions": [_website_session_summary(s) for s in sessions]}


@router.get("/website/session/{session_id}")
async def get_website_session(session_id: str):
    session = get_temp_website_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Website session not found",
        )
    return {
        "session": _website_session_summary(session),
        "messages": session.get("messages", []),
    }


@router.delete("/website/session/{session_id}")
async def delete_website_session(session_id: str):
    deleted = delete_temp_website_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Website session not found",
        )
    return {"message": "Website session deleted", "session_id": session_id}


@router.post("/website/message/{session_id}")
async def send_website_message(session_id: str, req: WebsiteMessageRequest):
    """
    Send a chat message against temporary context stored for a scraped website session.
    """
    session = get_temp_website_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Website session not found",
        )

    user_message = {
        "id": str(uuid.uuid4()),
        "role": "user",
        "content": req.message,
        "sources": [],
        "created_at": datetime.utcnow().isoformat(),
    }
    append_temp_website_message(session_id, user_message)

    try:
        context = (session.get("context", "") or "")[:WEBSITE_CONTEXT_LIMIT]
        answer = await asyncio.to_thread(
            llm_service.generate_chat_response,
            question=req.message,
            context=context,
        )

        assistant_message = {
            "id": str(uuid.uuid4()),
            "role": "assistant",
            "content": answer,
            "sources": [
                {
                    "url": session.get("url", ""),
                    "title": session.get("website_session_name", "Website"),
                    "similarity": 1.0,
                }
            ],
            "created_at": datetime.utcnow().isoformat(),
        }
        append_temp_website_message(session_id, assistant_message)

        try:
            from app.socketio_manager import sio

            room = f"website_chat_{session_id}"
            await sio.emit(
                "new_message",
                {
                    "session_id": session_id,
                    "message": assistant_message,
                },
                room=room,
            )
        except Exception:
            pass

        return {
            "user_message": user_message,
            "assistant_message": assistant_message,
        }
    except ValueError as e:
        return {
            "user_message": user_message,
            "assistant_message": None,
            "error": str(e),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate response: {str(e)}",
        )


@router.get("/website/history/{session_id}")
async def get_website_chat_history(session_id: str):
    session = get_temp_website_session(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Website session not found",
        )
    return {
        "session_id": session_id,
        "url": session.get("url"),
        "messages": session.get("messages", []),
    }
