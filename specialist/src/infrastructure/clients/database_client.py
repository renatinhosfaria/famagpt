"""
Database client for Specialist service to integrate with central database service.
"""
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from uuid import UUID

from shared.src.infrastructure.http_client import ServiceClient
from shared.src.utils.logging import get_logger

from ...domain.entities.property import Property, PropertyStatus, PropertyType
from ...domain.entities.user import UserProfile, ConversationContext, Message, PropertyInquiry


class DatabaseClient:
    """HTTP client for central Database service integration."""
    
    def __init__(self, database_service_url: str):
        self.client = ServiceClient("specialist", database_service_url)
        self.logger = get_logger("specialist_database_client")
    
    async def __aenter__(self):
        await self.client.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.close()
    
    async def get_user_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        """Get user by phone number."""
        try:
            response = await self.client.get(f"/users/phone/{phone}")
            
            if response.get("status") == "success":
                return response.get("user")
            return None
                
        except Exception as e:
            self.logger.error(f"Error getting user by phone {phone}: {str(e)}")
            return None
    
    async def get_user_preferences(self, user_id: UUID) -> Dict[str, Any]:
        """Get user preferences and search history."""
        try:
            response = await self.client.get(f"/users/{user_id}")
            
            if response.get("status") == "success":
                user_data = response.get("user", {})
                return user_data.get("preferences", {})
            return {}
                
        except Exception as e:
            self.logger.error(f"Error getting user preferences {user_id}: {str(e)}")
            return {}
    
    async def update_user_preferences(self, user_id: UUID, preferences: Dict[str, Any]) -> bool:
        """Update user preferences."""
        try:
            update_data = {
                "preferences": preferences,
                "metadata": {
                    "last_preference_update": datetime.utcnow().isoformat(),
                    "updated_by": "specialist_service"
                }
            }
            
            response = await self.client.patch(f"/users/{user_id}", json_data=update_data)
            return response.get("status") == "success"
                
        except Exception as e:
            self.logger.error(f"Error updating user preferences {user_id}: {str(e)}")
            return False
    
    async def save_property(self, property: Property) -> bool:
        """Save property to central database."""
        try:
            property_data = {
                "title": property.title,
                "description": property.description,
                "price": float(property.financial.price) if property.financial.price else None,
                "property_type": property.type.value if property.type else "house",
                "location": {
                    "city": property.address.city,
                    "state": property.address.state,
                    "neighborhood": property.address.neighborhood,
                    "street": property.address.street,
                    "number": property.address.number,
                    "zip_code": property.address.zip_code,
                    "coordinates": {
                        "lat": property.address.coordinates.latitude if property.address.coordinates else None,
                        "lng": property.address.coordinates.longitude if property.address.coordinates else None
                    }
                },
                "bedrooms": property.features.bedrooms if property.features else None,
                "bathrooms": property.features.bathrooms if property.features else None,
                "area_sqm": float(property.features.total_area) if property.features and property.features.total_area else None,
                "features": property.features.amenities if property.features else [],
                "images": [img.url for img in property.images] if property.images else [],
                "source_url": property.source_url,
                "source_name": property.source_name or "specialist_service",
                "is_active": property.status == PropertyStatus.AVAILABLE,
                "metadata": {
                    "specialist_id": str(property.id),
                    "status": property.status.value if property.status else "available",
                    "last_updated": datetime.utcnow().isoformat(),
                    "created_via": "specialist_service"
                }
            }
            
            response = await self.client.post("/properties", json_data=property_data)
            
            if response.get("status") == "success":
                self.logger.info(f"Property saved to database: {property.title}")
                return True
            else:
                self.logger.warning(f"Failed to save property: {response}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error saving property {property.id}: {str(e)}")
            return False
    
    async def search_properties(
        self, 
        criteria: Dict[str, Any], 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search properties in central database."""
        try:
            search_data = {
                **criteria,
                "limit": limit,
                "source": "specialist_service"
            }
            
            response = await self.client.post("/properties/search", json_data=search_data)
            
            if response.get("status") == "success":
                return response.get("properties", [])
            else:
                self.logger.warning(f"Property search failed: {response}")
                return []
                
        except Exception as e:
            self.logger.error(f"Error searching properties: {str(e)}")
            return []
    
    async def get_property_by_id(self, property_id: UUID) -> Optional[Dict[str, Any]]:
        """Get property by ID from central database."""
        try:
            # Search by specialist_id in metadata
            search_data = {
                "metadata_filter": {"specialist_id": str(property_id)},
                "limit": 1
            }
            
            response = await self.client.post("/properties/search", json_data=search_data)
            
            if response.get("status") == "success":
                properties = response.get("properties", [])
                return properties[0] if properties else None
            return None
                
        except Exception as e:
            self.logger.error(f"Error getting property by ID {property_id}: {str(e)}")
            return None
    
    async def update_property_status(self, property_id: UUID, status: str) -> bool:
        """Update property status."""
        try:
            property_data = await self.get_property_by_id(property_id)
            if not property_data:
                return False
            
            db_property_id = property_data.get("id")
            update_data = {
                "is_active": status == "available",
                "metadata": {
                    **property_data.get("metadata", {}),
                    "status": status,
                    "last_updated": datetime.utcnow().isoformat()
                }
            }
            
            response = await self.client.patch(f"/properties/{db_property_id}", json_data=update_data)
            return response.get("status") == "success"
                
        except Exception as e:
            self.logger.error(f"Error updating property status {property_id}: {str(e)}")
            return False
    
    async def get_property_stats(self) -> Dict[str, Any]:
        """Get property statistics from central database."""
        try:
            response = await self.client.get("/properties/stats", params={
                "source": "specialist_service"
            })
            
            if response.get("status") == "success":
                return response.get("stats", {})
            else:
                return {"error": "Failed to get stats from database"}
                
        except Exception as e:
            self.logger.error(f"Error getting property stats: {str(e)}")
            return {"error": str(e)}
    
    async def save_user_interaction(
        self, 
        user_id: UUID, 
        property_id: Optional[UUID], 
        interaction_type: str, 
        metadata: Dict[str, Any]
    ) -> bool:
        """Save user interaction for analytics."""
        try:
            interaction_data = {
                "user_id": str(user_id),
                "interaction_type": interaction_type,
                "metadata": {
                    **metadata,
                    "property_id": str(property_id) if property_id else None,
                    "service": "specialist",
                    "timestamp": datetime.utcnow().isoformat()
                }
            }
            
            # For now, we'll store interactions as a special type of message
            message_data = {
                "conversation_id": metadata.get("conversation_id", str(user_id)),
                "user_id": str(user_id),
                "content": f"User {interaction_type}",
                "message_type": "interaction",
                "metadata": interaction_data["metadata"]
            }
            
            response = await self.client.post("/messages", json_data=message_data)
            return response.get("status") == "success"
                
        except Exception as e:
            self.logger.error(f"Error saving user interaction: {str(e)}")
            return False