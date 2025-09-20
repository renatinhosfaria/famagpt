"""
Protocol for communicating with orchestrator service
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..entities import WhatsAppMessage


class OrchestratorClientProtocol(ABC):
    """Protocol for sending messages to orchestrator"""
    
    @abstractmethod
    async def send_message_to_orchestrator(
        self,
        message: WhatsAppMessage
    ) -> Dict[str, Any]:
        """
        Send parsed message to orchestrator for processing
        
        Args:
            message: Parsed WhatsApp message
            
        Returns:
            Response from orchestrator
        """
        pass
    
    @abstractmethod
    async def get_orchestrator_health(self) -> Dict[str, Any]:
        """
        Check orchestrator service health
        
        Returns:
            Health status response
        """
        pass