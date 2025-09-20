"""
Domain models for the system.
"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any
from uuid import UUID

from pydantic import Field, validator

from .base import Entity, ValueObject, AggregateRoot


class MessageType(str, Enum):
    """Types of messages."""
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    DOCUMENT = "document"
    VIDEO = "video"


class MessageStatus(str, Enum):
    """Message processing status."""
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    SENT = "sent"


class ConversationStatus(str, Enum):
    """Conversation status."""
    ACTIVE = "active"
    WAITING = "waiting"
    COMPLETED = "completed"
    ESCALATED = "escalated"


class AgentType(str, Enum):
    """Types of agents."""
    ORCHESTRATOR = "orchestrator"
    SPECIALIST = "specialist"
    TRANSCRIPTION = "transcription"
    WEB_SEARCH = "web_search"
    MEMORY = "memory"
    RAG = "rag"


class Priority(str, Enum):
    """Task priority levels."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ContactInfo(ValueObject):
    """Contact information value object."""
    phone: str
    name: Optional[str] = None
    email: Optional[str] = None
    
    @validator('phone')
    def validate_phone(cls, v):
        # Remove non-numeric characters
        cleaned = ''.join(filter(str.isdigit, v))
        if not cleaned or len(cleaned) < 10:
            raise ValueError('Invalid phone number format')
        return cleaned


class Location(ValueObject):
    """Location value object."""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None


class User(AggregateRoot):
    """User aggregate root."""
    contact_info: ContactInfo
    preferences: Dict[str, Any] = Field(default_factory=dict)
    location: Optional[Location] = None
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Message(Entity):
    """Message entity."""
    conversation_id: UUID
    user_id: UUID
    content: str
    message_type: MessageType
    status: MessageStatus = MessageStatus.RECEIVED
    metadata: Dict[str, Any] = Field(default_factory=dict)
    source_message_id: Optional[str] = None  # External message ID
    processed_content: Optional[str] = None  # For transcribed audio, etc.
    attachments: List[str] = Field(default_factory=list)
    

class Conversation(AggregateRoot):
    """Conversation aggregate root."""
    user_id: UUID
    status: ConversationStatus = ConversationStatus.ACTIVE
    messages: List[UUID] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    agent_assignments: Dict[str, UUID] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Task(Entity):
    """Task entity for agent processing."""
    task_type: str
    agent_type: AgentType
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    status: str = "pending"
    priority: Priority = Priority.NORMAL
    conversation_id: Optional[UUID] = None
    parent_task_id: Optional[UUID] = None
    dependencies: List[UUID] = Field(default_factory=list)
    retry_count: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class Property(Entity):
    """Property entity for real estate."""
    title: str
    description: str
    price: Optional[float] = None
    property_type: str  # house, apartment, land, etc.
    location: Location
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    area_sqm: Optional[float] = None
    features: List[str] = Field(default_factory=list)
    images: List[str] = Field(default_factory=list)
    source_url: Optional[str] = None
    source_name: Optional[str] = None
    is_active: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MemoryEntry(Entity):
    """Memory entry for conversation context."""
    user_id: UUID
    conversation_id: Optional[UUID] = None
    content: str
    memory_type: str  # short_term, long_term, preference, fact
    importance_score: float = 0.0
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Document(Entity):
    """Document entity for RAG system."""
    title: str
    content: str
    source: str
    document_type: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    embedding: Optional[List[float]] = None
    chunk_id: Optional[str] = None
    parent_document_id: Optional[UUID] = None
