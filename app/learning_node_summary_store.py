from datetime import datetime
from typing import List
import uuid


async def replace_collection_node_summaries(collection_id: str, nodes: List[dict]) -> int:
    """
    Replace all saved learning node summaries for a collection.
    Returns number of summaries saved.
    """
    from app.database import get_collection

    summaries_collection = get_collection("learning_node_summaries")

    await summaries_collection.delete_many({"collection_id": collection_id})

    now = datetime.utcnow()
    documents = []
    for node in nodes:
        summary_text = (node.get("summary") or "").strip()
        if not summary_text:
            continue

        documents.append({
            "id": str(uuid.uuid4()),
            "collection_id": collection_id,
            "node_id": node.get("id", ""),
            "node_label": node.get("label", ""),
            "summary": summary_text,
            "module": node.get("module"),
            "difficulty": node.get("difficulty"),
            "node_type": node.get("type"),
            "created_at": now,
            "updated_at": now,
        })

    if documents:
        await summaries_collection.insert_many(documents)

    return len(documents)


async def get_collection_node_summaries(collection_id: str) -> List[dict]:
    """Get all learning node summaries for a collection."""
    from app.database import get_collection

    summaries_collection = get_collection("learning_node_summaries")
    cursor = summaries_collection.find({"collection_id": collection_id}).sort("created_at", 1)

    result: List[dict] = []
    async for item in cursor:
        item.pop("_id", None)
        result.append(item)
    return result


async def get_collection_node_summary(collection_id: str, node_id: str):
    """Get summary for one node in a collection."""
    from app.database import get_collection

    summaries_collection = get_collection("learning_node_summaries")
    item = await summaries_collection.find_one({
        "collection_id": collection_id,
        "node_id": node_id,
    })
    if not item:
        return None
    item.pop("_id", None)
    return item
