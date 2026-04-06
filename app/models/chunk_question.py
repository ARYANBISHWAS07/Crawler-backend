from pydantic import BaseModel, Field
from typing import Dict, List
from datetime import datetime
import uuid


class MCQOptionSet(BaseModel):
    A: str
    B: str
    C: str
    D: str


class MCQQuestion(BaseModel):
    id: int
    question: str
    options: MCQOptionSet
    correct_option: str
    explanation: str = ""


class ChunkQuestionnaire(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    collection_id: str
    questionnaire: List[MCQQuestion] = Field(default_factory=list)
    metadata: Dict
    chunk_excerpt: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
