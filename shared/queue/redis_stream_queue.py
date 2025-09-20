"""
Redis Streams Queue implementation para FamaGPT
Sistema de filas resiliente com consumer groups e auto-recovery
"""

import redis.asyncio as redis
import json
import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import logging

# Importar métricas para observabilidade
try:
    from shared.monitoring.metrics import set_queue_depth, track_message_processing
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

class RedisStreamQueue:
    """
    Redis Streams Queue com consumer groups, retry automático e DLQ
    """
    
    def __init__(
        self,
        redis_url: str,
        stream_name: str = "messages:stream",
        consumer_group: str = "processors",
        max_len: int = 10000,
        block_ms: int = 1000
    ):
        self.redis_url = redis_url
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.max_len = max_len
        self.block_ms = block_ms
        self.redis_client: Optional[redis.Redis] = None
    
    async def connect(self):
        """Initialize Redis connection and consumer group"""
        self.redis_client = redis.from_url(self.redis_url)
        
        # Test connection
        await self.redis_client.ping()
        
        # Create consumer group if not exists
        try:
            await self.redis_client.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id='0',
                mkstream=True
            )
            logger.info(f"Created consumer group {self.consumer_group} for stream {self.stream_name}")
        except redis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
            logger.info(f"Consumer group {self.consumer_group} already exists")
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
    
    async def publish(
        self,
        message: Dict[str, Any],
        message_id: str = "*",
        priority: int = 1
    ) -> str:
        """
        Publish message to stream
        
        Args:
            message: Message payload
            message_id: Custom message ID (default: auto-generated)
            priority: Message priority (lower = higher priority)
        """
        if not self.redis_client:
            await self.connect()
        
        # Add metadata
        message_data = {
            "data": json.dumps(message),
            "timestamp": datetime.utcnow().isoformat(),
            "retry_count": str(message.get("retry_count", 0)),
            "priority": str(priority),
            "source": message.get("source", "unknown")
        }
        
        # Add to stream with automatic trimming
        msg_id = await self.redis_client.xadd(
            self.stream_name,
            message_data,
            maxlen=self.max_len,
            id=message_id
        )
        
        # Update metrics
        if METRICS_AVAILABLE:
            queue_length = await self.redis_client.xlen(self.stream_name)
            set_queue_depth(self.stream_name, queue_length)
        
        logger.info(f"Published message {msg_id} to stream {self.stream_name}")
        return msg_id
    
    async def consume(
        self,
        consumer_name: str,
        callback: Callable,
        batch_size: int = 1,
        error_handler: Optional[Callable] = None,
        auto_claim_idle_ms: int = 300000  # 5 minutes
    ):
        """
        Consume messages from stream with auto-recovery
        
        Args:
            consumer_name: Unique consumer identifier
            callback: Message processing function
            batch_size: Number of messages to process at once
            error_handler: Custom error handler function
            auto_claim_idle_ms: Time before claiming idle messages
        """
        if not self.redis_client:
            await self.connect()
        
        logger.info(f"Starting consumer {consumer_name} for stream {self.stream_name}")
        
        while True:
            try:
                # Claim abandoned messages first
                if auto_claim_idle_ms > 0:
                    claimed = await self.claim_abandoned_messages(
                        consumer_name, 
                        auto_claim_idle_ms
                    )
                    if claimed > 0:
                        logger.info(f"Claimed {claimed} abandoned messages")
                
                # Read new messages from stream
                messages = await self.redis_client.xreadgroup(
                    self.consumer_group,
                    consumer_name,
                    {self.stream_name: '>'},
                    count=batch_size,
                    block=self.block_ms
                )
                
                if not messages:
                    continue
                
                # Process each message
                for stream_name, stream_messages in messages:
                    for msg_id, data in stream_messages:
                        await self._process_single_message(
                            msg_id, data, callback, error_handler
                        )
                        
                        # Update queue depth metric
                        if METRICS_AVAILABLE:
                            queue_length = await self.redis_client.xlen(self.stream_name)
                            set_queue_depth(self.stream_name, queue_length)
                            
            except redis.ConnectionError as e:
                logger.error(f"Redis connection error: {e}")
                await asyncio.sleep(5)  # Wait before retrying
                await self.connect()  # Reconnect
                
            except Exception as e:
                logger.error(f"Consumer error: {e}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _process_single_message(
        self,
        msg_id: str,
        data: Dict[bytes, bytes],
        callback: Callable,
        error_handler: Optional[Callable]
    ):
        """Process a single message with error handling"""
        try:
            # Parse message
            message = json.loads(data[b'data'].decode())
            priority = int(data.get(b'priority', b'1'))
            retry_count = int(data.get(b'retry_count', b'0'))
            
            # Add message metadata
            message['_msg_id'] = msg_id
            message['_priority'] = priority
            message['_retry_count'] = retry_count
            
            # Process with callback
            result = await callback(message, msg_id)
            
            # Acknowledge message on success
            await self.redis_client.xack(
                self.stream_name,
                self.consumer_group,
                msg_id
            )
            
            # Track success metric
            if METRICS_AVAILABLE:
                track_message_processing(
                    "queue", "success", 
                    message.get("message_type", "unknown")
                )
            
            logger.info(f"Successfully processed message {msg_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing message {msg_id}: {e}")
            
            # Track error metric
            if METRICS_AVAILABLE:
                track_message_processing(
                    "queue", "error",
                    message.get("message_type", "unknown") if 'message' in locals() else "unknown"
                )
            
            if error_handler:
                try:
                    await error_handler(message if 'message' in locals() else data, msg_id, e)
                except Exception as handler_error:
                    logger.error(f"Error handler failed: {handler_error}")
                    await self._handle_failed_message(msg_id, data, e)
            else:
                # Default error handling
                await self._handle_failed_message(msg_id, data, e)
    
    async def _handle_failed_message(
        self,
        msg_id: str,
        data: Dict[bytes, bytes],
        error: Exception,
        max_retries: int = 3
    ):
        """Handle failed message with retry logic"""
        try:
            message = json.loads(data[b'data'].decode())
            retry_count = int(data.get(b'retry_count', b'0'))
            
            if retry_count >= max_retries:
                # Send to DLQ
                await self.send_to_dlq(msg_id, message, str(error))
            else:
                # Retry with exponential backoff
                delay = min(2 ** retry_count, 60)  # Max 60 seconds
                await asyncio.sleep(delay)
                
                message['retry_count'] = retry_count + 1
                message['last_error'] = str(error)
                message['retry_at'] = datetime.utcnow().isoformat()
                
                # Republish with updated retry count
                await self.publish(message, priority=int(data.get(b'priority', b'1')))
            
            # Acknowledge original message
            await self.redis_client.xack(
                self.stream_name,
                self.consumer_group,
                msg_id
            )
            
        except Exception as handle_error:
            logger.error(f"Failed to handle failed message {msg_id}: {handle_error}")
    
    async def send_to_dlq(
        self,
        msg_id: str,
        message: Dict[str, Any],
        error: str
    ):
        """Send failed message to Dead Letter Queue"""
        dlq_name = f"{self.stream_name}:dlq"
        
        dlq_data = {
            "original_id": msg_id,
            "data": json.dumps(message),
            "error": error,
            "failed_at": datetime.utcnow().isoformat(),
            "stream": self.stream_name,
            "retry_count": str(message.get("retry_count", 0))
        }
        
        dlq_msg_id = await self.redis_client.xadd(dlq_name, dlq_data)
        logger.error(f"Message {msg_id} sent to DLQ as {dlq_msg_id}: {error}")
        
        return dlq_msg_id
    
    async def get_pending_messages(
        self,
        consumer_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get pending messages for consumer"""
        if not self.redis_client:
            await self.connect()
            
        try:
            result = await self.redis_client.xpending_range(
                self.stream_name,
                self.consumer_group,
                min='-',
                max='+',
                count=100,
                consumer=consumer_name
            )
            
            pending = []
            for item in result:
                pending.append({
                    "message_id": item['message_id'],
                    "consumer": item['consumer'], 
                    "idle_time_ms": item['time_since_delivered'],
                    "delivery_count": item['times_delivered']
                })
            
            return pending
        except redis.ResponseError as e:
            logger.error(f"Error getting pending messages: {e}")
            return []
    
    async def claim_abandoned_messages(
        self,
        consumer_name: str,
        idle_time_ms: int = 300000  # 5 minutes
    ) -> int:
        """Claim messages abandoned by other consumers"""
        if not self.redis_client:
            await self.connect()
            
        try:
            result = await self.redis_client.xautoclaim(
                self.stream_name,
                self.consumer_group,
                consumer_name,
                idle_time_ms,
                start_id='0',
                count=10
            )
            
            claimed_messages = result[1] if len(result) > 1 else []
            claimed_count = len(claimed_messages)
            
            if claimed_count > 0:
                logger.info(f"Consumer {consumer_name} claimed {claimed_count} abandoned messages")
            
            return claimed_count
            
        except redis.ResponseError as e:
            logger.error(f"Error claiming abandoned messages: {e}")
            return 0
    
    async def get_stream_info(self) -> Dict[str, Any]:
        """Get comprehensive stream statistics"""
        if not self.redis_client:
            await self.connect()
            
        try:
            info = await self.redis_client.xinfo_stream(self.stream_name)
            
            try:
                groups = await self.redis_client.xinfo_groups(self.stream_name)
            except redis.ResponseError:
                groups = []
            
            # Get DLQ info
            dlq_name = f"{self.stream_name}:dlq"
            dlq_length = 0
            try:
                dlq_length = await self.redis_client.xlen(dlq_name)
            except redis.ResponseError:
                pass
            
            return {
                "stream_name": self.stream_name,
                "length": info['length'],
                "first_entry": info.get('first-entry'),
                "last_entry": info.get('last-entry'),
                "dlq_length": dlq_length,
                "consumer_groups": [
                    {
                        "name": g['name'],
                        "consumers": g['consumers'],
                        "pending": g['pending'],
                        "last_delivered_id": g.get('last-delivered-id')
                    }
                    for g in groups
                ]
            }
        except Exception as e:
            logger.error(f"Error getting stream info: {e}")
            return {
                "stream_name": self.stream_name,
                "error": str(e)
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Check queue health"""
        try:
            if not self.redis_client:
                await self.connect()
            
            # Test basic operations
            await self.redis_client.ping()
            
            # Get queue stats
            info = await self.get_stream_info()
            pending_count = sum(g['pending'] for g in info.get('consumer_groups', []))
            
            return {
                "status": "healthy",
                "queue_length": info.get('length', 0),
                "pending_messages": pending_count,
                "dlq_length": info.get('dlq_length', 0),
                "consumer_groups": len(info.get('consumer_groups', []))
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

# Export main class
__all__ = ['RedisStreamQueue']