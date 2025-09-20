"""
Caso de uso principal: Processar consulta do usuário.
"""

import asyncio
from typing import Dict, Any, Optional, List
from uuid import UUID

from shared.src.utils.logging import get_logger
from shared.src.domain.base import UseCase

from ..services.conversation_service import ConversationService
from ..services.property_service import PropertyService
from ..services.ai_orchestrator import AIOrchestrator


logger = get_logger(__name__)


class ProcessUserQueryUseCase(UseCase):
    """Caso de uso para processar consulta do usuário."""
    
    def __init__(
        self,
        conversation_service: ConversationService,
        property_service: PropertyService,
        ai_orchestrator: AIOrchestrator
    ):
        self.conversation_service = conversation_service
        self.property_service = property_service
        self.ai_orchestrator = ai_orchestrator
    
    async def execute(
        self,
        user_id: str,
        conversation_id: str,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Executa o processamento da consulta do usuário."""
        
        try:
            logger.info(
                "Processando consulta do usuário",
                user_id=user_id,
                conversation_id=conversation_id,
                message_preview=message[:100] + "..." if len(message) > 100 else message
            )
            
            # 1. Obter contexto da conversa
            conversation_context = await self.conversation_service.get_or_create_context(
                UUID(user_id), UUID(conversation_id)
            )
            
            # 2. Classificar intenção e extrair entidades
            intent_result = await self.ai_orchestrator.classify_intent(message)
            intent = intent_result.get("intent", "general_inquiry")
            entities = intent_result.get("entities", {})
            
            logger.info("Intenção classificada", intent=intent, entities=entities)
            
            # 3. Processar baseado na intenção
            if intent == "property_search":
                response = await self._handle_property_search(
                    message, entities, conversation_context, context or {}
                )
            
            elif intent == "property_inquiry":
                response = await self._handle_property_inquiry(
                    message, entities, conversation_context, context or {}
                )
            
            elif intent == "market_information":
                response = await self._handle_market_information(
                    message, entities, conversation_context
                )
            
            elif intent == "greeting":
                response = await self._handle_greeting(
                    message, conversation_context
                )
            
            else:
                response = await self._handle_general_inquiry(
                    message, conversation_context
                )
            
            # 4. Atualizar contexto da conversa
            await self.conversation_service.update_context(
                UUID(conversation_id),
                {
                    "last_intent": intent,
                    "last_entities": entities,
                    "response_type": response.get("response_type", "text")
                }
            )
            
            # 5. Armazenar interação na memória
            await self.conversation_service.store_interaction(
                UUID(user_id),
                UUID(conversation_id),
                message,
                response.get("response", "")
            )
            
            logger.info("Consulta processada com sucesso", user_id=user_id)
            
            return {
                "success": True,
                "intent": intent,
                "response": response.get("response", ""),
                "response_type": response.get("response_type", "text"),
                "suggestions": response.get("suggestions", []),
                "properties": response.get("properties", []),
                "metadata": response.get("metadata", {})
            }
            
        except Exception as e:
            logger.error(
                "Erro ao processar consulta do usuário",
                user_id=user_id,
                error=str(e),
                exc_info=True
            )
            
            return {
                "success": False,
                "error": str(e),
                "response": "Desculpe, ocorreu um erro ao processar sua mensagem. Tente novamente.",
                "response_type": "error"
            }
    
    async def _handle_property_search(
        self,
        message: str,
        entities: Dict[str, Any],
        conversation_context,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Processa busca por imóveis."""
        
        # Extrair critérios de busca
        search_criteria = await self.ai_orchestrator.extract_search_criteria(
            message, entities, conversation_context.search_criteria
        )
        
        logger.info("Critérios de busca extraídos", criteria=search_criteria)
        
        # Buscar imóveis
        properties = await self.property_service.search_properties(
            search_criteria, limit=5
        )
        
        if properties:
            # Gerar apresentação dos imóveis
            response_text = await self.ai_orchestrator.format_property_presentation(
                properties, search_criteria
            )
            
            # Atualizar últimos imóveis mostrados
            property_ids = [str(prop.id) for prop in properties]
            await self.conversation_service.update_last_properties_shown(
                conversation_context.id, property_ids
            )
            
            return {
                "response": response_text,
                "response_type": "property_list",
                "properties": [prop.to_dict() for prop in properties],
                "suggestions": [
                    "Ver mais detalhes de algum imóvel",
                    "Agendar visita",
                    "Ajustar critérios de busca",
                    "Ver imóveis similares"
                ],
                "metadata": {
                    "search_criteria": search_criteria,
                    "total_found": len(properties)
                }
            }
        else:
            suggestions_response = await self.ai_orchestrator.generate_search_suggestions(
                search_criteria
            )
            
            return {
                "response": f"Não encontrei imóveis que atendam exatamente seus critérios. {suggestions_response}",
                "response_type": "no_results",
                "suggestions": [
                    "Expandir área de busca",
                    "Ajustar faixa de preço",
                    "Ver opções similares",
                    "Falar com corretor"
                ],
                "metadata": {
                    "search_criteria": search_criteria,
                    "total_found": 0
                }
            }
    
    async def _handle_property_inquiry(
        self,
        message: str,
        entities: Dict[str, Any],
        conversation_context,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Processa interesse em imóvel específico."""
        
        property_reference = entities.get("property_reference")
        
        if property_reference and conversation_context.last_properties_shown:
            try:
                # Determinar qual imóvel foi referenciado
                property_index = int(property_reference) - 1
                if 0 <= property_index < len(conversation_context.last_properties_shown):
                    property_id = conversation_context.last_properties_shown[property_index]
                    
                    # Buscar detalhes completos do imóvel
                    property_details = await self.property_service.get_property_details(
                        UUID(property_id)
                    )
                    
                    if property_details:
                        response_text = await self.ai_orchestrator.generate_property_details_response(
                            property_details, message
                        )
                        
                        return {
                            "response": response_text,
                            "response_type": "property_details",
                            "properties": [property_details.to_dict()],
                            "suggestions": [
                                "Agendar visita",
                                "Falar com corretor",
                                "Ver imóveis similares",
                                "Simular financiamento"
                            ],
                            "metadata": {
                                "property_id": str(property_details.id),
                                "inquiry_type": "details"
                            }
                        }
            except (ValueError, IndexError):
                pass
        
        # Resposta genérica para interesse sem referência específica
        response_text = await self.ai_orchestrator.generate_response(
            message, conversation_context, intent="property_inquiry"
        )
        
        return {
            "response": response_text,
            "response_type": "inquiry_response",
            "suggestions": [
                "Me conte mais sobre o que procura",
                "Posso ajudar com informações específicas",
                "Vamos buscar opções juntos"
            ]
        }
    
    async def _handle_market_information(
        self,
        message: str,
        entities: Dict[str, Any],
        conversation_context
    ) -> Dict[str, Any]:
        """Processa pedidos de informação sobre o mercado."""
        
        # Buscar informações na base de conhecimento
        knowledge_response = await self.ai_orchestrator.query_knowledge_base(
            message, context="market_information"
        )
        
        response_text = await self.ai_orchestrator.generate_response(
            message,
            conversation_context,
            intent="market_information",
            knowledge=knowledge_response
        )
        
        return {
            "response": response_text,
            "response_type": "market_info",
            "suggestions": [
                "Ver tendências por bairro",
                "Comparar preços",
                "Dicas de investimento",
                "Falar com especialista"
            ],
            "metadata": {
                "sources": knowledge_response.get("sources", [])
            }
        }
    
    async def _handle_greeting(
        self,
        message: str,
        conversation_context
    ) -> Dict[str, Any]:
        """Processa saudações."""
        
        response_text = await self.ai_orchestrator.generate_greeting_response(
            conversation_context
        )
        
        return {
            "response": response_text,
            "response_type": "greeting",
            "suggestions": [
                "Buscar imóveis para compra",
                "Buscar imóveis para aluguel",
                "Avaliar meu imóvel",
                "Informações sobre o mercado"
            ]
        }
    
    async def _handle_general_inquiry(
        self,
        message: str,
        conversation_context
    ) -> Dict[str, Any]:
        """Processa consultas gerais."""
        
        # Buscar na base de conhecimento
        knowledge_response = await self.ai_orchestrator.query_knowledge_base(message)
        
        response_text = await self.ai_orchestrator.generate_response(
            message,
            conversation_context,
            knowledge=knowledge_response
        )
        
        return {
            "response": response_text,
            "response_type": "general",
            "suggestions": [
                "Como posso ajudar com imóveis?",
                "Buscar propriedades",
                "Informações sobre financiamento",
                "Falar com corretor"
            ],
            "metadata": {
                "sources": knowledge_response.get("sources", [])
            }
        }