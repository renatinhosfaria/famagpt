"""
Evolution API message sender implementation
"""

from typing import Dict, Any
import aiohttp
import asyncio

from ...domain.protocols import MessageSenderProtocol
from ...domain.entities import OutgoingMessage

# Shared modules
from shared.src.utils.logging import get_logger
from shared.src.utils.config import AppSettings as Settings


class EvolutionMessageSender(MessageSenderProtocol):
    """Message sender for Evolution API"""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger("evolution_sender")
        self.base_url = settings.whatsapp.evolution_api_url
        self.api_key = settings.whatsapp.evolution_api_key
        self.session = None
    
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
    
    async def send_message(
        self,
        message: OutgoingMessage
    ) -> Dict[str, Any]:
        """
        Send message via Evolution API
        
        Args:
            message: OutgoingMessage to send
            
        Returns:
            Response from Evolution API
        """
        try:
            await self._ensure_session()
            
            url = f"{self.base_url}/message/sendText/{message.instance_id}"
            headers = {
                "Content-Type": "application/json",
                "apikey": self.api_key
            }
            
            payload = message.to_evolution_api_format()
            
            self.logger.info(f"Sending message to {message.phone_number}")
            self.logger.debug(f"Payload: {payload}")
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                response_data = await response.json()
                
                if response.status == 200 or response.status == 201:
                    self.logger.info(f"Message sent successfully: {response_data}")
                    return {
                        "status": "success",
                        "message_id": response_data.get("key", {}).get("id"),
                        "response": response_data
                    }
                else:
                    self.logger.error(f"Failed to send message: {response.status} - {response_data}")
                    return {
                        "status": "error",
                        "error": response_data,
                        "status_code": response.status
                    }
                    
        except Exception as e:
            self.logger.error(f"Error sending message: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
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
            True if successful
        """
        try:
            await self._ensure_session()
            
            url = f"{self.base_url}/chat/presence/{instance_id}"
            headers = {
                "Content-Type": "application/json",
                "apikey": self.api_key
            }
            
            payload = {
                "number": phone_number,
                "presence": "composing" if typing else "paused"
            }
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status in [200, 201]:
                    self.logger.debug(f"Typing indicator sent: {typing}")
                    return True
                else:
                    response_data = await response.json()
                    self.logger.warning(f"Failed to send typing indicator: {response_data}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error sending typing indicator: {str(e)}")
            return False
    
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
            True if successful
        """
        try:
            await self._ensure_session()
            
            url = f"{self.base_url}/chat/markMessageAsRead/{instance_id}"
            headers = {
                "Content-Type": "application/json",
                "apikey": self.api_key
            }
            
            payload = {
                "readMessages": [
                    {
                        "id": message_id,
                        "fromMe": False,
                        "remoteJid": message_id.split("@")[0] + "@s.whatsapp.net"
                    }
                ]
            }
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                if response.status in [200, 201]:
                    self.logger.debug(f"Message marked as read: {message_id}")
                    return True
                else:
                    response_data = await response.json()
                    self.logger.warning(f"Failed to mark message as read: {response_data}")
                    return False
                    
        except Exception as e:
            self.logger.error(f"Error marking message as read: {str(e)}")
            return False
    
    async def send_media_message(
        self,
        instance_id: str,
        phone_number: str,
        media_url: str,
        media_type: str,
        caption: str = ""
    ) -> Dict[str, Any]:
        """
        Send media message via Evolution API
        
        Args:
            instance_id: WhatsApp instance ID
            phone_number: Target phone number
            media_url: URL of media file
            media_type: Type of media (image, video, audio, document)
            caption: Media caption
            
        Returns:
            Response from Evolution API
        """
        try:
            await self._ensure_session()
            
            # Map media types to Evolution API endpoints
            endpoint_map = {
                "image": "sendMedia",
                "video": "sendMedia", 
                "audio": "sendWhatsAppAudio",
                "document": "sendMedia"
            }
            
            endpoint = endpoint_map.get(media_type, "sendMedia")
            url = f"{self.base_url}/message/{endpoint}/{instance_id}"
            
            headers = {
                "Content-Type": "application/json",
                "apikey": self.api_key
            }
            
            payload = {
                "number": phone_number,
                "mediaMessage": {
                    "media": media_url,
                    "caption": caption
                }
            }
            
            async with self.session.post(url, json=payload, headers=headers) as response:
                response_data = await response.json()
                
                if response.status in [200, 201]:
                    self.logger.info(f"Media message sent successfully")
                    return {
                        "status": "success",
                        "message_id": response_data.get("key", {}).get("id"),
                        "response": response_data
                    }
                else:
                    self.logger.error(f"Failed to send media message: {response.status} - {response_data}")
                    return {
                        "status": "error",
                        "error": response_data,
                        "status_code": response.status
                    }
                    
        except Exception as e:
            self.logger.error(f"Error sending media message: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
