from datetime import datetime
import uuid
import os
from pymongo import MongoClient

def save_chunk_questionnaire(
    collection_id: str,
    questionnaire: dict,
    metadata: dict,
    chunk_text: str = "",
) -> bool:
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name = os.getenv("DATABASE_NAME", "scrapper_db")
    sync_client = MongoClient(mongodb_url)
    chunk_collection = sync_client[database_name]["chunk_question"]

    document = {
        "id": str(uuid.uuid4()),
        "collection_id": collection_id,
        "questionnaire": questionnaire.get("questions", []) if isinstance(questionnaire, dict) else [],
        "metadata": metadata,
        "chunk_excerpt": (chunk_text or "").strip()[:1200],
        "created_at": datetime.utcnow()
    }

    chunk_collection.insert_one(document)
    sync_client.close()
    return True
