from fastapi import APIRouter, HTTPException, status, Depends
import asyncio
from datetime import datetime
from typing import List
import uuid

from app.models import UserCreate, UserLogin, UserResponse, UserUpdate, Token
from app.database import delete_item, get_by_id, get_scan_attr, put_item, scan_table, update_item
from app import collection_store
from app.auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user
)

router = APIRouter(prefix="/users", tags=["users"])


async def _find_user_by_email(email: str):
    users = await asyncio.to_thread(scan_table, "users", get_scan_attr("email").eq(email), 1)
    return users[0] if users else None


async def _find_user_by_username(username: str):
    users = await asyncio.to_thread(scan_table, "users", get_scan_attr("username").eq(username), 1)
    return users[0] if users else None


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate):
    """Register a new user."""
    existing_user = await _find_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    existing_username = await _find_user_by_username(user_data.username)
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    user_id = str(uuid.uuid4())
    user_doc = {
        "PK": user_id,
        "id": user_id,
        "email": user_data.email,
        "username": user_data.username,
        "hashed_password": get_password_hash(user_data.password),
        "created_at": datetime.utcnow().isoformat(),
        "is_active": True,
        "scrape_jobs": [],
        "collections": []
    }

    await asyncio.to_thread(put_item, "users", user_doc)
    access_token = create_access_token(data={"sub": user_id})
    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/login", response_model=Token)
async def login(user_data: UserLogin):
    """Login and get access token."""
    user = await _find_user_by_email(user_data.email)

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

    access_token = create_access_token(data={"sub": user["id"]})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current user information."""
    return UserResponse(
        id=current_user["id"],
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
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}

    if not update_dict:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )

    if "email" in update_dict:
        existing = await _find_user_by_email(update_dict["email"])
        if existing and existing["id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use"
            )

    if "username" in update_dict:
        existing = await _find_user_by_username(update_dict["username"])
        if existing and existing["id"] != current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already taken"
            )

    await asyncio.to_thread(update_item, "users", {"PK": current_user["id"]}, update_dict)
    updated_user = await asyncio.to_thread(get_by_id, "users", current_user["id"])

    return UserResponse(
        id=updated_user["id"],
        email=updated_user["email"],
        username=updated_user["username"],
        created_at=updated_user["created_at"],
        is_active=updated_user.get("is_active", True)
    )


@router.get("/me/jobs")
async def get_user_jobs(current_user: dict = Depends(get_current_user)):
    """Get all scrape jobs for current user."""
    jobs = await asyncio.to_thread(
        scan_table,
        "scrape_jobs",
        get_scan_attr("user_id").eq(current_user["id"]),
    )
    jobs.sort(key=lambda item: item.get("created_at", ""), reverse=True)

    return {"jobs": [
        {
            "id": job.get("id"),
            "url": job.get("url"),
            "status": job.get("status"),
            "pages_stored": job.get("pages_stored", 0),
            "routes_crawled_count": job.get("routes_crawled_count", 0),
            "routes_not_crawled_count": job.get("routes_not_crawled_count", 0),
            "crawl_logs_count": job.get("crawl_logs_count", 0),
            "created_at": job.get("created_at"),
            "collection_name": job.get("collection_name")
        }
        for job in jobs[:100]
    ], "count": len(jobs[:100])}


@router.get("/me/collections")
async def get_user_collections(current_user: dict = Depends(get_current_user)):
    """Get all collections owned by current user."""
    collections = await collection_store.get_all_collections(user_id=current_user["id"])
    return {"collections": collections, "count": len(collections)}


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_current_user(current_user: dict = Depends(get_current_user)):
    """Delete current user account."""
    await asyncio.to_thread(delete_item, "users", {"PK": current_user["id"]})
    return None
