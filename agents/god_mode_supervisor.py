#!/usr/bin/env python3
"""
GOD MODE SUPERVISOR - Autonomous System Orchestration

This is the master orchestrator agent that monitors and manages the entire
GODMODESCANNER infrastructure using Agent Zero's hierarchical agent framework.

Responsibilities:
- Monitor 6-node Redis cluster health
- Track 30+ worker thread performance
- Auto-scale agents based on queue depth
- Handle RPC rate limiting and endpoint rotation
- Schedule periodic maintenance tasks
- Coordinate subordinate agents for complex operations
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import redis.asyncio as redis
import structlog
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from agentzero.agent_zero_core import Agent, AgentConfig, AgentContext

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger(__name__)


class GodModeSupervisor:
    """God Mode Supervisor - Master orchestrator for GODMODESCANNER.

    This agent uses Agent Zero's hierarchical framework to:
    1. Monitor system health via Redis Streams
    2. Auto-scale agents based on queue depth
    3. Handle infrastructure issues (RPC rate limits, etc.)
    4. Schedule periodic maintenance
    5. Coordinate complex multi-agent operations
    """

    def __init__(self, config_path: Optional[str] = None):
        """Initialize God Mode Supervisor.

        Args:
            config_path: Optional path to configuration file
        """
        # Load environment
        load_dotenv(project_root / ".env")

        # Configuration
        self.redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:16379")
        self.check_interval = 60  # Check every 60 seconds
        self.queue_threshold = 1000  # Auto-scale threshold
        self.memory_cleanup_interval = 3600  # 1 hour

        # State
        self.redis_client = None
        self.running = False
        self.last_memory_cleanup = datetime.now()
        self.agent_instances: Dict[str, List[str]] = {}

        # Agent Zero orchestrator
        self.orchestrator = None
        self.context = None

        logger.info("god_mode_supervisor_initialized")

    async def initialize(self) -> bool:
        """Initialize supervisor and connections."""
        try:
            # Connect to Redis
            self.redis_client = await redis.from_url(
                self.redis_url,
                decode_responses=True
            )
            await self.redis_client.ping()
            logger.info("redis_connected", url=self.redis_url)

            # Initialize Agent Zero orchestrator
            config = AgentConfig(
                profile="orchestrator",
                redis_host="127.0.0.1",
                redis_port=16379
            )
            self.context = AgentContext(config)
            self.orchestrator = Agent(config, self.context)

            logger.info("agent_zero_orchestrator_initialized")
            return True

        except Exception as e:
            logger.error("initialization_failed", error=str(e))
            return False

    async def check_system_health(self) -> Dict:
        """Check system health from Redis Streams.

        Returns:
            Dict with health metrics
        """
        try:
            # Read latest health data from godmode:system_health stream
            messages = await self.redis_client.xrevrange(
                "godmode:system_health",
                count=1
            )

            if not messages:
                return {"status": "unknown", "reason": "no_health_data"}

            msg_id, fields = messages[0]
            health_data = json.loads(fields.get("data", "{}"))

            logger.info("system_health_checked", health=health_data)
            return health_data

        except Exception as e:
            logger.error("health_check_failed", error=str(e))
            return {"status": "error", "error": str(e)}

    async def check_queue_depths(self) -> Dict[str, int]:
        """Check Redis Streams queue depths.

        Returns:
            Dict mapping stream names to pending message counts
        """
        streams = [
            "godmode:new_transactions",
            "godmode:new_tokens",
            "godmode:risk_scores",
            "godmode:alerts"
        ]

        queue_depths = {}

        for stream in streams:
            try:
                # Get stream length
                length = await self.redis_client.xlen(stream)
                queue_depths[stream] = length

                # Check pending messages for consumer groups
                try:
                    groups = await self.redis_client.xinfo_groups(stream)
                    for group in groups:
                        group_name = group["name"]
                        pending = group.get("pending", 0)
                        queue_depths[f"{stream}:{group_name}"] = pending
                except:
                    pass  # Stream might not have consumer groups yet

            except Exception as e:
                logger.warning("queue_depth_check_failed", stream=stream, error=str(e))
                queue_depths[stream] = -1

        logger.info("queue_depths_checked", depths=queue_depths)
        return queue_depths

    async def auto_scale_risk_assessors(self, current_count: int, target_count: int):
        """Auto-scale risk_assessor agents.

        Args:
            current_count: Current number of risk_assessor instances
            target_count: Target number of instances
        """
        try:
            logger.info(
                "auto_scaling_risk_assessors",
                current=current_count,
                target=target_count
            )

            # Use Agent Zero to spawn subordinate supervisor
            message = f"""
You are a supervisor agent responsible for scaling risk_assessor instances.

Current situation:
- Current risk_assessor instances: {current_count}
- Target instances: {target_count}
- Action required: Spawn {target_count - current_count} additional risk_assessor agents

Task:
1. Use the swarm_manager to spawn {target_count - current_count} new risk_assessor workers
2. Verify they connect to the risk-aggregator-group consumer group
3. Monitor their startup and confirm they begin processing messages
4. Report back with the new instance IDs and their status

Configuration:
- Consumer group: risk-aggregator-group
- Stream: godmode:risk_scores
- Batch size: 100
- Processing timeout: 30 seconds
"""

            # Call subordinate supervisor agent
            result = await self.orchestrator.call_subordinate(
                profile="orchestrator",
                message=message,
                reset=True
            )

            logger.info("auto_scale_completed", result=result)
            return result

        except Exception as e:
            logger.error("auto_scale_failed", error=str(e))
            return None

    async def handle_rate_limit_spike(self, endpoint: str):
        """Handle RPC rate limiting by switching endpoints.

        Args:
            endpoint: The endpoint experiencing rate limits
        """
        try:
            logger.warning("rate_limit_detected", endpoint=endpoint)

            # Use Agent Zero developer agent to switch RPC endpoint
            message = f"""
