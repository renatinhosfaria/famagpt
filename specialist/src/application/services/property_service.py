"""
Serviço de propriedades e imóveis.
"""

from typing import List, Dict, Any, Optional
from uuid import UUID

from shared.src.utils.logging import get_logger

from ...domain.entities.property import Property, PropertyType, PropertyStatus
from ...domain.interfaces.property_service import (
    PropertyRepository, 
    WebSearchService, 
    PropertyAnalysisService,
    PropertyRecommendationService
)


logger = get_logger(__name__)


class PropertyService:
    """Serviço principal para gerenciar propriedades."""
    
    def __init__(
        self,
        property_repository: PropertyRepository,
        web_search_service: WebSearchService,
        analysis_service: PropertyAnalysisService,
        recommendation_service: PropertyRecommendationService
    ):
        self.property_repository = property_repository
        self.web_search_service = web_search_service
        self.analysis_service = analysis_service
        self.recommendation_service = recommendation_service
    
    async def search_properties(
        self,
        criteria: Dict[str, Any],
        limit: int = 10,
        include_web_results: bool = True
    ) -> List[Property]:
        """Busca propriedades usando múltiples fontes."""
        
        logger.info("Iniciando busca de propriedades", criteria=criteria, limit=limit)
        
        # Buscar no repositório local primeiro
        local_properties = await self.property_repository.search(criteria, limit)
        
        logger.debug(f"Encontradas {len(local_properties)} propriedades locais")
        
        # Se não tiver resultados suficientes e web search estiver habilitado
        if len(local_properties) < limit and include_web_results:
            try:
                web_properties = await self.web_search_service.search_properties(criteria)
                logger.debug(f"Encontradas {len(web_properties)} propriedades na web")
                
                # Combinar resultados, evitando duplicatas
                all_properties = local_properties.copy()
                
                for web_prop in web_properties:
                    # Verificar se já existe baseado na URL ou características similares
                    if not self._is_duplicate_property(web_prop, all_properties):
                        all_properties.append(web_prop)
                        
                        # Salvar nova propriedade encontrada
                        try:
                            await self.property_repository.save(web_prop)
                            logger.debug("Nova propriedade salva", property_id=str(web_prop.id))
                        except Exception as e:
                            logger.warning("Erro ao salvar propriedade", error=str(e))
                
                return all_properties[:limit]
                
            except Exception as e:
                logger.error("Erro na busca web", error=str(e))
                return local_properties
        
        return local_properties
    
    async def get_property_details(self, property_id: UUID) -> Optional[Property]:
        """Obtém detalhes completos de uma propriedade."""
        
        property_details = await self.property_repository.find_by_id(property_id)
        
        if property_details:
            logger.debug("Propriedade encontrada", property_id=str(property_id))
            return property_details
        
        logger.warning("Propriedade não encontrada", property_id=str(property_id))
        return None
    
    async def get_property_recommendations(
        self,
        user_id: UUID,
        criteria: Dict[str, Any],
        limit: int = 5
    ) -> List[Property]:
        """Obtém recomendações personalizadas de propriedades."""
        
        try:
            recommendations = await self.recommendation_service.recommend_properties(
                user_id, criteria, limit
            )
            
            logger.info(
                f"Geradas {len(recommendations)} recomendações para usuário",
                user_id=str(user_id)
            )
            
            return recommendations
            
        except Exception as e:
            logger.error("Erro ao gerar recomendações", error=str(e))
            # Fallback para busca normal
            return await self.search_properties(criteria, limit)
    
    async def analyze_property_value(
        self, 
        property: Property
    ) -> Dict[str, Any]:
        """Analisa o valor de uma propriedade."""
        
        try:
            analysis = await self.analysis_service.analyze_property_value(property)
            
            logger.info("Análise de valor realizada", property_id=str(property.id))
            
            return analysis
            
        except Exception as e:
            logger.error("Erro na análise de valor", error=str(e))
            return {
                "error": "Não foi possível analisar o valor no momento",
                "property_id": str(property.id)
            }
    
    async def compare_properties(
        self, 
        property_ids: List[UUID]
    ) -> Dict[str, Any]:
        """Compara múltiplas propriedades."""
        
        # Buscar propriedades
        properties = []
        for prop_id in property_ids:
            prop = await self.property_repository.find_by_id(prop_id)
            if prop:
                properties.append(prop)
        
        if len(properties) < 2:
            return {
                "error": "É necessário pelo menos 2 propriedades para comparação",
                "found_properties": len(properties)
            }
        
        try:
            comparison = await self.analysis_service.compare_properties(properties)
            
            logger.info(f"Comparação realizada entre {len(properties)} propriedades")
            
            return comparison
            
        except Exception as e:
            logger.error("Erro na comparação", error=str(e))
            return {
                "error": "Não foi possível realizar a comparação no momento",
                "properties_count": len(properties)
            }
    
    async def get_market_trends(
        self,
        city: str = "Uberlândia",
        property_type: Optional[PropertyType] = None
    ) -> Dict[str, Any]:
        """Obtém tendências do mercado."""
        
        try:
            trends = await self.analysis_service.get_market_trends(city, property_type)
            
            logger.info("Tendências de mercado obtidas", city=city, property_type=property_type)
            
            return trends
            
        except Exception as e:
            logger.error("Erro ao obter tendências", error=str(e))
            return {
                "error": "Não foi possível obter tendências no momento",
                "city": city
            }
    
    async def search_by_location(
        self,
        city: str,
        neighborhood: Optional[str] = None,
        radius_km: Optional[float] = None,
        limit: int = 10
    ) -> List[Property]:
        """Busca propriedades por localização."""
        
        properties = await self.property_repository.find_by_location(
            city, neighborhood, radius_km, limit
        )
        
        logger.debug(
            f"Busca por localização retornou {len(properties)} propriedades",
            city=city,
            neighborhood=neighborhood
        )
        
        return properties
    
    async def search_by_price_range(
        self,
        min_price: Optional[float],
        max_price: Optional[float],
        property_type: Optional[PropertyType] = None,
        limit: int = 10
    ) -> List[Property]:
        """Busca propriedades por faixa de preço."""
        
        properties = await self.property_repository.find_by_price_range(
            min_price, max_price, property_type, limit
        )
        
        logger.debug(
            f"Busca por preço retornou {len(properties)} propriedades",
            min_price=min_price,
            max_price=max_price
        )
        
        return properties
    
    def _is_duplicate_property(
        self, 
        new_property: Property, 
        existing_properties: List[Property]
    ) -> bool:
        """Verifica se a propriedade já existe na lista."""
        
        for existing in existing_properties:
            # Comparar por URL fonte
            if (new_property.source_url and existing.source_url and 
                new_property.source_url == existing.source_url):
                return True
            
            # Comparar por localização e características similares
            if (existing.address.street == new_property.address.street and
                existing.address.number == new_property.address.number and
                existing.features.bedrooms == new_property.features.bedrooms and
                existing.financial.price == new_property.financial.price):
                return True
        
        return False