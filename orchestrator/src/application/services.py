"""
Orchestrator application services.
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime

from shared.src.utils.logging import get_logger

from ..domain.interfaces import AgentService
from ..domain.models import WorkflowExecution


logger = get_logger(__name__)


class OrchestrationService:
    """High-level orchestration service."""
    
    def __init__(self, agent_service: AgentService, memory_client=None):
        self.agent_service = agent_service
        self.memory_client = memory_client
    
    async def process_message(
        self,
        message_content: str,
        user_id: UUID,
        conversation_id: UUID,
        message_type: str = "text"
    ) -> Dict[str, Any]:
        """Process incoming message and route to appropriate workflow."""
        
        logger.info(
            "Processing message",
            user_id=user_id,
            conversation_id=conversation_id,
            message_type=message_type
        )
        
        try:
            # Store incoming message in memory
            if self.memory_client:
                await self.memory_client.store_message(
                    user_id=str(user_id),
                    conversation_id=str(conversation_id),
                    content=message_content,
                    sender="user",
                    message_type=message_type,
                    metadata={"timestamp": datetime.utcnow().isoformat()}
                )
            
            # Analyze message intent
            intent_analysis = await self._analyze_message_intent(
                message_content, message_type
            )
            
            # Route to appropriate workflow
            workflow_name = self._determine_workflow(intent_analysis)
            
            # Get user context from memory for personalization
            user_context = {}
            if self.memory_client:
                user_context = await self.memory_client.get_user_context(str(user_id))
            
            # Prepare workflow input
            workflow_input = {
                "message_content": message_content,
                "message_type": message_type,
                "user_id": str(user_id),
                "conversation_id": str(conversation_id),
                "intent_analysis": intent_analysis,
                "user_context": user_context
            }
            
            logger.info(
                "Routing to workflow",
                workflow_name=workflow_name,
                intent=intent_analysis.get("intent"),
                conversation_id=conversation_id,
                memory_enabled=self.memory_client is not None
            )
            
            return {
                "workflow_name": workflow_name,
                "workflow_input": workflow_input,
                "intent": intent_analysis
            }
            
        except Exception as e:
            logger.error(
                "Failed to process message",
                error=str(e),
                conversation_id=conversation_id,
                user_id=user_id
            )
            raise
    
    async def _analyze_message_intent(
        self, 
        message_content: str, 
        message_type: str
    ) -> Dict[str, Any]:
        """Analyze message intent."""
        
        # Simple intent classification logic
        # This will be enhanced with actual ML models
        
        content_lower = message_content.lower()
        
        # Real estate related keywords
        property_keywords = [
            "casa", "apartamento", "imovel", "imóvel", "comprar", "vender",
            "alugar", "aluguel", "venda", "corretor", "imobiliaria", "imobiliária",
            "terreno", "lote", "quarto", "sala", "cozinha", "banheiro",
            "garagem", "quintal", "piscina", "valor", "preço", "preco"
        ]
        
        # Greeting keywords
        greeting_keywords = [
            "oi", "olá", "ola", "bom dia", "boa tarde", "boa noite",
            "hello", "hi", "hey", "tchau", "ate logo"
        ]
        
        # Question keywords
        question_keywords = [
            "como", "onde", "quando", "quanto", "qual", "que", "quem",
            "porque", "por que", "?", "ajuda", "duvida", "dúvida"
        ]
        
        intent = "general"
        confidence = 0.5
        entities = {}
        
        if any(keyword in content_lower for keyword in property_keywords):
            intent = "property_search"
            confidence = 0.8
        elif any(keyword in content_lower for keyword in greeting_keywords):
            intent = "greeting"
            confidence = 0.9
        elif any(keyword in content_lower for keyword in question_keywords):
            intent = "question"
            confidence = 0.7
        elif message_type == "audio":
            intent = "audio_processing"
            confidence = 1.0
        
        return {
            "intent": intent,
            "confidence": confidence,
            "entities": entities,
            "message_type": message_type,
            "keywords_found": []
        }
    
    def _determine_workflow(self, intent_analysis: Dict[str, Any]) -> str:
        """Determine which workflow to execute based on intent."""
        
        intent = intent_analysis.get("intent", "general")
        message_type = intent_analysis.get("message_type", "text")
        
        # Workflow routing logic
        if message_type == "audio":
            return "audio_processing_workflow"
        elif intent == "property_search":
            return "property_search_workflow"
        elif intent == "greeting":
            return "greeting_workflow"
        elif intent == "question":
            return "question_answering_workflow"
        else:
            return "general_conversation_workflow"
