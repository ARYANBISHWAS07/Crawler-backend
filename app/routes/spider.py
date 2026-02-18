import uuid
import subprocess
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import asyncio
from app.job_store import create_job, get_job

router = APIRouter(prefix="/spider", tags=["spider"])

class CrawlRequest(BaseModel):
    urls: List[str]
    depth: int = 1

@router.post("/crawl")
async def start_crawl(data: CrawlRequest):
    job_id = str(uuid.uuid4())
    job_data = {
        "id": job_id,
        "status": "pending",
        "created_at": None,
        "urls": data.urls,
        "depth": data.depth
    }
    try:
        job_data["created_at"] = asyncio.get_event_loop().time()
        await create_job(job_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create job in DB: {e}")
    try:
        subprocess.Popen([
            "python",
            "crawler/run_spider.py",
            job_id,
            ",".join(data.urls),
            str(data.depth)
        ])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start crawler process: {e}")
    # Fetch and return the full job record
    job = await get_job(job_id)
    return job if job else job_data
