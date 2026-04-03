from pydantic import BaseModel, Field
from typing import Dict
from datetime import datetime
import uuid

class ChunkQuestionnaire(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    collection_id: str
    # chunk_content: str
    questionnaire: str
    metadata: Dict
    created_at: datetime = Field(default_factory=datetime.utcnow)