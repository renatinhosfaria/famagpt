"""
Redis client and utilities.
"""
import json
from typing import Any, Dict, List, Optional, Union
import redis.asyncio as redis
from redis.asyncio import Redis

from ..utils.config import RedisSettings
from ..utils.logging import get_logger


logger = get_logger(__name__)


class RedisClient:
    """Async Redis client wrapper."""
    
    def __init__(self, settings: RedisSettings):
        self.settings = settings
        self._client: Optional[Redis] = None
    
    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self._client = redis.from_url(
                self.settings.url,
                password=self.settings.password,
                db=self.settings.db,
                max_connections=self.settings.max_connections,
                retry_on_timeout=self.settings.retry_on_timeout,
                decode_responses=True
            )
            
            # Test connection
            await self._client.ping()
            logger.info("Connected to Redis", url=self.settings.url)
            
        except Exception as e:
            logger.error("Failed to connect to Redis", error=str(e))
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            logger.info("Disconnected from Redis")
    
    @property
    def client(self) -> Redis:
        """Get Redis client."""
        if not self._client:
            raise RuntimeError("Redis client not connected")
        return self._client
    
    async def get(self, key: str) -> Optional[str]:
        """Get value by key."""
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error("Redis GET failed", key=key, error=str(e))
            return None
    
    async def set(
        self, 
        key: str, 
        value: str, 
        ttl: Optional[int] = None
    ) -> bool:
        """Set key-value pair with optional TTL."""
        try:
            return await self.client.set(key, value, ex=ttl)
        except Exception as e:
            logger.error("Redis SET failed", key=key, error=str(e))
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key."""
        try:
            result = await self.client.delete(key)
            return result > 0
        except Exception as e:
            logger.error("Redis DELETE failed", key=key, error=str(e))
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            logger.error("Redis EXISTS failed", key=key, error=str(e))
            return False
    
    async def expire(self, key: str, ttl: int) -> bool:
        """Set TTL for key."""
        try:
            return await self.client.expire(key, ttl)
        except Exception as e:
            logger.error("Redis EXPIRE failed", key=key, ttl=ttl, error=str(e))
            return False

    async def scan_keys(self, pattern: str) -> List[str]:
        """Scan and return keys matching a pattern."""
        try:
            keys = []
            async for k in self.client.scan_iter(match=pattern):
                keys.append(k)
            return keys
        except Exception as e:
            logger.error("Redis SCAN failed", pattern=pattern, error=str(e))
            return []
    
    async def get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Get JSON value by key."""
        value = await self.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.error("Failed to decode JSON", key=key, error=str(e))
        return None
    
    async def set_json(
        self, 
        key: str, 
        value: Dict[str, Any], 
        ttl: Optional[int] = None
    ) -> bool:
        """Set JSON value with optional TTL."""
        try:
            json_str = json.dumps(value, default=str)
            return await self.set(key, json_str, ttl)
        except (TypeError, ValueError) as e:
            logger.error("Failed to encode JSON", key=key, error=str(e))
            return False
    
    async def lpush(self, key: str, *values: str) -> int:
        """Push values to left of list."""
        try:
            return await self.client.lpush(key, *values)
        except Exception as e:
            logger.error("Redis LPUSH failed", key=key, error=str(e))
            return 0

    async def list_push(self, key: str, value: Any) -> int:
        """Alias for LPUSH to keep compatibility with previous naming."""
        try:
            if not isinstance(value, str):
                value = json.dumps(value, default=str)
            return await self.client.lpush(key, value)
        except Exception as e:
            logger.error("Redis LIST_PUSH failed", key=key, error=str(e))
            return 0

    async def list_get_all(self, key: str) -> List[Any]:
        """Return all list items, attempting JSON decode per item."""
        try:
            items = await self.client.lrange(key, 0, -1)
            result = []
            for item in items:
                try:
                    result.append(json.loads(item))
                except Exception:
                    result.append(item)
            return result
        except Exception as e:
            logger.error("Redis LRANGE failed", key=key, error=str(e))
            return []
    
    async def rpop(self, key: str) -> Optional[str]:
        """Pop value from right of list."""
        try:
            return await self.client.rpop(key)
        except Exception as e:
            logger.error("Redis RPOP failed", key=key, error=str(e))
            return None
    
    async def llen(self, key: str) -> int:
        """Get list length."""
        try:
            return await self.client.llen(key)
        except Exception as e:
            logger.error("Redis LLEN failed", key=key, error=str(e))
            return 0
    
    async def sadd(self, key: str, *members: str) -> int:
        """Add members to set."""
        try:
            return await self.client.sadd(key, *members)
        except Exception as e:
            logger.error("Redis SADD failed", key=key, error=str(e))
            return 0

    async def set_add(self, key: str, member: str) -> int:
        """Compatibility helper to add a single member to a set."""
        try:
            return await self.client.sadd(key, member)
        except Exception as e:
            logger.error("Redis SET_ADD failed", key=key, error=str(e))
            return 0
    
    async def srem(self, key: str, *members: str) -> int:
        """Remove members from set."""
        try:
            return await self.client.srem(key, *members)
        except Exception as e:
            logger.error("Redis SREM failed", key=key, error=str(e))
            return 0
    
    async def smembers(self, key: str) -> set:
        """Get all set members."""
        try:
            return await self.client.smembers(key)
        except Exception as e:
            logger.error("Redis SMEMBERS failed", key=key, error=str(e))
            return set()

    async def set_members(self, key: str) -> List[str]:
        """Compatibility helper returning list of set members."""
        try:
            members = await self.client.smembers(key)
            # redis-py returns a set of strings (decode_responses=True)
            return list(members)
        except Exception as e:
            logger.error("Redis SET_MEMBERS failed", key=key, error=str(e))
            return []
    
    async def sismember(self, key: str, member: str) -> bool:
        """Check if member is in set."""
        try:
            return await self.client.sismember(key, member)
        except Exception as e:
            logger.error("Redis SISMEMBER failed", key=key, member=member, error=str(e))
            return False
    
    async def hset(self, key: str, field: str, value: str) -> bool:
        """Set hash field."""
        try:
            return await self.client.hset(key, field, value) > 0
        except Exception as e:
            logger.error("Redis HSET failed", key=key, field=field, error=str(e))
            return False
    
    async def hget(self, key: str, field: str) -> Optional[str]:
        """Get hash field."""
        try:
            return await self.client.hget(key, field)
        except Exception as e:
            logger.error("Redis HGET failed", key=key, field=field, error=str(e))
            return None
    
    async def hgetall(self, key: str) -> Dict[str, str]:
        """Get all hash fields."""
        try:
            return await self.client.hgetall(key)
        except Exception as e:
            logger.error("Redis HGETALL failed", key=key, error=str(e))
            return {}
    
    async def hdel(self, key: str, *fields: str) -> int:
        """Delete hash fields."""
        try:
            return await self.client.hdel(key, *fields)
        except Exception as e:
            logger.error("Redis HDEL failed", key=key, fields=fields, error=str(e))
            return 0
    
    async def incr(self, key: str) -> int:
        """Increment counter."""
        try:
            return await self.client.incr(key)
        except Exception as e:
            logger.error("Redis INCR failed", key=key, error=str(e))
            return 0
    
    async def decr(self, key: str) -> int:
        """Decrement counter."""
        try:
            return await self.client.decr(key)
        except Exception as e:
            logger.error("Redis DECR failed", key=key, error=str(e))
            return 0


