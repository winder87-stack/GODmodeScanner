#!/usr/bin/env python3
"""
GODMODESCANNER MCP Server
Model Context Protocol server for agent coordination and external tool integration
"""

import os
import json
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import redis.asyncio as redis
import uvicorn
from contextlib import asynccontextmanager

# Pydantic models for MCP protocol
class AgentRegistration(BaseModel):
    """Agent registration request"""
    agent_id: str = Field(..., description="Unique agent identifier")
    agent_type: str = Field(..., description="Type of agent")
    capabilities: List[str] = Field(default_factory=list, description="Agent capabilities")
    supervisor_id: Optional[str] = Field(None, description="Parent supervisor ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

class TaskDelegation(BaseModel):
    """Task delegation request"""
    task_id: str = Field(..., description="Unique task identifier")
    task_type: str = Field(..., description="Type of task")
    target_agent_type: Optional[str] = Field(None, description="Preferred agent type")
    target_agent_id: Optional[str] = Field(None, description="Specific agent ID")
    payload: Dict[str, Any] = Field(..., description="Task payload")
    priority: int = Field(default=5, ge=1, le=10, description="Task priority (1-10)")
    timeout: Optional[int] = Field(None, description="Task timeout in seconds")

class AgentMetrics(BaseModel):
    """Agent performance metrics"""
    agent_id: str
    cpu_usage: float = Field(ge=0, le=100)
    memory_usage: float = Field(ge=0, le=100)
    tasks_processed: int = Field(ge=0)
    tasks_queued: int = Field(ge=0)
    tasks_failed: int = Field(ge=0)
    avg_processing_time: float = Field(ge=0)
    uptime_seconds: float = Field(ge=0)
    timestamp: str

class ScalingTrigger(BaseModel):
    """Dynamic scaling trigger"""
    trigger_type: str = Field(..., description="Type of trigger (scale_up/scale_down)")
    agent_type: str = Field(..., description="Agent type to scale")
    reason: str = Field(..., description="Reason for scaling")
    current_count: int = Field(ge=0)
    target_count: int = Field(ge=0)
    metrics: Dict[str, Any] = Field(default_factory=dict)

class MCPResponse(BaseModel):
    """Standard MCP response"""
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

# Global state
class MCPServerState:
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.websocket_connections: Dict[str, WebSocket] = {}
        self.agent_registry: Dict[str, AgentRegistration] = {}
        self.task_queue: Dict[str, TaskDelegation] = {}

state = MCPServerState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    # Startup
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    state.redis_client = await redis.from_url(redis_url, decode_responses=True)
    print(f"✅ Connected to Redis: {redis_url}")

    # Start background tasks
    asyncio.create_task(monitor_agents())
    asyncio.create_task(process_scaling_triggers())

    yield

    # Shutdown
    if state.redis_client:
        await state.redis_client.close()
    print("✅ MCP Server shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="GODMODESCANNER MCP Server",
    description="Model Context Protocol server for multi-agent coordination",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# AGENT REGISTRATION ENDPOINTS
# ============================================================================

@app.post("/api/v1/agents/register", response_model=MCPResponse)
async def register_agent(registration: AgentRegistration):
    """
    Register a new agent with the MCP server

    This endpoint allows agents to register themselves and advertise their capabilities.
    """
    try:
        # Store in local registry
        state.agent_registry[registration.agent_id] = registration

        # Store in Redis
        agent_key = f"mcp:agent:{registration.agent_id}"
        await state.redis_client.hset(
            agent_key,
            mapping={
                "agent_id": registration.agent_id,
                "agent_type": registration.agent_type,
                "capabilities": json.dumps(registration.capabilities),
                "supervisor_id": registration.supervisor_id or "",
                "metadata": json.dumps(registration.metadata),
                "registered_at": datetime.utcnow().isoformat(),
                "status": "active"
            }
        )

        # Add to agent type index
        await state.redis_client.sadd(
            f"mcp:agents:by_type:{registration.agent_type}",
            registration.agent_id
        )

        # Publish registration event
        await state.redis_client.publish(
            "mcp:events:agent_registered",
            json.dumps({
                "agent_id": registration.agent_id,
                "agent_type": registration.agent_type,
                "timestamp": datetime.utcnow().isoformat()
            })
        )

        return MCPResponse(
            success=True,
            message=f"Agent {registration.agent_id} registered successfully",
            data={"agent_id": registration.agent_id}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/v1/agents/{agent_id}", response_model=MCPResponse)
async def unregister_agent(agent_id: str):
    """
    Unregister an agent from the MCP server
    """
    try:
        # Get agent info before deletion
        agent_key = f"mcp:agent:{agent_id}"
        agent_data = await state.redis_client.hgetall(agent_key)

        if not agent_data:
            raise HTTPException(status_code=404, detail="Agent not found")

        agent_type = agent_data.get('agent_type')

        # Remove from Redis
        await state.redis_client.delete(agent_key)
        await state.redis_client.srem(f"mcp:agents:by_type:{agent_type}", agent_id)

        # Remove from local registry
        if agent_id in state.agent_registry:
            del state.agent_registry[agent_id]

        # Publish unregistration event
        await state.redis_client.publish(
            "mcp:events:agent_unregistered",
            json.dumps({
                "agent_id": agent_id,
                "agent_type": agent_type,
                "timestamp": datetime.utcnow().isoformat()
            })
        )

        return MCPResponse(
            success=True,
            message=f"Agent {agent_id} unregistered successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/agents", response_model=MCPResponse)
async def list_agents(
    agent_type: Optional[str] = None,
    status: Optional[str] = None
):
    """
    List all registered agents, optionally filtered by type and status
    """
    try:
        agents = []

        if agent_type:
            # Get agents of specific type
            agent_ids = await state.redis_client.smembers(f"mcp:agents:by_type:{agent_type}")
        else:
            # Get all agents
            pattern = "mcp:agent:*"
            keys = await state.redis_client.keys(pattern)
            agent_ids = [key.split(':')[-1] for key in keys]

        for agent_id in agent_ids:
            agent_data = await state.redis_client.hgetall(f"mcp:agent:{agent_id}")
            if agent_data:
                if status and agent_data.get('status') != status:
                    continue
                agents.append({
                    "agent_id": agent_data['agent_id'],
                    "agent_type": agent_data['agent_type'],
                    "capabilities": json.loads(agent_data.get('capabilities', '[]')),
                    "supervisor_id": agent_data.get('supervisor_id'),
                    "status": agent_data.get('status'),
                    "registered_at": agent_data.get('registered_at')
                })

        return MCPResponse(
            success=True,
            message=f"Found {len(agents)} agents",
            data={"agents": agents, "count": len(agents)}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/agents/{agent_id}", response_model=MCPResponse)
async def get_agent(agent_id: str):
    """
    Get detailed information about a specific agent
    """
    try:
        agent_data = await state.redis_client.hgetall(f"mcp:agent:{agent_id}")

        if not agent_data:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Get metrics
        metrics_data = await state.redis_client.hgetall(f"mcp:metrics:{agent_id}")

        return MCPResponse(
            success=True,
            message="Agent found",
            data={
                "agent": {
                    "agent_id": agent_data['agent_id'],
                    "agent_type": agent_data['agent_type'],
                    "capabilities": json.loads(agent_data.get('capabilities', '[]')),
                    "supervisor_id": agent_data.get('supervisor_id'),
                    "status": agent_data.get('status'),
                    "registered_at": agent_data.get('registered_at'),
                    "metadata": json.loads(agent_data.get('metadata', '{}'))
                },
                "metrics": metrics_data if metrics_data else None
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# TASK DELEGATION ENDPOINTS
# ============================================================================

@app.post("/api/v1/tasks/delegate", response_model=MCPResponse)
async def delegate_task(task: TaskDelegation):
    """
    Delegate a task to an appropriate agent

    The server will select the best agent based on:
    - Agent type match
    - Current workload
    - Agent capabilities
    - Task priority
    """
    try:
        # Find suitable agent
        target_agent = None

        if task.target_agent_id:
            # Specific agent requested
            agent_data = await state.redis_client.hgetall(f"mcp:agent:{task.target_agent_id}")
            if agent_data and agent_data.get('status') == 'active':
                target_agent = task.target_agent_id
        elif task.target_agent_type:
            # Find best agent of specific type
            agent_ids = await state.redis_client.smembers(f"mcp:agents:by_type:{task.target_agent_type}")

            # Select agent with lowest workload
            best_agent = None
            min_queue = float('inf')

            for agent_id in agent_ids:
                metrics = await state.redis_client.hgetall(f"mcp:metrics:{agent_id}")
                if metrics:
                    queue_size = int(metrics.get('tasks_queued', 0))
                    if queue_size < min_queue:
                        min_queue = queue_size
                        best_agent = agent_id

            target_agent = best_agent

        if not target_agent:
            raise HTTPException(status_code=404, detail="No suitable agent found")

        # Store task
        task_key = f"mcp:task:{task.task_id}"
        await state.redis_client.hset(
            task_key,
            mapping={
                "task_id": task.task_id,
                "task_type": task.task_type,
                "target_agent": target_agent,
                "payload": json.dumps(task.payload),
                "priority": task.priority,
                "timeout": task.timeout or 0,
                "status": "delegated",
                "created_at": datetime.utcnow().isoformat()
            }
        )

        # Add to Redis Stream for the agent
        stream_key = f"mcp:stream:tasks:{target_agent}"
        await state.redis_client.xadd(
            stream_key,
            {
                "task_id": task.task_id,
                "task_type": task.task_type,
                "payload": json.dumps(task.payload),
                "priority": str(task.priority),
                "timeout": str(task.timeout or 0)
            }
        )

        # Publish task delegation event
        await state.redis_client.publish(
            "mcp:events:task_delegated",
            json.dumps({
                "task_id": task.task_id,
                "target_agent": target_agent,
                "timestamp": datetime.utcnow().isoformat()
            })
        )

        return MCPResponse(
            success=True,
            message=f"Task {task.task_id} delegated to agent {target_agent}",
            data={
                "task_id": task.task_id,
                "target_agent": target_agent
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/tasks/{task_id}", response_model=MCPResponse)
async def get_task_status(task_id: str):
    """
    Get the status of a delegated task
    """
    try:
        task_data = await state.redis_client.hgetall(f"mcp:task:{task_id}")

        if not task_data:
            raise HTTPException(status_code=404, detail="Task not found")

        return MCPResponse(
            success=True,
            message="Task found",
            data={
                "task_id": task_data['task_id'],
                "task_type": task_data['task_type'],
                "target_agent": task_data['target_agent'],
                "status": task_data['status'],
                "created_at": task_data['created_at'],
                "completed_at": task_data.get('completed_at'),
                "result": json.loads(task_data.get('result', 'null'))
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# MONITORING ENDPOINTS
# ============================================================================

@app.post("/api/v1/metrics/report", response_model=MCPResponse)
async def report_metrics(metrics: AgentMetrics):
    """
    Report agent performance metrics
    """
    try:
        metrics_key = f"mcp:metrics:{metrics.agent_id}"
        await state.redis_client.hset(
            metrics_key,
            mapping={
                "agent_id": metrics.agent_id,
                "cpu_usage": str(metrics.cpu_usage),
                "memory_usage": str(metrics.memory_usage),
                "tasks_processed": str(metrics.tasks_processed),
                "tasks_queued": str(metrics.tasks_queued),
                "tasks_failed": str(metrics.tasks_failed),
                "avg_processing_time": str(metrics.avg_processing_time),
                "uptime_seconds": str(metrics.uptime_seconds),
                "timestamp": metrics.timestamp
            }
        )

        # Set TTL (5 minutes)
        await state.redis_client.expire(metrics_key, 300)

        # Add to time series (Redis Stream)
        await state.redis_client.xadd(
            f"mcp:stream:metrics:{metrics.agent_id}",
            {
                "cpu": str(metrics.cpu_usage),
                "memory": str(metrics.memory_usage),
                "tasks_processed": str(metrics.tasks_processed),
                "timestamp": metrics.timestamp
            },
            maxlen=1000  # Keep last 1000 entries
        )

        return MCPResponse(
            success=True,
            message="Metrics reported successfully"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/metrics/dashboard", response_model=MCPResponse)
async def get_dashboard_metrics():
    """
    Get aggregated metrics for monitoring dashboard
    """
    try:
        # Get all active agents
        pattern = "mcp:agent:*"
        keys = await state.redis_client.keys(pattern)
        agent_ids = [key.split(':')[-1] for key in keys]

        total_agents = len(agent_ids)
        active_agents = 0
        total_cpu = 0.0
        total_memory = 0.0
        total_tasks_processed = 0
        total_tasks_queued = 0
        total_tasks_failed = 0

        agent_metrics = []

        for agent_id in agent_ids:
            agent_data = await state.redis_client.hgetall(f"mcp:agent:{agent_id}")
            metrics_data = await state.redis_client.hgetall(f"mcp:metrics:{agent_id}")

            if agent_data.get('status') == 'active':
                active_agents += 1

            if metrics_data:
                cpu = float(metrics_data.get('cpu_usage', 0))
                memory = float(metrics_data.get('memory_usage', 0))
                tasks_processed = int(metrics_data.get('tasks_processed', 0))
                tasks_queued = int(metrics_data.get('tasks_queued', 0))
                tasks_failed = int(metrics_data.get('tasks_failed', 0))

                total_cpu += cpu
                total_memory += memory
                total_tasks_processed += tasks_processed
                total_tasks_queued += tasks_queued
                total_tasks_failed += tasks_failed

                agent_metrics.append({
                    "agent_id": agent_id,
                    "agent_type": agent_data.get('agent_type'),
                    "cpu_usage": cpu,
                    "memory_usage": memory,
                    "tasks_processed": tasks_processed,
                    "tasks_queued": tasks_queued,
                    "tasks_failed": tasks_failed
                })

        return MCPResponse(
            success=True,
            message="Dashboard metrics retrieved",
            data={
                "summary": {
                    "total_agents": total_agents,
                    "active_agents": active_agents,
                    "avg_cpu_usage": total_cpu / max(total_agents, 1),
                    "avg_memory_usage": total_memory / max(total_agents, 1),
                    "total_tasks_processed": total_tasks_processed,
                    "total_tasks_queued": total_tasks_queued,
                    "total_tasks_failed": total_tasks_failed
                },
                "agents": agent_metrics
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# SCALING ENDPOINTS
# ============================================================================

@app.post("/api/v1/scaling/trigger", response_model=MCPResponse)
async def trigger_scaling(trigger: ScalingTrigger):
    """
    Trigger dynamic scaling of agents
    """
    try:
        # Store scaling trigger
        trigger_key = f"mcp:scaling:trigger:{datetime.utcnow().timestamp()}"
        await state.redis_client.hset(
            trigger_key,
            mapping={
                "trigger_type": trigger.trigger_type,
                "agent_type": trigger.agent_type,
                "reason": trigger.reason,
                "current_count": str(trigger.current_count),
                "target_count": str(trigger.target_count),
                "metrics": json.dumps(trigger.metrics),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

        # Publish scaling event
        await state.redis_client.publish(
            "mcp:events:scaling_triggered",
            json.dumps({
                "trigger_type": trigger.trigger_type,
                "agent_type": trigger.agent_type,
                "current_count": trigger.current_count,
                "target_count": trigger.target_count,
                "timestamp": datetime.utcnow().isoformat()
            })
        )

        return MCPResponse(
            success=True,
            message=f"Scaling trigger created: {trigger.trigger_type} {trigger.agent_type}",
            data={
                "trigger_type": trigger.trigger_type,
                "agent_type": trigger.agent_type,
                "target_count": trigger.target_count
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# WEBSOCKET ENDPOINTS
# ============================================================================

@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """
    WebSocket endpoint for real-time event streaming
    """
    await websocket.accept()
    client_id = f"ws_{datetime.utcnow().timestamp()}"
    state.websocket_connections[client_id] = websocket

    try:
        # Subscribe to Redis events
        pubsub = state.redis_client.pubsub()
        await pubsub.subscribe(
            "mcp:events:agent_registered",
            "mcp:events:agent_unregistered",
            "mcp:events:task_delegated",
            "mcp:events:scaling_triggered"
        )

        # Send events to WebSocket
        async for message in pubsub.listen():
            if message['type'] == 'message':
                await websocket.send_json({
                    "channel": message['channel'],
                    "data": json.loads(message['data'])
                })

    except WebSocketDisconnect:
        del state.websocket_connections[client_id]
    except Exception as e:
        print(f"WebSocket error: {e}")
        del state.websocket_connections[client_id]

# ============================================================================
# BACKGROUND TASKS
# ============================================================================

async def monitor_agents():
    """
    Background task to monitor agent health
    """
    while True:
        try:
            # Check for stale agents (no metrics in 5 minutes)
            pattern = "mcp:agent:*"
            keys = await state.redis_client.keys(pattern)

            for key in keys:
                agent_id = key.split(':')[-1]
                metrics_key = f"mcp:metrics:{agent_id}"

                # Check if metrics exist
                exists = await state.redis_client.exists(metrics_key)
                if not exists:
                    # Mark agent as inactive
                    await state.redis_client.hset(key, "status", "inactive")

            await asyncio.sleep(60)  # Check every minute

        except Exception as e:
            print(f"Monitor error: {e}")
            await asyncio.sleep(60)

async def process_scaling_triggers():
    """
    Background task to process scaling triggers
    """
    while True:
        try:
            # Get all agents and their metrics
            pattern = "mcp:agent:*"
            keys = await state.redis_client.keys(pattern)

            # Group by agent type
            agent_types = {}
            for key in keys:
                agent_data = await state.redis_client.hgetall(key)
                agent_type = agent_data.get('agent_type')
                if agent_type:
                    if agent_type not in agent_types:
                        agent_types[agent_type] = []
                    agent_types[agent_type].append(agent_data['agent_id'])

            # Check scaling conditions for each type
            for agent_type, agent_ids in agent_types.items():
                total_queue = 0
                total_cpu = 0.0

                for agent_id in agent_ids:
                    metrics = await state.redis_client.hgetall(f"mcp:metrics:{agent_id}")
                    if metrics:
                        total_queue += int(metrics.get('tasks_queued', 0))
                        total_cpu += float(metrics.get('cpu_usage', 0))

                avg_cpu = total_cpu / len(agent_ids) if agent_ids else 0
                avg_queue = total_queue / len(agent_ids) if agent_ids else 0

                # Scale up conditions
                if avg_queue > 100 or avg_cpu > 80:
                    trigger = ScalingTrigger(
                        trigger_type="scale_up",
                        agent_type=agent_type,
                        reason=f"High load: queue={avg_queue}, cpu={avg_cpu}%",
                        current_count=len(agent_ids),
                        target_count=len(agent_ids) + 1,
                        metrics={"avg_queue": avg_queue, "avg_cpu": avg_cpu}
                    )
                    await trigger_scaling(trigger)

                # Scale down conditions
                elif avg_queue < 10 and avg_cpu < 20 and len(agent_ids) > 1:
                    trigger = ScalingTrigger(
                        trigger_type="scale_down",
                        agent_type=agent_type,
                        reason=f"Low load: queue={avg_queue}, cpu={avg_cpu}%",
                        current_count=len(agent_ids),
                        target_count=len(agent_ids) - 1,
                        metrics={"avg_queue": avg_queue, "avg_cpu": avg_cpu}
                    )
                    await trigger_scaling(trigger)

            await asyncio.sleep(30)  # Check every 30 seconds

        except Exception as e:
            print(f"Scaling processor error: {e}")
            await asyncio.sleep(30)

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    try:
        # Check Redis connection
        await state.redis_client.ping()

        return {
            "status": "healthy",
            "redis": "connected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv('MCP_PORT', 8000)),
        log_level="info"
    )
