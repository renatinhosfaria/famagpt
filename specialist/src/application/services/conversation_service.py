"""
Serviço de conversação e contexto.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4

from shared.src.utils.logging import get_logger
from shared.src.infrastructure.redis_client import RedisClient

from ...domain.entities.user import ConversationContext, Message, MessageType, ConversationStatus
from ...domain.interfaces.ai_service import MemoryService


logger = get_logger(__name__)


class ConversationService:
    """Serviço para gerenciar conversações e contexto."""
    
    def __init__(
        self,
        redis_client: RedisClient,
        memory_service: MemoryService
    ):
        self.redis_client = redis_client
        self.memory_service = memory_service
    
    async def get_or_create_context(
        self,
        user_id: UUID,
        conversation_id: UUID
    ) -> ConversationContext:
        """Obtém ou cria contexto da conversa."""
        
        # Tentar recuperar do cache primeiro
        cache_key = f"conversation_context:{user_id}:{conversation_id}"
        cached_context = await self.redis_client.get_json(cache_key)
        
        if cached_context:
            logger.debug("Contexto encontrado no cache", conversation_id=str(conversation_id))
            return self._dict_to_context(cached_context)
        
        # Buscar na memória de longo prazo
        stored_context = await self.memory_service.get_conversation_context(
            user_id, conversation_id
        )
        
        if stored_context:
            logger.debug("Contexto encontrado na memória", conversation_id=str(conversation_id))
            # Cachear para acesso rápido
            await self.redis_client.set_json(
                cache_key, 
                self._context_to_dict(stored_context),
                ttl=3600  # 1 hora
            )
            return stored_context
        
        # Criar novo contexto
        logger.info("Criando novo contexto de conversa", conversation_id=str(conversation_id))
        new_context = ConversationContext(
            id=conversation_id,
            user_id=user_id,
            status=ConversationStatus.ACTIVE,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Cachear o novo contexto
        await self.redis_client.set_json(
            cache_key,
            self._context_to_dict(new_context),
            ttl=3600
        )
        
        return new_context
    
    async def update_context(
        self,
        conversation_id: UUID,
        updates: Dict[str, Any]
    ) -> None:
        """Atualiza contexto da conversa."""
        
        # Buscar contexto atual
        cache_key = f"conversation_context:*:{conversation_id}"
        keys = await self.redis_client.scan_keys(cache_key)
        
        if keys:
            for key in keys:
                cached_context = await self.redis_client.get_json(key)
                if cached_context:
                    # Aplicar atualizações
                    cached_context.update(updates)
                    cached_context['updated_at'] = datetime.utcnow().isoformat()
                    
                    # Salvar no cache
                    await self.redis_client.set_json(key, cached_context, ttl=3600)
                    
                    logger.debug(
                        "Contexto atualizado",
                        conversation_id=str(conversation_id),
                        updates=list(updates.keys())
                    )
                    break
    
    async def update_search_criteria(
        self,
        conversation_id: UUID,
        criteria: Dict[str, Any]
    ) -> None:
        """Atualiza critérios de busca no contexto."""
        
        await self.update_context(conversation_id, {
            "search_criteria": criteria,
            "current_intent": "property_search"
        })
    
    async def update_last_properties_shown(
        self,
        conversation_id: UUID,
        property_ids: List[str]
    ) -> None:
        """Atualiza últimos imóveis mostrados."""
        
        await self.update_context(conversation_id, {
            "last_properties_shown": property_ids
        })
    
    async def store_interaction(
        self,
        user_id: UUID,
        conversation_id: UUID,
        user_message: str,
        assistant_response: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Armazena interação na memória."""
        
        messages = [
            Message(
                id=uuid4(),
                conversation_id=conversation_id,
                content=user_message,
                message_type=MessageType.TEXT,
                sender="user",
                metadata=metadata or {},
                timestamp=datetime.utcnow()
            ),
            Message(
                id=uuid4(),
                conversation_id=conversation_id,
                content=assistant_response,
                message_type=MessageType.TEXT,
                sender="assistant",
                metadata=metadata or {},
                timestamp=datetime.utcnow()
            )
        ]
        
        # Armazenar na memória via serviço de memória
        await self.memory_service.store_conversation(
            user_id, conversation_id, messages
        )
        
        logger.debug(
            "Interação armazenada na memória",
            user_id=str(user_id),
            conversation_id=str(conversation_id)
        )
    
    async def get_conversation_history(
        self,
        user_id: UUID,
        conversation_id: UUID,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Obtém histórico da conversa."""
        
        # Buscar na memória
        memories = await self.memory_service.get_relevant_memories(
            user_id, f"conversation:{conversation_id}", limit=limit
        )
        
        return memories
    
    async def add_conversation_tag(
        self,
        conversation_id: UUID,
        tag: str
    ) -> None:
        """Adiciona tag à conversa."""
        
        # Buscar contexto atual
        cache_key = f"conversation_context:*:{conversation_id}"
        keys = await self.redis_client.scan_keys(cache_key)
        
        if keys:
            for key in keys:
                cached_context = await self.redis_client.get_json(key)
                if cached_context:
                    tags = cached_context.get('tags', [])
                    if tag not in tags:
                        tags.append(tag)
                        await self.update_context(conversation_id, {'tags': tags})
                    break
    
    async def close_conversation(
        self,
        conversation_id: UUID,
        summary: Optional[str] = None
    ) -> None:
        """Fecha conversa e persiste contexto."""
        
        updates = {
            'status': ConversationStatus.CLOSED.value,
            'updated_at': datetime.utcnow().isoformat()
        }
        
        if summary:
            updates['conversation_summary'] = summary
        
        await self.update_context(conversation_id, updates)
        
        logger.info("Conversa fechada", conversation_id=str(conversation_id))
    
    def _context_to_dict(self, context: ConversationContext) -> Dict[str, Any]:
        """Converte contexto para dicionário."""
        return {
            "id": str(context.id),
            "user_id": str(context.user_id),
            "status": context.status.value,
            "current_intent": context.current_intent,
            "search_criteria": context.search_criteria,
            "last_properties_shown": context.last_properties_shown,
            "conversation_summary": context.conversation_summary,
            "tags": context.tags,
            "created_at": context.created_at.isoformat() if context.created_at else None,
            "updated_at": context.updated_at.isoformat() if context.updated_at else None
        }
    
    def _dict_to_context(self, data: Dict[str, Any]) -> ConversationContext:
        """Converte dicionário para contexto."""
        return ConversationContext(
            id=UUID(data["id"]),
            user_id=UUID(data["user_id"]),
            status=ConversationStatus(data["status"]),
            current_intent=data.get("current_intent"),
            search_criteria=data.get("search_criteria"),
            last_properties_shown=data.get("last_properties_shown", []),
            conversation_summary=data.get("conversation_summary"),
            tags=data.get("tags", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
        )