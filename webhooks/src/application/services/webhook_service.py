"""
Application service for webhook processing
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from ...domain.entities import WhatsAppMessage, OutgoingMessage
from ...domain.entities.conversation_state import ConversationState
from ...domain.protocols import (
    WebhookParserProtocol,
    MessageSenderProtocol,
    OrchestratorClientProtocol,
    DatabaseClientProtocol
)

# Shared modules
from shared.src.utils.logging import get_logger
from shared.src.infrastructure.redis_client import RedisClient


class WebhookService:
    """Service for handling webhook operations"""
    
    def __init__(
        self,
        parser: WebhookParserProtocol,
        sender: MessageSenderProtocol,
        orchestrator: OrchestratorClientProtocol,
        database: DatabaseClientProtocol,
        redis_client: RedisClient
    ):
        self.parser = parser
        self.sender = sender
        self.orchestrator = orchestrator
        self.database = database
        self.redis = redis_client
        self.conversation_state = ConversationState(redis_client.client)
        self.logger = get_logger("webhook_service")
    
    async def process_incoming_webhook(
        self,
        webhook_data: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Process incoming webhook message
        
        Args:
            webhook_data: Raw webhook data from Evolution API
            
        Returns:
            Processing result
        """
        try:
            # Parse webhook data
            message = await self.parser.parse_incoming_message(webhook_data)
            
            if not message:
                self.logger.warning("Failed to parse webhook data")
                return {"status": "error", "message": "Failed to parse webhook"}
            
            # Check for duplicate messages
            if message.wa_message_id and await self.database.check_message_exists(message.wa_message_id):
                self.logger.info(f"Duplicate message {message.wa_message_id}")
                # Registrar mensagem duplicada nas métricas
                try:
                    from shared.src.utils.metrics import MetricsCollector
                    MetricsCollector.record_duplicate_message(message.instance_id)
                except ImportError:
                    pass
                return {"status": "skipped", "reason": "duplicate"}
            
            # Get conversation lock to prevent concurrent processing
            conversation_id = f"{message.instance_id}:{message.phone_number}"
            timeout = self.conversation_state.get_dynamic_lock_timeout(message.message_type.value)
            lock_acquired = await self.conversation_state.get_conversation_lock(conversation_id, timeout)
            
            if not lock_acquired:
                self.logger.warning(f"Could not acquire lock for conversation {conversation_id}")
                # Registrar falha de lock nas métricas
                try:
                    from shared.src.utils.metrics import MetricsCollector
                    MetricsCollector.record_lock_failure(message.message_type.value)
                except ImportError:
                    pass
                return {"status": "retry", "reason": "conversation_locked"}
            
            try:
                # Check message ordering
                if await self.conversation_state.is_out_of_order(conversation_id, message.timestamp):
                    self.logger.warning(f"Out of order message {message.wa_message_id}")
                    # Registrar mensagem fora de ordem nas métricas
                    try:
                        from shared.src.utils.metrics import MetricsCollector
                        MetricsCollector.record_out_of_order_message(message.instance_id)
                    except ImportError:
                        pass
                    return {"status": "skipped", "reason": "out_of_order"}
                
                # Process message (existing logic)
                result = await self._process_message_internal(message, conversation_id)
                
                # Update conversation state
                await self.conversation_state.set_last_timestamp(conversation_id, message.timestamp)
                
                # Mark as processed
                if message.wa_message_id:
                    await self.database.mark_message_processed(message.wa_message_id)
                
                return result
                
            finally:
                await self.conversation_state.release_conversation_lock(conversation_id)
                
        except Exception as e:
            self.logger.error(f"Error processing webhook: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    async def _process_message_internal(
        self,
        message: WhatsAppMessage,
        conversation_id: str
    ) -> Dict[str, str]:
        """
        Internal method for processing message with reliability improvements
        
        Args:
            message: Parsed WhatsApp message
            conversation_id: Unique conversation identifier
            
        Returns:
            Processing result
        """
        try:
            # Persist message to database
            await self._persist_message_to_database(message)
            
            # Cache message
            await self._cache_message(message)
            
            # Mark as read
            if message.instance_id and message.message_id:
                await self.sender.mark_as_read(
                    message.instance_id, 
                    message.message_id
                )
            
            # Send typing indicator
            if message.instance_id and message.phone_number:
                await self.sender.send_typing_indicator(
                    message.instance_id,
                    message.phone_number,
                    typing=True
                )
            
            # Send to orchestrator
            orchestrator_response = await self.orchestrator.send_message_to_orchestrator(message)

            # Try to send response back to WhatsApp if we have content
            try:
                if orchestrator_response and orchestrator_response.get("status") == "success":
                    resp = orchestrator_response.get("response") or {}
                    output = resp.get("output_data") if isinstance(resp, dict) else None
                    content = None
                    if isinstance(output, dict):
                        content = (
                            output.get("formatted_response")
                            or output.get("greeting")
                            or output.get("answer")
                            or output.get("response")
                        )
                    # Fallback generic content
                    if not content:
                        content = "Tudo certo por aqui. Como posso ajudar você com imóveis hoje?"

                    await self.send_response_message(
                        instance_id=message.instance_id,
                        phone_number=message.phone_number,
                        content=content,
                        reply_to=message.message_id,
                    )
            except Exception as send_err:
                self.logger.warning(f"Failed to send WhatsApp response: {send_err}")
            
            # Stop typing
            if message.instance_id and message.phone_number:
                await self.sender.send_typing_indicator(
                    message.instance_id,
                    message.phone_number,
                    typing=False
                )
            
            self.logger.info(f"Message processed successfully: {message.message_id}")
            
            return {
                "status": "success",
                "message_id": message.message_id,
                "orchestrator_response": orchestrator_response
            }
            
        except Exception as e:
            self.logger.error(f"Error processing message internally: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    async def send_response_message(
        self,
        instance_id: str,
        phone_number: str,
        content: str,
        reply_to: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send response message via WhatsApp
        
        Args:
            instance_id: WhatsApp instance ID
            phone_number: Target phone number
            content: Message content
            reply_to: Message ID to reply to
            
        Returns:
            Send result
        """
        try:
            message = OutgoingMessage(
                instance_id=instance_id,
                phone_number=phone_number,
                content=content,
                reply_to=reply_to
            )
            
            result = await self.sender.send_message(message)
            
            self.logger.info(f"Response sent to {phone_number}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Error sending response: {str(e)}")
            raise
    
    async def _cache_message(self, message: WhatsAppMessage) -> None:
        """Cache message in Redis"""
        try:
            cache_key = f"message:{message.instance_id}:{message.message_id}"
            message_data = {
                "message_id": message.message_id,
                "phone_number": message.phone_number,
                "content": message.content,
                "message_type": message.message_type.value,
                "timestamp": message.timestamp.isoformat(),
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.redis.set_json(cache_key, message_data, ttl=3600)  # 1 hour
            
        except Exception as e:
            self.logger.warning(f"Failed to cache message: {str(e)}")
    
    async def get_cached_message(
        self,
        instance_id: str,
        message_id: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieve cached message"""
        try:
            cache_key = f"message:{instance_id}:{message_id}"
            return await self.redis.get_json(cache_key)
        except Exception as e:
            self.logger.warning(f"Failed to retrieve cached message: {str(e)}")
            return None
    
    async def _persist_message_to_database(self, message: WhatsAppMessage) -> None:
        """Persist message and user data to database."""
        try:
            # Create or get user
            user = await self.database.create_or_get_user(
                phone=message.phone_number,
                name=None  # Name will be updated when available
            )
            user_id = user.get("id")
            
            if not user_id:
                self.logger.error("Failed to get user ID from database")
                return
            
            # Get or create active conversation
            conversation = await self.database.get_active_conversation(
                user_id=user_id,
                instance_id=message.instance_id
            )
            
            if not conversation:
                # Create new conversation
                conversation = await self.database.create_conversation(
                    user_id=user_id,
                    instance_id=message.instance_id,
                    context={"channel": "whatsapp"}
                )
            
            conversation_id = conversation.get("id")
            if not conversation_id:
                self.logger.error("Failed to get conversation ID from database")
                return
            
            # Save message
            await self.database.save_message(
                message=message,
                conversation_id=conversation_id,
                user_id=user_id
            )
            
            # Update conversation activity
            await self.database.update_conversation_activity(conversation_id)
            
            self.logger.info(f"Message {message.message_id} persisted to database")
            
        except Exception as e:
            self.logger.error(f"Failed to persist message to database: {str(e)}")
            # Continue processing even if database save fails
