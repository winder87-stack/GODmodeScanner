#!/usr/bin/env python3
"""
MCP Agent Client Library
Simplifies agent integration with MCP server
"""

import os
import json
import asyncio
import httpx
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
from redis_streams import AgentStreamsClient

class MCPAgentClient:
    """
    High-level client for agents to interact with MCP server

    Features:
    - Automatic registration/unregistration
    - Task listening via Redis Streams
    - Result publishing
    - Metrics reporting
    - Event publishing
    """

    def __init__(
        self,
        agent_id: str,
        agent_type: str,
        capabilities: List[str],
        mcp_server_url: str = "http://localhost:8000",
        redis_url: str = "redis://localhost:6379",
        supervisor_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.capabilities = capabilities
        self.mcp_server_url = mcp_server_url.rstrip('/')
        self.supervisor_id = supervisor_id
        self.metadata = metadata or {}

        # HTTP client for MCP API
        self.http_client = httpx.AsyncClient(timeout=30.0)

        # Redis Streams client for task/result messaging
        self.streams_client = AgentStreamsClient(
            agent_id=agent_id,
            agent_type=agent_type,
            redis_url=redis_url
        )

        # Metrics tracking
        self.metrics = {
            'tasks_processed': 0,
            'tasks_queued': 0,
            'tasks_failed': 0,
            'total_processing_time': 0.0,
            'start_time': datetime.utcnow()
        }

        # Background tasks
        self.metrics_reporter_task: Optional[asyncio.Task] = None
        self.running = False

    async def initialize(self):
        """Initialize the client and register with MCP server"""
        # Initialize streams client
        await self.streams_client.initialize()

        # Register with MCP server
        await self.register()

        # Start metrics reporter
        self.running = True
        self.metrics_reporter_task = asyncio.create_task(self._report_metrics_loop())

        print(f"✅ MCP Agent Client initialized: {self.agent_id}")

    async def register(self):
        """Register agent with MCP server"""
        try:
            response = await self.http_client.post(
                f"{self.mcp_server_url}/api/v1/agents/register",
                json={
                    'agent_id': self.agent_id,
                    'agent_type': self.agent_type,
                    'capabilities': self.capabilities,
                    'supervisor_id': self.supervisor_id,
                    'metadata': self.metadata
                }
            )
            response.raise_for_status()
            print(f"✅ Registered with MCP server: {self.agent_id}")
        except Exception as e:
            print(f"❌ Failed to register with MCP server: {e}")
            raise

    async def unregister(self):
        """Unregister agent from MCP server"""
        try:
            response = await self.http_client.delete(
                f"{self.mcp_server_url}/api/v1/agents/{self.agent_id}"
            )
            response.raise_for_status()
            print(f"✅ Unregistered from MCP server: {self.agent_id}")
        except Exception as e:
            print(f"❌ Failed to unregister from MCP server: {e}")

    async def listen_for_tasks(
        self,
        task_handler: Callable[[Dict[str, Any]], Dict[str, Any]],
        batch_size: int = 10
    ):
        """
        Listen for tasks and process them

        Args:
            task_handler: Async function that processes tasks and returns results
            batch_size: Number of tasks to process concurrently
        """
        async def process_task(task_data: Dict[str, Any]):
            task_id = task_data.get('task_id')
            payload = task_data.get('payload', {})

            # Deserialize payload if it's a string
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except:
                    pass

            print(f"📥 Processing task: {task_id}")

            start_time = datetime.utcnow()
            self.metrics['tasks_queued'] += 1

            try:
                # Call task handler
                result = await task_handler(payload)

                # Calculate processing time
                processing_time = (datetime.utcnow() - start_time).total_seconds()
                self.metrics['total_processing_time'] += processing_time
                self.metrics['tasks_processed'] += 1
                self.metrics['tasks_queued'] -= 1

                # Publish result
                await self.streams_client.publish_result(task_id, result)

                print(f"✅ Completed task: {task_id} ({processing_time:.2f}s)")

            except Exception as e:
                self.metrics['tasks_failed'] += 1
                self.metrics['tasks_queued'] -= 1

                error_result = {
                    'error': str(e),
                    'task_id': task_id,
                    'agent_id': self.agent_id
                }

                await self.streams_client.publish_result(task_id, error_result)
                print(f"❌ Failed task: {task_id} - {e}")

        # Start listening
        await self.streams_client.listen_for_tasks(
            callback=process_task,
            batch_size=batch_size
        )

    async def delegate_task(
        self,
        task_id: str,
        task_type: str,
        payload: Dict[str, Any],
        target_agent_type: Optional[str] = None,
        target_agent_id: Optional[str] = None,
        priority: int = 5,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Delegate a task to another agent via MCP server

        Args:
            task_id: Unique task identifier
            task_type: Type of task
            payload: Task payload
            target_agent_type: Preferred agent type
            target_agent_id: Specific agent ID
            priority: Task priority (1-10)
            timeout: Task timeout in seconds

        Returns:
            Delegation response
        """
        try:
            response = await self.http_client.post(
                f"{self.mcp_server_url}/api/v1/tasks/delegate",
                json={
                    'task_id': task_id,
                    'task_type': task_type,
                    'target_agent_type': target_agent_type,
                    'target_agent_id': target_agent_id,
                    'payload': payload,
                    'priority': priority,
                    'timeout': timeout
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Failed to delegate task: {e}")
            return {'success': False, 'error': str(e)}

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of a delegated task"""
        try:
            response = await self.http_client.get(
                f"{self.mcp_server_url}/api/v1/tasks/{task_id}"
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Failed to get task status: {e}")
            return {'success': False, 'error': str(e)}

    async def publish_event(
        self,
        event_type: str,
        data: Dict[str, Any]
    ):
        """Publish an event"""
        await self.streams_client.publish_event(event_type, data)

    async def report_metrics(self):
        """Report current metrics to MCP server"""
        uptime = (datetime.utcnow() - self.metrics['start_time']).total_seconds()
        avg_processing_time = (
            self.metrics['total_processing_time'] / max(self.metrics['tasks_processed'], 1)
        )

        # Get system metrics (simplified)
        import psutil
        process = psutil.Process()

        metrics_data = {
            'agent_id': self.agent_id,
            'cpu_usage': process.cpu_percent(),
            'memory_usage': process.memory_percent(),
            'tasks_processed': self.metrics['tasks_processed'],
            'tasks_queued': self.metrics['tasks_queued'],
            'tasks_failed': self.metrics['tasks_failed'],
            'avg_processing_time': avg_processing_time,
            'uptime_seconds': uptime,
            'timestamp': datetime.utcnow().isoformat()
        }

        try:
            response = await self.http_client.post(
                f"{self.mcp_server_url}/api/v1/metrics/report",
                json=metrics_data
            )
            response.raise_for_status()
        except Exception as e:
            print(f"⚠️  Failed to report metrics: {e}")

    async def _report_metrics_loop(self):
        """Background task to report metrics periodically"""
        while self.running:
            try:
                await self.report_metrics()
                await asyncio.sleep(30)  # Report every 30 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"❌ Metrics reporter error: {e}")
                await asyncio.sleep(30)

    async def close(self):
        """Close the client and cleanup"""
        self.running = False

        # Stop metrics reporter
        if self.metrics_reporter_task:
            self.metrics_reporter_task.cancel()
            try:
                await self.metrics_reporter_task
            except asyncio.CancelledError:
                pass

        # Unregister from MCP server
        await self.unregister()

        # Close streams client
        await self.streams_client.close()

        # Close HTTP client
        await self.http_client.aclose()

        print(f"✅ MCP Agent Client closed: {self.agent_id}")


# Example usage
if __name__ == "__main__":
    async def example_task_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Example task handler"""
        print(f"Processing payload: {payload}")
        await asyncio.sleep(1)  # Simulate work
        return {
            'status': 'completed',
            'result': f"Processed {payload.get('data', 'unknown')}"
        }

    async def main():
        # Create client
        client = MCPAgentClient(
            agent_id="example_agent_001",
            agent_type="example_agent",
            capabilities=["data_processing", "analysis"],
            mcp_server_url="http://localhost:8000",
            redis_url="redis://localhost:6379"
        )

        # Initialize
        await client.initialize()

        # Listen for tasks
        try:
            await client.listen_for_tasks(example_task_handler)
        except KeyboardInterrupt:
            print("
🛑 Shutting down...")
        finally:
            await client.close()

    asyncio.run(main())
