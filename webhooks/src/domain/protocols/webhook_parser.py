"""
Protocol for parsing webhook messages
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from ..entities import WhatsAppMessage


class WebhookParserProtocol(ABC):
    """Protocol for parsing incoming webhook messages"""
    
    @abstractmethod
    async def parse_incoming_message(
        self, 
        webhook_data: Dict[str, Any]
    ) -> Optional[WhatsAppMessage]:
        """
        Parse incoming webhook data into WhatsAppMessage
        
        Args:
            webhook_data: Raw webhook data from Evolution API
            
        Returns:
            Parsed WhatsAppMessage or None if parsing fails
        """
        pass
    
    @abstractmethod
    def validate_webhook_signature(
        self,
        payload: str,
        signature: str,
        secret: str
    ) -> bool:
        """
        Validate webhook signature for security
        
        Args:
            payload: Raw webhook payload
            signature: Webhook signature header
            secret: Webhook secret key
            
        Returns:
            True if signature is valid, False otherwise
        """
        pass