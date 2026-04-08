import asyncio
from datetime import datetime
from typing import List
import uuid

from app.database import delete_item, get_scan_attr, put_item, scan_table


async def replace_collection_node_summaries(collection_id: str, nodes: List[dict]) -> int:
    existing = await asyncio.to_thread(
        scan_table,
        "learning_node_summaries",
        get_scan_attr("collection_id").eq(collection_id),
    )
    for item in existing:
        await asyncio.to_thread(delete_item, "learning_node_summaries", {"PK": item["PK"]})

    now = datetime.utcnow().isoformat()
    documents = []
    for node in nodes:
        summary_text = (node.get("summary") or "").strip()
        if not summary_text:
            continue

        item_id = str(uuid.uuid4())
        document = {
            "PK": item_id,
            "id": item_id,
            "collection_id": collection_id,
            "node_id": node.get("id", ""),
            "node_label": node.get("label", ""),
            "summary": summary_text,
            "module": node.get("module"),
            "difficulty": node.get("difficulty"),
            "node_type": node.get("type"),
            "created_at": now,
            "updated_at": now,
        }
        await asyncio.to_thread(put_item, "learning_node_summaries", document)
        documents.append(document)

    return len(documents)


async def get_collection_node_summaries(collection_id: str) -> List[dict]:
    result = await asyncio.to_thread(
        scan_table,
        "learning_node_summaries",
        get_scan_attr("collection_id").eq(collection_id),
    )
    result.sort(key=lambda item: item.get("created_at", ""))
    return result


async def get_collection_node_summary(collection_id: str, node_id: str):
    items = await asyncio.to_thread(
        scan_table,
        "learning_node_summaries",
        get_scan_attr("collection_id").eq(collection_id) & get_scan_attr("node_id").eq(node_id),
        1,
    )
    return items[0] if items else None
