"""
Application service for web search operations
"""

from typing import List, Optional

from shared.src.utils.logging import get_logger

from ...domain.entities.property import Property, SearchQuery, SearchResult, PropertyType, PropertyListingType
from ..use_cases.search_properties import SearchPropertiesUseCase


logger = get_logger("web_search.app_service")


class WebSearchAppService:
    """Application service for web search operations"""
    
    def __init__(self, search_properties_use_case: SearchPropertiesUseCase):
        self.search_properties_use_case = search_properties_use_case
    
    async def search_properties(
        self,
        query: str,
        city: str = "Uberlândia",
        state: str = "MG",
        property_type: Optional[str] = None,
        listing_type: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        min_bedrooms: Optional[int] = None,
        max_bedrooms: Optional[int] = None,
        max_results: int = 50,
        use_cache: bool = True
    ) -> SearchResult:
        """
        Search for properties
        
        Args:
            query: Search query text
            city: Target city (default: Uberlândia)
            state: Target state (default: MG)
            property_type: Type of property (house, apartment, commercial, land, any)
            listing_type: Type of listing (sale, rent)
            min_price: Minimum price filter
            max_price: Maximum price filter
            min_bedrooms: Minimum bedrooms filter
            max_bedrooms: Maximum bedrooms filter
            max_results: Maximum number of results to return
            use_cache: Whether to use cache
            
        Returns:
            SearchResult with properties and metadata
            
        Raises:
            ValueError: If input parameters are invalid
            RuntimeError: If search fails
        """
        # Input validation
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")
        
        if not city or not city.strip():
            raise ValueError("City cannot be empty")
        
        if max_results <= 0 or max_results > 200:
            raise ValueError("max_results must be between 1 and 200")
        
        # Parse property type
        prop_type = PropertyType.ANY
        if property_type:
            try:
                prop_type = PropertyType(property_type.lower())
            except ValueError:
                logger.warning(f"Invalid property_type: {property_type}, using 'any'")
        
        # Parse listing type
        list_type = PropertyListingType.SALE
        if listing_type:
            try:
                list_type = PropertyListingType(listing_type.lower())
            except ValueError:
                logger.warning(f"Invalid listing_type: {listing_type}, using 'sale'")
        
        # Validate price range
        if min_price is not None and min_price < 0:
            raise ValueError("min_price cannot be negative")
        
        if max_price is not None and max_price < 0:
            raise ValueError("max_price cannot be negative")
        
        if (min_price is not None and max_price is not None and 
            min_price > max_price):
            raise ValueError("min_price cannot be greater than max_price")
        
        # Validate bedroom range
        if min_bedrooms is not None and min_bedrooms < 0:
            raise ValueError("min_bedrooms cannot be negative")
        
        if max_bedrooms is not None and max_bedrooms < 0:
            raise ValueError("max_bedrooms cannot be negative")
        
        if (min_bedrooms is not None and max_bedrooms is not None and 
            min_bedrooms > max_bedrooms):
            raise ValueError("min_bedrooms cannot be greater than max_bedrooms")
        
        # Create search query
        search_query = SearchQuery(
            query=query.strip(),
            city=city.strip(),
            state=state.strip(),
            property_type=prop_type,
            listing_type=list_type,
            min_price=min_price,
            max_price=max_price,
            min_bedrooms=min_bedrooms,
            max_bedrooms=max_bedrooms,
            max_results=max_results
        )
        
        logger.info(f"Processing property search request: {query} in {city}/{state}")
        
        # Execute search
        result = await self.search_properties_use_case.execute(
            query=search_query,
            use_cache=use_cache
        )
        
        return result
    
    async def get_property_details(
        self,
        property_url: str
    ) -> Property:
        """
        Get detailed information about a specific property
        
        Args:
            property_url: URL of the property listing
            
        Returns:
            Property with detailed information
            
        Raises:
            ValueError: If URL is invalid
            RuntimeError: If property details cannot be retrieved
        """
        # Input validation
        if not property_url or not property_url.strip():
            raise ValueError("Property URL cannot be empty")
        
        # Basic URL validation
        if not property_url.startswith(('http://', 'https://')):
            raise ValueError("Property URL must be a valid HTTP/HTTPS URL")
        
        logger.info(f"Processing property details request: {property_url}")
        
        # Execute property details retrieval
        property_obj = await self.search_properties_use_case.get_property_details(
            property_url=property_url.strip()
        )
        
        return property_obj
    
    async def get_service_info(self) -> dict:
        """Get web search service information"""
        return {
            "service": "web_search",
            "description": "Property search and web scraping service",
            "supported_cities": ["Uberlândia"],
            "supported_states": ["MG"],
            "property_types": [ptype.value for ptype in PropertyType],
            "listing_types": [ltype.value for ltype in PropertyListingType],
            "max_results_limit": 200,
            "cache_enabled": True,
            "cache_ttl_seconds": 1800,
            "scrapers": len(self.search_properties_use_case.scrapers),
            "features": {
                "price_filtering": True,
                "bedroom_filtering": True,
                "property_type_filtering": True,
                "caching": True,
                "deduplication": True,
                "multiple_sources": True
            }
        }