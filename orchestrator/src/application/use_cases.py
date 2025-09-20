"""
Workflow execution use cases.
"""
from typing import Dict, Any, Optional
from uuid import UUID

from shared.src.domain.base import UseCase
from shared.src.utils.logging import get_logger

from ..domain.interfaces import WorkflowEngine, WorkflowRepository
from ..domain.models import WorkflowExecution


logger = get_logger(__name__)


class ExecuteWorkflowUseCase(UseCase):
    """Use case for executing workflows."""
    
    def __init__(
        self,
        workflow_engine: WorkflowEngine,
        workflow_repository: WorkflowRepository
    ):
        self.workflow_engine = workflow_engine
        self.workflow_repository = workflow_repository
    
    async def execute(
        self,
        workflow_name: str,
        input_data: Dict[str, Any],
        conversation_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None
    ) -> WorkflowExecution:
        """Execute workflow."""
        
        logger.info(
            "Executing workflow",
            workflow_name=workflow_name,
            conversation_id=conversation_id,
            user_id=user_id
        )
        
        try:
            # Execute workflow
            execution = await self.workflow_engine.execute_workflow(
                workflow_name=workflow_name,
                input_data=input_data,
                conversation_id=conversation_id,
                user_id=user_id
            )
            
            # Save execution
            await self.workflow_repository.save_execution(execution)
            
            logger.info(
                "Workflow executed successfully",
                execution_id=execution.id,
                workflow_name=workflow_name,
                status=execution.status
            )
            
            return execution
            
        except Exception as e:
            logger.error(
                "Workflow execution failed",
                workflow_name=workflow_name,
                error=str(e),
                conversation_id=conversation_id,
                user_id=user_id
            )
            raise


class GetWorkflowStatusUseCase(UseCase):
    """Use case for getting workflow status."""
    
    def __init__(self, workflow_repository: WorkflowRepository):
        self.workflow_repository = workflow_repository
    
    async def execute(self, execution_id: UUID) -> Optional[WorkflowExecution]:
        """Get workflow execution status."""
        
        logger.info("Getting workflow status", execution_id=execution_id)
        
        execution = await self.workflow_repository.get_execution(execution_id)
        
        if not execution:
            logger.warning("Workflow execution not found", execution_id=execution_id)
        
        return execution
