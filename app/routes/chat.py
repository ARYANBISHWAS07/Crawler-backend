"""
Chat routes for collection-based conversations.
Uses Socket.IO for real-time messaging and HTTP endpoints for REST API.
"""
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid

from app import collection_store
from app import vector_store
from app import llm_service

router = APIRouter(prefix="/chat", tags=["chat"])

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


# Message Endpoints (REST API alternative to Socket.IO)

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
    # Verify collection
    collection = await collection_store.get_collection_by_id(collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    
    # Verify session
    session = await collection_store.get_chat_session(collection_id, session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found"
        )
    
    collection_name = collection.get('name')
    
    # Create and save user message
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
        # Get context from vector store
        context = vector_store.get_context_for_question(
            query=req.message,
            top_k=req.top_k,
            collection_name=collection_name
        )
        
        # Get source documents
        sources = vector_store.search(
            query=req.message,
            top_k=req.top_k,
            collection_name=collection_name
        )
        
        # Generate AI response
        answer = llm_service.generate_chat_response(
            question=req.message,
            context=context
        )
        
        # Create and save assistant message
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
