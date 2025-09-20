"""
Estado de conversação para validação de ordenação de eventos
"""

from datetime import datetime
from typing import Optional
import redis.asyncio as redis

from shared.src.utils.logging import get_logger

logger = get_logger("conversation_state")

class ConversationState:
    """Gerencia estado de conversação para validação de ordenação"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.ttl = 3600  # 1 hour
    
    async def get_last_timestamp(self, conversation_id: str) -> Optional[datetime]:
        """Get last processed message timestamp for conversation"""
        key = f"conv:{conversation_id}:last_ts"
        value = await self.redis.get(key)
        if value:
            return datetime.fromisoformat(value.decode())
        return None
    
    async def set_last_timestamp(self, conversation_id: str, timestamp: datetime):
        """Update last processed message timestamp"""
        key = f"conv:{conversation_id}:last_ts"
        await self.redis.setex(key, self.ttl, timestamp.isoformat())
    
    async def is_out_of_order(self, conversation_id: str, message_timestamp: datetime) -> bool:
        """Check if message is out of order"""
        last_ts = await self.get_last_timestamp(conversation_id)
        if last_ts and message_timestamp < last_ts:
            logger.warning(f"Out of order message detected in conversation {conversation_id}")
            return True
        return False
    
    async def get_conversation_lock(self, conversation_id: str, timeout: int = 10) -> bool:
        """Acquire conversation lock to prevent concurrent processing"""
        key = f"conv:{conversation_id}:lock"
        return await self.redis.set(key, "1", nx=True, ex=timeout)
    
    def get_dynamic_lock_timeout(self, message_type: str) -> int:
        """Calcular timeout de lock baseado no tipo de mensagem"""
        timeouts = {
            "audio": 30,      # Áudios precisam de mais tempo para transcrição
            "voice": 30,      # Mensagens de voz também
            "video": 25,      # Vídeos podem demorar para processar
            "image": 20,      # Imagens com análise
            "document": 20,   # Documentos podem ser grandes
            "text": 10,       # Texto é mais rápido
        }
        return timeouts.get(message_type.lower(), 10)  # Default 10s
    
    async def release_conversation_lock(self, conversation_id: str):
        """Release conversation lock"""
        key = f"conv:{conversation_id}:lock"
        await self.redis.delete(key)