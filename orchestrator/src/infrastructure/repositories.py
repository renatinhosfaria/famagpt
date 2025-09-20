"""
Orchestrator infrastructure repositories.
"""
from typing import Dict, Any, List, Optional
from uuid import UUID
import json

from shared.src.infrastructure.database import DatabaseClient
from shared.src.utils.logging import get_logger

from ..domain.interfaces import WorkflowRepository
from ..domain.models import WorkflowExecution, NodeExecution, WorkflowStatus, NodeStatus


logger = get_logger(__name__)


class PostgreSQLWorkflowRepository(WorkflowRepository):
    """PostgreSQL implementation of workflow repository."""
    
    def __init__(self, db_client: DatabaseClient):
        self.db = db_client
    
    async def save_execution(self, execution: WorkflowExecution) -> None:
        """Save workflow execution."""
        
        query = """
        INSERT INTO workflow_executions 
        (id, workflow_name, conversation_id, user_id, status, input_data, 
         output_data, current_node, executed_nodes, node_outputs, 
         error_message, priority, metadata, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        ON CONFLICT (id) DO UPDATE SET
            status = EXCLUDED.status,
            output_data = EXCLUDED.output_data,
            current_node = EXCLUDED.current_node,
            executed_nodes = EXCLUDED.executed_nodes,
            node_outputs = EXCLUDED.node_outputs,
            error_message = EXCLUDED.error_message,
            updated_at = EXCLUDED.updated_at
        """
        
        try:
            await self.db.execute(
                query,
                execution.id,
                execution.workflow_name,
                execution.conversation_id,
                execution.user_id,
                execution.status.value,
                json.dumps(execution.input_data, default=str),
                json.dumps(execution.output_data, default=str) if execution.output_data else None,
                execution.current_node,
                json.dumps(execution.executed_nodes),
                json.dumps(execution.node_outputs, default=str),
                execution.error_message,
                execution.priority.value,
                json.dumps(execution.metadata, default=str),
                execution.created_at,
                execution.updated_at
            )
            
            logger.info("Workflow execution saved", execution_id=execution.id)
            
        except Exception as e:
            logger.error("Failed to save workflow execution", execution_id=execution.id, error=str(e))
            raise
    
    async def get_execution(self, execution_id: UUID) -> Optional[WorkflowExecution]:
        """Get workflow execution by ID."""
        
        query = """
        SELECT id, workflow_name, conversation_id, user_id, status, input_data,
               output_data, current_node, executed_nodes, node_outputs,
               error_message, priority, metadata, created_at, updated_at
        FROM workflow_executions 
        WHERE id = $1
        """
        
        try:
            row = await self.db.fetch_one(query, execution_id)
            
            if not row:
                return None
            
            return WorkflowExecution(
                id=row['id'],
                workflow_name=row['workflow_name'],
                conversation_id=row['conversation_id'],
                user_id=row['user_id'],
                status=WorkflowStatus(row['status']),
                input_data=json.loads(row['input_data']) if row['input_data'] else {},
                output_data=json.loads(row['output_data']) if row['output_data'] else None,
                current_node=row['current_node'],
                executed_nodes=json.loads(row['executed_nodes']) if row['executed_nodes'] else [],
                node_outputs=json.loads(row['node_outputs']) if row['node_outputs'] else {},
                error_message=row['error_message'],
                priority=row['priority'],
                metadata=json.loads(row['metadata']) if row['metadata'] else {},
                created_at=row['created_at'],
                updated_at=row['updated_at']
            )
            
        except Exception as e:
            logger.error("Failed to get workflow execution", execution_id=execution_id, error=str(e))
            raise
    
    async def update_execution_status(
        self,
        execution_id: UUID,
        status: str,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update execution status."""
        
        query = """
        UPDATE workflow_executions 
        SET status = $2, output_data = $3, error_message = $4, updated_at = NOW()
        WHERE id = $1
        """
        
        try:
            await self.db.execute(
                query,
                execution_id,
                status,
                json.dumps(output_data, default=str) if output_data else None,
                error_message
            )
            
            logger.info("Workflow execution status updated", execution_id=execution_id, status=status)
            
        except Exception as e:
            logger.error("Failed to update execution status", execution_id=execution_id, error=str(e))
            raise
    
    async def save_node_execution(self, node_execution: NodeExecution) -> None:
        """Save node execution."""
        
        query = """
        INSERT INTO node_executions 
        (id, workflow_execution_id, node_name, agent_type, status, input_data,
         output_data, error_message, execution_time_ms, retry_count, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (id) DO UPDATE SET
            status = EXCLUDED.status,
            output_data = EXCLUDED.output_data,
            error_message = EXCLUDED.error_message,
            execution_time_ms = EXCLUDED.execution_time_ms,
            retry_count = EXCLUDED.retry_count,
            updated_at = EXCLUDED.updated_at
        """
        
        try:
            await self.db.execute(
                query,
                node_execution.id,
                node_execution.workflow_execution_id,
                node_execution.node_name,
                node_execution.agent_type.value,
                node_execution.status.value,
                json.dumps(node_execution.input_data, default=str),
                json.dumps(node_execution.output_data, default=str) if node_execution.output_data else None,
                node_execution.error_message,
                node_execution.execution_time_ms,
                node_execution.retry_count,
                node_execution.created_at,
                node_execution.updated_at
            )
            
            logger.info("Node execution saved", node_execution_id=node_execution.id)
            
        except Exception as e:
            logger.error("Failed to save node execution", node_execution_id=node_execution.id, error=str(e))
            raise
    
    async def get_executions_by_conversation(self, conversation_id: UUID) -> List[WorkflowExecution]:
        """Get all executions for a conversation."""
        
        query = """
        SELECT id, workflow_name, conversation_id, user_id, status, input_data,
               output_data, current_node, executed_nodes, node_outputs,
               error_message, priority, metadata, created_at, updated_at
        FROM workflow_executions 
        WHERE conversation_id = $1 
        ORDER BY created_at DESC
        """
        
        try:
            rows = await self.db.fetch_all(query, conversation_id)
            
            executions = []
            for row in rows:
                execution = WorkflowExecution(
                    id=row['id'],
                    workflow_name=row['workflow_name'],
                    conversation_id=row['conversation_id'],
                    user_id=row['user_id'],
                    status=WorkflowStatus(row['status']),
                    input_data=json.loads(row['input_data']) if row['input_data'] else {},
                    output_data=json.loads(row['output_data']) if row['output_data'] else None,
                    current_node=row['current_node'],
                    executed_nodes=json.loads(row['executed_nodes']) if row['executed_nodes'] else [],
                    node_outputs=json.loads(row['node_outputs']) if row['node_outputs'] else {},
                    error_message=row['error_message'],
                    priority=row['priority'],
                    metadata=json.loads(row['metadata']) if row['metadata'] else {},
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                executions.append(execution)
            
            return executions
            
        except Exception as e:
            logger.error("Failed to get executions by conversation", conversation_id=conversation_id, error=str(e))
            raise


class InMemoryWorkflowRepository(WorkflowRepository):
    """In-memory implementation of workflow repository for development."""
    
    def __init__(self):
        self.executions = {}  # Dict[UUID, WorkflowExecution]
        self.node_executions = {}  # Dict[UUID, NodeExecution]
    
    async def save_execution(self, execution: WorkflowExecution) -> None:
        """Save workflow execution in memory."""
        self.executions[execution.id] = execution
        logger.info("Workflow execution saved in memory", execution_id=execution.id)
    
    async def get_execution(self, execution_id: UUID) -> Optional[WorkflowExecution]:
        """Get workflow execution by ID from memory."""
        return self.executions.get(execution_id)
    
    async def update_execution_status(
        self,
        execution_id: UUID,
        status: str,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update execution status in memory."""
        if execution_id in self.executions:
            execution = self.executions[execution_id]
            execution.status = WorkflowStatus(status)
            if output_data:
                execution.output_data = output_data
            if error_message:
                execution.error_message = error_message
            logger.info("Workflow execution status updated in memory", execution_id=execution_id, status=status)
    
    async def save_node_execution(self, node_execution: NodeExecution) -> None:
        """Save node execution in memory."""
        self.node_executions[node_execution.id] = node_execution
        logger.info("Node execution saved in memory", node_execution_id=node_execution.id)
    
    async def get_executions_by_conversation(self, conversation_id: UUID) -> List[WorkflowExecution]:
        """Get all executions for a conversation from memory."""
        return [
            execution for execution in self.executions.values()
            if execution.conversation_id == conversation_id
        ]
