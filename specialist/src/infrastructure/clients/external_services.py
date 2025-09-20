"""
Clientes para serviços externos.
"""

import httpx
from typing import Dict, Any, List, Optional
from uuid import UUID

from shared.src.utils.logging import get_logger
from shared.src.infrastructure.http_client import HTTPClient

from ...domain.entities.user import Message, ConversationContext
from ...domain.interfaces.ai_service import MemoryService, RAGService, IntentClassificationService, ResponseGenerationService


logger = get_logger(__name__)


class ExternalMemoryService(MemoryService):
    """Cliente para o serviço de memória externo."""
    
    def __init__(self, http_client: HTTPClient, memory_service_url: str):
        self.http_client = http_client
        self.base_url = memory_service_url.rstrip('/')
    
    async def store_conversation(
        self, 
        user_id: UUID, 
        conversation_id: UUID, 
        messages: List[Message]
    ) -> None:
        """Armazena conversa na memória externa."""
        
        try:
            payload = {
                "user_id": str(user_id),
                "conversation_id": str(conversation_id),
                "messages": [
                    {
                        "content": msg.content,
                        "sender": msg.sender,
                        "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                        "metadata": msg.metadata
                    }
                    for msg in messages
                ]
            }
            
            await self.http_client.post(
                f"{self.base_url}/store",
                json=payload
            )
            
            logger.debug("Conversa armazenada no serviço de memória", user_id=str(user_id))
            
        except Exception as e:
            logger.error("Erro ao armazenar conversa", error=str(e))
            raise
    
    async def get_conversation_context(
        self, 
        user_id: UUID, 
        conversation_id: UUID
    ) -> Optional[ConversationContext]:
        """Obtém contexto da conversa."""
        
        try:
            response = await self.http_client.get(
                f"{self.base_url}/context/{user_id}/{conversation_id}"
            )
            
            if response.status_code == 200:
                data = response.json()
                # Aqui você converteria o JSON para ConversationContext
                # Por simplicidade, retornando None por agora
                return None
            
            return None
            
        except Exception as e:
            logger.error("Erro ao obter contexto da conversa", error=str(e))
            return None
    
    async def update_user_context(
        self, 
        user_id: UUID, 
        context: Dict[str, Any]
    ) -> None:
        """Atualiza contexto do usuário."""
        
        try:
            await self.http_client.post(
                f"{self.base_url}/update_context",
                json={
                    "user_id": str(user_id),
                    "context": context
                }
            )
            
        except Exception as e:
            logger.error("Erro ao atualizar contexto do usuário", error=str(e))
    
    async def get_relevant_memories(
        self, 
        user_id: UUID, 
        query: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Busca memórias relevantes."""
        
        try:
            response = await self.http_client.get(
                f"{self.base_url}/search",
                params={
                    "user_id": str(user_id),
                    "query": query,
                    "limit": limit
                }
            )
            
            if response.status_code == 200:
                return response.json().get("memories", [])
            
            return []
            
        except Exception as e:
            logger.error("Erro ao buscar memórias relevantes", error=str(e))
            return []


class ExternalRAGService(RAGService):
    """Cliente para o serviço RAG externo."""
    
    def __init__(self, http_client: HTTPClient, rag_service_url: str):
        self.http_client = http_client
        self.base_url = rag_service_url.rstrip('/')
    
    async def query_knowledge_base(
        self, 
        query: str, 
        context: Optional[str] = None,
        top_k: int = 5
    ) -> Dict[str, Any]:
        """Consulta a base de conhecimento."""
        
        try:
            payload = {
                "query": query,
                "context": context or "",
                "top_k": top_k
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/query",
                json=payload
            )
            
            if response.status_code == 200:
                return response.json()
            
            return {
                "answer": "Não consegui encontrar informações específicas no momento.",
                "sources": []
            }
            
        except Exception as e:
            logger.error("Erro na consulta RAG", error=str(e))
            return {
                "answer": "Erro ao consultar base de conhecimento.",
                "sources": [],
                "error": str(e)
            }
    
    async def index_document(
        self, 
        content: str, 
        metadata: Dict[str, Any]
    ) -> str:
        """Indexa um documento."""
        
        try:
            payload = {
                "content": content,
                "metadata": metadata
            }
            
            response = await self.http_client.post(
                f"{self.base_url}/index",
                json=payload
            )
            
            if response.status_code == 200:
                return response.json().get("document_id", "")
            
            return ""
            
        except Exception as e:
            logger.error("Erro ao indexar documento", error=str(e))
            return ""


class LocalIntentClassificationService(IntentClassificationService):
    """Serviço local de classificação de intenções."""
    
    def __init__(self):
        # Padrões simples para classificação de intenção
        self.intent_patterns = {
            "property_search": [
                "procuro", "busco", "quero", "encontrar", "imóvel", "casa", "apartamento",
                "comprar", "alugar", "venda", "aluguel", "propriedade"
            ],
            "property_inquiry": [
                "detalhe", "informação", "sobre", "esse", "este", "imóvel", "visita",
                "agendar", "interesse", "gostei", "quero ver"
            ],
            "market_information": [
                "mercado", "preço", "valor", "tendência", "análise", "comparar",
                "investimento", "valorização"
            ],
            "greeting": [
                "oi", "olá", "bom dia", "boa tarde", "boa noite", "tudo bem"
            ]
        }
    
    async def classify_intent(self, message: str) -> Dict[str, Any]:
        """Classifica a intenção da mensagem."""
        
        message_lower = message.lower()
        intent_scores = {}
        
        for intent, patterns in self.intent_patterns.items():
            score = sum(1 for pattern in patterns if pattern in message_lower)
            if score > 0:
                intent_scores[intent] = score / len(patterns)
        
        if intent_scores:
            best_intent = max(intent_scores.items(), key=lambda x: x[1])
            return {
                "intent": best_intent[0],
                "confidence": best_intent[1],
                "all_scores": intent_scores
            }
        
        return {
            "intent": "general_inquiry",
            "confidence": 0.5,
            "all_scores": {}
        }
    
    async def extract_entities(self, message: str) -> Dict[str, Any]:
        """Extrai entidades da mensagem."""
        
        entities = {}
        message_lower = message.lower()
        
        # Extrair tipos de propriedade
        property_types = {
            "casa": ["casa", "casas"],
            "apartamento": ["apartamento", "apartamentos", "apto"],
            "terreno": ["terreno", "lote", "terrenos"],
            "comercial": ["comercial", "loja", "escritório"]
        }
        
        for prop_type, keywords in property_types.items():
            if any(keyword in message_lower for keyword in keywords):
                entities["property_type"] = prop_type
                break
        
        # Extrair números (quartos, banheiros, preço)
        import re
        
        # Quartos
        bedroom_match = re.search(r'(\d+)\s*quarto', message_lower)
        if bedroom_match:
            entities["bedrooms"] = int(bedroom_match.group(1))
        
        # Banheiros
        bathroom_match = re.search(r'(\d+)\s*banheiro', message_lower)
        if bathroom_match:
            entities["bathrooms"] = int(bathroom_match.group(1))
        
        # Preço (formato brasileiro)
        price_match = re.search(r'r\$?\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)', message_lower)
        if price_match:
            price_str = price_match.group(1).replace('.', '').replace(',', '.')
            try:
                entities["price_range"] = {"max": float(price_str)}
            except ValueError:
                pass
        
        # Localização (básico)
        locations = ["uberlândia", "centro", "santa mônica", "jardim", "bairro"]
        for location in locations:
            if location in message_lower:
                entities["location"] = location
                break
        
        return {"entities": entities}


class LocalResponseGenerationService(ResponseGenerationService):
    """Serviço local de geração de respostas."""
    
    async def generate_response(
        self,
        user_message: str,
        context: ConversationContext,
        knowledge: Optional[Dict[str, Any]] = None,
        properties: Optional[List] = None
    ) -> Dict[str, Any]:
        """Gera resposta contextual."""
        
        # Implementação simples - em produção usaria LLM
        response_templates = {
            "property_search": "Entendi que você está procurando por imóveis. Com base no que você me disse, posso ajudar a encontrar as melhores opções.",
            "market_information": "Sobre o mercado imobiliário, posso compartilhar algumas informações relevantes.",
            "greeting": "Olá! Como posso ajudar você com imóveis hoje?",
            "general_inquiry": "Como posso ajudar você com questões imobiliárias?"
        }
        
        intent = context.current_intent or "general_inquiry"
        base_response = response_templates.get(intent, response_templates["general_inquiry"])
        
        # Incluir informações da base de conhecimento se disponível
        if knowledge and knowledge.get("answer"):
            base_response += f"\n\n{knowledge['answer']}"
        
        return {
            "response": base_response,
            "intent": intent,
            "used_knowledge": bool(knowledge)
        }
    
    async def format_property_presentation(
        self,
        properties: List,
        user_criteria: Dict[str, Any]
    ) -> str:
        """Formata apresentação de imóveis."""
        
        if not properties:
            return "Não encontrei imóveis que atendam aos critérios informados."
        
        response = f"Encontrei {len(properties)} propriedades que podem interessar você:\n\n"
        
        for i, prop in enumerate(properties, 1):
            if hasattr(prop, 'to_dict'):
                prop_dict = prop.to_dict()
            else:
                prop_dict = prop
            
            response += f"{i}. **{prop_dict.get('title', 'Imóvel')}**\n"
            
            address = prop_dict.get('address', {})
            if address.get('neighborhood'):
                response += f"   📍 {address['neighborhood']}"
                if address.get('city'):
                    response += f", {address['city']}"
                response += "\n"
            
            financial = prop_dict.get('financial', {})
            if financial.get('price'):
                response += f"   💰 R$ {financial['price']:,.0f}\n"
            elif financial.get('rental_price'):
                response += f"   💰 R$ {financial['rental_price']:,.0f}/mês\n"
            
            features = prop_dict.get('features', {})
            if features.get('bedrooms'):
                response += f"   🛏️ {features['bedrooms']} quartos"
                if features.get('bathrooms'):
                    response += f", {features['bathrooms']} banheiros"
                response += "\n"
            
            response += "\n"
        
        response += "Gostaria de ver mais detalhes de algum destes imóveis? Posso fornecer informações completas ou agendar uma visita."
        
        return response