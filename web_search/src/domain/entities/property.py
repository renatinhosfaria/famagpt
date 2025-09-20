"""
Domain entities for web search service
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class PropertyType(Enum):
    """Property types"""
    HOUSE = "casa"
    APARTMENT = "apartamento"
    COMMERCIAL = "comercial"
    LAND = "terreno"
    ANY = "any"


class PropertyListingType(Enum):
    """Property listing types"""
    SALE = "venda"
    RENT = "aluguel"


@dataclass
class PropertyLocation:
    """Property location information"""
    street: Optional[str] = None
    neighborhood: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass
class PropertyFeatures:
    """Property features and characteristics"""
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    garage_spaces: Optional[int] = None
    area_m2: Optional[float] = None
    lot_area_m2: Optional[float] = None
    floors: Optional[int] = None
    amenities: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.amenities is None:
            self.amenities = []


@dataclass
class Property:
    """Property entity"""
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    currency: str = "BRL"
    listing_type: Optional[PropertyListingType] = None
    property_type: Optional[PropertyType] = None
    location: Optional[PropertyLocation] = None
    features: Optional[PropertyFeatures] = None
    images: Optional[List[str]] = None
    source_url: Optional[str] = None
    source_site: Optional[str] = None
    contact_info: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    def __post_init__(self):
        if self.images is None:
            self.images = []
        if self.contact_info is None:
            self.contact_info = {}
        if self.location is None:
            self.location = PropertyLocation()
        if self.features is None:
            self.features = PropertyFeatures()
    
    def is_valid(self) -> bool:
        """Check if property has minimum required information"""
        return (
            self.title is not None and 
            len(self.title.strip()) > 0 and
            self.price is not None and
            self.price > 0 and
            self.location is not None and
            self.location.city is not None
        )
    
    def matches_criteria(
        self, 
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        property_type: Optional[PropertyType] = None,
        min_bedrooms: Optional[int] = None,
        max_bedrooms: Optional[int] = None,
        city: Optional[str] = None
    ) -> bool:
        """Check if property matches search criteria"""
        
        # Price filter
        if min_price is not None and (self.price is None or self.price < min_price):
            return False
        if max_price is not None and (self.price is None or self.price > max_price):
            return False
        
        # Property type filter
        if property_type is not None and property_type != PropertyType.ANY:
            if self.property_type != property_type:
                return False
        
        # Bedrooms filter
        if min_bedrooms is not None:
            if self.features is None or self.features.bedrooms is None or self.features.bedrooms < min_bedrooms:
                return False
        if max_bedrooms is not None:
            if self.features is None or self.features.bedrooms is None or self.features.bedrooms > max_bedrooms:
                return False
        
        # City filter
        if city is not None:
            if self.location is None or self.location.city is None:
                return False
            if city.lower() not in self.location.city.lower():
                return False
        
        return True


@dataclass
class SearchQuery:
    """Search query for properties"""
    query: str
    city: str = "Uberlândia"
    state: str = "MG"
    property_type: PropertyType = PropertyType.ANY
    listing_type: PropertyListingType = PropertyListingType.SALE
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_bedrooms: Optional[int] = None
    max_bedrooms: Optional[int] = None
    max_results: int = 50
    
    def generate_cache_key(self) -> str:
        """Generate cache key for this search"""
        import hashlib
        key_parts = [
            self.query,
            self.city,
            self.state,
            self.property_type.value,
            self.listing_type.value,
            str(self.min_price) if self.min_price else "",
            str(self.max_price) if self.max_price else "",
            str(self.min_bedrooms) if self.min_bedrooms else "",
            str(self.max_bedrooms) if self.max_bedrooms else "",
            str(self.max_results)
        ]
        key_string = "|".join(key_parts)
        hash_key = hashlib.md5(key_string.encode()).hexdigest()
        return f"web_search:query:{hash_key}"


@dataclass
class SearchResult:
    """Search result containing properties and metadata"""
    properties: List[Property]
    total_count: int
    query: SearchQuery
    search_time_seconds: Optional[float] = None
    cached: bool = False
    sources: Optional[List[str]] = None
    
    def __post_init__(self):
        if self.sources is None:
            self.sources = []