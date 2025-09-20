"""
Web Search Service - Property Search Integration
Handles web scraping for property listings
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel
import uvicorn

from shared.src.infrastructure.redis_client import RedisClient
from shared.src.utils.config import get_settings
from shared.src.utils.logging import setup_logging, get_logger

# Import infrastructure
try:
    from src.infrastructure.clients.database_client import DatabaseClient
    database_client_available = True
except ImportError:
    logger = get_logger("web_search")
    logger.warning("Database client not available, continuing without database integration")
    database_client_available = False

# Configuration
settings = get_settings()
setup_logging(service_name=settings.service.name, log_level=settings.log_level)
logger = get_logger("web_search")

# Initialize clients
redis_client = RedisClient(settings.redis)

# Database client (optional)
database_client = None
if database_client_available:
    try:
        database_service_url = f"http://database:{settings.services.get('database_port', 8006)}"
        database_client = DatabaseClient(database_service_url)
        logger.info("Database client initialized")
    except Exception as e:
        logger.warning(f"Database client initialization failed: {str(e)}")

# FastAPI app
app = FastAPI(
    title="FamaGPT Web Search Service",
    description="Property search and web scraping",
    version="1.0.0"
)

# CORS middleware
origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allow_origins = ["*"] if origins_env.strip() == "*" else [o.strip() for o in origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SearchQuery(BaseModel):
    """Search query model"""
    query: str
    city: str = "Uberlândia"
    state: str = "MG"
    property_type: str = "any"
    max_price: float = None
    min_price: float = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    timestamp: str


@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("Starting Web Search Service...")
    await redis_client.connect()
    
    # Initialize database client if available
    if database_client:
        try:
            await database_client.__aenter__()
            logger.info("Database client connected successfully")
        except Exception as e:
            logger.warning(f"Database client connection failed: {str(e)}")
    
    logger.info("Web Search Service started successfully")


@app.on_event("shutdown") 
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("Shutting down Web Search Service...")
    await redis_client.disconnect()
    
    # Close database client if available
    if database_client:
        try:
            await database_client.__aexit__(None, None, None)
            logger.info("Database client disconnected")
        except Exception as e:
            logger.warning(f"Error disconnecting database client: {str(e)}")
    
    logger.info("Web Search Service shutdown complete")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    import datetime
    return HealthResponse(
        status="healthy",
        service="web_search",
        timestamp=datetime.datetime.utcnow().isoformat()
    )


@app.post("/search")
async def search_properties(query: SearchQuery):
    """Search for properties"""
    import time
    start_time = time.time()
    
    try:
        logger.info(f"Searching properties: {query.query}")
        
        # Check cache first
        cache_key = f"search:{query.query}:{query.city}:{query.property_type}"
        cached_results = await redis_client.get_json(cache_key)
        
        if cached_results:
            logger.info(f"Returning cached results for: {query.query}")
            return {"results": cached_results, "cached": True}
        
        # TODO: Implement actual property search logic with web scraping
        # Placeholder response for now
        results = [
            {
                "id": "1",
                "title": f"Casa 3 quartos - {query.city}/{query.state}",
                "price": 450000.0,
                "description": "Casa ampla com 3 quartos e 2 banheiros",
                "url": "https://example.com/property/1",
                "property_type": "house",
                "bedrooms": 3,
                "bathrooms": 2,
                "area": 120.5,
                "city": query.city,
                "state": query.state
            }
        ]
        
        # Cache results
        await redis_client.set_json(cache_key, results, ttl=1800)  # 30 minutes
        
        # Log search and save results to database if available
        if database_client:
            try:
                execution_time = (time.time() - start_time) * 1000  # ms
                
                # Log search query
                await database_client.log_search_query(
                    search_query=query.query,
                    search_criteria=query.dict(),
                    results_count=len(results),
                    execution_time_ms=execution_time
                )
                
                # Save found properties to database
                for result in results:
                    await database_client.save_search_result(
                        search_query=query.query,
                        search_criteria=query.dict(),
                        property_data=result,
                        source_url=result["url"],
                        source_name="example_scraper"
                    )
                    
            except Exception as db_error:
                logger.warning(f"Database operations failed: {str(db_error)}")
        
        return {"results": results, "cached": False}
        
    except Exception as e:
        logger.error(f"Error searching properties: {str(e)}")
        raise HTTPException(status_code=500, detail="Search failed")

@app.get("/stats")
async def get_search_stats():
    """Get web search statistics"""
    try:
        stats = {"service_stats": {"searches_performed": 0, "error": "Database not configured"}}
        
        if database_client:
            stats = await database_client.get_search_stats()
        
        # Add Redis cache stats
        try:
            redis_info = await redis_client.client.info()
            cache_stats = {
                "redis_connected": True,
                "used_memory": redis_info.get("used_memory_human", "unknown"),
                "connected_clients": redis_info.get("connected_clients", 0)
            }
        except:
            cache_stats = {"redis_connected": False}
        
        return {
            "status": "healthy",
            "service": "web_search",
            "database_stats": stats,
            "cache_stats": cache_stats,
            "database_enabled": database_client is not None
        }
        
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        return {
            "status": "error", 
            "error": str(e),
            "database_enabled": False
        }

@app.get("/popular-searches")
async def get_popular_searches(limit: int = 10):
    """Get popular search queries"""
    if not database_client:
        raise HTTPException(status_code=503, detail="Database integration not available")
    
    try:
        searches = await database_client.get_popular_searches(limit)
        
        return {
            "status": "success",
            "popular_searches": searches,
            "total": len(searches)
        }
        
    except Exception as e:
        logger.error(f"Error getting popular searches: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get popular searches")

@app.get("/health/extended")
async def health_check_extended():
    """Extended health check with dependencies"""
    try:
        import datetime
        
        # Check Redis
        redis_status = "healthy"
        try:
            await redis_client.client.ping()
        except Exception:
            redis_status = "unhealthy"
        
        # Check Database
        database_status = "not_configured"
        if database_client:
            try:
                stats = await database_client.get_search_stats()
                database_status = "healthy" if not stats.get("error") else "unhealthy"
            except Exception:
                database_status = "unhealthy"
        
        return {
            "status": "healthy",
            "service": "web_search",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "dependencies": {
                "redis": redis_status,
                "database": database_status
            }
        }
        
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8003,
        reload=True
    )
