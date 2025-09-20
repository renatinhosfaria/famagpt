"""
Orquestrador de serviços de IA.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID

from shared.src.utils.logging import get_logger

from ...domain.entities.property import Property
from ...domain.entities.user import ConversationContext
from ...domain.interfaces.ai_service import (
    MemoryService, 
    RAGService, 
    IntentClassificationService,
    ResponseGenerationService
)


logger = get_logger(__name__)


class AIOrchestrator:
    """Orquestrador central dos serviços de IA."""
    
    def __init__(
        self,
        memory_service: MemoryService,
        rag_service: RAGService,
        intent_service: IntentClassificationService,
        response_service: ResponseGenerationService
    ):
        self.memory_service = memory_service
        self.rag_service = rag_service
        self.intent_service = intent_service
        self.response_service = response_service
    
    async def classify_intent(self, message: str) -> Dict[str, Any]:
        """Classifica a intenção da mensagem."""
        
        try:
            result = await self.intent_service.classify_intent(message)
            
            # Extrair entidades também
            entities = await self.intent_service.extract_entities(message)
            result["entities"] = entities.get("entities", {})
            
            logger.debug("Intenção classificada", intent=result.get("intent"), confidence=result.get("confidence"))
            
            return result
            
        except Exception as e:
            logger.error("Erro na classificação de intenção", error=str(e))
            return {
                "intent": "general_inquiry",
                "confidence": 0.5,
                "entities": {},
                "error": str(e)
            }
    
    async def extract_search_criteria(
        self,
        message: str,
        entities: Dict[str, Any],
        existing_criteria: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Extrai critérios de busca da mensagem."""
        
        criteria = existing_criteria.copy() if existing_criteria else {}
        
        # Processar entidades extraídas
        if "location" in entities:
            location = entities["location"]
            if isinstance(location, dict):
                criteria.update({
                    "city": location.get("city", criteria.get("city")),
                    "neighborhood": location.get("neighborhood", criteria.get("neighborhood")),
                })
            else:
                criteria["location"] = str(location)
        
        if "property_type" in entities:
            criteria["property_type"] = entities["property_type"]
        
        if "price_range" in entities:
            price_info = entities["price_range"]
            if isinstance(price_info, dict):
                if price_info.get("min"):
                    criteria["price_min"] = float(price_info["min"])
                if price_info.get("max"):
                    criteria["price_max"] = float(price_info["max"])
            else:
                # Tentar extrair preço do texto
                try:
                    criteria["price_max"] = float(price_info)
                except (ValueError, TypeError):
                    pass
        
        if "bedrooms" in entities:
            try:
                criteria["bedrooms"] = int(entities["bedrooms"])
            except (ValueError, TypeError):
                pass
        
        if "bathrooms" in entities:
            try:
                criteria["bathrooms"] = int(entities["bathrooms"])
            except (ValueError, TypeError):
                pass
        
        # Aplicar padrões para Uberlândia se não especificado
        if not criteria.get("city") and not criteria.get("location"):
            criteria["city"] = "Uberlândia"
            criteria["state"] = "MG"
        
        logger.debug("Critérios de busca extraídos", criteria=criteria)
        
        return criteria
    
    async def query_knowledge_base(
        self,
        query: str,
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """Consulta a base de conhecimento."""
        
        try:
            # Passar contexto como keyword para alinhar com expectativa de teste e clareza
            result = await self.rag_service.query_knowledge_base(
                query, context=context, top_k=5
            )
            
            logger.debug("Consulta à base de conhecimento realizada", query_preview=query[:50])
            
            return result
            
        except Exception as e:
            logger.error("Erro na consulta à base de conhecimento", error=str(e))
            return {
                "answer": "Não consegui encontrar informações específicas sobre isso no momento.",
                "sources": [],
                "error": str(e)
            }
    
    async def generate_response(
        self,
        user_message: str,
        context: ConversationContext,
        intent: Optional[str] = None,
        knowledge: Optional[Dict[str, Any]] = None,
        properties: Optional[List[Property]] = None
    ) -> str:
        """Gera resposta contextual."""
        
        try:
            response = await self.response_service.generate_response(
                user_message, context, knowledge, properties
            )
            
            return response.get("response", "Como posso ajudar você hoje?")
            
        except Exception as e:
            logger.error("Erro na geração de resposta", error=str(e))
            return "Desculpe, ocorreu um erro. Como posso ajudar você de outra forma?"
    
    async def format_property_presentation(
        self,
        properties: List[Property],
        user_criteria: Dict[str, Any]
    ) -> str:
        """Formata apresentação de propriedades."""
        
        try:
            response = await self.response_service.format_property_presentation(
                properties, user_criteria
            )
            
            return response
            
        except Exception as e:
            logger.error("Erro na formatação de propriedades", error=str(e))
            
            # Fallback para formatação simples
            return self._format_properties_fallback(properties)
    
    async def generate_greeting_response(
        self,
        context: ConversationContext
    ) -> str:
        """Gera resposta de saudação personalizada."""
        
        try:
            # Buscar histórico do usuário para personalização
            user_memories = await self.memory_service.get_relevant_memories(
                context.user_id, "greeting", limit=3
            )
            
            is_returning_user = len(user_memories) > 0
            
            if is_returning_user:
                greeting = "Olá novamente! 👋 É bom te ver por aqui!\n\n"
                greeting += "Como posso ajudar você hoje com imóveis? "
                greeting += "Posso continuar de onde paramos ou buscar algo novo."
            else:
                greeting = "Olá! 👋 Bem-vindo à FamaGPT!\n\n"
                greeting += "Sou seu assistente especializado em imóveis de Uberlândia e região. "
                greeting += "Posso ajudar você a encontrar a casa dos seus sonhos, "
                greeting += "avaliar propriedades, ou esclarecer dúvidas sobre o mercado imobiliário."
            
            greeting += "\n\n🏠 Como posso ajudar você hoje?"
            
            return greeting
            
        except Exception as e:
            logger.error("Erro na geração de saudação", error=str(e))
            return "Olá! Como posso ajudar você com imóveis hoje?"
    
    async def generate_search_suggestions(
        self,
        failed_criteria: Dict[str, Any]
    ) -> str:
        """Gera sugestões quando a busca não retorna resultados."""
        
        suggestions = []
        
        if failed_criteria.get("price_max"):
            suggestions.append(f"aumentar o orçamento acima de R$ {failed_criteria['price_max']:,.0f}")
        
        if failed_criteria.get("neighborhood"):
            suggestions.append("considerar bairros próximos")
        
        if failed_criteria.get("bedrooms"):
            suggestions.append("flexibilizar o número de quartos")
        
        if failed_criteria.get("property_type"):
            suggestions.append("considerar outros tipos de imóvel")
        
        if not suggestions:
            suggestions.append("expandir os critérios de busca")
        
        response = "Que tal tentar " + ", ".join(suggestions[:2]) + "? "
        response += "Posso mostrar opções similares que podem te interessar!"
        
        return response
    
    async def generate_property_details_response(
        self,
        property: Property,
        user_message: str
    ) -> str:
        """Gera resposta detalhada sobre uma propriedade específica."""
        
        response = f"📋 **{property.title}**\n\n"
        
        # Informações básicas
        response += f"🏠 **Tipo:** {property.property_type.value.title()}\n"
        response += f"📍 **Local:** {property.address.neighborhood}, {property.address.city}\n"
        
        # Características
        if property.features.bedrooms:
            response += f"🛏️ **Quartos:** {property.features.bedrooms}\n"
        if property.features.bathrooms:
            response += f"🚿 **Banheiros:** {property.features.bathrooms}\n"
        if property.features.area_built:
            response += f"📐 **Área:** {property.features.area_built}m²\n"
        
        # Preço
        if property.financial.price:
            response += f"💰 **Preço:** R$ {property.financial.price:,.0f}\n"
        elif property.financial.rental_price:
            response += f"💰 **Aluguel:** R$ {property.financial.rental_price:,.0f}/mês\n"
        
        # Descrição
        if property.description:
            response += f"\n📝 **Detalhes:** {property.description[:200]}"
            if len(property.description) > 200:
                response += "..."
        
        response += "\n\n🤔 Gostaria de mais informações ou tem alguma pergunta específica sobre este imóvel?"
        
        return response
    
    def _format_properties_fallback(self, properties: List[Property]) -> str:
        """Formatação simples de propriedades em caso de erro."""
        
        if not properties:
            return "Não encontrei propriedades que atendam aos critérios informados."
        
        response = f"Encontrei {len(properties)} propriedades interessantes:\n\n"
        
        for i, prop in enumerate(properties, 1):
            response += f"{i}. **{prop.title}**\n"
            response += f"   📍 {prop.address.neighborhood}\n"
            
            if prop.financial.price:
                response += f"   💰 R$ {prop.financial.price:,.0f}\n"
            elif prop.financial.rental_price:
                response += f"   💰 R$ {prop.financial.rental_price:,.0f}/mês\n"
            
            if prop.features.bedrooms:
                response += f"   🛏️ {prop.features.bedrooms} quartos"
                if prop.features.bathrooms:
                    response += f", {prop.features.bathrooms} banheiros"
                response += "\n"
            
            response += "\n"
        
        response += "Gostaria de ver mais detalhes de algum destes imóveis?"
        
        return response