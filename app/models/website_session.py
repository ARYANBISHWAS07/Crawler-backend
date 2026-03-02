"""
Website scraping chat session models.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class WebsiteChatMessage(BaseModel):
    id: str
    role: str
    content: str
    sources: list[dict] = Field(default_factory=list)
    created_at: str


class WebsiteSession(BaseModel):
    id: str
    website_session_name: str
    user_id: Optional[str] = None
    url: str
    domain: str
    context: str
    messages: list[WebsiteChatMessage] = Field(default_factory=list)
    created_at: str
    updated_at: str


class WebsiteSessionSummary(BaseModel):
    id: str
    website_session_name: str
    user_id: Optional[str] = None
    url: str
    domain: str
    context_length: int
    message_count: int
    created_at: str
    updated_at: str


class WebsiteSessionCreateRequest(BaseModel):
    url: HttpUrl
    website_session_name: Optional[str] = None
    user_id: Optional[str] = None


class WebsiteScrapePageRequest(BaseModel):
    url: HttpUrl
    website_session_name: Optional[str] = None
    user_id: Optional[str] = None
    create_session: bool = True


class WebsiteMessageRequest(BaseModel):
    message: str = Field(..., min_length=1)

