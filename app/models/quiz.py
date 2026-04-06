from datetime import datetime
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
import uuid


class QuizQuestionPublic(BaseModel):
    id: str
    question: str
    options: Dict[str, str]


class QuizStartRequest(BaseModel):
    collection_id: str
    question_count: int = Field(default=5, ge=5, le=10)
    user_id: Optional[str] = None


class QuizStartResponse(BaseModel):
    quiz_session_id: str
    collection_id: str
    total_questions: int
    questions: List[QuizQuestionPublic]
    created_at: datetime


class QuizAnswerItem(BaseModel):
    question_id: str
    selected_option: str


class QuizSubmitRequest(BaseModel):
    answers: List[QuizAnswerItem]


class WrongQuestionFeedback(BaseModel):
    question_id: str
    question: str
    selected_option: str
    correct_option: str
    options: Dict[str, str]
    explanation: str = ""


class QuizSubmitResponse(BaseModel):
    quiz_session_id: str
    score: int
    total_questions: int
    percentage: float
    wrong_answers: List[WrongQuestionFeedback]
    llm_suggestions: str
    completed_at: datetime


class QuizSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    collection_id: str
    user_id: Optional[str] = None
    status: str = "in_progress"
    total_questions: int = 0
    score: int = 0
    questions: List[dict] = Field(default_factory=list)
    answers: List[dict] = Field(default_factory=list)
    wrong_answers: List[dict] = Field(default_factory=list)
    llm_suggestions: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
