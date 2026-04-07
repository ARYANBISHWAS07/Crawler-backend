"""
Job storage service using DynamoDB for persistence.
"""
import asyncio
from datetime import datetime
from typing import List, Optional
import uuid

from app.database import get_by_id, put_item, scan_table, update_item, delete_item


async def create_job(job_data: dict) -> dict:
    job_id = job_data.get("id") or job_data.get("PK") or str(uuid.uuid4())
    document = {
        "PK": job_id,
        "id": job_id,
        **job_data,
    }
    await asyncio.to_thread(put_item, "scrape_jobs", document)
    return document


async def get_job(job_id: str) -> Optional[dict]:
    return await asyncio.to_thread(get_by_id, "scrape_jobs", job_id)


async def update_job(job_id: str, updates: dict) -> Optional[dict]:
    updates["updated_at"] = datetime.utcnow().isoformat()
    return await asyncio.to_thread(update_item, "scrape_jobs", {"PK": job_id}, updates)


def update_job_sync(job_id: str, updates: dict) -> bool:
    updates["updated_at"] = datetime.utcnow().isoformat()
    try:
        return update_item("scrape_jobs", {"PK": job_id}, updates) is not None
    except Exception as exc:
        print(f"DynamoDB sync update error: {exc}")
        return False


async def get_all_jobs(limit: int = 100) -> List[dict]:
    jobs = await asyncio.to_thread(scan_table, "scrape_jobs", None, limit)
    jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return jobs[:limit]


async def delete_job(job_id: str) -> bool:
    return await asyncio.to_thread(delete_item, "scrape_jobs", {"PK": job_id})
