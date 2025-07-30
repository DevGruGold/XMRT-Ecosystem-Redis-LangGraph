"""
LangGraph Workflow Orchestrator for XMRT-Ecosystem

This module provides advanced workflow orchestration for complex AI automation tasks
and decision trees using LangGraph's state management and graph execution capabilities.
"""

import asyncio
import logging
import json
from typing import Any, Dict, List, Optional, Callable, TypeVar, Generic
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, asdict
import uuid

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig

from ..shared.exceptions import WorkflowError, StateError
from ..shared.utils import serialize_data, deserialize_data
from .state_manager import StateManager
from .error_handler import ErrorHandler


class WorkflowStatus(Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class NodeType(Enum):
    """Types of workflow nodes"""
    DECISION = "decision"
    ACTION = "action"
    CONDITION = "condition"
    PARALLEL = "parallel"
    LOOP = "loop"
    HUMAN_INPUT = "human_input"


@dataclass
class WorkflowNode:
    """Represents a workflow node"""
    id: str
    name: str
    type: NodeType
    function: Optional[Callable] = None
    conditions: Optional[Dict[str, Any]] = None
    retry_config: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = None


@dataclass
class WorkflowExecution:
    """Represents a workflow execution instance"""
    id: str
    workflow_id: str
    status: WorkflowStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_node: Optional[str] = None
    state: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    result: Optional[Any] = None


class WorkflowState:
    """Base state class for LangGraph workflows"""
    
    def __init__(self, **kwargs):
        self.execution_id: str = kwargs.get('execution_id', str(uuid.uuid4()))
        self.workflow_id: str = kwargs.get('workflow_id', '')
        self.current_node: str = kwargs.get('current_node', '')
        self.data: Dict[str, Any] = kwargs.get('data', {})
        self.messages: List[BaseMessage] = kwargs.get('messages', [])
        self.error: Optional[str] = kwargs.get('error')
        self.retry_count: int = kwargs.get('retry_count', 0)
        self.metadata: Dict[str, Any] = kwargs.get('metadata', {})
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary"""
        return {
            'execution_id': self.execution_id,
            'workflow_id': self.workflow_id,
            'current_node': self.current_node,
            'data': self.data,
            'messages': [msg.dict() if hasattr(msg, 'dict') else str(msg) for msg in self.messages],
            'error': self.error,
            'retry_count': self.retry_count,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkflowState':
        """Create state from dictionary"""
        # Reconstruct messages
        messages = []
        for msg_data in data.get('messages', []):
            if isinstance(msg_data, dict):
                if msg_data.get('type') == 'human':
                    messages.append(HumanMessage(content=msg_data.get('content', '')))
                elif msg_data.get('type') == 'ai':
                    messages.append(AIMessage(content=msg_data.get('content', '')))
            else:
                messages.append(HumanMessage(content=str(msg_data)))
        
        data['messages'] = messages
        return cls(**data)


class WorkflowOrchestrator:
    """
    Advanced workflow orchestrator using LangGraph
    
    Manages complex AI automation workflows with state persistence,
    error handling, and parallel execution capabilities.
    """
    
    def __init__(self, state_manager: StateManager, error_handler: ErrorHandler):
        self.state_manager = state_manager
        self.error_handler = error_handler
        self.logger = logging.getLogger(__name__)
        
        # Workflow registry
        self.workflows: Dict[str, StateGraph] = {}
        self.workflow_configs: Dict[str, Dict[str, Any]] = {}
        
        # Execution tracking
        self.executions: Dict[str, WorkflowExecution] = {}
        
        # Memory saver for state persistence
        self.memory_saver = MemorySaver()
    
    def register_workflow(
        self,
        workflow_id: str,
        workflow_graph: StateGraph,
        config: Optional[Dict[str, Any]] = None
    ):
        """Register a workflow for execution"""
        try:
            self.workflows[workflow_id] = workflow_graph
            self.workflow_configs[workflow_id] = config or {}
            
            self.logger.info(f"Registered workflow: {workflow_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to register workflow {workflow_id}: {e}")
            raise WorkflowError(f"Workflow registration failed: {e}")
    
    async def create_execution(
        self,
        workflow_id: str,
        initial_state: Optional[Dict[str, Any]] = None,
        config: Optional[RunnableConfig] = None
    ) -> str:
        """Create a new workflow execution"""
        try:
            if workflow_id not in self.workflows:
                raise WorkflowError(f"Workflow {workflow_id} not found")
            
            execution_id = str(uuid.uuid4())
            
            # Create execution record
            execution = WorkflowExecution(
                id=execution_id,
                workflow_id=workflow_id,
                status=WorkflowStatus.PENDING,
                created_at=datetime.utcnow(),
                state=initial_state or {}
            )
            
            self.executions[execution_id] = execution
            
            # Save initial state
            if initial_state:
                await self.state_manager.save_state(execution_id, initial_state)
            
            self.logger.info(f"Created workflow execution: {execution_id}")
            return execution_id
            
        except Exception as e:
            self.logger.error(f"Failed to create workflow execution: {e}")
            raise WorkflowError(f"Execution creation failed: {e}")
    
    async def execute_workflow(
        self,
        execution_id: str,
        input_data: Optional[Dict[str, Any]] = None,
        config: Optional[RunnableConfig] = None
    ) -> Any:
        """Execute a workflow"""
        try:
            execution = self.executions.get(execution_id)
            if not execution:
                raise WorkflowError(f"Execution {execution_id} not found")
            
            workflow = self.workflows[execution.workflow_id]
            
            # Update execution status
            execution.status = WorkflowStatus.RUNNING
            execution.started_at = datetime.utcnow()
            
            # Prepare initial state
            state_data = execution.state or {}
            if input_data:
                state_data.update(input_data)
            
            # Create workflow state
            workflow_state = WorkflowState(
                execution_id=execution_id,
                workflow_id=execution.workflow_id,
                data=state_data
            )
            
            # Configure execution
            run_config = config or RunnableConfig(
                configurable={"thread_id": execution_id},
                checkpointer=self.memory_saver
            )
            
            # Execute workflow
            self.logger.info(f"Starting workflow execution: {execution_id}")
            
            result = await workflow.ainvoke(
                workflow_state.to_dict(),
                config=run_config
            )
            
            # Update execution with result
            execution.status = WorkflowStatus.COMPLETED
            execution.completed_at = datetime.utcnow()
            execution.result = result
            
            # Save final state
            await self.state_manager.save_state(execution_id, result)
            
            self.logger.info(f"Workflow execution completed: {execution_id}")
            return result
            
        except Exception as e:
            # Handle execution error
            await self._handle_execution_error(execution_id, e)
            raise WorkflowError(f"Workflow execution failed: {e}")
    
    async def pause_execution(self, execution_id: str) -> bool:
        """Pause a running workflow execution"""
        try:
            execution = self.executions.get(execution_id)
            if not execution:
                return False
            
            if execution.status == WorkflowStatus.RUNNING:
                execution.status = WorkflowStatus.PAUSED
                
                # Save current state
                current_state = await self.state_manager.get_state(execution_id)
                if current_state:
                    execution.state = current_state
                
                self.logger.info(f"Paused workflow execution: {execution_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to pause execution {execution_id}: {e}")
            return False
    
    async def resume_execution(self, execution_id: str) -> bool:
        """Resume a paused workflow execution"""
        try:
            execution = self.executions.get(execution_id)
            if not execution:
                return False
            
            if execution.status == WorkflowStatus.PAUSED:
                execution.status = WorkflowStatus.RUNNING
                
                # Continue execution from saved state
                await self.execute_workflow(execution_id)
                
                self.logger.info(f"Resumed workflow execution: {execution_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to resume execution {execution_id}: {e}")
            return False
    
    async def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a workflow execution"""
        try:
            execution = self.executions.get(execution_id)
            if not execution:
                return False
            
            if execution.status in [WorkflowStatus.RUNNING, WorkflowStatus.PAUSED]:
                execution.status = WorkflowStatus.CANCELLED
                execution.completed_at = datetime.utcnow()
                
                self.logger.info(f"Cancelled workflow execution: {execution_id}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to cancel execution {execution_id}: {e}")
            return False
    
    async def get_execution_status(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get the status of a workflow execution"""
        return self.executions.get(execution_id)
    
    async def list_executions(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[WorkflowStatus] = None
    ) -> List[WorkflowExecution]:
        """List workflow executions with optional filters"""
        executions = list(self.executions.values())
        
        if workflow_id:
            executions = [e for e in executions if e.workflow_id == workflow_id]
        
        if status:
            executions = [e for e in executions if e.status == status]
        
        return executions
    
    async def cleanup_completed_executions(self, older_than_hours: int = 24) -> int:
        """Clean up completed executions older than specified hours"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=older_than_hours)
            cleaned = 0
            
            to_remove = []
            for execution_id, execution in self.executions.items():
                if (execution.status in [WorkflowStatus.COMPLETED, WorkflowStatus.FAILED, WorkflowStatus.CANCELLED] and
                    execution.completed_at and execution.completed_at < cutoff_time):
                    to_remove.append(execution_id)
            
            for execution_id in to_remove:
                del self.executions[execution_id]
                await self.state_manager.delete_state(execution_id)
                cleaned += 1
            
            if cleaned > 0:
                self.logger.info(f"Cleaned up {cleaned} completed executions")
            
            return cleaned
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup executions: {e}")
            return 0
    
    async def _handle_execution_error(self, execution_id: str, error: Exception):
        """Handle workflow execution error"""
        try:
            execution = self.executions.get(execution_id)
            if execution:
                execution.status = WorkflowStatus.FAILED
                execution.completed_at = datetime.utcnow()
                execution.error = str(error)
            
            # Log error with context
            await self.error_handler.handle_error(
                error,
                context={
                    'execution_id': execution_id,
                    'workflow_id': execution.workflow_id if execution else 'unknown'
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to handle execution error: {e}")
    
    def get_workflow_stats(self) -> Dict[str, Any]:
        """Get workflow execution statistics"""
        stats = {
            'total_executions': len(self.executions),
            'by_status': {},
            'by_workflow': {}
        }
        
        for execution in self.executions.values():
            # Count by status
            status_key = execution.status.value
            stats['by_status'][status_key] = stats['by_status'].get(status_key, 0) + 1
            
            # Count by workflow
            workflow_key = execution.workflow_id
            stats['by_workflow'][workflow_key] = stats['by_workflow'].get(workflow_key, 0) + 1
        
        return stats


# Utility functions for common workflow patterns
def create_decision_node(
    node_id: str,
    decision_function: Callable,
    branches: Dict[str, str]
) -> Callable:
    """Create a decision node that routes based on function result"""
    
    async def decision_node(state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            decision_result = await decision_function(state)
            next_node = branches.get(decision_result, END)
            
            return {
                **state,
                'current_node': next_node,
                'decision_result': decision_result
            }
            
        except Exception as e:
            return {
                **state,
                'error': str(e),
                'current_node': END
            }
    
    return decision_node


def create_action_node(
    node_id: str,
    action_function: Callable,
    next_node: str = END
) -> Callable:
    """Create an action node that executes a function"""
    
    async def action_node(state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = await action_function(state)
            
            return {
                **state,
                'current_node': next_node,
                'action_result': result,
                'data': {**state.get('data', {}), f'{node_id}_result': result}
            }
            
        except Exception as e:
            return {
                **state,
                'error': str(e),
                'current_node': END
            }
    
    return action_node

