"""
Redis cache service for web search results
"""

from typing import Optional
import json
from datetime import datetime

from shared.src.infrastructure.redis_client import RedisClient
from shared.src.utils.logging import get_logger

from ...domain.entities.property import Property, SearchResult, SearchQuery
from ...domain.protocols.web_scraper import CacheServiceProtocol


logger = get_logger("web_search.cache")


class RedisCacheService(CacheServiceProtocol):
    """Redis implementation for caching search results"""
    
    def __init__(self, redis_client: RedisClient):
        self.redis_client = redis_client
        self.key_prefix = "web_search:cache:"
    
    async def get_cached_search(self, cache_key: str) -> Optional[SearchResult]:
        """Get cached search result"""
        try:
            full_key = f"{self.key_prefix}{cache_key}"
            cached_data = await self.redis_client.get_json(full_key)
            
            if not cached_data:
                logger.debug(f"Cache miss for key: {cache_key}")
                return None
            
            logger.debug(f"Cache hit for key: {cache_key}")
            
            # Convert cached data back to SearchResult
            properties = []
            for prop_data in cached_data.get("properties", []):
                property_obj = self._dict_to_property(prop_data)
                if property_obj:
                    properties.append(property_obj)
            
            # Reconstruct SearchQuery
            query_data = cached_data.get("query", {})
            query = SearchQuery(**query_data) if query_data else None
            
            search_result = SearchResult(
                properties=properties,
                total_count=cached_data.get("total_count", len(properties)),
                query=query,
                search_time_seconds=cached_data.get("search_time_seconds"),
                cached=True,
                sources=cached_data.get("sources", [])
            )
            
            return search_result
            
        except Exception as e:
            logger.error(f"Error getting cached search: {str(e)}")
            return None
    
    async def cache_search(
        self,
        cache_key: str,
        result: SearchResult,
        ttl_seconds: int = 1800
    ) -> None:
        """Cache search result"""
        try:
            full_key = f"{self.key_prefix}{cache_key}"
            
            # Convert SearchResult to dict for JSON serialization
            cache_data = {
                "properties": [self._property_to_dict(prop) for prop in result.properties],
                "total_count": result.total_count,
                "query": self._search_query_to_dict(result.query) if result.query else None,
                "search_time_seconds": result.search_time_seconds,
                "cached": False,  # Will be True when retrieved from cache
                "sources": result.sources or [],
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.redis_client.set_json(
                full_key,
                cache_data,
                ttl=ttl_seconds
            )
            
            logger.debug(f"Cached search result with key: {cache_key}, TTL: {ttl_seconds}s, properties: {len(result.properties)}")
            
        except Exception as e:
            logger.error(f"Error caching search result: {str(e)}")
            # Don't raise exception - caching failure shouldn't break the flow
    
    async def invalidate_search_cache(self, cache_key: str) -> None:
        """Invalidate cached search result"""
        try:
            full_key = f"{self.key_prefix}{cache_key}"
            deleted = await self.redis_client.delete(full_key)
            
            if deleted:
                logger.debug(f"Cache invalidated for key: {cache_key}")
            else:
                logger.debug(f"No cache found to invalidate for key: {cache_key}")
                
        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}")
    
    def _property_to_dict(self, property_obj: Property) -> dict:
        """Convert Property object to dictionary"""
        return {
            "id": property_obj.id,
            "title": property_obj.title,
            "description": property_obj.description,
            "price": property_obj.price,
            "currency": property_obj.currency,
            "listing_type": property_obj.listing_type.value if property_obj.listing_type else None,
            "property_type": property_obj.property_type.value if property_obj.property_type else None,
            "location": {
                "street": property_obj.location.street if property_obj.location else None,
                "neighborhood": property_obj.location.neighborhood if property_obj.location else None,
                "city": property_obj.location.city if property_obj.location else None,
                "state": property_obj.location.state if property_obj.location else None,
                "zip_code": property_obj.location.zip_code if property_obj.location else None,
                "latitude": property_obj.location.latitude if property_obj.location else None,
                "longitude": property_obj.location.longitude if property_obj.location else None,
            },
            "features": {
                "bedrooms": property_obj.features.bedrooms if property_obj.features else None,
                "bathrooms": property_obj.features.bathrooms if property_obj.features else None,
                "garage_spaces": property_obj.features.garage_spaces if property_obj.features else None,
                "area_m2": property_obj.features.area_m2 if property_obj.features else None,
                "lot_area_m2": property_obj.features.lot_area_m2 if property_obj.features else None,
                "floors": property_obj.features.floors if property_obj.features else None,
                "amenities": property_obj.features.amenities if property_obj.features else None,
            },
            "images": property_obj.images,
            "source_url": property_obj.source_url,
            "source_site": property_obj.source_site,
            "contact_info": property_obj.contact_info,
            "created_at": property_obj.created_at.isoformat() if property_obj.created_at else None,
            "updated_at": property_obj.updated_at.isoformat() if property_obj.updated_at else None,
        }
    
    def _dict_to_property(self, data: dict) -> Optional[Property]:
        """Convert dictionary back to Property object"""
        try:
            from ...domain.entities.property import (
                PropertyLocation, PropertyFeatures, PropertyType, PropertyListingType
            )
            
            # Parse location
            location_data = data.get("location", {})
            location = PropertyLocation(
                street=location_data.get("street"),
                neighborhood=location_data.get("neighborhood"),
                city=location_data.get("city"),
                state=location_data.get("state"),
                zip_code=location_data.get("zip_code"),
                latitude=location_data.get("latitude"),
                longitude=location_data.get("longitude")
            )
            
            # Parse features
            features_data = data.get("features", {})
            features = PropertyFeatures(
                bedrooms=features_data.get("bedrooms"),
                bathrooms=features_data.get("bathrooms"),
                garage_spaces=features_data.get("garage_spaces"),
                area_m2=features_data.get("area_m2"),
                lot_area_m2=features_data.get("lot_area_m2"),
                floors=features_data.get("floors"),
                amenities=features_data.get("amenities") or []
            )
            
            # Parse enums
            listing_type = None
            if data.get("listing_type"):
                try:
                    listing_type = PropertyListingType(data["listing_type"])
                except ValueError:
                    pass
            
            property_type = None
            if data.get("property_type"):
                try:
                    property_type = PropertyType(data["property_type"])
                except ValueError:
                    pass
            
            # Parse dates
            created_at = None
            if data.get("created_at"):
                try:
                    created_at = datetime.fromisoformat(data["created_at"])
                except ValueError:
                    pass
            
            updated_at = None
            if data.get("updated_at"):
                try:
                    updated_at = datetime.fromisoformat(data["updated_at"])
                except ValueError:
                    pass
            
            return Property(
                id=data.get("id"),
                title=data.get("title"),
                description=data.get("description"),
                price=data.get("price"),
                currency=data.get("currency", "BRL"),
                listing_type=listing_type,
                property_type=property_type,
                location=location,
                features=features,
                images=data.get("images", []),
                source_url=data.get("source_url"),
                source_site=data.get("source_site"),
                contact_info=data.get("contact_info", {}),
                created_at=created_at,
                updated_at=updated_at
            )
            
        except Exception as e:
            logger.error(f"Error converting dict to Property: {str(e)}")
            return None
    
    def _search_query_to_dict(self, query: SearchQuery) -> dict:
        """Convert SearchQuery to dictionary"""
        return {
            "query": query.query,
            "city": query.city,
            "state": query.state,
            "property_type": query.property_type.value,
            "listing_type": query.listing_type.value,
            "min_price": query.min_price,
            "max_price": query.max_price,
            "min_bedrooms": query.min_bedrooms,
            "max_bedrooms": query.max_bedrooms,
            "max_results": query.max_results
        }