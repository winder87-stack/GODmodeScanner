#!/usr/bin/env python3
"""
LangGraph Integration for GODMODESCANNER
Provides stateful multi-agent workflows with hierarchical capabilities
"""

import os
import json
import asyncio
from typing import Dict, List, Optional, Any, TypedDict, Annotated
from datetime import datetime
import operator

try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.memory import MemorySaver
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    print("⚠️  LangGraph not installed. Install with: pip install langgraph")

import redis.asyncio as redis

# State definition for agent workflows
class AgentState(TypedDict):
    """State shared across agent workflow"""
    task_id: str
    task_type: str
    payload: Dict[str, Any]
    current_agent: Optional[str]
    agent_history: Annotated[List[str], operator.add]
    results: Annotated[Dict[str, Any], operator.add]
    errors: Annotated[List[str], operator.add]
    status: str
    metadata: Dict[str, Any]

class LangGraphWorkflow:
    """
    LangGraph-based workflow manager for multi-agent coordination

    Provides:
    - Stateful workflow execution
    - Agent chaining and branching
    - Checkpoint/resume capabilities
    - Hierarchical agent coordination
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.workflows: Dict[str, StateGraph] = {}
        self.checkpointer = MemorySaver() if LANGGRAPH_AVAILABLE else None

    async def initialize(self):
        """Initialize Redis connection"""
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=True)
        print("✅ LangGraph workflow manager initialized")

    def create_detection_workflow(self) -> StateGraph:
        """
        Create insider detection workflow

        Flow:
        1. Transaction Monitor → Detect new token
        2. Wallet Analyzer → Profile early buyers
        3. Pattern Recognition → Identify insider patterns
        4. Sybil Detection → Check for coordinated networks
        5. Risk Scoring → Calculate insider probability
        6. Alert Manager → Send alerts if threshold exceeded
        """
        if not LANGGRAPH_AVAILABLE:
            raise RuntimeError("LangGraph not available")

        workflow = StateGraph(AgentState)

        # Define agent nodes
        workflow.add_node("transaction_monitor", self._transaction_monitor_node)
        workflow.add_node("wallet_analyzer", self._wallet_analyzer_node)
        workflow.add_node("pattern_recognition", self._pattern_recognition_node)
        workflow.add_node("sybil_detection", self._sybil_detection_node)
        workflow.add_node("risk_scoring", self._risk_scoring_node)
        workflow.add_node("alert_manager", self._alert_manager_node)

        # Define workflow edges
        workflow.set_entry_point("transaction_monitor")
        workflow.add_edge("transaction_monitor", "wallet_analyzer")
        workflow.add_edge("wallet_analyzer", "pattern_recognition")
        workflow.add_edge("pattern_recognition", "sybil_detection")
        workflow.add_edge("sybil_detection", "risk_scoring")

        # Conditional edge: only alert if high risk
        workflow.add_conditional_edges(
            "risk_scoring",
            self._should_alert,
            {
                "alert": "alert_manager",
                "end": END
            }
        )

        workflow.add_edge("alert_manager", END)

        # Compile with checkpointer
        compiled = workflow.compile(checkpointer=self.checkpointer)
        self.workflows["detection"] = compiled

        return compiled

    async def _transaction_monitor_node(self, state: AgentState) -> AgentState:
        """Transaction monitoring node"""
        print(f"📊 Transaction Monitor processing task {state['task_id']}")

        # Delegate to actual transaction monitor agent via MCP
        result = await self._delegate_to_agent(
            agent_type="transaction_monitor",
            task_id=state['task_id'],
            payload=state['payload']
        )

        state['agent_history'].append('transaction_monitor')
        state['results']['transaction_monitor'] = result
        state['current_agent'] = 'wallet_analyzer'

        return state

    async def _wallet_analyzer_node(self, state: AgentState) -> AgentState:
        """Wallet analysis node"""
        print(f"👛 Wallet Analyzer processing task {state['task_id']}")

        # Get transaction data from previous step
        tx_data = state['results'].get('transaction_monitor', {})

        # Delegate to wallet analyzer
        result = await self._delegate_to_agent(
            agent_type="wallet_analyzer",
            task_id=state['task_id'],
            payload={**state['payload'], 'transaction_data': tx_data}
        )

        state['agent_history'].append('wallet_analyzer')
        state['results']['wallet_analyzer'] = result
        state['current_agent'] = 'pattern_recognition'

        return state

    async def _pattern_recognition_node(self, state: AgentState) -> AgentState:
        """Pattern recognition node"""
        print(f"🔍 Pattern Recognition processing task {state['task_id']}")

        # Get wallet data from previous step
        wallet_data = state['results'].get('wallet_analyzer', {})

        # Delegate to pattern recognition
        result = await self._delegate_to_agent(
            agent_type="pattern_recognition",
            task_id=state['task_id'],
            payload={**state['payload'], 'wallet_data': wallet_data}
        )

        state['agent_history'].append('pattern_recognition')
        state['results']['pattern_recognition'] = result
        state['current_agent'] = 'sybil_detection'

        return state

    async def _sybil_detection_node(self, state: AgentState) -> AgentState:
        """Sybil detection node"""
        print(f"🕸️ Sybil Detection processing task {state['task_id']}")

        # Get pattern data from previous step
        pattern_data = state['results'].get('pattern_recognition', {})

        # Delegate to sybil detection
        result = await self._delegate_to_agent(
            agent_type="sybil_detection",
            task_id=state['task_id'],
            payload={**state['payload'], 'pattern_data': pattern_data}
        )

        state['agent_history'].append('sybil_detection')
        state['results']['sybil_detection'] = result
        state['current_agent'] = 'risk_scoring'

        return state

    async def _risk_scoring_node(self, state: AgentState) -> AgentState:
        """Risk scoring node"""
        print(f"⚖️ Risk Scoring processing task {state['task_id']}")

        # Aggregate all previous results
        all_data = {
            'transaction': state['results'].get('transaction_monitor', {}),
            'wallet': state['results'].get('wallet_analyzer', {}),
            'pattern': state['results'].get('pattern_recognition', {}),
            'sybil': state['results'].get('sybil_detection', {})
        }

        # Delegate to risk scoring
        result = await self._delegate_to_agent(
            agent_type="risk_scoring",
            task_id=state['task_id'],
            payload={**state['payload'], 'analysis_data': all_data}
        )

        state['agent_history'].append('risk_scoring')
        state['results']['risk_scoring'] = result
        state['metadata']['risk_score'] = result.get('risk_score', 0)

        return state

    async def _alert_manager_node(self, state: AgentState) -> AgentState:
        """Alert manager node"""
        print(f"🚨 Alert Manager processing task {state['task_id']}")

        # Get risk score
        risk_score = state['metadata'].get('risk_score', 0)

        # Delegate to alert manager
        result = await self._delegate_to_agent(
            agent_type="alert_manager",
            task_id=state['task_id'],
            payload={
                **state['payload'],
                'risk_score': risk_score,
                'analysis_results': state['results']
            }
        )

        state['agent_history'].append('alert_manager')
        state['results']['alert_manager'] = result
        state['status'] = 'completed'

        return state

    def _should_alert(self, state: AgentState) -> str:
        """Determine if alert should be sent based on risk score"""
        risk_score = state['metadata'].get('risk_score', 0)

        # Alert if risk score >= 0.65 (HIGH threshold)
        if risk_score >= 0.65:
            return "alert"
        else:
            state['status'] = 'completed_no_alert'
            return "end"

    async def _delegate_to_agent(
        self,
        agent_type: str,
        task_id: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Delegate task to agent via MCP server

        In production, this would call the MCP server's task delegation endpoint.
        For now, we'll use Redis Streams for direct agent communication.
        """
        if not self.redis_client:
            return {"error": "Redis not connected"}

        try:
            # Add task to agent's stream
            stream_key = f"mcp:stream:tasks:{agent_type}"
            message_id = await self.redis_client.xadd(
                stream_key,
                {
                    "task_id": task_id,
                    "payload": json.dumps(payload),
                    "timestamp": datetime.utcnow().isoformat()
                }
            )

            # Wait for result (with timeout)
            result_key = f"mcp:result:{task_id}"

            # Poll for result (max 30 seconds)
            for _ in range(30):
                result = await self.redis_client.get(result_key)
                if result:
                    await self.redis_client.delete(result_key)
                    return json.loads(result)
                await asyncio.sleep(1)

            return {"error": "Timeout waiting for agent response"}

        except Exception as e:
            return {"error": str(e)}

    async def execute_workflow(
        self,
        workflow_name: str,
        task_id: str,
        task_type: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a workflow

        Args:
            workflow_name: Name of workflow to execute
            task_id: Unique task identifier
            task_type: Type of task
            payload: Task payload

        Returns:
            Final workflow state
        """
        if workflow_name not in self.workflows:
            raise ValueError(f"Workflow {workflow_name} not found")

        workflow = self.workflows[workflow_name]

        # Initialize state
        initial_state: AgentState = {
            "task_id": task_id,
            "task_type": task_type,
            "payload": payload,
            "current_agent": None,
            "agent_history": [],
            "results": {},
            "errors": [],
            "status": "running",
            "metadata": {}
        }

        # Execute workflow
        config = {"configurable": {"thread_id": task_id}}

        try:
            final_state = await workflow.ainvoke(initial_state, config)
            return final_state
        except Exception as e:
            return {
                **initial_state,
                "status": "failed",
                "errors": [str(e)]
            }

    async def get_workflow_state(
        self,
        workflow_name: str,
        task_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get current state of a workflow execution

        Args:
            workflow_name: Name of workflow
            task_id: Task identifier (thread_id)

        Returns:
            Current workflow state or None
        """
        if workflow_name not in self.workflows:
            return None

        workflow = self.workflows[workflow_name]
        config = {"configurable": {"thread_id": task_id}}

        try:
            state = await workflow.aget_state(config)
            return state.values if state else None
        except Exception as e:
            print(f"Error getting workflow state: {e}")
            return None

    async def close(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()


if __name__ == "__main__":
    async def test_workflow():
        """Test the LangGraph workflow"""
        if not LANGGRAPH_AVAILABLE:
            print("❌ LangGraph not available. Install with: pip install langgraph")
            return

        # Create workflow manager
        manager = LangGraphWorkflow()
        await manager.initialize()

        # Create detection workflow
        workflow = manager.create_detection_workflow()
        print("✅ Detection workflow created")

        # Execute workflow
        result = await manager.execute_workflow(
            workflow_name="detection",
            task_id="test_001",
            task_type="insider_detection",
            payload={
                "token_address": "test_token_123",
                "timestamp": datetime.utcnow().isoformat()
            }
        )

        print("
📊 Workflow Result:")
        print(json.dumps(result, indent=2))

        await manager.close()

    # Run test
    asyncio.run(test_workflow())
