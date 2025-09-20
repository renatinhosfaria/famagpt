"""
PostgreSQL implementation of PropertyRepository
"""

from typing import Optional, List, Dict, Any
from uuid import UUID
import asyncpg

from ...domain.interfaces import PropertyRepository
from shared.src.domain.models import Property

# Import shared modules
import sys
sys.path.append('/app/shared')
from shared.utils.logger import setup_logger


class PostgreSQLPropertyRepository(PropertyRepository):
    """PostgreSQL implementation of PropertyRepository"""
    
    def __init__(self, connection_pool: asyncpg.Pool):
        self.pool = connection_pool
        self.logger = setup_logger("property_repository")
    
    async def create(self, property: Property) -> Property:
        """Create a new property"""
        try:
            query = """
                INSERT INTO properties (
                    id, external_id, title, description, property_type, address,
                    city, state, postal_code, price, bedrooms, bathrooms, area,
                    features, images, contact_info, source, status, coordinates,
                    created_at, updated_at, is_active
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22)
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    property.id,
                    property.external_id,
                    property.title,
                    property.description,
                    property.property_type,
                    property.address,
                    property.city,
                    property.state,
                    property.postal_code,
                    property.price,
                    property.bedrooms,
                    property.bathrooms,
                    property.area,
                    property.features,
                    property.images,
                    property.contact_info,
                    property.source,
                    property.status,
                    property.coordinates,
                    property.created_at,
                    property.updated_at,
                    property.is_active
                )
                
                if row:
                    self.logger.info(f"Property created successfully: {property.id}")
                    return Property(**dict(row))
                else:
                    raise Exception("Failed to create property")
                    
        except Exception as e:
            self.logger.error(f"Error creating property: {str(e)}")
            raise
    
    async def get_by_id(self, property_id: UUID) -> Optional[Property]:
        """Get property by ID"""
        try:
            query = "SELECT * FROM properties WHERE id = $1 AND is_active = true"
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, property_id)
                
                if row:
                    return Property(**dict(row))
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting property by ID: {str(e)}")
            raise
    
    async def get_by_external_id(self, external_id: str) -> Optional[Property]:
        """Get property by external ID"""
        try:
            query = "SELECT * FROM properties WHERE external_id = $1 AND is_active = true"
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(query, external_id)
                
                if row:
                    return Property(**dict(row))
                return None
                
        except Exception as e:
            self.logger.error(f"Error getting property by external ID: {str(e)}")
            raise
    
    async def search(self, criteria: Dict[str, Any]) -> List[Property]:
        """Search properties by criteria"""
        try:
            # Build dynamic query based on criteria
            conditions = ["is_active = true"]
            params = []
            param_count = 1
            
            if "city" in criteria and criteria["city"]:
                conditions.append(f"city ILIKE ${param_count}")
                params.append(f"%{criteria['city']}%")
                param_count += 1
            
            if "property_type" in criteria and criteria["property_type"]:
                conditions.append(f"property_type = ${param_count}")
                params.append(criteria["property_type"])
                param_count += 1
            
            if "min_price" in criteria and criteria["min_price"]:
                conditions.append(f"price >= ${param_count}")
                params.append(criteria["min_price"])
                param_count += 1
            
            if "max_price" in criteria and criteria["max_price"]:
                conditions.append(f"price <= ${param_count}")
                params.append(criteria["max_price"])
                param_count += 1
            
            if "min_bedrooms" in criteria and criteria["min_bedrooms"]:
                conditions.append(f"bedrooms >= ${param_count}")
                params.append(criteria["min_bedrooms"])
                param_count += 1
            
            if "min_bathrooms" in criteria and criteria["min_bathrooms"]:
                conditions.append(f"bathrooms >= ${param_count}")
                params.append(criteria["min_bathrooms"])
                param_count += 1
            
            if "min_area" in criteria and criteria["min_area"]:
                conditions.append(f"area >= ${param_count}")
                params.append(criteria["min_area"])
                param_count += 1
            
            if "max_area" in criteria and criteria["max_area"]:
                conditions.append(f"area <= ${param_count}")
                params.append(criteria["max_area"])
                param_count += 1
            
            if "status" in criteria and criteria["status"]:
                conditions.append(f"status = ${param_count}")
                params.append(criteria["status"])
                param_count += 1
            
            # Text search in title and description
            if "query" in criteria and criteria["query"]:
                conditions.append(f"(title ILIKE ${param_count} OR description ILIKE ${param_count})")
                search_term = f"%{criteria['query']}%"
                params.extend([search_term, search_term])
                param_count += 2
            
            where_clause = " AND ".join(conditions)
            limit = criteria.get("limit", 50)
            
            query = f"""
                SELECT * FROM properties 
                WHERE {where_clause}
                ORDER BY updated_at DESC
                LIMIT {limit}
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, *params)
                
                return [Property(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error searching properties: {str(e)}")
            raise
    
    async def search_by_location(
        self, 
        lat: float, 
        lng: float, 
        radius_km: float = 10
    ) -> List[Property]:
        """Search properties by location using PostGIS"""
        try:
            # Using Haversine formula for distance calculation
            query = """
                SELECT *, 
                    (6371 * acos(cos(radians($1)) * cos(radians((coordinates->>'lat')::float)) * 
                     cos(radians((coordinates->>'lng')::float) - radians($2)) + 
                     sin(radians($1)) * sin(radians((coordinates->>'lat')::float)))) AS distance
                FROM properties
                WHERE coordinates IS NOT NULL
                    AND is_active = true
                    AND (6371 * acos(cos(radians($1)) * cos(radians((coordinates->>'lat')::float)) * 
                         cos(radians((coordinates->>'lng')::float) - radians($2)) + 
                         sin(radians($1)) * sin(radians((coordinates->>'lat')::float)))) <= $3
                ORDER BY distance
                LIMIT 50
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, lat, lng, radius_km)
                
                properties = []
                for row in rows:
                    row_dict = dict(row)
                    # Remove the distance field as it's not part of Property model
                    distance = row_dict.pop('distance', None)
                    prop = Property(**row_dict)
                    properties.append(prop)
                
                return properties
                
        except Exception as e:
            self.logger.error(f"Error searching properties by location: {str(e)}")
            raise
    
    async def update(self, property: Property) -> Property:
        """Update property"""
        try:
            query = """
                UPDATE properties SET
                    title = $2,
                    description = $3,
                    property_type = $4,
                    address = $5,
                    city = $6,
                    state = $7,
                    postal_code = $8,
                    price = $9,
                    bedrooms = $10,
                    bathrooms = $11,
                    area = $12,
                    features = $13,
                    images = $14,
                    contact_info = $15,
                    status = $16,
                    coordinates = $17,
                    updated_at = $18,
                    is_active = $19
                WHERE id = $1
                RETURNING *
            """
            
            async with self.pool.acquire() as connection:
                row = await connection.fetchrow(
                    query,
                    property.id,
                    property.title,
                    property.description,
                    property.property_type,
                    property.address,
                    property.city,
                    property.state,
                    property.postal_code,
                    property.price,
                    property.bedrooms,
                    property.bathrooms,
                    property.area,
                    property.features,
                    property.images,
                    property.contact_info,
                    property.status,
                    property.coordinates,
                    property.updated_at,
                    property.is_active
                )
                
                if row:
                    self.logger.info(f"Property updated successfully: {property.id}")
                    return Property(**dict(row))
                else:
                    raise Exception("Failed to update property")
                    
        except Exception as e:
            self.logger.error(f"Error updating property: {str(e)}")
            raise
    
    async def delete(self, property_id: UUID) -> None:
        """Soft delete property"""
        try:
            query = """
                UPDATE properties SET 
                    is_active = false,
                    status = 'deleted',
                    updated_at = NOW()
                WHERE id = $1
            """
            
            async with self.pool.acquire() as connection:
                result = await connection.execute(query, property_id)
                
                if result == "UPDATE 1":
                    self.logger.info(f"Property deleted successfully: {property_id}")
                else:
                    raise Exception("Property not found or already deleted")
                    
        except Exception as e:
            self.logger.error(f"Error deleting property: {str(e)}")
            raise
    
    async def get_featured_properties(self, limit: int = 10) -> List[Property]:
        """Get featured/highlighted properties"""
        try:
            query = """
                SELECT * FROM properties 
                WHERE is_active = true 
                AND status = 'available'
                ORDER BY price DESC, updated_at DESC
                LIMIT $1
            """
            
            async with self.pool.acquire() as connection:
                rows = await connection.fetch(query, limit)
                
                return [Property(**dict(row)) for row in rows]
                
        except Exception as e:
            self.logger.error(f"Error getting featured properties: {str(e)}")
            raise