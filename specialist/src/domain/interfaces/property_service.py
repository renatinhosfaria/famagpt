"""
Interfaces para serviços relacionados a imóveis.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from uuid import UUID

from ..entities.property import Property, PropertyType, PropertyStatus


class PropertyRepository(ABC):
    """Interface para repositório de imóveis."""
    
    @abstractmethod
    async def save(self, property: Property) -> Property:
        """Salva um imóvel."""
        pass
    
    @abstractmethod
    async def find_by_id(self, property_id: UUID) -> Optional[Property]:
        """Busca imóvel por ID."""
        pass
    
    @abstractmethod
    async def search(self, criteria: Dict[str, Any], limit: int = 10) -> List[Property]:
        """Busca imóveis por critérios."""
        pass
    
    @abstractmethod
    async def find_by_location(
        self, 
        city: str, 
        neighborhood: Optional[str] = None,
        radius_km: Optional[float] = None,
        limit: int = 10
    ) -> List[Property]:
        """Busca imóveis por localização."""
        pass
    
    @abstractmethod
    async def find_by_price_range(
        self, 
        min_price: Optional[float], 
        max_price: Optional[float],
        property_type: Optional[PropertyType] = None,
        limit: int = 10
    ) -> List[Property]:
        """Busca imóveis por faixa de preço."""
        pass


class WebSearchService(ABC):
    """Interface para serviço de busca web."""
    
    @abstractmethod
    async def search_properties(self, criteria: Dict[str, Any]) -> List[Property]:
        """Busca imóveis em portais web."""
        pass
    
    @abstractmethod
    async def get_property_details(self, url: str) -> Optional[Property]:
        """Obtém detalhes de um imóvel específico."""
        pass


class PropertyAnalysisService(ABC):
    """Interface para análise de imóveis."""
    
    @abstractmethod
    async def analyze_property_value(self, property: Property) -> Dict[str, Any]:
        """Analisa o valor de um imóvel."""
        pass
    
    @abstractmethod
    async def compare_properties(self, properties: List[Property]) -> Dict[str, Any]:
        """Compara múltiplos imóveis."""
        pass
    
    @abstractmethod
    async def get_market_trends(
        self, 
        city: str, 
        property_type: Optional[PropertyType] = None
    ) -> Dict[str, Any]:
        """Obtém tendências do mercado."""
        pass


class PropertyRecommendationService(ABC):
    """Interface para recomendação de imóveis."""
    
    @abstractmethod
    async def recommend_properties(
        self, 
        user_id: UUID, 
        criteria: Dict[str, Any],
        limit: int = 5
    ) -> List[Property]:
        """Recomenda imóveis para um usuário."""
        pass
    
    @abstractmethod
    async def update_user_preferences(
        self, 
        user_id: UUID, 
        preferences: Dict[str, Any]
    ) -> None:
        """Atualiza preferências do usuário."""
        pass