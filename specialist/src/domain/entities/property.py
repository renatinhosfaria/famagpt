"""
Entidades do domínio imobiliário.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import UUID


class PropertyType(str, Enum):
    """Tipos de imóveis."""
    CASA = "casa"
    APARTAMENTO = "apartamento"
    TERRENO = "terreno"
    COMERCIAL = "comercial"
    RURAL = "rural"
    LOTE = "lote"


class PropertyStatus(str, Enum):
    """Status do imóvel."""
    VENDA = "venda"
    ALUGUEL = "aluguel"
    VENDIDO = "vendido"
    ALUGADO = "alugado"
    INDISPONIVEL = "indisponivel"


class PropertyCondition(str, Enum):
    """Condição do imóvel."""
    NOVO = "novo"
    SEMINOVO = "seminovo"
    USADO = "usado"
    REFORMA = "reforma"


@dataclass
class Address:
    """Endereço do imóvel."""
    street: str
    number: str
    complement: Optional[str] = None
    neighborhood: str = ""
    city: str = ""
    state: str = ""
    zip_code: str = ""
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass
class PropertyFeatures:
    """Características do imóvel."""
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    suites: Optional[int] = None
    parking_spaces: Optional[int] = None
    area_built: Optional[float] = None  # m²
    area_total: Optional[float] = None  # m²
    has_pool: bool = False
    has_garden: bool = False
    has_balcony: bool = False
    has_elevator: bool = False
    is_furnished: bool = False
    pets_allowed: bool = False


@dataclass
class PropertyFinancial:
    """Informações financeiras do imóvel."""
    price: Optional[Decimal] = None
    price_per_sqm: Optional[Decimal] = None
    rental_price: Optional[Decimal] = None
    condominium_fee: Optional[Decimal] = None
    iptu: Optional[Decimal] = None  # Imposto predial
    financing_available: bool = False
    financing_down_payment: Optional[Decimal] = None


@dataclass
class Property:
    """Entidade principal de imóvel."""
    id: UUID
    title: str
    description: str
    property_type: PropertyType
    status: PropertyStatus
    condition: PropertyCondition
    address: Address
    features: PropertyFeatures
    financial: PropertyFinancial
    images: List[str] = None
    source_url: Optional[str] = None
    source_platform: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        if self.images is None:
            self.images = []
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "property_type": self.property_type.value,
            "status": self.status.value,
            "condition": self.condition.value,
            "address": {
                "street": self.address.street,
                "number": self.address.number,
                "complement": self.address.complement,
                "neighborhood": self.address.neighborhood,
                "city": self.address.city,
                "state": self.address.state,
                "zip_code": self.address.zip_code,
                "latitude": self.address.latitude,
                "longitude": self.address.longitude,
            },
            "features": {
                "bedrooms": self.features.bedrooms,
                "bathrooms": self.features.bathrooms,
                "suites": self.features.suites,
                "parking_spaces": self.features.parking_spaces,
                "area_built": self.features.area_built,
                "area_total": self.features.area_total,
                "has_pool": self.features.has_pool,
                "has_garden": self.features.has_garden,
                "has_balcony": self.features.has_balcony,
                "has_elevator": self.features.has_elevator,
                "is_furnished": self.features.is_furnished,
                "pets_allowed": self.features.pets_allowed,
            },
            "financial": {
                "price": float(self.financial.price) if self.financial.price else None,
                "price_per_sqm": float(self.financial.price_per_sqm) if self.financial.price_per_sqm else None,
                "rental_price": float(self.financial.rental_price) if self.financial.rental_price else None,
                "condominium_fee": float(self.financial.condominium_fee) if self.financial.condominium_fee else None,
                "iptu": float(self.financial.iptu) if self.financial.iptu else None,
                "financing_available": self.financial.financing_available,
                "financing_down_payment": float(self.financial.financing_down_payment) if self.financial.financing_down_payment else None,
            },
            "images": self.images,
            "source_url": self.source_url,
            "source_platform": self.source_platform,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }