"""
Collection routes for managing scraped website collections.
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from httpcore import request
from numpy import generic
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

from app.crawler import crawl_manual, crawl_sync, crawl_site
from app import vector_store
from app import job_store
from app import collection_store
from app.socketio_manager import emit_job_update_sync, emit_collection_update_sync, emit_progress_sync
from urllib.parse import urlparse
router = APIRouter(prefix="/collections", tags=["collections"])


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
        
        # Run the crawler with progress
        data = crawl_sync(req.url, req.max_pages, req.max_depth, progress_callback=crawl_progress)
        
        # Update status to embedding
        job_store.update_job_sync(job_id, {"status": "embedding", "pages_crawled": len(data)})
        collection_store.update_collection_sync(collection_id, {"status": "embedding"})
        
        emit_job_update_sync(job_id, {
            "status": "embedding",
            "pages_crawled": len(data),
            "message": f"Crawled {len(data)} pages. Creating embeddings..."
        })
        emit_collection_update_sync(collection_id, {"status": "embedding", "pages_count": len(data)})
        
        # Progress callback for embedding
        def embed_progress(current: int, total: int, message: str):
            emit_progress_sync(job_id, current, total, message, stage="embedding")
        
        # Store in vector database using collection name with progress
        pages_stored = vector_store.store_pages(data, req.name, progress_callback=embed_progress)
        
        # Update job as completed
        job_store.update_job_sync(job_id, {
            "status": "completed",
            "pages_stored": pages_stored,
            "collection_name": req.name,
            "results_count": len(data)
        })
        
        # Update collection as completed
        collection_store.update_collection_sync(collection_id, {
            "status": "completed",
            "pages_count": pages_stored
        })
        
        emit_job_update_sync(job_id, {
            "status": "completed",
            "pages_stored": pages_stored,
            "percentage": 100,
            "message": f"Successfully stored {pages_stored} chunks. Ready to chat!"
        })
        emit_collection_update_sync(collection_id, {
            "status": "completed",
            "pages_count": pages_stored
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


@router.post("/crawl/site")
async def crawl_site_endpoint(
    url: str,
    background_tasks: BackgroundTasks
):
    background_tasks.add_task(
        crawl_manual,
        start_url=url,
        max_depth=2,
        max_pages=10
    )

    return {
        "status": "crawl started",
        "url": url,
        "depth": 2,
        "max_pages": 10,
        "manual_crawl": "crawl_manual"
    }

@router.post("/crawl/site/BFS")
async def crawl_site_endpoint(
    url: str,
    background_tasks: BackgroundTasks
):
    domain = urlparse(url).netloc
    
    background_tasks.add_task(
        crawl_site,
        start_url=url,
        domain=domain,
        max_depth=2,
        max_pages=10
    )

    return {
        "status": "crawl started",
        "url": url,
        "depth": 2,
        "max_pages": 10,
        "domain": domain
    }


