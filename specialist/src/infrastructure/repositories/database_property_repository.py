"""
Property repository that integrates with central database service.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID

from shared.src.utils.logging import get_logger

from ...domain.interfaces.property_service import PropertyRepository
from ...domain.entities.property import Property, PropertyType, PropertyStatus, Address, PropertyFeatures, PropertyFinancial
from ..clients.database_client import DatabaseClient


class DatabasePropertyRepository(PropertyRepository):
    """Property repository with central database integration."""
    
    def __init__(self, database_client: DatabaseClient):
        self.database_client = database_client
        self.logger = get_logger("database_property_repository")
    
    async def save(self, property: Property) -> Property:
        """Save property to database."""
        try:
            success = await self.database_client.save_property(property)
            if success:
                self.logger.info(f"Property saved: {property.id}")
            else:
                self.logger.warning(f"Failed to save property: {property.id}")
            return property
        except Exception as e:
            self.logger.error(f"Error saving property {property.id}: {str(e)}")
            return property
    
    async def find_by_id(self, property_id: UUID) -> Optional[Property]:
        """Find property by ID."""
        try:
            property_data = await self.database_client.get_property_by_id(property_id)
            
            if property_data:
                return self._convert_from_db_format(property_data)
            return None
            
        except Exception as e:
            self.logger.error(f"Error finding property {property_id}: {str(e)}")
            return None
    
    async def search(self, criteria: Dict[str, Any], limit: int = 10) -> List[Property]:
        """Search properties by criteria."""
        try:
            # Convert criteria to database format
            db_criteria = self._convert_criteria_to_db_format(criteria)
            
            properties_data = await self.database_client.search_properties(db_criteria, limit)
            
            properties = []
            for prop_data in properties_data:
                try:
                    property_obj = self._convert_from_db_format(prop_data)
                    properties.append(property_obj)
                except Exception as e:
                    self.logger.warning(f"Error converting property from DB: {str(e)}")
                    continue
            
            self.logger.info(f"Found {len(properties)} properties matching criteria")
            return properties
            
        except Exception as e:
            self.logger.error(f"Error searching properties: {str(e)}")
            return []
    
    async def find_by_location(
        self,
        city: str,
        neighborhood: Optional[str] = None,
        radius_km: Optional[float] = None,
        limit: int = 10
    ) -> List[Property]:
        """Find properties by location."""
        criteria = {"city": city}
        
        if neighborhood:
            criteria["neighborhood"] = neighborhood
        
        if radius_km:
            criteria["radius_km"] = radius_km
        
        return await self.search(criteria, limit)
    
    async def find_by_price_range(
        self,
        min_price: Optional[float],
        max_price: Optional[float],
        property_type: Optional[PropertyType] = None,
        limit: int = 10
    ) -> List[Property]:
        """Find properties by price range."""
        criteria = {}
        
        if min_price:
            criteria["price_min"] = min_price
        
        if max_price:
            criteria["price_max"] = max_price
        
        if property_type:
            criteria["property_type"] = property_type.value
        
        return await self.search(criteria, limit)
    
    async def update_status(self, property_id: UUID, status: PropertyStatus) -> bool:
        """Update property status."""
        try:
            success = await self.database_client.update_property_status(
                property_id, status.value
            )
            
            if success:
                self.logger.info(f"Property status updated: {property_id} -> {status.value}")
            else:
                self.logger.warning(f"Failed to update property status: {property_id}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error updating property status {property_id}: {str(e)}")
            return False
    
    async def delete(self, property_id: UUID) -> bool:
        """Delete property (mark as inactive)."""
        return await self.update_status(property_id, PropertyStatus.INACTIVE)
    
    def _convert_criteria_to_db_format(self, criteria: Dict[str, Any]) -> Dict[str, Any]:
        """Convert search criteria to database format."""
        db_criteria = {}
        
        # Map common fields
        field_mapping = {
            "city": "location.city",
            "neighborhood": "location.neighborhood",
            "property_type": "property_type",
            "bedrooms": "bedrooms",
            "bathrooms": "bathrooms",
            "price_min": "price_min",
            "price_max": "price_max",
            "area_min": "area_sqm_min",
            "area_max": "area_sqm_max"
        }
        
        for key, value in criteria.items():
            if key in field_mapping:
                db_key = field_mapping[key]
                db_criteria[db_key] = value
            else:
                db_criteria[key] = value
        
        return db_criteria
    
    def _convert_from_db_format(self, property_data: Dict[str, Any]) -> Property:
        """Convert database property data to Property entity."""
        from ...domain.entities.property import PropertyCoordinates, PropertyImage
        
        # Extract location data
        location = property_data.get("location", {})
        coordinates = None
        if location.get("coordinates"):
            coords = location["coordinates"]
            if coords.get("lat") and coords.get("lng"):
                coordinates = PropertyCoordinates(
                    latitude=coords["lat"],
                    longitude=coords["lng"]
                )
        
        address = PropertyAddress(
            street=location.get("street", ""),
            number=location.get("number", ""),
            neighborhood=location.get("neighborhood", ""),
            city=location.get("city", ""),
            state=location.get("state", ""),
            zip_code=location.get("zip_code", ""),
            coordinates=coordinates
        )
        
        # Extract features
        features = PropertyFeatures(
            bedrooms=property_data.get("bedrooms", 0),
            bathrooms=property_data.get("bathrooms", 0),
            total_area=property_data.get("area_sqm"),
            amenities=property_data.get("features", [])
        )
        
        # Extract financial info
        financial = PropertyFinancial(
            price=property_data.get("price"),
            currency="BRL"
        )
        
        # Extract images
        images = []
        for img_url in property_data.get("images", []):
            images.append(PropertyImage(url=img_url))
        
        # Extract metadata for specialist ID
        metadata = property_data.get("metadata", {})
        specialist_id = metadata.get("specialist_id")
        
        # Map property type
        property_type = PropertyType.HOUSE  # Default
        if property_data.get("property_type"):
            try:
                property_type = PropertyType(property_data["property_type"].upper())
            except ValueError:
                pass
        
        # Map status
        status = PropertyStatus.AVAILABLE
        if not property_data.get("is_active", True):
            status = PropertyStatus.INACTIVE
        elif metadata.get("status"):
            try:
                status = PropertyStatus(metadata["status"].upper())
            except ValueError:
                pass
        
        property_obj = Property(
            id=UUID(specialist_id) if specialist_id else UUID(property_data["id"]),
            title=property_data.get("title", ""),
            description=property_data.get("description", ""),
            type=property_type,
            status=status,
            address=address,
            features=features,
            financial=financial,
            images=images,
            source_url=property_data.get("source_url"),
            source_name=property_data.get("source_name", "database")
        )
        
        return property_obj