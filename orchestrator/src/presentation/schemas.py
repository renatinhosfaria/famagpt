"""
Orchestrator API schemas.
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
from pydantic import BaseModel, Field

from shared.src.domain.models import Priority


class ExecuteWorkflowRequest(BaseModel):
    """Request to execute a workflow."""
    workflow_name: str = Field(..., description="Name of the workflow to execute")
    input_data: Dict[str, Any] = Field(..., description="Input data for the workflow")
    conversation_id: Optional[UUID] = Field(None, description="Associated conversation ID")
    user_id: Optional[UUID] = Field(None, description="User ID")
    priority: Priority = Field(Priority.NORMAL, description="Execution priority")


class ExecuteWorkflowResponse(BaseModel):
    """Response from workflow execution."""
    execution_id: UUID = Field(..., description="Workflow execution ID")
    workflow_name: str = Field(..., description="Name of the executed workflow")
    status: str = Field(..., description="Current execution status")
    output_data: Optional[Dict[str, Any]] = Field(None, description="Workflow output data")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class ProcessMessageRequest(BaseModel):
    """Request to process a message."""
    message_content: str = Field(..., description="Message content")
    user_id: UUID = Field(..., description="User ID")
    conversation_id: UUID = Field(..., description="Conversation ID")
    message_type: str = Field("text", description="Message type (text, audio, image)")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ProcessMessageResponse(BaseModel):
    """Response from message processing."""
    workflow_name: str = Field(..., description="Selected workflow")
    execution_id: UUID = Field(..., description="Workflow execution ID")
    intent: Dict[str, Any] = Field(..., description="Detected intent")
    response: Optional[str] = Field(None, description="Generated response")
    status: str = Field(..., description="Processing status")
    sources: Optional[List[Dict[str, Any]]] = Field(default=None, description="Sources or evidence used in the response")


class WorkflowStatusResponse(BaseModel):
    """Workflow execution status response."""
    execution_id: UUID = Field(..., description="Workflow execution ID")
    workflow_name: str = Field(..., description="Workflow name")
    status: str = Field(..., description="Current status")
    current_node: Optional[str] = Field(None, description="Current node being executed")
    executed_nodes: List[str] = Field(default_factory=list, description="Completed nodes")
    output_data: Optional[Dict[str, Any]] = Field(None, description="Output data")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    progress_percentage: float = Field(..., description="Execution progress (0-100)")


class HealthCheckResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Service version")
    uptime_seconds: int = Field(..., description="Service uptime")
    agents_health: Dict[str, bool] = Field(..., description="Health status of connected agents")


class WorkflowListResponse(BaseModel):
    """Available workflows response."""
    workflows: List[str] = Field(..., description="List of available workflow names")


class AgentHealthResponse(BaseModel):
    """Agent health status response."""
    agent_type: str = Field(..., description="Agent type")
    healthy: bool = Field(..., description="Health status")
    last_check: float = Field(..., description="Last health check timestamp (epoch seconds)")


class ErrorResponse(BaseModel):
    """Error response."""
    error: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")
