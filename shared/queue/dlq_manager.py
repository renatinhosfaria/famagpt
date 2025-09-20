"""
Dead Letter Queue Manager para FamaGPT
Sistema de gerenciamento de mensagens falhadas com reprocessamento
"""

import redis.asyncio as redis
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import logging

# Importar métricas para observabilidade
try:
    from shared.monitoring.metrics import track_message_processing
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = logging.getLogger(__name__)

class DLQManager:
    """
    Gerenciador de Dead Letter Queue com funcionalidades avançadas:
    - Armazenamento de mensagens falhadas
    - Reprocessamento seletivo
    - Limpeza automática
    - Análise de padrões de falha
    """
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.dlq_prefix = "dlq:"
    
    async def connect(self):
        """Initialize Redis connection"""
        self.redis_client = redis.from_url(self.redis_url)
        await self.redis_client.ping()
    
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            self.redis_client = None
    
    async def add_to_dlq(
        self,
        queue_name: str,
        message: Dict[str, Any],
        error: str,
        metadata: Optional[Dict[str, Any]] = None,
        original_message_id: Optional[str] = None
    ) -> str:
        """
        Add failed message to DLQ
        
        Args:
            queue_name: Original queue name
            message: Failed message payload
            error: Error description
            metadata: Additional metadata
            original_message_id: Original message ID from stream
        """
        if not self.redis_client:
            await self.connect()
        
        dlq_name = f"{self.dlq_prefix}{queue_name}"
        
        # Create comprehensive DLQ entry
        dlq_entry = {
            "message": json.dumps(message),
            "error": error,
            "failed_at": datetime.utcnow().isoformat(),
            "retry_count": str(message.get("retry_count", 0)),
            "original_queue": queue_name,
            "original_message_id": original_message_id or "",
            "metadata": json.dumps(metadata or {}),
            "message_type": message.get("message_type", "unknown"),
            "source": message.get("source", "unknown")
        }
        
        # Add to DLQ stream
        msg_id = await self.redis_client.xadd(dlq_name, dlq_entry)
        
        # Also add to sorted set for time-based queries
        await self.redis_client.zadd(
            f"{dlq_name}:index",
            {msg_id: datetime.utcnow().timestamp()}
        )
        
        # Increment counters
        await self.redis_client.incr(f"{dlq_name}:total")
        await self.redis_client.incr(f"{dlq_name}:errors:{self._categorize_error(error)}")
        
        # Track metric
        if METRICS_AVAILABLE:
            track_message_processing("dlq", "added", message.get("message_type", "unknown"))
        
        logger.error(f"Added message to DLQ {dlq_name}: {msg_id} - {error}")
        return msg_id
    
    def _categorize_error(self, error: str) -> str:
        """Categorize error for statistics"""
        error_lower = error.lower()
        
        if "timeout" in error_lower:
            return "timeout"
        elif "connection" in error_lower:
            return "connection"
        elif "rate" in error_lower or "limit" in error_lower:
            return "rate_limit"
        elif "auth" in error_lower or "permission" in error_lower:
            return "auth"
        elif "validation" in error_lower or "invalid" in error_lower:
            return "validation"
        else:
            return "other"
    
    async def get_dlq_messages(
        self,
        queue_name: str,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        message_type: Optional[str] = None,
        error_category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieve messages from DLQ with filtering
        
        Args:
            queue_name: Queue name to search
            limit: Maximum messages to return
            start_time: Filter by start time
            end_time: Filter by end time
            message_type: Filter by message type
            error_category: Filter by error category
        """
        if not self.redis_client:
            await self.connect()
        
        dlq_name = f"{self.dlq_prefix}{queue_name}"
        
        try:
            # Get messages by time range if specified
            if start_time or end_time:
                start = start_time.timestamp() if start_time else '-inf'
                end = end_time.timestamp() if end_time else '+inf'
                
                msg_ids = await self.redis_client.zrangebyscore(
                    f"{dlq_name}:index",
                    start,
                    end,
                    start=0,
                    num=limit
                )
                
                messages = []
                for msg_id in msg_ids:
                    entries = await self.redis_client.xrange(dlq_name, msg_id, msg_id)
                    if entries:
                        messages.extend(entries)
            else:
                # Get latest messages
                messages = await self.redis_client.xrevrange(dlq_name, count=limit)
            
            # Parse and filter messages
            result = []
            for msg_id, data in messages:
                try:
                    parsed_message = {
                        "id": msg_id,
                        "message": json.loads(data[b'message'].decode()),
                        "error": data[b'error'].decode(),
                        "failed_at": data[b'failed_at'].decode(),
                        "retry_count": int(data.get(b'retry_count', 0)),
                        "original_queue": data[b'original_queue'].decode(),
                        "original_message_id": data.get(b'original_message_id', b'').decode(),
                        "message_type": data.get(b'message_type', b'unknown').decode(),
                        "source": data.get(b'source', b'unknown').decode()
                    }
                    
                    # Apply filters
                    if message_type and parsed_message["message_type"] != message_type:
                        continue
                    
                    if error_category:
                        if self._categorize_error(parsed_message["error"]) != error_category:
                            continue
                    
                    # Add metadata if exists
                    if b'metadata' in data:
                        try:
                            parsed_message["metadata"] = json.loads(data[b'metadata'].decode())
                        except:
                            pass
                    
                    result.append(parsed_message)
                    
                except Exception as parse_error:
                    logger.error(f"Error parsing DLQ message {msg_id}: {parse_error}")
                    continue
            
            return result
            
        except redis.ResponseError as e:
            logger.error(f"Error getting DLQ messages: {e}")
            return []
    
    async def reprocess_dlq_message(
        self,
        queue_name: str,
        message_id: str,
        target_queue: Optional[str] = None,
        reset_retry_count: bool = True
    ) -> bool:
        """
        Reprocess a message from DLQ
        
        Args:
            queue_name: Original queue name
            message_id: DLQ message ID
            target_queue: Target queue (defaults to original)
            reset_retry_count: Whether to reset retry count
        """
        if not self.redis_client:
            await self.connect()
        
        dlq_name = f"{self.dlq_prefix}{queue_name}"
        
        try:
            # Get message from DLQ
            entries = await self.redis_client.xrange(dlq_name, message_id, message_id)
            if not entries:
                logger.error(f"Message {message_id} not found in DLQ")
                return False
            
            msg_id, data = entries[0]
            
            # Parse message
            original_message = json.loads(data[b'message'].decode())
            original_queue = target_queue or data[b'original_queue'].decode()
            
            # Prepare message for reprocessing
            if reset_retry_count:
                original_message['retry_count'] = 0
            
            original_message['reprocessed_from_dlq'] = True
            original_message['dlq_message_id'] = msg_id
            original_message['reprocessed_at'] = datetime.utcnow().isoformat()
            
            # Add back to original queue
            reprocess_id = await self.redis_client.xadd(
                original_queue,
                {
                    "data": json.dumps(original_message),
                    "timestamp": datetime.utcnow().isoformat(),
                    "retry_count": "0" if reset_retry_count else str(original_message.get("retry_count", 0)),
                    "source": "dlq_reprocess"
                }
            )
            
            # Remove from DLQ
            await self.redis_client.xdel(dlq_name, msg_id)
            await self.redis_client.zrem(f"{dlq_name}:index", msg_id)
            
            # Update counters
            await self.redis_client.incr(f"{dlq_name}:reprocessed")
            
            # Track metric
            if METRICS_AVAILABLE:
                track_message_processing("dlq", "reprocessed", original_message.get("message_type", "unknown"))
            
            logger.info(f"Reprocessed message {message_id} from DLQ to {original_queue} as {reprocess_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error reprocessing message {message_id}: {e}")
            return False
    
    async def bulk_reprocess(
        self,
        queue_name: str,
        message_ids: List[str],
        target_queue: Optional[str] = None
    ) -> Dict[str, bool]:
        """Bulk reprocess multiple messages from DLQ"""
        results = {}
        
        for msg_id in message_ids:
            try:
                success = await self.reprocess_dlq_message(
                    queue_name, msg_id, target_queue
                )
                results[msg_id] = success
            except Exception as e:
                logger.error(f"Error bulk reprocessing {msg_id}: {e}")
                results[msg_id] = False
        
        return results
    
    async def purge_old_dlq_messages(
        self,
        queue_name: str,
        older_than_days: int = 7
    ) -> int:
        """Purge old messages from DLQ"""
        if not self.redis_client:
            await self.connect()
        
        dlq_name = f"{self.dlq_prefix}{queue_name}"
        cutoff_time = datetime.utcnow() - timedelta(days=older_than_days)
        
        try:
            # Get old message IDs
            old_msg_ids = await self.redis_client.zrangebyscore(
                f"{dlq_name}:index",
                '-inf',
                cutoff_time.timestamp()
            )
            
            if not old_msg_ids:
                return 0
            
            # Delete messages
            await self.redis_client.xdel(dlq_name, *old_msg_ids)
            await self.redis_client.zrem(f"{dlq_name}:index", *old_msg_ids)
            
            # Update counter
            await self.redis_client.incr(f"{dlq_name}:purged", len(old_msg_ids))
            
            logger.info(f"Purged {len(old_msg_ids)} old messages from DLQ {dlq_name}")
            return len(old_msg_ids)
            
        except Exception as e:
            logger.error(f"Error purging DLQ messages: {e}")
            return 0
    
    async def get_dlq_stats(self, queue_name: str) -> Dict[str, Any]:
        """Get comprehensive DLQ statistics"""
        if not self.redis_client:
            await self.connect()
        
        dlq_name = f"{self.dlq_prefix}{queue_name}"
        
        try:
            # Get basic counts
            total = await self.redis_client.get(f"{dlq_name}:total") or 0
            current = await self.redis_client.xlen(dlq_name)
            reprocessed = await self.redis_client.get(f"{dlq_name}:reprocessed") or 0
            purged = await self.redis_client.get(f"{dlq_name}:purged") or 0
            
            # Get time range
            oldest = await self.redis_client.xrange(dlq_name, count=1)
            newest = await self.redis_client.xrevrange(dlq_name, count=1)
            
            # Get error categories
            error_keys = await self.redis_client.keys(f"{dlq_name}:errors:*")
            error_stats = {}
            for key in error_keys:
                category = key.decode().split(":")[-1]
                count = await self.redis_client.get(key) or 0
                error_stats[category] = int(count)
            
            stats = {
                "queue": queue_name,
                "total_failed": int(total),
                "current_size": current,
                "reprocessed": int(reprocessed),
                "purged": int(purged),
                "oldest_message": None,
                "newest_message": None,
                "error_categories": error_stats
            }
            
            if oldest:
                stats["oldest_message"] = oldest[0][1][b'failed_at'].decode()
            if newest:
                stats["newest_message"] = newest[0][1][b'failed_at'].decode()
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting DLQ stats: {e}")
            return {
                "queue": queue_name,
                "error": str(e)
            }
    
    async def analyze_failure_patterns(
        self,
        queue_name: str,
        hours_back: int = 24
    ) -> Dict[str, Any]:
        """Analyze failure patterns in DLQ"""
        if not self.redis_client:
            await self.connect()
        
        start_time = datetime.utcnow() - timedelta(hours=hours_back)
        messages = await self.get_dlq_messages(
            queue_name,
            limit=1000,
            start_time=start_time
        )
        
        # Analyze patterns
        message_type_failures = {}
        error_category_failures = {}
        hourly_failures = {}
        source_failures = {}
        
        for msg in messages:
            # Message type analysis
            msg_type = msg.get("message_type", "unknown")
            message_type_failures[msg_type] = message_type_failures.get(msg_type, 0) + 1
            
            # Error category analysis
            error_category = self._categorize_error(msg["error"])
            error_category_failures[error_category] = error_category_failures.get(error_category, 0) + 1
            
            # Hourly analysis
            try:
                failed_at = datetime.fromisoformat(msg["failed_at"])
                hour_key = failed_at.strftime("%Y-%m-%d %H:00")
                hourly_failures[hour_key] = hourly_failures.get(hour_key, 0) + 1
            except:
                pass
            
            # Source analysis
            source = msg.get("source", "unknown")
            source_failures[source] = source_failures.get(source, 0) + 1
        
        return {
            "analysis_period_hours": hours_back,
            "total_failures": len(messages),
            "message_type_failures": dict(sorted(message_type_failures.items(), key=lambda x: x[1], reverse=True)),
            "error_category_failures": dict(sorted(error_category_failures.items(), key=lambda x: x[1], reverse=True)),
            "source_failures": dict(sorted(source_failures.items(), key=lambda x: x[1], reverse=True)),
            "hourly_failures": dict(sorted(hourly_failures.items())),
            "top_errors": self._get_top_errors(messages)
        }
    
    def _get_top_errors(self, messages: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
        """Get top error messages"""
        error_counts = {}
        
        for msg in messages:
            error = msg["error"][:200]  # Truncate for grouping
            if error not in error_counts:
                error_counts[error] = {
                    "error": error,
                    "count": 0,
                    "first_seen": msg["failed_at"],
                    "last_seen": msg["failed_at"]
                }
            
            error_counts[error]["count"] += 1
            error_counts[error]["last_seen"] = msg["failed_at"]
        
        return sorted(error_counts.values(), key=lambda x: x["count"], reverse=True)[:top_n]
    
    async def health_check(self) -> Dict[str, Any]:
        """Check DLQ manager health"""
        try:
            if not self.redis_client:
                await self.connect()
            
            await self.redis_client.ping()
            
            return {
                "status": "healthy",
                "redis_connection": "ok"
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }

# Export main class
__all__ = ['DLQManager']