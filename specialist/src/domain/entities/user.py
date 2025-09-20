"""
Entidades relacionadas ao usuário e conversa.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID


class UserType(str, Enum):
    """Tipo de usuário."""
    CLIENTE = "cliente"
    CORRETOR = "corretor"
    ADMIN = "admin"


class ConversationStatus(str, Enum):
    """Status da conversa."""
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"


class MessageType(str, Enum):
    """Tipo de mensagem."""
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    PROPERTY_SUGGESTION = "property_suggestion"
    PROPERTY_INQUIRY = "property_inquiry"


@dataclass
class UserProfile:
    """Perfil do usuário."""
    id: UUID
    phone_number: str
    name: Optional[str] = None
    email: Optional[str] = None
    user_type: UserType = UserType.CLIENTE
    preferences: Optional[Dict[str, Any]] = None
    location: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    created_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    
    def __post_init__(self):
        if self.preferences is None:
            self.preferences = {}
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.last_activity is None:
            self.last_activity = datetime.utcnow()


@dataclass
class ConversationContext:
    """Contexto da conversa."""
    id: UUID
    user_id: UUID
    status: ConversationStatus = ConversationStatus.ACTIVE
    current_intent: Optional[str] = None
    search_criteria: Optional[Dict[str, Any]] = None
    last_properties_shown: List[UUID] = None
    conversation_summary: Optional[str] = None
    tags: List[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.last_properties_shown is None:
            self.last_properties_shown = []
        if self.tags is None:
            self.tags = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()


@dataclass
class Message:
    """Mensagem da conversa."""
    id: UUID
    conversation_id: UUID
    content: str
    message_type: MessageType
    sender: str  # "user" ou "assistant"
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


@dataclass
class PropertyInquiry:
    """Interesse em imóvel."""
    id: UUID
    user_id: UUID
    property_id: UUID
    inquiry_type: str  # "interesse", "visita", "proposta"
    message: Optional[str] = None
    contact_preference: Optional[str] = None
    created_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()