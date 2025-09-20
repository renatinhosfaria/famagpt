"""
Orchestrator domain interfaces.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from uuid import UUID

from .models import WorkflowExecution, WorkflowDefinition, NodeExecution


class WorkflowRepository(ABC):
    """Repository for workflow executions."""
    
    @abstractmethod
    async def save_execution(self, execution: WorkflowExecution) -> None:
        """Save workflow execution."""
        pass
    
    @abstractmethod
    async def get_execution(self, execution_id: UUID) -> Optional[WorkflowExecution]:
        """Get workflow execution by ID."""
        pass
    
    @abstractmethod
    async def update_execution_status(
        self, 
        execution_id: UUID, 
        status: str,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update execution status."""
        pass
    
    @abstractmethod
    async def save_node_execution(self, node_execution: NodeExecution) -> None:
        """Save node execution."""
        pass


class AgentService(ABC):
    """Interface for communicating with agents."""
    
    @abstractmethod
    async def execute_task(
        self,
        agent_type: str,
        task_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute task on specific agent."""
        pass
    
    @abstractmethod
    async def health_check(self, agent_type: str) -> bool:
        """Check agent health."""
        pass


class WorkflowEngine(ABC):
    """Workflow execution engine."""
    
    @abstractmethod
    async def execute_workflow(
        self,
        workflow_name: str,
        input_data: Dict[str, Any],
        conversation_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None
    ) -> WorkflowExecution:
        """Execute workflow."""
        pass
    
    @abstractmethod
    async def get_workflow_definition(self, workflow_name: str) -> Optional[WorkflowDefinition]:
        """Get workflow definition."""
        pass
