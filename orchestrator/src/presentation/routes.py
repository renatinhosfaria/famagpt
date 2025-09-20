"""
Orchestrator API routes.
"""
import time
from typing import Dict, Any
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse

from shared.src.utils.logging import get_logger, get_logger_adapter
from shared.src.utils.helpers import generate_correlation_id
from shared.src.domain.exceptions import NotFoundError, ValidationError

from ..application.use_cases import ExecuteWorkflowUseCase, GetWorkflowStatusUseCase
from ..application.services import OrchestrationService
from ..infrastructure.agent_service import HTTPAgentService
from ..domain.interfaces import AgentService
from .schemas import (
    ExecuteWorkflowRequest,
    ExecuteWorkflowResponse,
    ProcessMessageRequest,
    ProcessMessageResponse,
    WorkflowStatusResponse,
    HealthCheckResponse,
    AgentHealthResponse,
    ErrorResponse
)


logger = get_logger(__name__)
router = APIRouter()


# Dependency injection placeholders - will be set up in main.py
orchestration_service: OrchestrationService = None
execute_workflow_use_case: ExecuteWorkflowUseCase = None
get_workflow_status_use_case: GetWorkflowStatusUseCase = None
agent_service: AgentService = None


def get_correlation_id() -> str:
    """Generate correlation ID for request tracing."""
    return generate_correlation_id()


@router.post("/execute", response_model=ExecuteWorkflowResponse)
async def execute_workflow(
    request: ExecuteWorkflowRequest,
    background_tasks: BackgroundTasks,
    correlation_id: str = Depends(get_correlation_id)
):
    """Execute a workflow."""
    
    request_logger = get_logger_adapter(
        logger, 
        correlation_id=correlation_id,
        user_id=request.user_id,
        conversation_id=request.conversation_id
    )
    
    request_logger.info(
        "Executing workflow",
        workflow_name=request.workflow_name,
        input_data_keys=list(request.input_data.keys())
    )
    
    try:
        # Execute workflow
        execution = await execute_workflow_use_case.execute(
            workflow_name=request.workflow_name,
            input_data=request.input_data,
            conversation_id=request.conversation_id,
            user_id=request.user_id
        )
        
        response = ExecuteWorkflowResponse(
            execution_id=execution.id,
            workflow_name=execution.workflow_name,
            status=execution.status.value,
            output_data=execution.output_data,
            error_message=execution.error_message
        )
        
        request_logger.info(
            "Workflow executed successfully",
            execution_id=execution.id,
            status=execution.status.value
        )
        
        return response
        
    except ValidationError as e:
        request_logger.warning("Validation error", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        request_logger.error("Workflow execution failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/process-message", response_model=ProcessMessageResponse)
async def process_message(
    request: ProcessMessageRequest,
    correlation_id: str = Depends(get_correlation_id)
):
    """Process incoming message and execute appropriate workflow."""
    
    request_logger = get_logger_adapter(
        logger,
        correlation_id=correlation_id,
        user_id=request.user_id,
        conversation_id=request.conversation_id
    )
    
    request_logger.info(
        "Processing message",
        message_type=request.message_type,
        content_length=len(request.message_content)
    )
    
    try:
        # Process message and determine workflow
        processing_result = await orchestration_service.process_message(
            message_content=request.message_content,
            user_id=request.user_id,
            conversation_id=request.conversation_id,
            message_type=request.message_type
        )
        
        # Execute the determined workflow
        execution = await execute_workflow_use_case.execute(
            workflow_name=processing_result["workflow_name"],
            input_data=processing_result["workflow_input"],
            conversation_id=request.conversation_id,
            user_id=request.user_id
        )
        
        # Extract response and sources from workflow output
        response_text = None
        sources = None
        if execution.output_data:
            response_text = (
                execution.output_data.get("formatted_response") or
                execution.output_data.get("greeting") or
                execution.output_data.get("answer") or
                execution.output_data.get("response")
            )
            # Pass through RAG/web_search sources if available
            if isinstance(execution.output_data, dict):
                sources = execution.output_data.get("sources")
        
        response = ProcessMessageResponse(
            workflow_name=execution.workflow_name,
            execution_id=execution.id,
            intent=processing_result["intent"],
            response=response_text,
            status=execution.status.value,
            sources=sources
        )
        
        request_logger.info(
            "Message processed successfully",
            workflow_name=execution.workflow_name,
            execution_id=execution.id,
            intent=processing_result["intent"]["intent"]
        )
        
        return response
        
    except Exception as e:
        request_logger.error("Message processing failed", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/status/{execution_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(
    execution_id: UUID,
    correlation_id: str = Depends(get_correlation_id)
):
    """Get workflow execution status."""
    
    request_logger = get_logger_adapter(logger, correlation_id=correlation_id)
    request_logger.info("Getting workflow status", execution_id=execution_id)
    
    try:
        execution = await get_workflow_status_use_case.execute(execution_id)
        
        if not execution:
            raise HTTPException(status_code=404, detail="Workflow execution not found")
        
        # Calculate progress percentage
        total_nodes = len(execution.executed_nodes) + 1  # +1 for current node
        completed_nodes = len(execution.executed_nodes)
        progress = (completed_nodes / total_nodes) * 100 if total_nodes > 0 else 0
        
        response = WorkflowStatusResponse(
            execution_id=execution.id,
            workflow_name=execution.workflow_name,
            status=execution.status.value,
            current_node=execution.current_node,
            executed_nodes=execution.executed_nodes,
            output_data=execution.output_data,
            error_message=execution.error_message,
            progress_percentage=progress
        )
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        request_logger.error("Failed to get workflow status", execution_id=execution_id, error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


# Health check endpoint moved to main.py root level
# @router.get("/health") - removed to avoid duplication

@router.get("/ping")
async def ping():
    """Simple ping endpoint for testing."""
    return {"status": "pong"}


@router.get("/agents/health", response_model=Dict[str, AgentHealthResponse])
async def get_agents_health():
    """Get detailed health status of all agents."""
    
    try:
        agents_health = await agent_service.health_check_all()
        
        response = {}
        for agent_type, healthy in agents_health.items():
            response[agent_type] = AgentHealthResponse(
                agent_type=agent_type,
                healthy=healthy,
                last_check=time.time()
            )
        
        return response
        
    except Exception as e:
        logger.error("Failed to get agents health", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/workflows")
async def list_workflows():
    """List available workflows."""
    
    # This would be dynamically generated from the workflow engine
    workflows = [
        "audio_processing_workflow",
        "property_search_workflow", 
        "greeting_workflow",
        "question_answering_workflow",
        "general_conversation_workflow"
    ]
    
    return {"workflows": workflows}


# Exception handlers should be defined in main.py app, not router
# @router.exception_handler(ValidationError)
async def validation_error_handler(request, exc: ValidationError):
    """Handle validation errors."""
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error=exc.message,
            code=exc.code,
            details={"type": "validation_error"}
        ).dict()
    )


# @router.exception_handler(NotFoundError)
async def not_found_error_handler(request, exc: NotFoundError):
    """Handle not found errors."""
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(
            error=exc.message,
            code=exc.code,
            details={"type": "not_found_error"}
        ).dict()
    )


# Global variable to track service start time
start_time = time.time()
