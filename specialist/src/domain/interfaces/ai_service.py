"""
Interfaces para serviços de IA.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from uuid import UUID

from ..entities.user import Message, ConversationContext


class MemoryService(ABC):
    """Interface para serviço de memória."""
    
    @abstractmethod
    async def store_conversation(
        self, 
        user_id: UUID, 
        conversation_id: UUID, 
        messages: List[Message]
    ) -> None:
        """Armazena conversa na memória."""
        pass
    
    @abstractmethod
    async def get_conversation_context(
        self, 
        user_id: UUID, 
        conversation_id: UUID
    ) -> Optional[ConversationContext]:
        """Obtém contexto da conversa."""
        pass
    
    @abstractmethod
    async def update_user_context(
        self, 
        user_id: UUID, 
        context: Dict[str, Any]
    ) -> None:
        """Atualiza contexto do usuário."""
        pass
    
    @abstractmethod
    async def get_relevant_memories(
        self, 
        user_id: UUID, 
        query: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Busca memórias relevantes."""
        pass


class RAGService(ABC):
    """Interface para serviço RAG."""
    
    @abstractmethod
    async def query_knowledge_base(
        self, 
        query: str, 
        context: Optional[str] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """Consulta a base de conhecimento."""
        pass
    
    @abstractmethod
    async def index_document(
        self, 
        content: str, 
        metadata: Dict[str, Any]
    ) -> str:
        """Indexa um documento."""
        pass


class IntentClassificationService(ABC):
    """Interface para classificação de intenções."""
    
    @abstractmethod
    async def classify_intent(self, message: str) -> Dict[str, Any]:
        """Classifica a intenção da mensagem."""
        pass
    
    @abstractmethod
    async def extract_entities(self, message: str) -> Dict[str, Any]:
        """Extrai entidades da mensagem."""
        pass


class ResponseGenerationService(ABC):
    """Interface para geração de respostas."""
    
    @abstractmethod
    async def generate_response(
        self,
        user_message: str,
        context: ConversationContext,
        knowledge: Optional[Dict[str, Any]] = None,
        properties: Optional[List] = None
    ) -> Dict[str, Any]:
        """Gera resposta contextual."""
        pass
    
    @abstractmethod
    async def format_property_presentation(
        self,
        properties: List,
        user_criteria: Dict[str, Any]
    ) -> str:
        """Formata apresentação de imóveis."""
        pass