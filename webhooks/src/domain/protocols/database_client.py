"""
Database client protocol for webhooks service.
"""
from typing import Dict, Any, Optional, Protocol
from datetime import datetime
from uuid import UUID

from ..entities import WhatsAppMessage


class DatabaseClientProtocol(Protocol):
    """Protocol for database operations in webhooks service."""
    
    async def create_or_get_user(
        self,
        phone: str,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create user or get existing by phone number."""
        ...
    
    async def create_conversation(
        self,
        user_id: UUID,
        instance_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create new conversation."""
        ...
    
    async def get_active_conversation(
        self,
        user_id: UUID,
        instance_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get active conversation for user in specific instance."""
        ...
    
    async def save_message(
        self,
        message: WhatsAppMessage,
        conversation_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """Save incoming WhatsApp message."""
        ...
    
    async def update_conversation_activity(
        self,
        conversation_id: UUID
    ) -> None:
        """Update conversation last activity timestamp."""
        ...
    
    async def get_conversation_messages(
        self,
        conversation_id: UUID,
        limit: int = 50
    ) -> list[Dict[str, Any]]:
        """Get recent messages from conversation."""
        ...