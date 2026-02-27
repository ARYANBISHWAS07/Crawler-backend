"""
Collection routes for managing scraped website collections.
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

from app.crawler import crawl_sync
from app import vector_store
from app import job_store
from app import collection_store
from app.socketio_manager import emit_job_update_sync, emit_collection_update_sync, emit_progress_sync
from app.crawler import handle_chunk
import asyncio

router = APIRouter(prefix="/collections", tags=["collections"])

CRAWL_LOG_STORE_LIMIT = 5000


class CreateCollectionRequest(BaseModel):
    name: str
    url: str
    max_pages: int = 0  # 0 = unlimited
    max_depth: int = 10
    user_id: Optional[str] = None


class UpdateCollectionRequest(BaseModel):
    name: Optional[str] = None


def run_collection_scrape_job(job_id: str, collection_id: str, req: CreateCollectionRequest):
    """Background task to scrape and process a collection with real-time progress."""
    try:
        # Update status to crawling
        job_store.update_job_sync(job_id, {"status": "crawling"})
        collection_store.update_collection_sync(collection_id, {"status": "crawling"})
        
        # Emit Socket.IO update
        emit_job_update_sync(job_id, {"status": "crawling", "message": "Starting to crawl website..."})
        emit_collection_update_sync(collection_id, {"status": "crawling"})
        
        # Progress callback for crawling
        def crawl_progress(current: int, total: int, message: str):
            emit_progress_sync(job_id, current, total, message, stage="crawling")
        
        # Run crawler and capture route-level crawl report
        crawl_report = crawl_sync(
            req.url,
            req.max_pages,
            req.max_depth,
            progress_callback=crawl_progress,
            include_report=True,
        )

        if isinstance(crawl_report, dict):
            data = crawl_report.get("pages", [])
            crawled_routes = crawl_report.get("crawled_routes", [])
            not_crawled_routes = crawl_report.get("not_crawled_routes", [])
            crawl_logs = crawl_report.get("crawl_logs", [])
            crawl_summary = crawl_report.get("summary", {})
        else:
            data = crawl_report
            crawled_routes = [page.get("url", "") for page in data if page.get("url")]
            not_crawled_routes = []
            crawl_logs = []
            crawl_summary = {}

        if len(crawl_logs) > CRAWL_LOG_STORE_LIMIT:
            crawl_logs = crawl_logs[-CRAWL_LOG_STORE_LIMIT:]

        routes_crawled_count = len(crawled_routes)
        routes_not_crawled_count = len(not_crawled_routes)
        crawl_logs_count = len(crawl_logs)
        
        # Update status to embedding
        job_store.update_job_sync(job_id, {
            "status": "embedding",
            "pages_crawled": len(data),
            "routes_crawled": crawled_routes,
            "routes_not_crawled": not_crawled_routes,
            "routes_crawled_count": routes_crawled_count,
            "routes_not_crawled_count": routes_not_crawled_count,
            "crawl_logs": crawl_logs,
            "crawl_logs_count": crawl_logs_count,
            "crawl_summary": crawl_summary,
        })
        collection_store.update_collection_sync(collection_id, {
            "status": "embedding",
            "routes_crawled_count": routes_crawled_count,
            "routes_not_crawled_count": routes_not_crawled_count,
        })
        
        emit_job_update_sync(job_id, {
            "status": "embedding",
            "pages_crawled": len(data),
            "routes_crawled_count": routes_crawled_count,
            "routes_not_crawled_count": routes_not_crawled_count,
            "crawl_logs_count": crawl_logs_count,
            "message": (
                f"Crawled {routes_crawled_count} route(s). "
                f"Not crawled: {routes_not_crawled_count}. Creating embeddings..."
            ),
        })
        emit_collection_update_sync(collection_id, {
            "status": "embedding",
            "pages_count": len(data),
            "routes_crawled_count": routes_crawled_count,
            "routes_not_crawled_count": routes_not_crawled_count,
        })
        
        # Progress callback for embedding
        def embed_progress(current: int, total: int, message: str):
            emit_progress_sync(job_id, current, total, message, stage="embedding")
        
        # Store in vector database using collection name with progress and creation of questionnaire
        pages_stored = vector_store.store_pages(data, req.name, progress_callback=embed_progress, chunk_callback=lambda chunk, metadata:
        handle_chunk(chunk, metadata, collection_id))

        # Update job as completed
        job_store.update_job_sync(job_id, {
            "status": "completed",
            "pages_stored": pages_stored,
            "collection_name": req.name,
            "results_count": len(data),
            "routes_crawled": crawled_routes,
            "routes_not_crawled": not_crawled_routes,
            "routes_crawled_count": routes_crawled_count,
            "routes_not_crawled_count": routes_not_crawled_count,
            "crawl_logs": crawl_logs,
            "crawl_logs_count": crawl_logs_count,
            "crawl_summary": crawl_summary,
        })
        
        # Update collection as completed
        collection_store.update_collection_sync(collection_id, {
            "status": "completed",
            "pages_count": pages_stored,
            "routes_crawled_count": routes_crawled_count,
            "routes_not_crawled_count": routes_not_crawled_count,
        })
        
        emit_job_update_sync(job_id, {
            "status": "completed",
            "pages_stored": pages_stored,
            "routes_crawled_count": routes_crawled_count,
            "routes_not_crawled_count": routes_not_crawled_count,
            "crawl_logs_count": crawl_logs_count,
            "percentage": 100,
            "message": f"Successfully stored {pages_stored} chunks. Ready to chat!"
        })
        emit_collection_update_sync(collection_id, {
            "status": "completed",
            "pages_count": pages_stored,
            "routes_crawled_count": routes_crawled_count,
            "routes_not_crawled_count": routes_not_crawled_count,
        })
        
    except Exception as e:
        error_msg = str(e)
        job_store.update_job_sync(job_id, {
            "status": "error",
            "error": error_msg
        })
        collection_store.update_collection_sync(collection_id, {
            "status": "error"
        })
        
        emit_job_update_sync(job_id, {"status": "error", "error": error_msg})
        emit_collection_update_sync(collection_id, {"status": "error", "error": error_msg})


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_collection(
    req: CreateCollectionRequest,
    background_tasks: BackgroundTasks
):
    """
    Create a new collection and start scraping the website.
    Returns both collection and job IDs for tracking.
    """
    # Check if collection name already exists
    existing = await collection_store.get_collection_by_name(req.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Collection '{req.name}' already exists"
        )
    
    collection_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    # Create collection
    collection_data = {
        "id": collection_id,
        "name": req.name,
        "url": req.url,
        "status": "pending",
        "pages_count": 0,
        "routes_crawled_count": 0,
        "routes_not_crawled_count": 0,
        "job_id": job_id,
        "user_id": req.user_id,
        "chat_sessions": [],
        "created_at": now,
        "updated_at": now
    }
    await collection_store.create_collection(collection_data)
    
    # Create associated job
    job_data = {
        "id": job_id,
        "url": req.url,
        "max_pages": req.max_pages,
        "max_depth": req.max_depth,
        "collection_name": req.name,
        "collection_id": collection_id,
        "status": "pending",
        "pages_stored": 0,
        "routes_crawled": [],
        "routes_not_crawled": [],
        "routes_crawled_count": 0,
        "routes_not_crawled_count": 0,
        "crawl_logs": [],
        "crawl_logs_count": 0,
        "created_at": now,
        "updated_at": now
    }
    await job_store.create_job(job_data)
    
    # Start background task
    background_tasks.add_task(run_collection_scrape_job, job_id, collection_id, req)
    
    return {
        "collection_id": collection_id,
        "job_id": job_id,
        "name": req.name,
        "url": req.url,
        "status": "pending",
        "message": "Collection created and scraping started. Use Socket.IO to receive real-time updates."
    }


@router.get("/")
async def list_collections(user_id: Optional[str] = None):
    """List all collections, optionally filtered by user."""
    collections = await collection_store.get_all_collections(user_id)
    return {"collections": collections, "count": len(collections)}


@router.get("/{collection_id}")
async def get_collection(collection_id: str):
    """Get a specific collection with its details."""
    collection = await collection_store.get_collection_by_id(collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    
    # Get vector store stats
    try:
        stats = vector_store.get_collection_stats(collection.get("name"))
        collection["vector_stats"] = stats
    except:
        collection["vector_stats"] = None
    
    return collection


@router.get("/name/{name}")
async def get_collection_by_name(name: str):
    """Get a collection by its name."""
    collection = await collection_store.get_collection_by_name(name)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    return collection


@router.patch("/{collection_id}")
async def update_collection(collection_id: str, req: UpdateCollectionRequest):
    """Update collection metadata."""
    updates = {k: v for k, v in req.dict().items() if v is not None}
    
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No updates provided"
        )
    
    collection = await collection_store.update_collection(collection_id, updates)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    
    return collection


@router.delete("/{collection_id}")
async def delete_collection(collection_id: str):
    """Delete a collection and its associated data."""
    collection = await collection_store.get_collection_by_id(collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    
    # Delete from vector store
    try:
        vector_store.clear_collection(collection.get("name"))
    except:
        pass
    
    # Delete associated job
    if collection.get("job_id"):
        await job_store.delete_job(collection.get("job_id"))
    
    # Delete collection
    await collection_store.delete_collection(collection_id)
    
    return {"message": "Collection deleted", "collection_id": collection_id}


@router.get("/{collection_id}/job")
async def get_collection_job(collection_id: str):
    """Get the scraping job associated with a collection."""
    collection = await collection_store.get_collection_by_id(collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )
    
    job_id = collection.get("job_id")
    if not job_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No job associated with this collection"
        )
    
    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    return job


@router.get("/{collection_id}/routes")
async def get_collection_routes(collection_id: str):
    """Get crawled and not-crawled routes for a collection."""
    collection = await collection_store.get_collection_by_id(collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )

    job_id = collection.get("job_id")
    if not job_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No job associated with this collection"
        )

    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    routes_crawled = job.get("routes_crawled", [])
    routes_not_crawled = job.get("routes_not_crawled", [])

    return {
        "collection_id": collection_id,
        "job_id": job_id,
        "routes_crawled_count": job.get("routes_crawled_count", len(routes_crawled)),
        "routes_not_crawled_count": job.get("routes_not_crawled_count", len(routes_not_crawled)),
        "routes_crawled": routes_crawled,
        "routes_not_crawled": routes_not_crawled,
        "crawl_summary": job.get("crawl_summary", {}),
    }


@router.get("/{collection_id}/crawl-logs")
async def get_collection_crawl_logs(
    collection_id: str,
    limit: int = Query(200, ge=1, le=5000),
    offset: int = Query(0, ge=0),
):
    """Get crawl logs for a collection job (including crawled and skipped endpoints)."""
    collection = await collection_store.get_collection_by_id(collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Collection not found"
        )

    job_id = collection.get("job_id")
    if not job_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No job associated with this collection"
        )

    job = await job_store.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )

    logs = job.get("crawl_logs", [])
    sliced_logs = logs[offset:offset + limit]

    return {
        "collection_id": collection_id,
        "job_id": job_id,
        "crawl_logs_count": job.get("crawl_logs_count", len(logs)),
        "offset": offset,
        "limit": limit,
        "logs": sliced_logs,
    }
