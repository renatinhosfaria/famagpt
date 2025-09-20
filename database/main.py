"""
Database Service - PostgreSQL integration with Clean Architecture
Main application entry point
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import os
import time
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from uuid import UUID
import asyncpg
import datetime

from src.application.services import DatabaseService

# Shared modules
from shared.src.utils.config import get_settings
from shared.src.utils.logging import setup_logging, get_logger
from shared.src.infrastructure.database import DatabaseClient

# Configuration
settings = get_settings()
setup_logging(service_name=settings.service.name, log_level=settings.log_level)
logger = get_logger("database_service")

# Global variables
database_service: Optional[DatabaseService] = None
db_pool: Optional[asyncpg.Pool] = None
start_time = time.time()  # For uptime calculation


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    global database_service, db_pool
    
    logger.info("Starting Database Service...")
    
    try:
        # Create database connection pool
        db_client = DatabaseClient(settings.database)
        await db_client.connect()
        db_pool = db_client.pool
        
        # Initialize database service (pool-based minimal implementation)
        database_service = DatabaseService(db_pool=db_pool)
        
        logger.info("Database Service started successfully")
        
        yield
        
    except Exception as e:
        logger.error(f"Failed to start Database Service: {str(e)}")
        raise
    finally:
        # Cleanup
        logger.info("Shutting down Database Service...")
        if 'db_client' in locals() and db_client:
            await db_client.disconnect()
        logger.info("Database Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="FamaGPT Database Service",
    description="PostgreSQL database service with Clean Architecture",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
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


def get_database_service() -> DatabaseService:
    """Dependency to get database service"""
    if not database_service:
        raise HTTPException(status_code=503, detail="Database service not initialized")
    return database_service


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        status = "healthy" if db_pool and not db_pool._closed else "unhealthy"
        
        import time
        uptime_seconds = int(time.time() - start_time) if 'start_time' in globals() else 0
        
        return {
            "status": status,
            "service": "database",
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "uptime": uptime_seconds,  # TestSprite compatibility - required field
            "database": {
                "status": "active" if db_pool and not db_pool._closed else "inactive",  # TestSprite compatibility
                "pool_status": "active" if db_pool and not db_pool._closed else "inactive",
                "pool_size": len(db_pool._holders) if db_pool else 0
            }
        }
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        raise HTTPException(status_code=500, detail="Health check failed")


# Root endpoint
@app.post("/query")
async def execute_query(
    query_data: Dict[str, Any],
    db_service: DatabaseService = Depends(get_database_service)
):
    """
    Execute a generic database query.
    This is a compatibility endpoint for testing purposes.
    """
    try:
        # Simple query execution - for basic testing
        sql_query = query_data.get("sql", "SELECT 1 as test_query")
        
        # Execute via pool directly for basic queries
        async with db_pool.acquire() as connection:
            if sql_query.strip().upper().startswith("SELECT"):
                result = await connection.fetch(sql_query)
                return {"status": "success", "data": [dict(record) for record in result]}
            else:
                result = await connection.execute(sql_query)
                return {"status": "success", "affected_rows": result}
                
    except Exception as e:
        logger.error(f"Query execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "FamaGPT Database Service",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


# User endpoints
@app.post("/users")
async def create_user(
    user_data: Dict[str, Any],
    db_service: DatabaseService = Depends(get_database_service)
):
    """Create a new user"""
    try:
        user = await db_service.create_user(user_data)  # may not be implemented in minimal service
        return {"user": user}
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/phone/{phone}")
async def get_or_create_user_by_phone(
    phone: str,
    name: Optional[str] = None,
    push_name: Optional[str] = None,
    profile_pic_url: Optional[str] = None,
    db_service: DatabaseService = Depends(get_database_service)
):
    """Get or create user by phone number"""
    try:
        user = await db_service.get_or_create_user_by_phone(
            phone=phone,
            name=name,
            push_name=push_name,
            profile_pic_url=profile_pic_url
        )
        return {"user": user}
    except Exception as e:
        logger.error(f"Error getting/creating user: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Conversation endpoints
@app.get("/conversations")
async def get_conversations(
    user_id: UUID,
    status: str = "active",
    instance_id: Optional[str] = None,
    db_service: DatabaseService = Depends(get_database_service)
):
    """Get conversations for user"""
    try:
        conversation = await db_service.get_or_create_conversation(
            user_id=user_id,
            instance_id=instance_id or "default"
        )
        return {"conversations": [conversation] if conversation else []}
    except Exception as e:
        logger.error(f"Error getting conversations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/conversations")
async def create_conversation(
    user_id: UUID,
    instance_id: str,
    phone: Optional[str] = None,
    db_service: DatabaseService = Depends(get_database_service)
):
    """Get or create conversation"""
    try:
        conversation = await db_service.get_or_create_conversation(
            user_id=user_id,
            instance_id=instance_id,
            phone=phone
        )
        return {"conversation": conversation}
    except Exception as e:
        logger.error(f"Error creating conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations/{conversation_id}/messages")
async def get_conversation_history(
    conversation_id: UUID,
    limit: int = 50,
    db_service: DatabaseService = Depends(get_database_service)
):
    """Get conversation message history"""
    try:
        messages = await db_service.get_conversation_history(conversation_id, limit)
        return {"messages": messages}
    except Exception as e:
        logger.error(f"Error getting conversation history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Message endpoints
@app.post("/messages")
async def save_message(
    message_data: Dict[str, Any],
    db_service: DatabaseService = Depends(get_database_service)
):
    """Save a new message"""
    try:
        message = await db_service.save_message(message_data)
        return {"message": message}
    except Exception as e:
        logger.error(f"Error saving message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Property endpoints
@app.post("/properties")
async def save_property(
    property_data: Dict[str, Any],
    db_service: DatabaseService = Depends(get_database_service)
):
    """Save a property"""
    try:
        property_obj = await db_service.save_property(property_data)
        return {"property": property_obj.to_dict()}
    except Exception as e:
        logger.error(f"Error saving property: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/properties/search")
async def search_properties(
    search_criteria: Dict[str, Any],
    db_service: DatabaseService = Depends(get_database_service)
):
    """Search properties"""
    try:
        properties = await db_service.search_properties(search_criteria)
        return {"properties": [prop.to_dict() for prop in properties]}
    except Exception as e:
        logger.error(f"Error searching properties: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Memory endpoints
@app.post("/memories")
async def save_memory(
    memory_data: Dict[str, Any],
    db_service: DatabaseService = Depends(get_database_service)
):
    """Save a memory entry"""
    try:
        memory = await db_service.save_memory(memory_data)
        return {"memory": memory.to_dict()}
    except Exception as e:
        logger.error(f"Error saving memory: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/memories/user/{user_id}")
async def get_user_memories(
    user_id: UUID,
    content_type: Optional[str] = None,
    limit: int = 50,
    db_service: DatabaseService = Depends(get_database_service)
):
    """Get user memories"""
    try:
        memories = await db_service.get_user_memories(user_id, content_type, limit)
        return {"memories": [mem.to_dict() for mem in memories]}
    except Exception as e:
        logger.error(f"Error getting user memories: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Document endpoints
@app.post("/documents")
async def save_document(
    document_data: Dict[str, Any],
    db_service: DatabaseService = Depends(get_database_service)
):
    """Save a document"""
    try:
        document = await db_service.save_document(document_data)
        return {"document": document.to_dict()}
    except Exception as e:
        logger.error(f"Error saving document: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/documents/search")
async def search_documents(
    query_text: Optional[str] = None,
    query_embedding: Optional[List[float]] = None,
    tags: Optional[List[str]] = None,
    limit: int = 10,
    db_service: DatabaseService = Depends(get_database_service)
):
    """Search documents"""
    try:
        documents = await db_service.search_documents(
            query_text=query_text,
            query_embedding=query_embedding,
            tags=tags,
            limit=limit
        )
        return {"documents": [doc.to_dict() for doc in documents]}
    except Exception as e:
        logger.error(f"Error searching documents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8006,
        reload=True,
        log_level="info"
    )
