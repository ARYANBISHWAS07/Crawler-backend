"""
Job storage service using MongoDB for persistence.
"""
import json
import os
from datetime import datetime
from typing import Optional, Dict, List
from dotenv import load_dotenv

load_dotenv()


async def create_job(job_data: dict) -> dict:
    """
    Create a new job in MongoDB.
    Returns the created job data.
    """
    from app.database import get_collection
    
    # Store in MongoDB 
    jobs_collection = get_collection("scrape_jobs")
    await jobs_collection.insert_one(job_data.copy())
    
    return job_data


async def get_job(job_id: str) -> Optional[dict]:
    """
    Get job by ID from MongoDB.
    """
    from app.database import get_collection
    
    jobs_collection = get_collection("scrape_jobs")
    job = await jobs_collection.find_one({"id": job_id})
    
    if job:
        job.pop("_id", None)
        return job
    
    return None


async def update_job(job_id: str, updates: dict) -> Optional[dict]:
    """
    Update job in MongoDB.
    """
    from app.database import get_collection
    
    updates["updated_at"] = datetime.utcnow().isoformat()
    
    # Update in MongoDB
    jobs_collection = get_collection("scrape_jobs")
    result = await jobs_collection.find_one_and_update(
        {"id": job_id},
        {"$set": updates},
        return_document=True
    )
    
    if result:
        result.pop("_id", None)
        return result
    
    return None


def update_job_sync(job_id: str, updates: dict) -> bool:
    """
    Synchronous job update for use in background tasks.
    Uses PyMongo for sync MongoDB update.
    """
    from pymongo import MongoClient
    
    updates["updated_at"] = datetime.utcnow().isoformat()
    
    # Update MongoDB using sync PyMongo client
    try:
        mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
        database_name = os.getenv("DATABASE_NAME", "scrapper_db")
        
        sync_client = MongoClient(mongodb_url)
        db = sync_client[database_name]
        jobs_collection = db["scrape_jobs"]
        
        jobs_collection.update_one(
            {"id": job_id},
            {"$set": updates}
        )
        sync_client.close()
    except Exception as e:
        print(f"MongoDB sync update error: {e}")
        return False
    
    return True


async def get_all_jobs(limit: int = 100) -> List[dict]:
    """
    Get all jobs from MongoDB.
    """
    from app.database import get_collection
    
    jobs_collection = get_collection("scrape_jobs")
    cursor = jobs_collection.find().sort("created_at", -1).limit(limit)
    
    jobs = []
    async for job in cursor:
        job.pop("_id", None)
        jobs.append(job)
    
    return jobs


async def delete_job(job_id: str) -> bool:
    """
    Delete job from MongoDB.
    """
    from app.database import get_collection
    
    jobs_collection = get_collection("scrape_jobs")
    result = await jobs_collection.delete_one({"id": job_id})
    
    return result.deleted_count > 0
# app/job_store.py
from enum import Enum

class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"

JOB_STORE = {}
