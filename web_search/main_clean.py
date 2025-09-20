"""
Web Search Service - Property Search with Clean Architecture
Handles web scraping for property listings
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import datetime

from shared.src.utils.config import get_settings
from shared.src.utils.logging import setup_logging, get_logger
from shared.src.infrastructure.redis_client import RedisClient

# Configuration
settings = get_settings()
setup_logging(service_name=settings.service.name, log_level=settings.log_level)
logger = get_logger("web_search")

# FastAPI app
app = FastAPI(
    title="FamaGPT Web Search Service",
    description="Property search and web scraping with Clean Architecture",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Response Models
class PropertyResponse(BaseModel):
    """Property response model"""
    id: Optional[str] = None
    title: str
    description: Optional[str] = None
    price: Optional[float] = None
    currency: str = "BRL"
    listing_type: Optional[str] = None
    property_type: Optional[str] = None
    location: dict = {}
    features: dict = {}
    images: List[str] = []
    source_url: Optional[str] = None
    source_site: Optional[str] = None


class SearchResultResponse(BaseModel):
    """Search result response model"""
    properties: List[PropertyResponse]
    total_count: int
    search_time_seconds: Optional[float] = None
    cached: bool = False
    sources: List[str] = []
    query: dict = {}


class ServiceInfoResponse(BaseModel):
    """Service info response model"""
    service: str
    description: str
    supported_cities: List[str]
    supported_states: List[str]
    property_types: List[str]
    listing_types: List[str]
    max_results_limit: int
    cache_enabled: bool
    features: dict


class HealthResponse(BaseModel):
    """Health response model"""
    status: str
    service: str
    timestamp: str


class SearchRequest(BaseModel):
    """Search request model for JSON input"""
    query: str
    city: str = "Uberlândia"
    state: str = "MG" 
    property_type: Optional[str] = None
    listing_type: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_bedrooms: Optional[int] = None
    max_bedrooms: Optional[int] = None
    max_results: int = 50
    use_cache: bool = True


# Dependency injection setup
def setup_dependencies():
    """Setup dependency injection"""
    try:
        # Redis client
        redis_client = RedisClient(settings.redis)
        
        # Import Clean Architecture components
        from src.infrastructure.scrapers.generic_property_scraper import GenericPropertyScraper
        from src.infrastructure.services.redis_cache_service import RedisCacheService
        from src.application.use_cases.search_properties import SearchPropertiesUseCase
        from src.application.services.web_search_app_service import WebSearchAppService
        
        # Create instances
        scrapers = [
            GenericPropertyScraper(site_name="mock_real_estate")
        ]
        cache_service = RedisCacheService(redis_client)
        search_use_case = SearchPropertiesUseCase(scrapers, cache_service)
        app_service = WebSearchAppService(search_use_case)
        
        return {
            'redis_client': redis_client,
            'app_service': app_service,
            'scrapers': scrapers
        }
        
    except ImportError as e:
        logger.warning(f"Clean Architecture components not available: {e}")
        return None

# Try to setup dependencies
dependencies = setup_dependencies()


@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("Starting Web Search Service...")
    
    if dependencies:
        await dependencies['redis_client'].connect()
        logger.info("Web Search Service started with Clean Architecture")
    else:
        logger.info("Web Search Service started with fallback implementation")


@app.on_event("shutdown") 
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("Shutting down Web Search Service...")
    
    if dependencies:
        await dependencies['redis_client'].disconnect()
        # Cleanup scrapers
        for scraper in dependencies['scrapers']:
            if hasattr(scraper, 'cleanup'):
                await scraper.cleanup()
    
    logger.info("Web Search Service shutdown complete")


@app.get("/")
async def root():
    """Root endpoint with service information"""
    return {
        "service": "web_search",
        "version": "2.0.0",
        "description": "Property search and web scraping service",
        "clean_architecture": dependencies is not None,
        "endpoints": {
            "POST /search": "Search for properties",
            "GET /property/details": "Get property details by URL",
            "GET /info": "Get service capabilities",
            "GET /health": "Health check",
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="web_search",
        timestamp=datetime.datetime.utcnow().isoformat()
    )


@app.get("/info", response_model=ServiceInfoResponse)
async def service_info():
    """Get service information and capabilities"""
    if dependencies:
        try:
            info = await dependencies['app_service'].get_service_info()
            return ServiceInfoResponse(**info)
        except Exception as e:
            logger.error(f"Error getting service info: {str(e)}")
    
    # Fallback response
    return ServiceInfoResponse(
        service="web_search",
        description="Property search and web scraping service",
        supported_cities=["Uberlândia"],
        supported_states=["MG"],
        property_types=["house", "apartment", "commercial", "land", "any"],
        listing_types=["sale", "rent"],
        max_results_limit=200,
        cache_enabled=True,
        features={
            "price_filtering": True,
            "bedroom_filtering": True,
            "property_type_filtering": True,
            "caching": True,
            "deduplication": True,
            "multiple_sources": True
        }
    )


@app.post("/search/json", response_model=SearchResultResponse)
async def search_properties_json(request: SearchRequest):
    """Search for properties with JSON request body (for API testing compatibility)"""
    return await search_properties_internal(
        query=request.query,
        city=request.city,
        state=request.state,
        property_type=request.property_type,
        listing_type=request.listing_type,
        min_price=request.min_price,
        max_price=request.max_price,
        min_bedrooms=request.min_bedrooms,
        max_bedrooms=request.max_bedrooms,
        max_results=request.max_results,
        use_cache=request.use_cache
    )

@app.post("/search", response_model=SearchResultResponse)
async def search_properties(
    query: str,
    city: str = "Uberlândia",
    state: str = "MG",
    property_type: Optional[str] = Query(None, description="house, apartment, commercial, land, any"),
    listing_type: Optional[str] = Query(None, description="sale, rent"),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    min_bedrooms: Optional[int] = Query(None, ge=0),
    max_bedrooms: Optional[int] = Query(None, ge=0),
    max_results: int = Query(50, ge=1, le=200),
    use_cache: bool = True
):
    """Search for properties with query parameters"""
    return await search_properties_internal(
        query=query,
        city=city,
        state=state,
        property_type=property_type,
        listing_type=listing_type,
        min_price=min_price,
        max_price=max_price,
        min_bedrooms=min_bedrooms,
        max_bedrooms=max_bedrooms,
        max_results=max_results,
        use_cache=use_cache
    )

async def search_properties_internal(
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
):
    """Search for properties with filters"""
    try:
        if dependencies:
            # Use Clean Architecture implementation
            result = await dependencies['app_service'].search_properties(
                query=query,
                city=city,
                state=state,
                property_type=property_type,
                listing_type=listing_type,
                min_price=min_price,
                max_price=max_price,
                min_bedrooms=min_bedrooms,
                max_bedrooms=max_bedrooms,
                max_results=max_results,
                use_cache=use_cache
            )
            
            # Convert to response format
            properties = []
            for prop in result.properties:
                prop_response = PropertyResponse(
                    id=prop.id,
                    title=prop.title or "Unnamed Property",
                    description=prop.description,
                    price=prop.price,
                    currency=prop.currency,
                    listing_type=prop.listing_type.value if prop.listing_type else None,
                    property_type=prop.property_type.value if prop.property_type else None,
                    location={
                        "city": prop.location.city if prop.location else None,
                        "state": prop.location.state if prop.location else None,
                        "neighborhood": prop.location.neighborhood if prop.location else None,
                    },
                    features={
                        "bedrooms": prop.features.bedrooms if prop.features else None,
                        "bathrooms": prop.features.bathrooms if prop.features else None,
                        "area_m2": prop.features.area_m2 if prop.features else None,
                        "garage_spaces": prop.features.garage_spaces if prop.features else None,
                    },
                    images=prop.images or [],
                    source_url=prop.source_url,
                    source_site=prop.source_site
                )
                properties.append(prop_response)
            
            return SearchResultResponse(
                properties=properties,
                total_count=result.total_count,
                search_time_seconds=result.search_time_seconds,
                cached=result.cached,
                sources=result.sources or [],
                query={
                    "query": query,
                    "city": city,
                    "state": state,
                    "filters_applied": {
                        "property_type": property_type,
                        "listing_type": listing_type,
                        "min_price": min_price,
                        "max_price": max_price,
                        "min_bedrooms": min_bedrooms,
                        "max_bedrooms": max_bedrooms
                    }
                }
            )
        
        else:
            # Fallback implementation with mock data
            logger.info(f"Using fallback search for: {query}")
            
            mock_properties = [
                PropertyResponse(
                    id="mock_1",
                    title=f"Apartamento 2 quartos - {city}",
                    description="Apartamento moderno em ótima localização",
                    price=280000.0,
                    currency="BRL",
                    listing_type="sale",
                    property_type="apartment",
                    location={"city": city, "state": state, "neighborhood": "Centro"},
                    features={"bedrooms": 2, "bathrooms": 1, "area_m2": 65.0, "garage_spaces": 1},
                    source_url="https://example.com/property/1",
                    source_site="mock_site"
                ),
                PropertyResponse(
                    id="mock_2", 
                    title=f"Casa 3 quartos - {city}",
                    description="Casa com quintal e garagem",
                    price=450000.0,
                    currency="BRL",
                    listing_type="sale",
                    property_type="house",
                    location={"city": city, "state": state, "neighborhood": "Bairro Residencial"},
                    features={"bedrooms": 3, "bathrooms": 2, "area_m2": 120.0, "garage_spaces": 2},
                    source_url="https://example.com/property/2",
                    source_site="mock_site"
                )
            ]
            
            return SearchResultResponse(
                properties=mock_properties,
                total_count=len(mock_properties),
                search_time_seconds=0.1,
                cached=False,
                sources=["mock_site"],
                query={"query": query, "city": city, "state": state}
            )
            
    except ValueError as e:
        logger.warning(f"Invalid search parameters: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"Error searching properties: {str(e)}")
        raise HTTPException(status_code=500, detail="Search failed")


@app.get("/property/details")
async def get_property_details(url: str):
    """Get detailed property information by URL"""
    try:
        if dependencies:
            property_obj = await dependencies['app_service'].get_property_details(url)
            
            return PropertyResponse(
                id=property_obj.id,
                title=property_obj.title or "Unnamed Property",
                description=property_obj.description,
                price=property_obj.price,
                currency=property_obj.currency,
                listing_type=property_obj.listing_type.value if property_obj.listing_type else None,
                property_type=property_obj.property_type.value if property_obj.property_type else None,
                location={
                    "city": property_obj.location.city if property_obj.location else None,
                    "state": property_obj.location.state if property_obj.location else None,
                    "neighborhood": property_obj.location.neighborhood if property_obj.location else None,
                    "street": property_obj.location.street if property_obj.location else None,
                },
                features={
                    "bedrooms": property_obj.features.bedrooms if property_obj.features else None,
                    "bathrooms": property_obj.features.bathrooms if property_obj.features else None,
                    "area_m2": property_obj.features.area_m2 if property_obj.features else None,
                    "garage_spaces": property_obj.features.garage_spaces if property_obj.features else None,
                    "amenities": property_obj.features.amenities if property_obj.features else [],
                },
                images=property_obj.images or [],
                source_url=property_obj.source_url,
                source_site=property_obj.source_site
            )
        else:
            # Fallback
            return {
                "message": "Property details feature requires Clean Architecture implementation",
                "url": url,
                "status": "not_available"
            }
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"Error getting property details: {str(e)}")
        raise HTTPException(status_code=500, detail="Could not retrieve property details")


if __name__ == "__main__":
    uvicorn.run(
        "main_clean:app",
        host="0.0.0.0", 
        port=8003,
        reload=True
    )