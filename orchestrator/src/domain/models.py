"""
Orchestrator domain models.
"""
from typing import Dict, Any, List, Optional
from uuid import UUID
from enum import Enum

from shared.src.domain.base import Entity, ValueObject
from pydantic import Field
from shared.src.domain.models import AgentType, Priority


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeStatus(str, Enum):
    """Node execution status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowDefinition(ValueObject):
    """Workflow definition."""
    name: str
    description: str
    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    entry_point: str
    metadata: Dict[str, Any] = {}


class WorkflowExecution(Entity):
    """Workflow execution instance."""
    workflow_name: str
    conversation_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    status: WorkflowStatus = WorkflowStatus.PENDING
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    current_node: Optional[str] = None
    executed_nodes: List[str] = Field(default_factory=list)
    node_outputs: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    priority: Priority = Priority.NORMAL
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NodeExecution(Entity):
    """Node execution instance."""
    workflow_execution_id: UUID
    node_name: str
    agent_type: AgentType
    status: NodeStatus = NodeStatus.PENDING
    input_data: Dict[str, Any]
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    execution_time_ms: Optional[int] = None
    retry_count: int = 0
