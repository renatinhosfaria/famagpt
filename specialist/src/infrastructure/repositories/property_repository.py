"""
Repositório de propriedades com implementação básica.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID, uuid4
from decimal import Decimal

from shared.src.utils.logging import get_logger
from shared.src.infrastructure.redis_client import RedisClient

from ...domain.entities.property import (
    Property, PropertyType, PropertyStatus, PropertyCondition,
    Address, PropertyFeatures, PropertyFinancial
)
from ...domain.interfaces.property_service import PropertyRepository


logger = get_logger(__name__)


class InMemoryPropertyRepository(PropertyRepository):
    """Repositório de propriedades em memória com cache Redis."""
    
    def __init__(self, redis_client: RedisClient):
        self.redis_client = redis_client
        # Dados de exemplo para demonstração
        self._populate_sample_data()
    
    def _populate_sample_data(self):
        """Popula dados de exemplo."""
        self.sample_properties = [
            {
                "id": uuid4(),
                "title": "Casa 3 quartos no Jardim Brasília",
                "description": "Linda casa com 3 quartos, 2 banheiros, garagem para 2 carros. Localizada em bairro residencial tranquilo.",
                "property_type": PropertyType.CASA,
                "status": PropertyStatus.VENDA,
                "condition": PropertyCondition.USADO,
                "address": Address(
                    street="Rua das Flores",
                    number="123",
                    neighborhood="Jardim Brasília",
                    city="Uberlândia",
                    state="MG",
                    zip_code="38400-000"
                ),
                "features": PropertyFeatures(
                    bedrooms=3,
                    bathrooms=2,
                    parking_spaces=2,
                    area_built=150.0,
                    area_total=300.0,
                    has_garden=True
                ),
                "financial": PropertyFinancial(
                    price=Decimal("450000.00"),
                    price_per_sqm=Decimal("3000.00")
                ),
                "images": ["https://example.com/casa1_1.jpg", "https://example.com/casa1_2.jpg"]
            },
            {
                "id": uuid4(),
                "title": "Apartamento 2 quartos no Centro",
                "description": "Apartamento moderno no centro da cidade, próximo a shoppings e universidades.",
                "property_type": PropertyType.APARTAMENTO,
                "status": PropertyStatus.ALUGUEL,
                "condition": PropertyCondition.SEMINOVO,
                "address": Address(
                    street="Av. João Naves de Ávila",
                    number="456",
                    complement="Apto 302",
                    neighborhood="Centro",
                    city="Uberlândia",
                    state="MG",
                    zip_code="38400-100"
                ),
                "features": PropertyFeatures(
                    bedrooms=2,
                    bathrooms=1,
                    parking_spaces=1,
                    area_built=80.0,
                    has_balcony=True,
                    has_elevator=True
                ),
                "financial": PropertyFinancial(
                    rental_price=Decimal("1500.00"),
                    condominium_fee=Decimal("350.00")
                ),
                "images": ["https://example.com/apto1_1.jpg"]
            },
            {
                "id": uuid4(),
                "title": "Casa 4 quartos no Santa Mônica",
                "description": "Casa espaçosa com piscina e churrasqueira, ideal para famílias grandes.",
                "property_type": PropertyType.CASA,
                "status": PropertyStatus.VENDA,
                "condition": PropertyCondition.USADO,
                "address": Address(
                    street="Rua dos Sabiás",
                    number="789",
                    neighborhood="Santa Mônica",
                    city="Uberlândia",
                    state="MG",
                    zip_code="38408-100"
                ),
                "features": PropertyFeatures(
                    bedrooms=4,
                    bathrooms=3,
                    suites=2,
                    parking_spaces=3,
                    area_built=250.0,
                    area_total=500.0,
                    has_pool=True,
                    has_garden=True
                ),
                "financial": PropertyFinancial(
                    price=Decimal("850000.00"),
                    price_per_sqm=Decimal("3400.00"),
                    financing_available=True
                ),
                "images": ["https://example.com/casa2_1.jpg", "https://example.com/casa2_2.jpg", "https://example.com/casa2_3.jpg"]
            }
        ]
    
    async def save(self, property: Property) -> Property:
        """Salva uma propriedade."""
        
        try:
            # Converter para dict e salvar no cache Redis
            cache_key = f"property:{property.id}"
            await self.redis_client.set_json(
                cache_key,
                property.to_dict(),
                ttl=86400  # 24 horas
            )
            
            logger.debug("Propriedade salva", property_id=str(property.id))
            return property
            
        except Exception as e:
            logger.error("Erro ao salvar propriedade", property_id=str(property.id), error=str(e))
            raise
    
    async def find_by_id(self, property_id: UUID) -> Optional[Property]:
        """Busca propriedade por ID."""
        
        try:
            # Buscar no cache Redis primeiro
            cache_key = f"property:{property_id}"
            cached_data = await self.redis_client.get_json(cache_key)
            
            if cached_data:
                return self._dict_to_property(cached_data)
            
            # Buscar nos dados de exemplo
            for prop_data in self.sample_properties:
                if prop_data["id"] == property_id:
                    property_obj = self._sample_to_property(prop_data)
                    # Cachear para próximas consultas
                    await self.save(property_obj)
                    return property_obj
            
            logger.debug("Propriedade não encontrada", property_id=str(property_id))
            return None
            
        except Exception as e:
            logger.error("Erro ao buscar propriedade", property_id=str(property_id), error=str(e))
            return None
    
    async def search(self, criteria: Dict[str, Any], limit: int = 10) -> List[Property]:
        """Busca propriedades por critérios."""
        
        try:
            results = []
            
            for prop_data in self.sample_properties:
                if self._matches_criteria(prop_data, criteria):
                    property_obj = self._sample_to_property(prop_data)
                    results.append(property_obj)
                    
                    if len(results) >= limit:
                        break
            
            logger.debug(f"Busca retornou {len(results)} propriedades", criteria=criteria)
            return results
            
        except Exception as e:
            logger.error("Erro na busca de propriedades", error=str(e))
            return []
    
    async def find_by_location(
        self, 
        city: str, 
        neighborhood: Optional[str] = None,
        radius_km: Optional[float] = None,
        limit: int = 10
    ) -> List[Property]:
        """Busca propriedades por localização."""
        
        criteria = {"city": city}
        if neighborhood:
            criteria["neighborhood"] = neighborhood
        
        return await self.search(criteria, limit)
    
    async def find_by_price_range(
        self, 
        min_price: Optional[float], 
        max_price: Optional[float],
        property_type: Optional[PropertyType] = None,
        limit: int = 10
    ) -> List[Property]:
        """Busca propriedades por faixa de preço."""
        
        criteria = {}
        if min_price:
            criteria["price_min"] = min_price
        if max_price:
            criteria["price_max"] = max_price
        if property_type:
            criteria["property_type"] = property_type.value
        
        return await self.search(criteria, limit)
    
    def _matches_criteria(self, prop_data: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
        """Verifica se propriedade atende aos critérios."""
        
        # Localização
        if "city" in criteria:
            if prop_data["address"].city.lower() != criteria["city"].lower():
                return False
        
        if "neighborhood" in criteria:
            if criteria["neighborhood"].lower() not in prop_data["address"].neighborhood.lower():
                return False
        
        # Tipo de propriedade
        if "property_type" in criteria:
            if prop_data["property_type"].value != criteria["property_type"]:
                return False
        
        # Quartos
        if "bedrooms" in criteria:
            if prop_data["features"].bedrooms != criteria["bedrooms"]:
                return False
        
        # Preço
        price = float(prop_data["financial"].price or prop_data["financial"].rental_price or 0)
        
        if "price_min" in criteria and price < criteria["price_min"]:
            return False
        
        if "price_max" in criteria and price > criteria["price_max"]:
            return False
        
        return True
    
    def _sample_to_property(self, prop_data: Dict[str, Any]) -> Property:
        """Converte dados de exemplo para objeto Property."""
        
        return Property(
            id=prop_data["id"],
            title=prop_data["title"],
            description=prop_data["description"],
            property_type=prop_data["property_type"],
            status=prop_data["status"],
            condition=prop_data["condition"],
            address=prop_data["address"],
            features=prop_data["features"],
            financial=prop_data["financial"],
            images=prop_data["images"],
            source_platform="sample_data"
        )
    
    def _dict_to_property(self, data: Dict[str, Any]) -> Property:
        """Converte dicionário para objeto Property."""
        
        # Implementação básica - em produção seria mais robusta
        address = Address(
            street=data["address"]["street"],
            number=data["address"]["number"],
            complement=data["address"].get("complement"),
            neighborhood=data["address"]["neighborhood"],
            city=data["address"]["city"],
            state=data["address"]["state"],
            zip_code=data["address"]["zip_code"]
        )
        
        features = PropertyFeatures(
            bedrooms=data["features"].get("bedrooms"),
            bathrooms=data["features"].get("bathrooms"),
            suites=data["features"].get("suites"),
            parking_spaces=data["features"].get("parking_spaces"),
            area_built=data["features"].get("area_built"),
            area_total=data["features"].get("area_total"),
            has_pool=data["features"].get("has_pool", False),
            has_garden=data["features"].get("has_garden", False),
            has_balcony=data["features"].get("has_balcony", False),
            has_elevator=data["features"].get("has_elevator", False)
        )
        
        financial = PropertyFinancial(
            price=Decimal(str(data["financial"]["price"])) if data["financial"].get("price") else None,
            rental_price=Decimal(str(data["financial"]["rental_price"])) if data["financial"].get("rental_price") else None,
            condominium_fee=Decimal(str(data["financial"]["condominium_fee"])) if data["financial"].get("condominium_fee") else None
        )
        
        return Property(
            id=UUID(data["id"]),
            title=data["title"],
            description=data["description"],
            property_type=PropertyType(data["property_type"]),
            status=PropertyStatus(data["status"]),
            condition=PropertyCondition(data["condition"]),
            address=address,
            features=features,
            financial=financial,
            images=data.get("images", [])
        )