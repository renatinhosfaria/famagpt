"""
Specialist Service - Real Estate AI Agent
The main AI agent specializing in real estate assistance
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from shared.src.infrastructure.redis_client import RedisClient
from shared.src.infrastructure.http_client import HTTPClient
from shared.src.utils.config import get_settings
from shared.src.utils.logging import setup_logging, get_logger

# Configuration
settings = get_settings()
setup_logging(service_name=settings.service.name, log_level=settings.log_level)
logger = get_logger("specialist")

# Initialize clients
redis_client = RedisClient(settings.redis)
http_client = HTTPClient()

# FastAPI app
app = FastAPI(
    title="FamaGPT Specialist Service",
    description="Real Estate AI Agent Specialist",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    """Query request model"""
    user_id: str
    conversation_id: str
    message: str
    context: dict = {}


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
    logger.info("Specialist Service started successfully")


@app.on_event("shutdown") 
async def shutdown_event():
    """Shutdown event handler"""
    logger.info("Shutting down Specialist Service...")
    await redis_client.disconnect()
    await http_client.close()
    logger.info("Specialist Service shutdown complete")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    import datetime
    return HealthResponse(
        status="healthy",
        service="specialist",
        timestamp=datetime.datetime.utcnow().isoformat()
    )


@app.post("/process")
async def process_query(request: QueryRequest):
    """Process user query with AI specialist"""
    try:
        logger.info(f"Processing query for user {request.user_id}")
        
        # TODO: Implement AI specialist logic
        # This would integrate with:
        # - Memory service for context
        # - RAG service for knowledge
        # - Web search for property data
        
        # Placeholder response
        response = {
            "response": f"Como especialista em imóveis de Uberlândia, posso ajudar com: {request.message}",
            "suggestions": [
                "Buscar imóveis na região",
                "Informações sobre financiamento",
                "Análise de mercado"
            ],
            "context_updated": True
        }
        
        # Cache conversation state
        cache_key = f"specialist:{request.user_id}:{request.conversation_id}"
        await redis_client.set_json(cache_key, response, ttl=3600)
        
        return response
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail="Query processing failed")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8007,
        reload=True
    )
