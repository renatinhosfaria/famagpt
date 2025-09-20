"""
RAG Service Main Application - Clean Architecture Implementation
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os

from shared.src.utils.logging import get_logger
from shared.src.utils.config import get_settings
from shared.src.infrastructure.redis_client import RedisClient

# RAG Domain and Infrastructure
from src.infrastructure.services.text_processor import TextProcessor
from src.infrastructure.services.openai_embedding_service import OpenAIEmbeddingService
from src.infrastructure.services.pgvector_store import PGVectorStore
from src.infrastructure.services.openai_generation_service import OpenAIGenerationService
from src.infrastructure.services.redis_rag_cache import RedisRAGCache

# RAG Application Layer
from src.application.use_cases.rag_pipeline import RAGPipelineUseCase
from src.application.services.rag_service import RAGService

# RAG Infrastructure - Database Client
from src.infrastructure.services.database_client import DatabaseClient

# RAG Presentation Layer
from src.presentation.api.rag_controller import create_rag_router


logger = get_logger("rag.main")
settings = get_settings()

# Global services
rag_service: RAGService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global rag_service
    
    try:
        logger.info("Starting RAG service...")
        
        # Initialize Redis client
        redis_client = RedisClient(settings.redis)
        await redis_client.connect()
        logger.info("Redis client initialized")
        
        # Initialize RAG cache
        cache_service = RedisRAGCache(redis_client)
        logger.info("RAG cache service initialized")
        
        # Initialize services with Clean Architecture dependency injection
        document_processor = TextProcessor()
        embedding_service = OpenAIEmbeddingService(cache_service=cache_service)
        vector_store = PGVectorStore()
        generation_service = OpenAIGenerationService()
        
        # Initialize vector store (creates tables if needed)
        await vector_store.initialize()
        logger.info("Vector store initialized")
        
        # Initialize Database client (optional - for central database integration)
        database_client = None
        try:
            database_service_url = f"http://database:{settings.services.get('database_port', 8006)}"
            database_client = DatabaseClient(database_service_url)
            await database_client.__aenter__()
            logger.info("Database client initialized")
        except Exception as e:
            logger.warning(f"Database client initialization failed (continuing without): {str(e)}")
        
        # Initialize RAG pipeline
        rag_pipeline = RAGPipelineUseCase(
            document_processor=document_processor,
            embedding_service=embedding_service,
            vector_store=vector_store,
            generation_service=generation_service,
            cache_service=cache_service
        )
        
        # Initialize application service
        rag_service = RAGService(rag_pipeline, database_client)
        logger.info("RAG service initialized successfully")
        
        # Test system health
        health = await rag_service.health_check()
        if health["status"] == "healthy":
            logger.info("RAG service health check passed")
        else:
            logger.warning(f"RAG service health check failed: {health}")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to initialize RAG service: {str(e)}")
        raise
    finally:
        # Cleanup
        logger.info("Shutting down RAG service...")
        try:
            if vector_store:
                await vector_store.cleanup()
            if redis_client:
                await redis_client.disconnect()
            if database_client:
                await database_client.__aexit__(None, None, None)
            logger.info("RAG service cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")


# Create FastAPI app
app = FastAPI(
    title="RAG Service",
    description="Retrieval-Augmented Generation service for FamaGPT",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allow_origins = ["*"] if origins_env.strip() == "*" else [o.strip() for o in origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,  # Configure via env ALLOWED_ORIGINS
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_rag_service_dependency() -> RAGService:
    """Dependency to get RAG service instance"""
    if rag_service is None:
        raise RuntimeError("RAG service not initialized")
    return rag_service

# Create and include router with dependency injection
rag_router = create_rag_router(get_rag_service_dependency)
app.include_router(rag_router)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "rag",
        "version": "1.0.0",
        "description": "Retrieval-Augmented Generation service for FamaGPT",
        "status": "operational",
        "endpoints": {
            "ingest": "POST /api/v1/rag/ingest",
            "query": "POST /api/v1/rag/query", 
            "search": "POST /api/v1/rag/search",
            "delete": "DELETE /api/v1/rag/documents/{document_id}",
            "stats": "GET /api/v1/rag/stats",
            "health": "GET /api/v1/rag/health"
        }
    }


@app.post("/query")
async def query_rag_root(request: dict):
    """
    Root query endpoint for backward compatibility.
    Alias for /api/v1/rag/query endpoint.
    """
    from src.presentation.api.rag_controller import RAGQueryDTO
    
    try:
        # Convert dict to DTO
        query_dto = RAGQueryDTO(**request)
        
        if rag_service is None:
            raise HTTPException(status_code=503, detail="RAG service not initialized")
        
        # Process query
        response = await rag_service.query_rag(
            query=query_dto.query,
            top_k=query_dto.top_k,
            min_similarity=query_dto.min_similarity,
            filters=query_dto.filters,
            use_cache=query_dto.use_cache,
            system_prompt=query_dto.system_prompt,
            temperature=query_dto.temperature
        )
        
        # Convert to simple dict format
        sources = []
        for chunk_result in response.retrieved_chunks:
            sources.append({
                "content": chunk_result.content,
                "similarity": chunk_result.similarity_score,
                "metadata": chunk_result.metadata
            })
        
        return {
            "answer": response.generated_text,
            "sources": sources,
            "query": query_dto.query
        }
        
    except Exception as e:
        logger.error(f"Query error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    """Simple health check endpoint"""
    try:
        if rag_service:
            return await rag_service.health_check()
        else:
            return {
                "service": "rag",
                "status": "starting",
                "message": "Service is still initializing"
            }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "service": "rag",
            "status": "unhealthy",
            "error": str(e)
        }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8005,
        reload=True
    )
