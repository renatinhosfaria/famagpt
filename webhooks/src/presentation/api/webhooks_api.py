"""
FastAPI routes for webhooks service
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, Header, Response
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import datetime
import asyncio

from ...application.services import WebhookService
from ...infrastructure import (
    EvolutionWebhookParser,
    EvolutionMessageSender,
    OrchestratorClient,
    DatabaseClient
)

# Shared modules
from shared.src.infrastructure.redis_client import RedisClient
from shared.src.utils.config import get_settings
from shared.src.utils.logging import get_logger, setup_logging

# Observabilidade
from shared.monitoring.metrics import (
    metrics_endpoint, track_duration, track_message_processing,
    set_service_info, set_active_conversations, track_webhook_event
)
from shared.logging.structured_logger import (
    get_logger as get_structured_logger, CorrelationMiddleware,
    extract_context_from_webhook_data
)
from shared.health.health_check import HealthChecker, simple_health_check, liveness_check
from shared.middleware.backpressure import (
    BackpressureMiddleware, RateLimitMiddleware, AdaptiveThrottlingMiddleware
)
from .admin.dlq_endpoints import router as dlq_router


# Pydantic models
class WebhookPayload(BaseModel):
    """Webhook payload from Evolution API"""
    instance: str = Field(..., description="WhatsApp instance ID")
    data: Dict[str, Any] = Field(..., description="Webhook data")


class SendMessageRequest(BaseModel):
    """Request to send message via WhatsApp"""
    instance_id: str = Field(..., description="WhatsApp instance ID")
    phone_number: str = Field(..., description="Target phone number")
    content: str = Field(..., description="Message content")
    reply_to: Optional[str] = Field(None, description="Message ID to reply to")


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    timestamp: str
    dependencies: Dict[str, str]


def create_webhooks_app() -> FastAPI:
    """Create and configure FastAPI app for webhooks service"""
    
    # Configuration
    settings = get_settings()
    setup_logging(service_name=settings.service.name, log_level=settings.log_level)
    logger = get_logger("webhooks_api")
    struct_logger = get_structured_logger("webhooks_api")
    
    # Initialize health checker
    health_checker = HealthChecker("webhooks")
    service_start_time = datetime.datetime.utcnow()
    
    # Initialize dependencies
    redis_client = RedisClient(settings.redis)
    
    # Create app
    app = FastAPI(
        title="FamaGPT Webhooks Service",
        description="WhatsApp Evolution API webhook handler with Clean Architecture",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Add resilience middleware (order matters!)
    app.add_middleware(
        BackpressureMiddleware,
        redis_url=settings.redis.url if settings.redis.url else "redis://localhost:6379",
        queue_threshold=int(os.getenv("QUEUE_THRESHOLD", "1000")),
        pending_threshold=int(os.getenv("PENDING_THRESHOLD", "500"))
    )
    
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=settings.redis.url if settings.redis.url else "redis://localhost:6379",
        requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "120")),
        burst_size=int(os.getenv("RATE_LIMIT_BURST", "20"))
    )
    
    app.add_middleware(
        AdaptiveThrottlingMiddleware,
        redis_url=settings.redis.url if settings.redis.url else "redis://localhost:6379",
        base_delay_ms=int(os.getenv("BASE_THROTTLE_DELAY_MS", "0")),
        max_delay_ms=int(os.getenv("MAX_THROTTLE_DELAY_MS", "1000"))
    )
    
    # Add observability middleware
    app.add_middleware(CorrelationMiddleware)
    
    # CORS middleware (should be last)
    origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
    allow_origins = ["*"] if origins_env.strip() == "*" else [o.strip() for o in origins_env.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Initialize services (will be done in startup)
    webhook_service: Optional[WebhookService] = None
    database_client: Optional[DatabaseClient] = None
    
    @app.on_event("startup")
    async def startup_event():
        """Initialize services on startup"""
        nonlocal webhook_service, database_client
        
        struct_logger.info("Starting Webhooks Service...")
        
        # Set service info for metrics
        set_service_info(
            name="webhooks",
            version="1.0.0", 
            environment=os.getenv("ENVIRONMENT", "production")
        )
        
        try:
            # Connect to Redis
            await redis_client.connect()
            
            # Initialize infrastructure components
            parser = EvolutionWebhookParser()
            sender = EvolutionMessageSender(settings)
            orchestrator_client = OrchestratorClient(settings)
            database_client = DatabaseClient(settings.service.database_url)
            
            # Start database client
            await database_client.__aenter__()
            
            # Initialize webhook service
            webhook_service = WebhookService(
                parser=parser,
                sender=sender,
                orchestrator=orchestrator_client,
                database=database_client,
                redis_client=redis_client
            )
            
            struct_logger.info("Webhooks Service started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start Webhooks Service: {str(e)}")
            raise
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """Cleanup on shutdown"""
        logger.info("Shutting down Webhooks Service...")
        
        try:
            if redis_client:
                await redis_client.disconnect()
            if database_client:
                await database_client.__aexit__(None, None, None)
            logger.info("Webhooks Service shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")
    
    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        """Health check endpoint"""
        try:
            # Check Redis connection
            try:
                if redis_client and redis_client.client:
                    await redis_client.client.ping()
                    redis_status = "healthy"
                else:
                    redis_status = "unhealthy"
            except Exception:
                redis_status = "unhealthy"
            
            # Check orchestrator if webhook_service is available
            orchestrator_status = "unknown"
            if webhook_service and webhook_service.orchestrator:
                try:
                    orchestrator_health = await webhook_service.orchestrator.get_orchestrator_health()
                    orchestrator_status = orchestrator_health.get("status", "unknown")
                    logger.info(f"Orchestrator health check result: {orchestrator_health}")
                except Exception as e:
                    logger.error(f"Failed to check orchestrator health: {str(e)}")
                    orchestrator_status = "unhealthy"
            else:
                logger.warning("webhook_service or orchestrator not available for health check")
            
            # Check database
            database_status = "unknown"
            if database_client:
                try:
                    await database_client.client.get("/health")
                    database_status = "healthy"
                except Exception:
                    database_status = "unhealthy"
            
            return HealthResponse(
                status="healthy",
                service="webhooks",
                timestamp=datetime.datetime.utcnow().isoformat(),
                dependencies={
                    "redis": redis_status,
                    "orchestrator": orchestrator_status,
                    "database": database_status,
                    "whatsapp_integration": "healthy"
                }
            )
        except Exception as e:
            logger.error(f"Health check error: {str(e)}")
            raise HTTPException(status_code=500, detail="Health check failed")
    
    @app.post("/webhook/evolution")
    @track_duration(service="webhooks", operation="process_webhook")
    async def receive_evolution_webhook(
        payload: WebhookPayload,
        background_tasks: BackgroundTasks,
        request: Request,
        x_webhook_signature: Optional[str] = Header(None, alias="x-webhook-signature")
    ):
        """
        Receive webhook from Evolution API
        
        This endpoint receives webhooks from Evolution API and processes them
        asynchronously in the background.
        """
        try:
            if not webhook_service:
                raise HTTPException(
                    status_code=503, 
                    detail="Webhook service not initialized"
                )
            
            # Extract correlation context from webhook data
            context = extract_context_from_webhook_data(payload.data)
            ctx_logger = struct_logger.with_context(**context)
            
            # Get message type for metrics
            message_type = payload.data.get("messageType", "unknown")
            event_type = payload.data.get("event", "message")
            
            ctx_logger.info(
                "Received webhook from Evolution API",
                instance_id=payload.instance,
                event_type=event_type,
                message_type=message_type
            )
            
            # Track webhook event
            track_webhook_event(payload.instance, event_type, "received")
            
            # Validate webhook signature if configured
            if settings.whatsapp.webhook_secret and x_webhook_signature:
                raw_body = await request.body()
                parser = EvolutionWebhookParser()
                
                if not parser.validate_webhook_signature(
                    raw_body.decode(),
                    x_webhook_signature,
                    settings.whatsapp.webhook_secret
                ):
                    ctx_logger.warning("Invalid webhook signature")
                    track_webhook_event(payload.instance, event_type, "signature_invalid")
                    raise HTTPException(status_code=401, detail="Invalid signature")
            
            # Process webhook in background with instrumented task
            async def instrumented_webhook_processing():
                """Process webhook with metrics tracking"""
                try:
                    result = await webhook_service.process_incoming_webhook(payload.dict())
                    
                    # Track success
                    status = result.get("status", "unknown")
                    track_message_processing("webhooks", status, message_type)
                    track_webhook_event(payload.instance, event_type, status)
                    
                    ctx_logger.info(
                        "Webhook processing completed",
                        status=status,
                        processing_result=result
                    )
                    
                except Exception as e:
                    # Track error
                    track_message_processing("webhooks", "error", message_type)
                    track_webhook_event(payload.instance, event_type, "error")
                    
                    ctx_logger.error(
                        "Webhook processing failed",
                        error=str(e),
                        exc_info=True
                    )
                    raise
            
            background_tasks.add_task(instrumented_webhook_processing)
            
            # Update active conversations count (approximate)
            try:
                # This could be improved with actual count from database
                set_active_conversations("webhooks", 100)  # Placeholder
            except Exception:
                pass  # Don't fail if metrics update fails
            
            track_webhook_event(payload.instance, event_type, "accepted")
            
            return {"status": "received", "message": "Webhook processing started"}
            
        except HTTPException:
            raise
        except Exception as e:
            struct_logger.error(f"Error receiving webhook: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Internal server error")
    
    @app.post("/send-message")
    async def send_message(request: SendMessageRequest):
        """
        Send message via WhatsApp
        
        This endpoint allows sending messages via WhatsApp Evolution API.
        """
        try:
            if not webhook_service:
                raise HTTPException(
                    status_code=503,
                    detail="Webhook service not initialized"
                )
            
            result = await webhook_service.send_response_message(
                instance_id=request.instance_id,
                phone_number=request.phone_number,
                content=request.content,
                reply_to=request.reply_to
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/message/{instance_id}/{message_id}")
    async def get_cached_message(instance_id: str, message_id: str):
        """Get cached message by ID"""
        try:
            if not webhook_service:
                raise HTTPException(
                    status_code=503,
                    detail="Webhook service not initialized"
                )
            
            message = await webhook_service.get_cached_message(instance_id, message_id)
            
            if not message:
                raise HTTPException(status_code=404, detail="Message not found")
            
            return {"message": message}
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving message: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Observabilidade endpoints
    @app.get("/metrics")
    async def get_metrics():
        """Endpoint de métricas Prometheus"""
        return await metrics_endpoint()
    
    @app.get("/health/ready")
    async def readiness_check(response: Response):
        """Verificação completa de prontidão"""
        dependencies = {
            "redis_url": settings.redis.url if settings.redis.url else "",
            "database_url": settings.service.database_url,
            "orchestrator": {
                "url": settings.service.orchestrator_url,
                "timeout": 5
            }
        }
        
        result = await health_checker.run_all_checks(dependencies)
        
        # Set appropriate status code
        if result["status"] == "unhealthy":
            response.status_code = 503
        elif result["status"] == "degraded":
            response.status_code = 200  # Still ready but degraded
        
        return result
    
    @app.get("/health/live")
    async def liveness_check_endpoint():
        """Verificação simples de vida"""
        return await liveness_check("webhooks", service_start_time)
    
    @app.post("/webhook")
    @track_duration(service="webhooks", operation="process_webhook_alias")
    async def receive_webhook_alias(
        payload: WebhookPayload,
        background_tasks: BackgroundTasks,
        request: Request,
        x_webhook_signature: Optional[str] = Header(None, alias="x-webhook-signature")
    ):
        """
        Alias for /webhook/evolution endpoint for backward compatibility.
        This endpoint provides the same functionality as /webhook/evolution.
        """
        return await receive_evolution_webhook(payload, background_tasks, request, x_webhook_signature)

    @app.get("/")
    async def root():
        """Root endpoint"""
        return {
            "service": "FamaGPT Webhooks Service",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs"
        }
    
    # Include admin routes
    app.include_router(dlq_router)
    
    return app


# Create the app instance
app = create_webhooks_app()
