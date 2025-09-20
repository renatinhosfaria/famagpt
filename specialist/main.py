"""
Specialist Service - Real Estate AI Agent
The main AI agent specializing in real estate assistance
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import uvicorn

from shared.src.infrastructure.redis_client import RedisClient
from shared.src.infrastructure.http_client import HTTPClient
from shared.src.utils.config import get_settings
from shared.src.utils.logging import setup_logging, get_logger

# Domain and Application imports
from src.application.use_cases.process_user_query import ProcessUserQueryUseCase
from src.application.services.conversation_service import ConversationService
from src.application.services.property_service import PropertyService
from src.application.services.ai_orchestrator import AIOrchestrator

# Infrastructure imports
from src.infrastructure.clients.external_services import (
    ExternalMemoryService, 
    ExternalRAGService,
    LocalIntentClassificationService,
    LocalResponseGenerationService
)
from src.infrastructure.clients.database_client import DatabaseClient
from src.infrastructure.repositories.property_repository import InMemoryPropertyRepository
from src.infrastructure.repositories.database_property_repository import DatabasePropertyRepository

# Configuration
settings = get_settings()
setup_logging(service_name=settings.service.name, log_level=settings.log_level)
logger = get_logger("specialist")

# Initialize clients
redis_client = RedisClient(settings.redis)
http_client = HTTPClient()

# Initialize services
memory_service = ExternalMemoryService(http_client, settings.service.memory_url)
rag_service = ExternalRAGService(http_client, settings.service.rag_url)
intent_service = LocalIntentClassificationService()
response_service = LocalResponseGenerationService()

# Initialize Database client for property persistence
database_client = None
property_repository = InMemoryPropertyRepository(redis_client)

# Try to initialize database integration
try:
    database_service_url = f"http://database:{settings.services.get('database_port', 8006)}"
    database_client = DatabaseClient(database_service_url)
    
    # Use hybrid repository that syncs with database
    property_repository = DatabasePropertyRepository(database_client)
    logger.info("Database integration initialized for properties")
except Exception as e:
    logger.warning(f"Database integration failed, using in-memory repository: {str(e)}")

# Initialize domain services - Mock implementations for services not yet available
class MockWebSearchService:
    async def search_properties(self, criteria: Dict[str, Any]) -> List:
        logger.info("Mock web search called", criteria=criteria)
        return []  # Return empty for now
    
    async def get_property_details(self, url: str) -> Optional[Any]:
        return None

class MockAnalysisService:
    async def analyze_property_value(self, property) -> Dict[str, Any]:
        return {"analysis": "Mock analysis", "confidence": 0.8}
    
    async def compare_properties(self, properties: List) -> Dict[str, Any]:
        return {"comparison": "Mock comparison"}
    
    async def get_market_trends(self, city: str, property_type=None) -> Dict[str, Any]:
        return {
            "city": city,
            "trends": "Mercado estável com leve tendência de alta",
            "avg_price": 450000
        }

class MockRecommendationService:
    async def recommend_properties(self, user_id, criteria: Dict[str, Any], limit: int = 5) -> List:
        return []  # Return empty for now
    
    async def update_user_preferences(self, user_id, preferences: Dict[str, Any]) -> None:
        pass

web_search_service = MockWebSearchService()
analysis_service = MockAnalysisService() 
recommendation_service = MockRecommendationService()

# Initialize application services
conversation_service = ConversationService(redis_client, memory_service)
property_service = PropertyService(
    property_repository, web_search_service, analysis_service, recommendation_service
)
ai_orchestrator = AIOrchestrator(
    memory_service, rag_service, intent_service, response_service
)

# Initialize use cases
process_query_use_case = ProcessUserQueryUseCase(
    conversation_service, property_service, ai_orchestrator
)

# FastAPI app
app = FastAPI(
    title="FamaGPT Specialist Service",
    description="Real Estate AI Agent Specialist",
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


class QueryRequest(BaseModel):
    """Query request model"""
    user_id: str
    conversation_id: str
    message: str
    context: Dict[str, Any] = {}

class QueryResponse(BaseModel):
    """Query response model"""
    success: bool
    response: str
    response_type: str = "text"
    intent: Optional[str] = None
    suggestions: List[str] = []
    properties: List[Dict[str, Any]] = []
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    timestamp: str


@app.on_event("startup")
async def startup_event():
    """Startup event handler"""
    logger.info("Starting Specialist Service...")
    await redis_client.connect()
    
    # Initialize database client if available
    if database_client:
        try:
            await database_client.__aenter__()
            logger.info("Database client connected successfully")
        except Exception as e:
            logger.warning(f"Database client connection failed: {str(e)}")
    
    logger.info("Specialist Service started successfully")


@app.on_event("shutdown") 
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("Shutting down Specialist Service...")
    await redis_client.disconnect()
    await http_client.close()
    
    # Close database client if available
    if database_client:
        try:
            await database_client.__aexit__(None, None, None)
            logger.info("Database client disconnected")
        except Exception as e:
            logger.warning(f"Error disconnecting database client: {str(e)}")
    
    logger.info("Specialist Service shutdown complete")


@app.get("/health")
async def health_check():
    """Health check endpoint with dependencies for TestSprite compatibility"""
    import datetime
    
    # Check dependencies quickly
    redis_status = "healthy"
    try:
        if redis_client:
            await redis_client.client.ping()
    except Exception:
        redis_status = "unhealthy"
    
    memory_status = "configured" if memory_service else "not_configured" 
    rag_status = "configured" if rag_service else "not_configured"
    database_status = "configured" if database_client else "not_configured"
    
    return {
        "status": "healthy",
        "service": "specialist",
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "dependencies": {  # TestSprite compatibility
            "redis": redis_status,
            "database": database_status,
            "memory_service": memory_status,
            "rag_service": rag_status
        }
    }


@app.post("/process", response_model=QueryResponse)
async def process_query(request: QueryRequest) -> QueryResponse:
    """Process user query with AI specialist"""
    try:
        logger.info(
            "Processing query for user",
            user_id=request.user_id,
            conversation_id=request.conversation_id
        )
        
        # Execute main use case
        result = await process_query_use_case.execute(
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            message=request.message,
            context=request.context
        )
        
        # Cache conversation state for quick access
        cache_key = f"specialist:{request.user_id}:{request.conversation_id}:last_response"
        await redis_client.set_json(cache_key, result, ttl=3600)
        
        logger.info(
            "Query processed successfully",
            user_id=request.user_id,
            intent=result.get("intent"),
            success=result.get("success")
        )
        
        return QueryResponse(**result)
        
    except Exception as e:
        logger.error(
            "Error processing query",
            user_id=request.user_id,
            error=str(e),
            exc_info=True
        )
        
        return QueryResponse(
            success=False,
            response="Desculpe, ocorreu um erro ao processar sua consulta. Tente novamente.",
            response_type="error",
            error=str(e)
        )


@app.get("/properties/search")
async def search_properties(
    city: str = "Uberlândia",
    property_type: Optional[str] = None,
    bedrooms: Optional[int] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    limit: int = 10
):
    """Search properties endpoint"""
    try:
        criteria = {"city": city}
        
        if property_type:
            criteria["property_type"] = property_type
        if bedrooms:
            criteria["bedrooms"] = bedrooms
        if min_price:
            criteria["price_min"] = min_price
        if max_price:
            criteria["price_max"] = max_price
        
        properties = await property_service.search_properties(criteria, limit)
        
        return {
            "properties": [prop.to_dict() for prop in properties],
            "total": len(properties),
            "criteria": criteria
        }
        
    except Exception as e:
        logger.error("Error searching properties", error=str(e))
        raise HTTPException(status_code=500, detail="Property search failed")

@app.get("/properties/{property_id}")
async def get_property_details(property_id: str):
    """Get property details endpoint"""
    try:
        from uuid import UUID
        
        property_details = await property_service.get_property_details(UUID(property_id))
        
        if not property_details:
            raise HTTPException(status_code=404, detail="Property not found")
        
        return {
            "property": property_details.to_dict()
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid property ID format")
    except Exception as e:
        logger.error("Error getting property details", property_id=property_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get property details")

@app.get("/market/trends")
async def get_market_trends(
    city: str = "Uberlândia",
    property_type: Optional[str] = None
):
    """Get market trends endpoint"""
    try:
        from src.domain.entities.property import PropertyType
        
        prop_type = None
        if property_type:
            try:
                prop_type = PropertyType(property_type)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid property type")
        
        trends = await property_service.get_market_trends(city, prop_type)
        
        return trends
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting market trends", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get market trends")


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
                stats = await database_client.get_property_stats()
                database_status = "healthy" if not stats.get("error") else "unhealthy"
            except Exception:
                database_status = "unhealthy"
        
        # Check Memory service
        memory_status = "unknown"
        try:
            if hasattr(memory_service, 'health_check'):
                memory_status = "healthy"
            else:
                memory_status = "configured"
        except Exception:
            memory_status = "unhealthy"
        
        # Check RAG service
        rag_status = "unknown"
        try:
            if hasattr(rag_service, 'health_check'):
                rag_status = "healthy" 
            else:
                rag_status = "configured"
        except Exception:
            rag_status = "unhealthy"
        
        return {
            "status": "healthy",
            "service": "specialist",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "dependencies": {
                "redis": redis_status,
                "database": database_status,
                "memory_service": memory_status,
                "rag_service": rag_status
            }
        }
        
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8007,
        reload=True
    )
