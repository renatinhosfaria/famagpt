"""
Protocol for sending messages via WhatsApp
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from ..entities import OutgoingMessage


class MessageSenderProtocol(ABC):
    """Protocol for sending messages via Evolution API"""
    
    @abstractmethod
    async def send_message(
        self,
        message: OutgoingMessage
    ) -> Dict[str, Any]:
        """
        Send message via WhatsApp
        
        Args:
            message: OutgoingMessage to send
            
        Returns:
            Response from Evolution API
        """
        pass
    
    @abstractmethod
    async def send_typing_indicator(
        self,
        instance_id: str,
        phone_number: str,
        typing: bool = True
    ) -> bool:
        """
        Send typing indicator
        
        Args:
            instance_id: WhatsApp instance ID
            phone_number: Target phone number
            typing: True to start typing, False to stop
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def mark_as_read(
        self,
        instance_id: str,
        message_id: str
    ) -> bool:
        """
        Mark message as read
        
        Args:
            instance_id: WhatsApp instance ID
            message_id: Message ID to mark as read
            
        Returns:
            True if successful, False otherwise
        """
        pass