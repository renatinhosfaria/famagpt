"""
Message Publisher para sistema de filas Redis Streams
Publica mensagens com prioridade e metadata
"""

from shared.queue.redis_stream_queue import RedisStreamQueue
from shared.logging.structured_logger import get_logger
from typing import Dict, Any, Optional
import os

logger = get_logger(__name__)

class MessagePublisher:
    """
    Publisher de mensagens para Redis Streams
    
    Features:
    - Priorização automática baseada no tipo de mensagem
    - Metadata contextual
    - IDs determinísticos para idempotência
    - Integração com observabilidade
    """
    
    def __init__(self, redis_url: Optional[str] = None):
        self.queue = RedisStreamQueue(
            redis_url=redis_url or os.getenv("REDIS_URL", "redis://localhost:6379"),
            stream_name="messages:stream",
            consumer_group="processors"
        )
    
    async def initialize(self):
        """Initialize queue connection"""
        await self.queue.connect()
        logger.info("Message publisher initialized")
    
    async def shutdown(self):
        """Shutdown queue connection"""
        await self.queue.disconnect()
        logger.info("Message publisher shutdown")
    
    async def publish_for_processing(
        self, 
        message: Dict[str, Any],
        priority: Optional[int] = None,
        use_message_id_as_stream_id: bool = True
    ) -> str:
        """
        Publish message to processing queue
        
        Args:
            message: Message payload
            priority: Custom priority (lower = higher priority)
            use_message_id_as_stream_id: Use wa_message_id as stream ID for ordering
        """
        try:
            # Calculate priority if not provided
            if priority is None:
                priority = self._calculate_priority(message)
            
            # Add processing metadata
            message['priority'] = priority
            message['published_by'] = 'webhooks_service'
            
            # Determine stream message ID
            message_id = "*"  # Default: auto-generated
            if use_message_id_as_stream_id and message.get('wa_message_id'):
                # Use wa_message_id to ensure ordering per conversation
                message_id = message['wa_message_id']
            
            # Publish to stream
            stream_msg_id = await self.queue.publish(
                message=message,
                message_id=message_id,
                priority=priority
            )
            
            logger.info(
                "Message published to processing queue",
                stream_message_id=stream_msg_id,
                wa_message_id=message.get('wa_message_id'),
                message_type=message.get('message_type'),
                priority=priority
            )
            
            return stream_msg_id
            
        except Exception as e:
            logger.error(
                "Failed to publish message to queue",
                error=str(e),
                wa_message_id=message.get('wa_message_id'),
                exc_info=True
            )
            raise
    
    def _calculate_priority(self, message: Dict[str, Any]) -> int:
        """
        Calculate message priority based on type and context
        
        Priority levels:
        0: System/critical messages
        1: Text messages (fast processing)
        2: Media messages (slower processing)
        3: Large files/documents
        """
        message_type = message.get('message_type', 'text').lower()
        
        # System messages have highest priority
        if message.get('is_system_message') or message_type == 'system':
            return 0
        
        # Text messages are fast to process
        if message_type in ['text', 'emoji']:
            return 1
        
        # Voice/audio get medium priority (transcription needed)
        if message_type in ['audio', 'voice', 'ptt']:
            return 2
        
        # Images get medium priority (analysis possible)
        if message_type in ['image', 'sticker']:
            return 2
        
        # Videos and documents are slowest
        if message_type in ['video', 'document']:
            return 3
        
        # Unknown types get medium priority
        return 2
    
    async def publish_high_priority(self, message: Dict[str, Any]) -> str:
        """Publish message with high priority (priority 0)"""
        return await self.publish_for_processing(message, priority=0)
    
    async def publish_batch(
        self,
        messages: list[Dict[str, Any]],
        preserve_order: bool = True
    ) -> list[str]:
        """
        Publish multiple messages as a batch
        
        Args:
            messages: List of messages to publish
            preserve_order: Whether to preserve order using sequential IDs
        """
        published_ids = []
        
        for i, message in enumerate(messages):
            try:
                if preserve_order:
                    # Use sequential IDs to preserve order
                    base_id = message.get('wa_message_id', f"batch_{i}")
                    stream_id = f"{base_id}_{i:04d}"
                else:
                    stream_id = "*"
                
                published_id = await self.queue.publish(
                    message=message,
                    message_id=stream_id,
                    priority=self._calculate_priority(message)
                )
                published_ids.append(published_id)
                
            except Exception as e:
                logger.error(
                    f"Failed to publish message {i} in batch",
                    error=str(e),
                    message_id=message.get('wa_message_id')
                )
                # Continue with remaining messages
                published_ids.append(None)
        
        logger.info(f"Published batch of {len(messages)} messages, {len([x for x in published_ids if x])} successful")
        return published_ids
    
    async def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        try:
            return await self.queue.get_stream_info()
        except Exception as e:
            logger.error(f"Error getting queue status: {e}")
            return {"error": str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for publisher"""
        try:
            return await self.queue.health_check()
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

# Export main class
__all__ = ['MessagePublisher']