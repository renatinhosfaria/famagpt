"""
Database client implementation for webhooks service.
"""
import json
from typing import Dict, Any, Optional
from datetime import datetime
from uuid import UUID, uuid4

from shared.src.infrastructure.http_client import ServiceClient
from shared.src.utils.logging import get_logger

from ...domain.protocols import DatabaseClientProtocol
from ...domain.entities import WhatsAppMessage


class DatabaseClient(DatabaseClientProtocol):
    """HTTP client for Database service."""
    
    def __init__(self, database_url: str):
        self.client = ServiceClient("webhooks", database_url)
        self.logger = get_logger("webhooks_database_client")
    
    async def __aenter__(self):
        await self.client.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()
    
    async def create_or_get_user(
        self,
        phone: str,
        name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create user or get existing by phone number."""
        try:
            # Try to get existing user first using the correct endpoint
            # Only send non-None parameters
            params = {}
            if name is not None:
                params["name"] = name
                params["push_name"] = name
            
            response = await self.client.get(f"/users/phone/{phone}", params=params)
            
            # Database service returns {"user": {...}} directly without status field
            if response and response.get("user"):
                self.logger.info(f"Found existing user for phone: {phone}")
                return response.get("user", {})
            
            # If we reach here, user doesn't exist, but the database service
            # should have created it via get_or_create_user_by_phone endpoint
            self.logger.warning(f"User creation should have happened automatically for phone: {phone}")
            raise Exception(f"Unexpected response from database service: {response}")
                
        except Exception as e:
            self.logger.error(f"Error creating/getting user for phone {phone}: {str(e)}")
            raise
    
    async def create_conversation(
        self,
        user_id: UUID,
        instance_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create new conversation."""
        try:
            # Build URL with query parameters since POST doesn't accept params
            url = f"/conversations?user_id={str(user_id)}&instance_id={instance_id}"
            if context and context.get("phone"):
                url += f"&phone={context.get('phone')}"
            
            response = await self.client.post(url)
            
            if response.get("status") == "success":
                self.logger.info(f"Created conversation for user {user_id}")
                return response.get("conversation", {})
            else:
                raise Exception(f"Failed to create conversation: {response}")
                
        except Exception as e:
            self.logger.error(f"Error creating conversation for user {user_id}: {str(e)}")
            raise
    
    async def get_active_conversation(
        self,
        user_id: UUID,
        instance_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get active conversation for user in specific instance."""
        try:
            params = {
                "user_id": str(user_id),
                "status": "active",
                "instance_id": instance_id
            }
            
            response = await self.client.get("/conversations", params=params)
            
            if response.get("status") == "success":
                conversations = response.get("conversations", [])
                if conversations:
                    self.logger.info(f"Found active conversation for user {user_id}")
                    return conversations[0]
            
            return None
                
        except Exception as e:
            self.logger.error(f"Error getting active conversation for user {user_id}: {str(e)}")
            return None
    
    async def save_message(
        self,
        message: WhatsAppMessage,
        conversation_id: UUID,
        user_id: UUID
    ) -> Dict[str, Any]:
        """Save incoming WhatsApp message."""
        try:
            message_data = {
                "conversation_id": str(conversation_id),
                "user_id": str(user_id),
                "content": message.content,
                "message_type": message.message_type.value,
                "status": "received",
                "metadata": {
                    "instance_id": message.instance_id,
                    "phone_number": message.phone_number,
                    "timestamp": message.timestamp.isoformat(),
                    "attachments": message.attachments or []
                },
                "source_message_id": message.message_id,
                "processed_content": None,
                "attachments": message.attachments or []
            }
            
            response = await self.client.post("/messages", json_data=message_data)
            
            if response.get("status") == "success":
                self.logger.info(f"Saved message {message.message_id} to database")
                return response.get("message", {})
            else:
                raise Exception(f"Failed to save message: {response}")
                
        except Exception as e:
            self.logger.error(f"Error saving message {message.message_id}: {str(e)}")
            raise
    
    async def update_conversation_activity(
        self,
        conversation_id: UUID
    ) -> None:
        """Update conversation last activity timestamp."""
        try:
            update_data = {
                "last_activity": datetime.utcnow().isoformat()
            }
            
            response = await self.client.patch(f"/conversations/{conversation_id}", json_data=update_data)
            
            if response.get("status") != "success":
                self.logger.warning(f"Failed to update conversation activity: {response}")
                
        except Exception as e:
            self.logger.error(f"Error updating conversation activity {conversation_id}: {str(e)}")
    
    async def get_conversation_messages(
        self,
        conversation_id: UUID,
        limit: int = 50
    ) -> list[Dict[str, Any]]:
        """Get recent messages from conversation."""
        try:
            params = {"limit": limit}
            response = await self.client.get(f"/conversations/{conversation_id}/messages", params=params)
            
            if response.get("status") == "success":
                return response.get("messages", [])
            else:
                self.logger.warning(f"Failed to get conversation messages: {response}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error getting conversation messages {conversation_id}: {str(e)}")
            return []

    async def check_message_exists(self, wa_message_id: str) -> bool:
        """Verificar se mensagem já foi processada"""
        try:
            response = await self.client.get(f"/messages/wa/{wa_message_id}")
            return response.get("status") == "success"
        except Exception:
            return False

    async def mark_message_processed(self, wa_message_id: str):
        """Marcar mensagem como processada"""
        try:
            update_data = {
                "processing_status": "completed", 
                "processed_at": datetime.utcnow().isoformat()
            }
            await self.client.patch(f"/messages/wa/{wa_message_id}", json_data=update_data)
        except Exception as e:
            self.logger.error(f"Error marking message {wa_message_id} as processed: {str(e)}")