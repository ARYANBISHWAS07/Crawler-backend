import uuid
import subprocess
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List

from app.job_store import JOB_STORE, JobStatus

router = APIRouter(prefix="/spider", tags=["spider"])

class CrawlRequest(BaseModel):
    urls: List[str]
    depth: int = 1

@router.post("/crawl")
def start_crawl(data: CrawlRequest):
    job_id = str(uuid.uuid4())

    JOB_STORE[job_id] = {"status": JobStatus.pending}

    subprocess.Popen([
        "python",
        "crawler/run_spider.py",
        job_id,
        ",".join(data.urls),
        str(data.depth)
    ])

    return {
        "job_id": job_id,
        "status": JobStatus.pending
    }
