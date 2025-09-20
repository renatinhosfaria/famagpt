"""
Database client for Web Search service to integrate with central database service.
"""
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from shared.src.infrastructure.http_client import ServiceClient
from shared.src.utils.logging import get_logger


class DatabaseClient:
    """HTTP client for central Database service integration."""
    
    def __init__(self, database_service_url: str):
        self.client = ServiceClient("web_search", database_service_url)
        self.logger = get_logger("websearch_database_client")
    
    async def __aenter__(self):
        await self.client.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()
    
    async def save_search_result(
        self,
        search_query: str,
        search_criteria: Dict[str, Any],
        property_data: Dict[str, Any],
        source_url: str,
        source_name: str
    ) -> bool:
        """Save scraped property to central database."""
        try:
            # Transform web search result to database property format
            property_entry = {
                "title": property_data.get("title", ""),
                "description": property_data.get("description", ""),
                "price": property_data.get("price"),
                "property_type": property_data.get("property_type", "house"),
                "location": {
                    "city": search_criteria.get("city", "Uberlândia"),
                    "state": search_criteria.get("state", "MG"),
                    "neighborhood": property_data.get("neighborhood", ""),
                    "street": property_data.get("address", ""),
                    "coordinates": property_data.get("coordinates", {})
                },
                "bedrooms": property_data.get("bedrooms"),
                "bathrooms": property_data.get("bathrooms"),
                "area_sqm": property_data.get("area"),
                "features": property_data.get("features", []),
                "images": property_data.get("images", []),
                "source_url": source_url,
                "source_name": source_name,
                "is_active": True,
                "metadata": {
                    "search_query": search_query,
                    "search_criteria": search_criteria,
                    "scraped_at": datetime.utcnow().isoformat(),
                    "scraper_version": "1.0.0",
                    "web_search_id": property_data.get("id", ""),
                    "created_via": "web_search_service"
                }
            }
            
            response = await self.client.post("/properties", json_data=property_entry)
            
            if response.get("status") == "success":
                self.logger.info(f"Property saved from web search: {property_data.get('title', 'Unknown')}")
                return True
            else:
                self.logger.warning(f"Failed to save property from web search: {response}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error saving search result: {str(e)}")
            return False
    
    async def get_existing_properties_by_source(
        self, 
        source_name: str, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get existing properties from a specific source."""
        try:
            search_data = {
                "source_name": source_name,
                "limit": limit,
                "is_active": True
            }
            
            response = await self.client.post("/properties/search", json_data=search_data)
            
            if response.get("status") == "success":
                return response.get("properties", [])
            else:
                self.logger.warning(f"Failed to get existing properties: {response}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error getting existing properties: {str(e)}")
            return []
    
    async def update_property_availability(
        self, 
        source_url: str, 
        is_available: bool
    ) -> bool:
        """Update property availability status."""
        try:
            # Find property by source URL
            search_data = {
                "source_url": source_url,
                "limit": 1
            }
            
            response = await self.client.post("/properties/search", json_data=search_data)
            
            if response.get("status") == "success":
                properties = response.get("properties", [])
                if properties:
                    property_id = properties[0].get("id")
                    update_data = {
                        "is_active": is_available,
                        "metadata": {
                            **properties[0].get("metadata", {}),
                            "last_checked": datetime.utcnow().isoformat(),
                            "availability_updated_by": "web_search_service"
                        }
                    }
                    
                    update_response = await self.client.patch(f"/properties/{property_id}", json_data=update_data)
                    return update_response.get("status") == "success"
            
            return False
                
        except Exception as e:
            self.logger.error(f"Error updating property availability: {str(e)}")
            return False
    
    async def log_search_query(
        self,
        search_query: str,
        search_criteria: Dict[str, Any],
        results_count: int,
        user_id: Optional[str] = None,
        execution_time_ms: Optional[float] = None
    ) -> bool:
        """Log search query for analytics."""
        try:
            # Store search analytics as a special document type
            search_log = {
                "title": f"Search: {search_query}",
                "content": f"Web search performed: {search_query}",
                "source": "web_search_service",
                "document_type": "search_analytics",
                "metadata": {
                    "search_query": search_query,
                    "search_criteria": search_criteria,
                    "results_count": results_count,
                    "user_id": user_id,
                    "execution_time_ms": execution_time_ms,
                    "service": "web_search",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
            response = await self.client.post("/documents", json_data=search_log)
            return response.get("status") == "success"
                
        except Exception as e:
            self.logger.error(f"Error logging search query: {str(e)}")
            return False
    
    async def get_search_stats(self) -> Dict[str, Any]:
        """Get web search statistics."""
        try:
            # Get property stats for web search sources
            response = await self.client.get("/properties/stats", params={
                "source": "web_search_service"
            })
            
            if response.get("status") == "success":
                property_stats = response.get("stats", {})
            else:
                property_stats = {"error": "Failed to get property stats"}
            
            # Get search analytics stats
            doc_response = await self.client.get("/documents/stats", params={
                "document_type": "search_analytics"
            })
            
            if doc_response.get("status") == "success":
                search_stats = doc_response.get("stats", {})
            else:
                search_stats = {"error": "Failed to get search stats"}
            
            return {
                "property_stats": property_stats,
                "search_analytics": search_stats
            }
                
        except Exception as e:
            self.logger.error(f"Error getting search stats: {str(e)}")
            return {"error": str(e)}
    
    async def get_popular_searches(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most popular search queries."""
        try:
            search_data = {
                "document_type": "search_analytics",
                "limit": limit,
                "order_by": "created_at",
                "order_direction": "desc"
            }
            
            response = await self.client.post("/documents/search", json_data=search_data)
            
            if response.get("status") == "success":
                documents = response.get("documents", [])
                searches = []
                
                for doc in documents:
                    metadata = doc.get("metadata", {})
                    searches.append({
                        "query": metadata.get("search_query", ""),
                        "criteria": metadata.get("search_criteria", {}),
                        "results_count": metadata.get("results_count", 0),
                        "timestamp": metadata.get("timestamp", ""),
                        "execution_time_ms": metadata.get("execution_time_ms", 0)
                    })
                
                return searches
            else:
                return []
                
        except Exception as e:
            self.logger.error(f"Error getting popular searches: {str(e)}")
            return []