class CacheManager:
    """High-level cache manager."""
    
    def __init__(self, redis_client: RedisClient, prefix: str = "cache"):
        self.redis = redis_client
        self.prefix = prefix
    
    def _make_key(self, key: str) -> str:
        """Make prefixed cache key."""
        return f"{self.prefix}:{key}"
    
    async def get(self, key: str) -> Optional[Any]:
        """Get cached value."""
        cache_key = self._make_key(key)
        return await self.redis.get_json(cache_key)
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set cached value."""
        cache_key = self._make_key(key)
        return await self.redis.set_json(cache_key, value, ttl)
    
    async def delete(self, key: str) -> bool:
        """Delete cached value."""
        cache_key = self._make_key(key)
        return await self.redis.delete(cache_key)
    
    async def exists(self, key: str) -> bool:
        """Check if cached value exists."""
        cache_key = self._make_key(key)
        return await self.redis.exists(cache_key)


class PubSubManager:
    """Redis pub/sub manager."""
    
    def __init__(self, redis_client: RedisClient):
        self.redis = redis_client
    
    async def publish(self, channel: str, message: Dict[str, Any]) -> int:
        """Publish message to channel."""
        try:
            message_str = json.dumps(message, default=str)
            return await self.redis.client.publish(channel, message_str)
        except Exception as e:
            logger.error("Failed to publish message", channel=channel, error=str(e))
            return 0
    
    async def subscribe(self, *channels: str):
        """Subscribe to channels."""
        pubsub = self.redis.client.pubsub()
        await pubsub.subscribe(*channels)
        return pubsub
