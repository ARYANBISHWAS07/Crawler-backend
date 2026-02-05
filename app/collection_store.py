"""
Collection storage service using MongoDB.
Manages collections and their associated chat histories.
"""
import json
from datetime import datetime
from typing import Optional, List, Dict
import uuid


async def create_collection(collection_data: dict) -> dict:
    """Create a new collection in MongoDB."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    await collections.insert_one(collection_data.copy())
    return collection_data


async def get_collection_by_id(collection_id: str) -> Optional[dict]:
    """Get collection by ID."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    collection = await collections.find_one({"id": collection_id})
    
    if collection:
        collection.pop("_id", None)
        return collection
    return None


async def get_collection_by_name(name: str) -> Optional[dict]:
    """Get collection by name."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    collection = await collections.find_one({"name": name})
    
    if collection:
        collection.pop("_id", None)
        return collection
    return None


async def update_collection(collection_id: str, updates: dict) -> Optional[dict]:
    """Update collection in MongoDB."""
    from app.database import get_collection
    
    updates["updated_at"] = datetime.utcnow().isoformat()
    
    collections = get_collection("collections")
    result = await collections.find_one_and_update(
        {"id": collection_id},
        {"$set": updates},
        return_document=True
    )
    
    if result:
        result.pop("_id", None)
        return result
    return None


def update_collection_sync(collection_id: str, updates: dict) -> bool:
    """Synchronous collection update for use in background tasks."""
    from pymongo import MongoClient
    import os
    
    updates["updated_at"] = datetime.utcnow().isoformat()
    
    try:
        mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
        database_name = os.getenv("DATABASE_NAME", "scrapper_db")
        
        sync_client = MongoClient(mongodb_url)
        db = sync_client[database_name]
        collections = db["collections"]
        
        collections.update_one(
            {"id": collection_id},
            {"$set": updates}
        )
        sync_client.close()
        return True
    except Exception as e:
        print(f"MongoDB sync update error: {e}")
        return False


async def get_all_collections(user_id: Optional[str] = None, limit: int = 100) -> List[dict]:
    """Get all collections, optionally filtered by user."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    
    query = {}
    if user_id:
        query["user_id"] = user_id
    
    cursor = collections.find(query).sort("created_at", -1).limit(limit)
    
    result = []
    async for coll in cursor:
        coll.pop("_id", None)
        result.append(coll)
    
    return result


async def delete_collection(collection_id: str) -> bool:
    """Delete a collection."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    result = await collections.delete_one({"id": collection_id})
    return result.deleted_count > 0


# Chat Session Management

async def create_chat_session(collection_id: str, session_data: dict) -> dict:
    """Create a new chat session within a collection."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    
    await collections.update_one(
        {"id": collection_id},
        {
            "$push": {"chat_sessions": session_data},
            "$set": {"updated_at": datetime.utcnow().isoformat()}
        }
    )
    
    return session_data


async def get_chat_session(collection_id: str, session_id: str) -> Optional[dict]:
    """Get a specific chat session from a collection."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    collection = await collections.find_one(
        {"id": collection_id, "chat_sessions.id": session_id},
        {"chat_sessions.$": 1}
    )
    
    if collection and "chat_sessions" in collection:
        return collection["chat_sessions"][0]
    return None


async def get_all_chat_sessions(collection_id: str) -> List[dict]:
    """Get all chat sessions for a collection."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    collection = await collections.find_one({"id": collection_id})
    
    if collection:
        return collection.get("chat_sessions", [])
    return []


async def add_message_to_session(
    collection_id: str, 
    session_id: str, 
    message_data: dict
) -> bool:
    """Add a message to an existing chat session."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    
    result = await collections.update_one(
        {"id": collection_id, "chat_sessions.id": session_id},
        {
            "$push": {"chat_sessions.$.messages": message_data},
            "$set": {
                "chat_sessions.$.updated_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    )
    
    return result.modified_count > 0


async def update_session_title(collection_id: str, session_id: str, title: str) -> bool:
    """Update the title of a chat session."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    
    result = await collections.update_one(
        {"id": collection_id, "chat_sessions.id": session_id},
        {
            "$set": {
                "chat_sessions.$.title": title,
                "chat_sessions.$.updated_at": datetime.utcnow().isoformat()
            }
        }
    )
    
    return result.modified_count > 0


async def delete_chat_session(collection_id: str, session_id: str) -> bool:
    """Delete a chat session from a collection."""
    from app.database import get_collection
    
    collections = get_collection("collections")
    
    result = await collections.update_one(
        {"id": collection_id},
        {
            "$pull": {"chat_sessions": {"id": session_id}},
            "$set": {"updated_at": datetime.utcnow().isoformat()}
        }
    )
    
    return result.modified_count > 0
