from fastapi import APIRouter, HTTPException, status, Depends
from datetime import datetime
from bson import ObjectId
from typing import List

from app.models import UserCreate, UserLogin, UserResponse, UserUpdate, Token
from app.database import get_collection
from app import collection_store
from app.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user
)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """Register a new user."""
    users_collection = get_collection("users")
    
    # Check if email already exists
    existing_user = await users_collection.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username already exists
    existing_username = await users_collection.find_one({"username": user_data.username})
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create user document
    user_doc = {
        "email": user_data.email,
        "username": user_data.username,
        "hashed_password": get_password_hash(user_data.password),
        "created_at": datetime.utcnow(),
        "is_active": True,
        "scrape_jobs": [],
        "collections": []
    }
    
    result = await users_collection.insert_one(user_doc)
    
    # Create access token
    access_token = create_access_token(data={"sub": str(result.inserted_id)})
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    """Login and get access token."""
    users_collection = get_collection("users")
    
    user = await users_collection.find_one({"email": user_data.email})
    
    if not user or not verify_password(user_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )
    
    access_token = create_access_token(data={"sub": str(user["_id"])})
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        username=current_user["username"],
        created_at=current_user["created_at"],
        is_active=current_user.get("is_active", True)
    )


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    update_data: UserUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update current user information."""
    users_collection = get_collection("users")
    
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if not update_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )
    
    # Check if new email is already taken
    if "email" in update_dict:
        existing = await users_collection.find_one({
            "email": update_dict["email"],
            "_id": {"$ne": current_user["_id"]}
        })
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use"
            )
    
    # Check if new username is already taken
    if "username" in update_dict:
        existing = await users_collection.find_one({
            "username": update_dict["username"],
            "_id": {"$ne": current_user["_id"]}
        })
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )
    
    await users_collection.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_dict}
    )
    
    updated_user = await users_collection.find_one({"_id": current_user["_id"]})
    
    return UserResponse(
        id=str(updated_user["_id"]),
        email=updated_user["email"],
        username=updated_user["username"],
        created_at=updated_user["created_at"],
        is_active=updated_user.get("is_active", True)
    )


@router.get("/me/jobs")
async def get_user_jobs(current_user: dict = Depends(get_current_user)):
    """Get all scrape jobs for current user."""
    jobs_collection = get_collection("scrape_jobs")
    
    cursor = jobs_collection.find({"user_id": str(current_user["_id"])})
    jobs = await cursor.to_list(length=100)
    
    return {"jobs": [
        {
            "id": str(job["_id"]),
            "url": job.get("url"),
            "status": job.get("status"),
            "pages_stored": job.get("pages_stored", 0),
            "routes_crawled_count": job.get("routes_crawled_count", 0),
            "routes_not_crawled_count": job.get("routes_not_crawled_count", 0),
            "crawl_logs_count": job.get("crawl_logs_count", 0),
            "created_at": job.get("created_at"),
            "collection_name": job.get("collection_name")
        }
        for job in jobs
    ], "count": len(jobs)}


@router.get("/me/collections")
async def get_user_collections(current_user: dict = Depends(get_current_user)):
    """Get all collections owned by current user."""
    user_id = str(current_user["_id"])
    collections = await collection_store.get_all_collections(user_id=user_id)
    return {"collections": collections, "count": len(collections)}


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user(current_user: dict = Depends(get_current_user)):
    """Delete current user account."""
    users_collection = get_collection("users")
    await users_collection.delete_one({"_id": current_user["_id"]})
    return None
