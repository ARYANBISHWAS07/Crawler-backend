from datetime import datetime
import uuid

def save_chunk_questionnaire(
    collection_id: str,
    # chunk_content: str,
    questionnaire: str,
    metadata: dict
) -> bool:
    from app.database import get_collection

    chunk_collection = get_collection("chunk_question")

    document = {
        "id": str(uuid.uuid4()),
        "collection_id": collection_id,
        # "chunk_content": chunk_content,
        "questionnaire": questionnaire,
        "metadata": metadata,
        "created_at": datetime.utcnow()
    }

    chunk_collection.insert_one(document)
    return True