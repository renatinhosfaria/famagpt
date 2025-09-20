"""
Domain protocols for web scraping
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from ..entities.property import Property, SearchQuery, SearchResult


class WebScraperProtocol(ABC):
    """Protocol for web scrapers"""
    
    @abstractmethod
    async def search_properties(self, query: SearchQuery) -> List[Property]:
        """
        Search for properties based on query
        
        Args:
            query: Search query with filters
            
        Returns:
            List of properties found
        """
        pass
    
    @abstractmethod
    async def get_property_details(self, property_url: str) -> Optional[Property]:
        """
        Get detailed information about a specific property
        
        Args:
            property_url: URL of the property listing
            
        Returns:
            Property with detailed information or None if not found
        """
        pass
    
    @abstractmethod
    def get_site_name(self) -> str:
        """Get the name of the site this scraper handles"""
        pass
    
    @abstractmethod
    def can_handle_url(self, url: str) -> bool:
        """Check if this scraper can handle the given URL"""
        pass


class CacheServiceProtocol(ABC):
    """Protocol for caching search results"""
    
    @abstractmethod
    async def get_cached_search(self, cache_key: str) -> Optional[SearchResult]:
        """Get cached search result"""
        pass
    
    @abstractmethod
    async def cache_search(
        self,
        cache_key: str,
        result: SearchResult,
        ttl_seconds: int = 1800
    ) -> None:
        """Cache search result"""
        pass
    
    @abstractmethod
    async def invalidate_search_cache(self, cache_key: str) -> None:
        """Invalidate cached search result"""
        pass


class PropertyExtractorProtocol(ABC):
    """Protocol for extracting property data from HTML"""
    
    @abstractmethod
    def extract_properties_from_html(
        self, 
        html: str, 
        base_url: str
    ) -> List[Property]:
        """Extract property listings from HTML content"""
        pass
    
    @abstractmethod
    def extract_property_details_from_html(
        self, 
        html: str, 
        property_url: str
    ) -> Optional[Property]:
        """Extract detailed property information from HTML"""
        pass