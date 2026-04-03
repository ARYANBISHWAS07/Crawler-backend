"""
Collection and Chat History Models
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """Individual chat message within a collection."""
    id: str
    role: MessageRole
    content: str
    sources: Optional[List[dict]] = []  # Sources from vector search
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatSession(BaseModel):
    """A chat session containing multiple messages."""
    id: str
    collection_id: str
    title: Optional[str] = None
    messages: List[ChatMessage] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CollectionStatus(str, Enum):
    PENDING = "pending"
    CRAWLING = "crawling"
    EMBEDDING = "embedding"
    COMPLETED = "completed"
    ERROR = "error"


class CollectionCreate(BaseModel):
    """Request model for creating a collection."""
    name: str
    url: str
    user_id: Optional[str] = None


class CollectionResponse(BaseModel):
    """Response model for a collection."""
    id: str
    name: str
    url: str
    status: CollectionStatus
    pages_count: int = 0
    job_id: Optional[str] = None
    user_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CollectionWithChats(CollectionResponse):
    """Collection with associated chat sessions."""
    chat_sessions: List[ChatSession] = []


class CollectionInDB(BaseModel):
    """Collection model as stored in MongoDB."""
    id: str
    name: str
    url: str
    status: str = "pending"
    pages_count: int = 0
    job_id: Optional[str] = None
    user_id: Optional[str] = None
    chat_sessions: List[dict] = []
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class SendMessageRequest(BaseModel):
    """Request to send a message in a collection chat."""
    collection_id: str
    session_id: Optional[str] = None  # If None, creates new session
    message: str
    top_k: int = 3


class ChatHistoryResponse(BaseModel):
    """Response containing chat history."""
    session_id: str
    collection_id: str
    messages: List[ChatMessage]


class LearningLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class NodeType(str, Enum):
    CORE_TOPIC = "core_topic"
    SUB_TOPIC = "sub_topic"


class NodePosition(BaseModel):
    """Position of a node in the graph for visualization."""
    x: float = 0
    y: float = 0


class LearningModule(BaseModel):
    """A module grouping related topics."""
    id: str
    title: str
    description: Optional[str] = None


class LearningNode(BaseModel):
    """A node in the learning path graph representing a topic."""
    id: str
    label: str
    summary: Optional[str] = None
    module: Optional[str] = None
    difficulty: LearningLevel = LearningLevel.BEGINNER
    type: NodeType = NodeType.CORE_TOPIC
    position: NodePosition = NodePosition()
    # Deprecated field for backward compatibility
    level: Optional[LearningLevel] = None


class LearningEdge(BaseModel):
    """An edge in the learning path graph representing a prerequisite relationship."""
    source: str
    target: str
    type: str = "prerequisite"


class LearningPathResponse(BaseModel):
    """Response model for the generated learning path."""
    modules: List[LearningModule] = []
    nodes: List[LearningNode]
    edges: List[LearningEdge]
    learning_path: List[str]


class GenerateLearningPathRequest(BaseModel):
    """Request model for generating a learning path from URLs."""
    urls: List[str]