You are a developer agent responsible for handling RPC rate limiting.

Current situation:
- Endpoint experiencing 429 errors: {endpoint}
- Action required: Switch to alternative RPC endpoint immediately

Task:
1. Read the current RPC_ENDPOINTS from .env file
2. Identify the failing endpoint: {endpoint}
3. Rotate to the next available endpoint in the list
4. Update the .env file with the new primary endpoint
5. Send a control message to all agents via Redis pub/sub:
   - Channel: godmode:control
   - Command: config_update
   - Parameters: {{"rpc_endpoint": "<new_endpoint>"}}
6. Verify agents acknowledge the config update
7. Monitor for 60 seconds to ensure 429 errors stop
8. Report back with the new endpoint and confirmation

Urgency: IMMEDIATE - This is affecting live transaction monitoring
"""

            # Call subordinate developer agent
            result = await self.orchestrator.call_subordinate(
                profile="developer",
                message=message,
                reset=True
            )

            logger.info("rate_limit_handled", result=result)
            return result

        except Exception as e:
            logger.error("rate_limit_handling_failed", error=str(e))
            return None

    async def schedule_memory_cleanup(self):
        """Schedule periodic memory cleanup via memory_curator agent."""
        try:
            # Check if it's time for cleanup
            now = datetime.now()
            time_since_last = (now - self.last_memory_cleanup).total_seconds()

            if time_since_last < self.memory_cleanup_interval:
                return  # Not time yet

            logger.info("scheduling_memory_cleanup")

            # Use Agent Zero to call memory_curator
            message = """
You are the memory_curator agent responsible for FAISS vector storage maintenance.

Task: Prune old memory entries to conserve memory

1. Connect to FAISS vector storage at data/memory/
2. Query all memory entries with metadata
3. Identify entries older than 7 days:
   - Filter: timestamp < (now - 7 days)
4. Delete identified entries from FAISS index
5. Compact the FAISS index to reclaim space
6. Generate a cleanup report:
   - Total entries before cleanup
   - Entries deleted
   - Total entries after cleanup
   - Space reclaimed (MB)
   - Cleanup duration
7. Save report to data/memory/cleanup_report_{timestamp}.json
8. Publish cleanup metrics to godmode:system_health stream

Expected outcome:
- Reduced memory footprint
- Maintained recent memory entries (<7 days)
- No impact on active detection patterns
"""

            # Call subordinate memory_curator agent
            result = await self.orchestrator.call_subordinate(
                profile="developer",  # Use developer for now, can create memory_curator profile
                message=message,
                reset=True
            )

            # Update last cleanup time
            self.last_memory_cleanup = now

            logger.info("memory_cleanup_scheduled", result=result)
            return result

        except Exception as e:
            logger.error("memory_cleanup_failed", error=str(e))
            return None

    async def monitor_and_respond(self):
        """Main monitoring loop - checks health and responds to issues."""
        logger.info("monitoring_loop_started")

        while self.running:
            try:
                # 1. Check system health
                health = await self.check_system_health()

                # 2. Check queue depths
                queue_depths = await self.check_queue_depths()

                # 3. Auto-scale risk assessors if needed
                risk_queue = queue_depths.get("godmode:risk_scores:risk-aggregator-group", 0)
                if risk_queue > self.queue_threshold:
                    logger.warning(
                        "risk_queue_threshold_exceeded",
                        current=risk_queue,
                        threshold=self.queue_threshold
                    )

                    # Calculate how many additional instances needed
                    # Assume each instance can handle ~200 messages
                    additional_needed = (risk_queue - self.queue_threshold) // 200
                    additional_needed = max(1, min(additional_needed, 5))  # 1-5 instances

                    current_count = len(self.agent_instances.get("risk_assessor", []))
                    target_count = current_count + additional_needed

                    await self.auto_scale_risk_assessors(current_count, target_count)

                # 4. Check for rate limiting in logs
                # This would typically parse recent logs, simplified here
                # In production, integrate with log aggregation system

                # 5. Schedule memory cleanup if needed
                await self.schedule_memory_cleanup()

                # 6. Publish supervisor heartbeat
                await self.redis_client.xadd(
                    "godmode:system_health",
                    {
                        "data": json.dumps({
                            "supervisor": "god_mode",
                            "status": "healthy",
                            "timestamp": datetime.now().isoformat(),
                            "queue_depths": queue_depths,
                            "health": health
                        })
                    }
                )

                # Wait before next check
                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error("monitoring_loop_error", error=str(e))
                await asyncio.sleep(self.check_interval)

    async def start(self):
        """Start the God Mode Supervisor."""
        logger.info("god_mode_supervisor_starting")

        if not await self.initialize():
            logger.error("supervisor_initialization_failed")
            return False

        self.running = True

        # Start monitoring loop
        await self.monitor_and_respond()

        return True

    async def stop(self):
        """Stop the God Mode Supervisor."""
        logger.info("god_mode_supervisor_stopping")
        self.running = False

        if self.redis_client:
            await self.redis_client.close()


async def main():
    """Main entry point."""
    supervisor = GodModeSupervisor()

    try:
        await supervisor.start()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
    finally:
        await supervisor.stop()


if __name__ == "__main__":
    asyncio.run(main())
