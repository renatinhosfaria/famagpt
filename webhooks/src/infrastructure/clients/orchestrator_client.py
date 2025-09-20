"""
Orchestrator service client implementation
"""

from typing import Dict, Any
import aiohttp

from ...domain.protocols import OrchestratorClientProtocol
from ...domain.entities import WhatsAppMessage

# Shared modules
from shared.src.utils.logging import get_logger
from shared.src.utils.config import AppSettings as Settings
from shared.src.utils.circuit_breaker import CircuitBreaker, resilient_call


class OrchestratorClient(OrchestratorClientProtocol):
    """Client for communicating with orchestrator service"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger("orchestrator_client")
        self.base_url = settings.service.orchestrator_url
        self.session = None
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=30,
            expected_exception=aiohttp.ClientError,
            service_name="webhooks",
            function_name="send_message_to_orchestrator"
        )
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    async def _ensure_session(self):
        """Ensure HTTP session is available"""
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    @resilient_call(stop_attempts=3, wait_min=2, wait_max=10)
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
        return await self.circuit_breaker.call(self._send_message_to_orchestrator_internal)(message)
    
    async def _send_message_to_orchestrator_internal(self, message: WhatsAppMessage) -> Dict[str, Any]:
        """Internal method for sending messages with circuit breaker protection"""
        try:
            await self._ensure_session()
            
            # Use execute endpoint since process-message requires UUIDs we don't have here
            url = f"{self.base_url}/api/v1/execute"
            headers = {
                "Content-Type": "application/json"
            }
            
            # Choose workflow based on message type
            workflow_name = "general_conversation_workflow"
            if message.message_type.value in ["audio", "voice"]:
                workflow_name = "audio_processing_workflow"
            elif message.message_type.value in ["image", "video", "document"]:
                # Keep general for now; can route to specialized later
                workflow_name = "general_conversation_workflow"

            input_data = {
                "message_content": message.content,
                "message_type": message.message_type.value,
                "phone_number": message.phone_number,
                "instance_id": message.instance_id,
                "contact": {
                    "phone": message.contact.phone,
                    "name": message.contact.name,
                    "push_name": message.contact.push_name
                }
            }

            # Include media info when available (e.g., audio URL)
            if message.media_info and message.media_info.url:
                input_data["audio_url"] = message.media_info.url
                if message.media_info.mime_type:
                    input_data["content_type"] = message.media_info.mime_type

            payload = {
                "workflow_name": workflow_name,
                "input_data": input_data
            }
            
            self.logger.info(f"Sending message to orchestrator: {message.message_id}")
            self.logger.debug(f"Payload: {payload}")
            
            # Set timeout for orchestrator requests (30 seconds)
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with self.session.post(
                url, 
                json=payload, 
                headers=headers,
                timeout=timeout
            ) as response:
                response_data = await response.json()
                
                if response.status == 200:
                    self.logger.info(f"Message processed by orchestrator successfully")
                    return {
                        "status": "success",
                        "response": response_data
                    }
                else:
                    self.logger.error(f"Orchestrator error: {response.status} - {response_data}")
                    if response.status >= 500:
                        raise aiohttp.ClientError(f"Server error: {response.status}")
                    return {
                        "status": "error",
                        "error": response_data,
                        "status_code": response.status
                    }
                    
        except aiohttp.ClientTimeout:
            self.logger.error("Timeout sending message to orchestrator")
            raise aiohttp.ClientError("Timeout communicating with orchestrator")
        except Exception as e:
            self.logger.error(f"Error sending to orchestrator: {str(e)}")
            raise
    
    async def get_orchestrator_health(self) -> Dict[str, Any]:
        """
        Check orchestrator service health
        
        Returns:
            Health status response
        """
        try:
            await self._ensure_session()
            
            url = f"{self.base_url}/health"
            
            # Short timeout for health checks
            timeout = aiohttp.ClientTimeout(total=5)
            
            async with self.session.get(url, timeout=timeout) as response:
                if response.status == 200:
                    response_data = await response.json()
                    return {
                        "status": "healthy",
                        "response": response_data
                    }
                else:
                    return {
                        "status": "unhealthy",
                        "status_code": response.status
                    }
                    
        except aiohttp.ClientTimeout:
            return {
                "status": "timeout",
                "error": "Timeout checking orchestrator health"
            }
        except Exception as e:
            self.logger.error(f"Error checking orchestrator health: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def send_response_back_to_whatsapp(
        self,
        instance_id: str,
        phone_number: str,
        response_content: str,
        reply_to: str = None
    ) -> Dict[str, Any]:
        """
        Send orchestrator response back to WhatsApp via webhook endpoint
        
        Args:
            instance_id: WhatsApp instance ID
            phone_number: Target phone number  
            response_content: Response content from orchestrator
            reply_to: Message ID to reply to
            
        Returns:
            Response status
        """
        try:
            await self._ensure_session()
            
            url = f"{self.base_url}/send-response"
            headers = {
                "Content-Type": "application/json"
            }
            
            payload = {
                "instance_id": instance_id,
                "phone_number": phone_number,
                "content": response_content,
                "reply_to": reply_to
            }
            
            self.logger.info(f"Sending response back to WhatsApp: {phone_number}")
            
            timeout = aiohttp.ClientTimeout(total=10)
            
            async with self.session.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout
            ) as response:
                if response.status == 200:
                    response_data = await response.json()
                    return {
                        "status": "success",
                        "response": response_data
                    }
                else:
                    response_data = await response.json()
                    return {
                        "status": "error",
                        "error": response_data,
                        "status_code": response.status
                    }
                    
        except Exception as e:
            self.logger.error(f"Error sending response to WhatsApp: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
