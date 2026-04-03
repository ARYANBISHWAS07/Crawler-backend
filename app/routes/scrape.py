# app/routes/scrape.py
from __future__ import annotations

import json
from datetime import datetime
from threading import RLock
from typing import Any, Optional
from urllib.parse import urlparse
import uuid

from fastapi import APIRouter, HTTPException

from app.extensions import scrape_single_page
from app.models import WebsiteChatMessage, WebsiteScrapePageRequest, WebsiteSession

router = APIRouter(prefix="/scrape", tags=["scrape"])


# Global temporary store for scraped website chat sessions.
# Key: session_id
# Value: {
#   id, website_session_name, user_id, url, domain, context, messages, created_at, updated_at
# }
TEMP_WEBSITE_CONTEXT_STORE: dict[str, WebsiteSession] = {}
_TEMP_STORE_LOCK = RLock()


def extract_scraped_text(raw: Any) -> str:
    """Normalize various scrape result shapes into plain text."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return (
            raw.get("words")
            or raw.get("text")
            or raw.get("content")
            or json.dumps(raw, ensure_ascii=False)
        )
    return str(raw)


def create_temp_website_session(
    url: str,
    context: str,
    website_session_name: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Create and store an in-memory website chat session."""
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.hostname or "website"
    now = datetime.utcnow().isoformat()
    session = WebsiteSession(
        id=str(uuid.uuid4()),
        website_session_name=website_session_name or f"Website Session - {domain}",
        user_id=user_id,
        url=url,
        domain=domain,
        context=context,
        messages=[],
        created_at=now,
        updated_at=now,
    )
    with _TEMP_STORE_LOCK:
        TEMP_WEBSITE_CONTEXT_STORE[session.id] = session
    return session.model_dump()


def get_temp_website_session(session_id: str) -> Optional[dict[str, Any]]:
    with _TEMP_STORE_LOCK:
        session = TEMP_WEBSITE_CONTEXT_STORE.get(session_id)
        return session.model_dump() if session else None


def list_temp_website_sessions() -> list[dict[str, Any]]:
    with _TEMP_STORE_LOCK:
        return [value.model_dump() for value in TEMP_WEBSITE_CONTEXT_STORE.values()]


def append_temp_website_message(session_id: str, message: dict[str, Any]) -> bool:
    with _TEMP_STORE_LOCK:
        session = TEMP_WEBSITE_CONTEXT_STORE.get(session_id)
        if not session:
            return False
        session.messages.append(WebsiteChatMessage(**message))
        session.updated_at = datetime.utcnow().isoformat()
        return True


def delete_temp_website_session(session_id: str) -> bool:
    with _TEMP_STORE_LOCK:
        if session_id not in TEMP_WEBSITE_CONTEXT_STORE:
            return False
        del TEMP_WEBSITE_CONTEXT_STORE[session_id]
        return True


@router.post("/page")
async def scrape_page(payload: WebsiteScrapePageRequest):
    """
    Scrape one page and optionally create an in-memory website chat session
    using the scraped context.
    """
    try:
        raw = await scrape_single_page(str(payload.url))
        scraped_text = extract_scraped_text(raw).strip()
        if not scraped_text:
            raise RuntimeError("Scraped page did not return readable text content.")

        session_data = None
        if payload.create_session:
            session_data = create_temp_website_session(
                url=str(payload.url),
                context=scraped_text,
                website_session_name=payload.website_session_name,
                user_id=payload.user_id,
            )

        return {
            "answer": scraped_text,
            "words": scraped_text,
            "session_id": session_data["id"] if session_data else None,
            "website_session": (
                {
                    "id": session_data["id"],
                    "website_session_name": session_data["website_session_name"],
                    "user_id": session_data.get("user_id"),
                    "url": session_data["url"],
                    "domain": session_data["domain"],
                    "created_at": session_data["created_at"],
                    "updated_at": session_data["updated_at"],
                }
                if session_data
                else None
            ),
            "sources": [{"title": "Scraped Page", "url": str(payload.url)}],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scrape failed: {e}")
