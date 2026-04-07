from datetime import datetime
import uuid

from app.database import put_item


def save_chunk_questionnaire(
    collection_id: str,
    questionnaire: str,
    metadata: dict
) -> bool:
    item_id = str(uuid.uuid4())
    document = {
        "PK": item_id,
        "id": item_id,
        "collection_id": collection_id,
        "questionnaire": questionnaire,
        "metadata": metadata,
        "created_at": datetime.utcnow().isoformat(),
    }
    put_item("chunk_question", document)
    return True
