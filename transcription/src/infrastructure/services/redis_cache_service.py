"""
Redis cache service for transcription results
"""

from typing import Optional
import json
from datetime import datetime

from shared.src.infrastructure.redis_client import RedisClient
from shared.src.utils.logging import get_logger

from ...domain.entities.transcription import Transcription
from ...domain.protocols.transcription_service import CacheServiceProtocol


logger = get_logger("transcription.redis_cache")


class RedisCacheService(CacheServiceProtocol):
    """Redis implementation for caching transcription results"""
    
    def __init__(self, redis_client: RedisClient):
        self.redis_client = redis_client
        self.key_prefix = "transcription:cache:"
    
    async def get_cached_transcription(
        self, 
        cache_key: str
    ) -> Optional[Transcription]:
        """
        Get cached transcription result
        
        Args:
            cache_key: Cache key for the transcription
            
        Returns:
            Cached transcription or None if not found
        """
        try:
            full_key = f"{self.key_prefix}{cache_key}"
            cached_data = await self.redis_client.get_json(full_key)
            
            if not cached_data:
                logger.debug(f"Cache miss for key: {cache_key}")
                return None
            
            logger.debug(f"Cache hit for key: {cache_key}")
            
            # Convert cached data back to Transcription entity
            transcription = Transcription(
                id=cached_data.get("id"),
                audio_filename=cached_data.get("audio_filename"),
                text=cached_data.get("text"),
                language=cached_data.get("language"),
                confidence=cached_data.get("confidence"),
                duration_seconds=cached_data.get("duration_seconds"),
                processing_time_seconds=cached_data.get("processing_time_seconds"),
                model_used=cached_data.get("model_used"),
                created_at=self._parse_datetime(cached_data.get("created_at"))
            )
            
            return transcription
            
        except Exception as e:
            logger.error(f"Error getting cached transcription: {str(e)}")
            return None
    
    async def cache_transcription(
        self,
        cache_key: str,
        transcription: Transcription,
        ttl_seconds: int = 3600
    ) -> None:
        """
        Cache transcription result
        
        Args:
            cache_key: Cache key for the transcription
            transcription: Transcription result to cache
            ttl_seconds: Time to live in seconds (default: 1 hour)
        """
        try:
            full_key = f"{self.key_prefix}{cache_key}"
            
            # Convert transcription to dict for JSON serialization
            cache_data = {
                "id": transcription.id,
                "audio_filename": transcription.audio_filename,
                "text": transcription.text,
                "language": transcription.language,
                "confidence": transcription.confidence,
                "duration_seconds": transcription.duration_seconds,
                "processing_time_seconds": transcription.processing_time_seconds,
                "model_used": transcription.model_used,
                "created_at": transcription.created_at.isoformat() if transcription.created_at else None,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.redis_client.set_json(
                full_key,
                cache_data,
                ttl=ttl_seconds
            )
            
            logger.debug(f"Cached transcription with key: {cache_key}, TTL: {ttl_seconds}s")
            
        except Exception as e:
            logger.error(f"Error caching transcription: {str(e)}")
            # Don't raise exception - caching failure shouldn't break the flow
    
    async def invalidate_cache(self, cache_key: str) -> None:
        """
        Invalidate cached transcription
        
        Args:
            cache_key: Cache key to invalidate
        """
        try:
            full_key = f"{self.key_prefix}{cache_key}"
            deleted = await self.redis_client.delete(full_key)
            
            if deleted:
                logger.debug(f"Cache invalidated for key: {cache_key}")
            else:
                logger.debug(f"No cache found to invalidate for key: {cache_key}")
                
        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}")
    
    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO datetime string back to datetime object"""
        if not datetime_str:
            return None
        
        try:
            return datetime.fromisoformat(datetime_str)
        except Exception as e:
            logger.warning(f"Error parsing datetime: {datetime_str}, error: {e}")
            return None