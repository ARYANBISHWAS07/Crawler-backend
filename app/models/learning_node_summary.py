from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional
import uuid


class LearningNodeSummary(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    collection_id: str
    node_id: str
    node_label: str
    summary: str
    module: Optional[str] = None
    difficulty: Optional[str] = None
    node_type: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
