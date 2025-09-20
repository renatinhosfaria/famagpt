"""
Database domain interfaces.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from uuid import UUID

from shared.src.domain.models import User, Conversation, Message, Property, MemoryEntry, Document


class UserRepository(ABC):
    """User repository interface."""
    
    @abstractmethod
    async def create(self, user: User) -> User:
        """Create a new user."""
        pass
    
    @abstractmethod
    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        pass
    
    @abstractmethod
    async def get_by_phone(self, phone: str) -> Optional[User]:
        """Get user by phone number."""
        pass
    
    @abstractmethod
    async def update(self, user: User) -> User:
        """Update user."""
        pass
    
    @abstractmethod
    async def delete(self, user_id: UUID) -> None:
        """Delete user."""
        pass


class ConversationRepository(ABC):
    """Conversation repository interface."""
    
    @abstractmethod
    async def create(self, conversation: Conversation) -> Conversation:
        """Create a new conversation."""
        pass
    
    @abstractmethod
    async def get_by_id(self, conversation_id: UUID) -> Optional[Conversation]:
        """Get conversation by ID."""
        pass
    
    @abstractmethod
    async def get_by_user_id(self, user_id: UUID) -> List[Conversation]:
        """Get conversations for a user."""
        pass
    
    @abstractmethod
    async def update(self, conversation: Conversation) -> Conversation:
        """Update conversation."""
        pass
    
    @abstractmethod
    async def delete(self, conversation_id: UUID) -> None:
        """Delete conversation."""
        pass


class MessageRepository(ABC):
    """Message repository interface."""
    
    @abstractmethod
    async def create(self, message: Message) -> Message:
        """Create a new message."""
        pass
    
    @abstractmethod
    async def get_by_id(self, message_id: UUID) -> Optional[Message]:
        """Get message by ID."""
        pass
    
    @abstractmethod
    async def get_by_conversation_id(self, conversation_id: UUID) -> List[Message]:
        """Get messages for a conversation."""
        pass
    
    @abstractmethod
    async def update(self, message: Message) -> Message:
        """Update message."""
        pass
    
    @abstractmethod
    async def delete(self, message_id: UUID) -> None:
        """Delete message."""
        pass


class PropertyRepository(ABC):
    """Property repository interface."""
    
    @abstractmethod
    async def create(self, property: Property) -> Property:
        """Create a new property."""
        pass
    
    @abstractmethod
    async def get_by_id(self, property_id: UUID) -> Optional[Property]:
        """Get property by ID."""
        pass
    
    @abstractmethod
    async def search(self, criteria: Dict[str, Any]) -> List[Property]:
        """Search properties by criteria."""
        pass
    
    @abstractmethod
    async def update(self, property: Property) -> Property:
        """Update property."""
        pass
    
    @abstractmethod
    async def delete(self, property_id: UUID) -> None:
        """Delete property."""
        pass


class MemoryRepository(ABC):
    """Memory repository interface."""
    
    @abstractmethod
    async def create(self, memory: MemoryEntry) -> MemoryEntry:
        """Create a new memory entry."""
        pass
    
    @abstractmethod
    async def get_by_user_id(self, user_id: UUID) -> List[MemoryEntry]:
        """Get memory entries for a user."""
        pass
    
    @abstractmethod
    async def search_by_content(self, user_id: UUID, query: str) -> List[MemoryEntry]:
        """Search memory entries by content."""
        pass
    
    @abstractmethod
    async def update(self, memory: MemoryEntry) -> MemoryEntry:
        """Update memory entry."""
        pass
    
    @abstractmethod
    async def delete(self, memory_id: UUID) -> None:
        """Delete memory entry."""
        pass


class DocumentRepository(ABC):
    """Document repository interface."""
    
    @abstractmethod
    async def create(self, document: Document) -> Document:
        """Create a new document."""
        pass
    
    @abstractmethod
    async def get_by_id(self, document_id: UUID) -> Optional[Document]:
        """Get document by ID."""
        pass
    
    @abstractmethod
    async def search_by_embedding(self, embedding: List[float], limit: int = 10) -> List[Document]:
        """Search documents by embedding similarity."""
        pass
    
    @abstractmethod
    async def update(self, document: Document) -> Document:
        """Update document."""
        pass
    
    @abstractmethod
    async def delete(self, document_id: UUID) -> None:
        """Delete document."""
        pass
