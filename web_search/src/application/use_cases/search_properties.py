"""
Use case for searching properties
"""

from typing import List
import time
from datetime import datetime

from shared.src.utils.logging import get_logger

from ...domain.entities.property import Property, SearchQuery, SearchResult
from ...domain.protocols.web_scraper import WebScraperProtocol, CacheServiceProtocol


logger = get_logger("web_search.use_cases")


class SearchPropertiesUseCase:
    """Use case for searching properties across multiple sources"""
    
    def __init__(
        self,
        scrapers: List[WebScraperProtocol],
        cache_service: CacheServiceProtocol
    ):
        self.scrapers = scrapers
        self.cache_service = cache_service
    
    async def execute(
        self,
        query: SearchQuery,
        use_cache: bool = True
    ) -> SearchResult:
        """
        Execute property search
        
        Args:
            query: Search query with filters
            use_cache: Whether to use cache for results
            
        Returns:
            SearchResult with properties and metadata
            
        Raises:
            RuntimeError: If search fails
        """
        start_time = time.time()
        
        try:
            cache_key = query.generate_cache_key()
            
            # Check cache first
            if use_cache:
                cached_result = await self.cache_service.get_cached_search(cache_key)
                if cached_result:
                    logger.info(f"Cache hit for property search: {query.query}")
                    return cached_result
            
            # Perform search across all scrapers
            logger.info(f"Starting property search: {query.query} in {query.city}/{query.state}")
            
            all_properties = []
            sources = []
            
            for scraper in self.scrapers:
                try:
                    scraper_start = time.time()
                    properties = await scraper.search_properties(query)
                    scraper_time = time.time() - scraper_start
                    
                    if properties:
                        all_properties.extend(properties)
                        sources.append(scraper.get_site_name())
                        logger.info(
                            f"Scraper {scraper.get_site_name()} found {len(properties)} properties "
                            f"in {scraper_time:.2f}s"
                        )
                    else:
                        logger.debug(f"Scraper {scraper.get_site_name()} found no properties")
                        
                except Exception as e:
                    logger.error(f"Error in scraper {scraper.get_site_name()}: {str(e)}")
                    continue
            
            # Remove duplicates and filter results
            unique_properties = self._remove_duplicates(all_properties)
            filtered_properties = self._apply_filters(unique_properties, query)
            
            # Limit results
            final_properties = filtered_properties[:query.max_results]
            
            search_time = time.time() - start_time
            
            # Create search result
            result = SearchResult(
                properties=final_properties,
                total_count=len(filtered_properties),
                query=query,
                search_time_seconds=search_time,
                cached=False,
                sources=sources
            )
            
            # Cache successful result
            if use_cache and final_properties:
                await self.cache_service.cache_search(
                    cache_key,
                    result,
                    ttl_seconds=1800  # 30 minutes
                )
            
            logger.info(
                f"Property search completed. "
                f"Found: {len(all_properties)} total, "
                f"Unique: {len(unique_properties)}, "
                f"Filtered: {len(filtered_properties)}, "
                f"Returned: {len(final_properties)}, "
                f"Sources: {len(sources)}, "
                f"Time: {search_time:.2f}s"
            )
            
            return result
                
        except Exception as e:
            search_time = time.time() - start_time
            logger.error(
                f"Property search failed for {query.query}: {str(e)}. "
                f"Search time: {search_time:.2f}s"
            )
            raise RuntimeError(f"Property search failed: {str(e)}") from e
    
    def _remove_duplicates(self, properties: List[Property]) -> List[Property]:
        """Remove duplicate properties based on title and price"""
        seen = set()
        unique_properties = []
        
        for property_obj in properties:
            # Create a key based on title and price for deduplication
            key = (
                property_obj.title.lower().strip() if property_obj.title else "",
                property_obj.price or 0,
                property_obj.location.city.lower() if property_obj.location and property_obj.location.city else ""
            )
            
            if key not in seen and key[0]:  # Must have a title
                seen.add(key)
                unique_properties.append(property_obj)
        
        logger.debug(f"Removed {len(properties) - len(unique_properties)} duplicate properties")
        return unique_properties
    
    def _apply_filters(self, properties: List[Property], query: SearchQuery) -> List[Property]:
        """Apply query filters to properties"""
        filtered = []
        
        for property_obj in properties:
            if property_obj.matches_criteria(
                min_price=query.min_price,
                max_price=query.max_price,
                property_type=query.property_type,
                min_bedrooms=query.min_bedrooms,
                max_bedrooms=query.max_bedrooms,
                city=query.city
            ):
                filtered.append(property_obj)
        
        logger.debug(f"Filtered {len(properties)} properties down to {len(filtered)}")
        return filtered
    
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
            RuntimeError: If property details cannot be retrieved
        """
        try:
            logger.info(f"Getting property details: {property_url}")
            
            # Find appropriate scraper for this URL
            scraper = None
            for s in self.scrapers:
                if s.can_handle_url(property_url):
                    scraper = s
                    break
            
            if not scraper:
                raise RuntimeError(f"No scraper available for URL: {property_url}")
            
            property_obj = await scraper.get_property_details(property_url)
            
            if not property_obj:
                raise RuntimeError(f"Could not extract property details from: {property_url}")
            
            logger.info(f"Successfully retrieved property details: {property_obj.title}")
            return property_obj
            
        except Exception as e:
            logger.error(f"Error getting property details for {property_url}: {str(e)}")
            raise RuntimeError(f"Failed to get property details: {str(e)}") from e