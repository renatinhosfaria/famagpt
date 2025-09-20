"""
Orchestrator FastAPI application.
"""
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi.middleware.gzip import GZipMiddleware

from shared.src.utils.config import get_settings
from shared.src.utils.logging import setup_logging, get_logger
from shared.src.infrastructure.http_client import ServiceClient
from shared.src.infrastructure.redis_client import RedisClient

from ..application.use_cases import ExecuteWorkflowUseCase, GetWorkflowStatusUseCase
from ..application.services import OrchestrationService
from ..infrastructure.langgraph_engine import LangGraphWorkflowEngine
from ..infrastructure.repositories import InMemoryWorkflowRepository
from ..infrastructure.agent_service import HTTPAgentService, LocalAgentService
from ..infrastructure.memory_service import MemoryServiceClient
from .routes import router
from . import routes


logger = get_logger(__name__)


# Global application state
app_state = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    
    settings = get_settings()
    
    # Setup logging
    setup_logging(
        service_name=settings.service.name,
        log_level=settings.log_level
    )
    
    logger.info("Starting Orchestrator service", port=settings.service.port)
    
    try:
        # Initialize database service client
        database_client = ServiceClient("orchestrator", settings.service.database_url)
        app_state["database_client"] = database_client
        
        # Initialize Redis
        redis_client = RedisClient(settings.redis)
        await redis_client.connect()
        app_state["redis_client"] = redis_client
        
        # Use in-memory repository since database service handles persistence
        workflow_repository = InMemoryWorkflowRepository()
        app_state["workflow_repository"] = workflow_repository
        
        # Initialize agent service
        if settings.environment == "development":
            agent_service = LocalAgentService()
        else:
            agent_service = HTTPAgentService(settings.service, redis_client)
            await agent_service.start()
        app_state["agent_service"] = agent_service
        
        # Initialize memory service client
        memory_client = MemoryServiceClient()
        app_state["memory_client"] = memory_client
        
        # Initialize workflow engine
        workflow_engine = LangGraphWorkflowEngine(agent_service, memory_client)
        app_state["workflow_engine"] = workflow_engine
        
        # Initialize use cases
        execute_workflow_use_case = ExecuteWorkflowUseCase(
            workflow_engine, workflow_repository
        )
        get_workflow_status_use_case = GetWorkflowStatusUseCase(workflow_repository)
        app_state["execute_workflow_use_case"] = execute_workflow_use_case
        app_state["get_workflow_status_use_case"] = get_workflow_status_use_case
        
        # Initialize orchestration service
        orchestration_service = OrchestrationService(agent_service, memory_client)
        app_state["orchestration_service"] = orchestration_service
        
        # Inject dependencies into routes module
        routes.orchestration_service = orchestration_service
        routes.execute_workflow_use_case = execute_workflow_use_case
        routes.get_workflow_status_use_case = get_workflow_status_use_case
        routes.agent_service = agent_service
        routes.memory_client = memory_client
        
        logger.info("Orchestrator service started successfully")
        
        yield
        
    finally:
        # Cleanup
        logger.info("Shutting down Orchestrator service")
        
        if "agent_service" in app_state:
            if hasattr(app_state["agent_service"], "stop"):
                await app_state["agent_service"].stop()
        
        if "redis_client" in app_state:
            await app_state["redis_client"].disconnect()
        
        if "database_client" in app_state:
            await app_state["database_client"].close()
        
        logger.info("Orchestrator service stopped")


def create_app() -> FastAPI:
    """Create FastAPI application."""
    
    app = FastAPI(
        title="FamaGPT Orchestrator Service",
        description="LangGraph-based workflow orchestration service",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Add CORS middleware with env-based configuration
    origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
    allow_origins = ["*"] if origins_env.strip() == "*" else [o.strip() for o in origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Add root health endpoint BEFORE routes for priority
    @app.get("/health")
    async def health_check_root():
        """Root health check endpoint for backward compatibility"""
        return {
            "status": "healthy",
            "service": "orchestrator",
            "version": "1.0.0"
        }
    
    # Add routes
    app.include_router(router, prefix="/api/v1")
    
    return app


# Create application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "main:app",
        host=settings.service.host,
        port=settings.service.port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
