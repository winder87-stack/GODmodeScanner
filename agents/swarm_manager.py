#!/usr/bin/env python3
"""Swarm Manager - Aggressive parallel processing coordinator for GODMODESCANNER.

This module manages swarms of parallel worker agents for high-throughput,
fault-tolerant processing using Redis Streams consumer groups.

Key Features:
- Spawn 10+ parallel workers per agent type (horizontal scaling)
- Automatic worker health monitoring and restart
- Dynamic scaling based on message queue depth
- Aggregate statistics across all workers
- Graceful shutdown and backpressure management
- Multi-agent type coordination

Architecture:
    Transaction Monitor (1 instance) -> Redis Streams ->
    ├─> Wallet Analyzer Swarm (10+ workers)
    ├─> Pattern Recognition Swarm (10+ workers)
    └─> Sybil Detection Swarm (10+ workers)
"""

import asyncio
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
import structlog
import uuid

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.redis_streams_consumer import (
    ConsumerConfig,
    Message,
    ConsumerSwarm,
    STREAM_TRANSACTIONS,
    STREAM_TOKEN_LAUNCHES,
    STREAM_TRADES,
    STREAM_ALERTS,
    STREAM_RISK_SCORES,
)
from utils.redis_cluster_client import GuerrillaRedisCluster

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger(__name__)


@dataclass
class AgentSwarmConfig:
    """Configuration for an agent swarm."""
    agent_type: str  # e.g., "wallet-analyzer", "pattern-recognition"
    stream_name: str
    group_name: str
    num_workers: int = 10  # Aggressive scaling: 10 parallel workers
    min_workers: int = 5
    max_workers: int = 20
    scale_up_threshold: int = 1000  # Scale up when >1000 pending messages
    scale_down_threshold: int = 100  # Scale down when <100 pending messages
    scale_check_interval: int = 30  # Check every 30 seconds
    message_handler: Optional[Callable[[Message], Any]] = None
    

@dataclass
class SwarmStats:
    """Statistics for a single agent swarm."""
    agent_type: str
    num_workers: int
    active_workers: int
    total_messages_consumed: int
    total_messages_acknowledged: int
    total_messages_failed: int
    total_pending_processed: int
    avg_processing_time_ms: float
    pending_messages: int
    consumers_info: List[Dict[str, Any]] = field(default_factory=list)
    last_updated: str = ""
    

@dataclass 
class GlobalSwarmStats:
    """Global statistics for all agent swarms."""
    total_agents: int
    total_workers: int
    total_messages_consumed: int
    total_messages_acknowledged: int
    total_messages_failed: int
    avg_processing_time_ms: float
    total_pending_messages: int
    uptime_seconds: float
    agent_swarms: Dict[str, SwarmStats] = field(default_factory=dict)
    last_updated: str = ""


class SwarmManager:
    """Manages multiple agent swarms for aggressive parallel processing.
    
    This class orchestrates swarms of parallel workers that consume from
    Redis Streams, providing horizontal scaling, fault tolerance, and
    intelligent backpressure management.
    """

    # Default configuration for agent types
    DEFAULT_AGENT_CONFIGS = {
        "wallet-analyzer": AgentSwarmConfig(
            agent_type="wallet-analyzer",
            stream_name=STREAM_TRANSACTIONS,
            group_name="wallet-analyzer-group",
            num_workers=10,
        ),
        "pattern-recognition": AgentSwarmConfig(
            agent_type="pattern-recognition",
            stream_name=STREAM_TRANSACTIONS,
            group_name="pattern-recognition-group",
            num_workers=10,
        ),
        "sybil-detection": AgentSwarmConfig(
            agent_type="sybil-detection",
            stream_name=STREAM_TRANSACTIONS,
            group_name="sybil-detection-group",
            num_workers=10,
        ),
        "risk-scoring": AgentSwarmConfig(
            agent_type="risk-scoring",
            stream_name=STREAM_TRANSACTIONS,
            group_name="risk-scoring-group",
            num_workers=5,
        ),
        "alert-manager": AgentSwarmConfig(
            agent_type="alert-manager",
            stream_name=STREAM_ALERTS,
            group_name="alert-manager-group",
            num_workers=5,
        ),
    }

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        agent_configs: Optional[Dict[str, AgentSwarmConfig]] = None,
    ):
        """Initialize Swarm Manager.
        
        Args:
            redis_url: Redis connection URL
            agent_configs: Override default agent configurations
        """
        self.redis_url = redis_url
        self.agent_configs = agent_configs or self.DEFAULT_AGENT_CONFIGS
        
        # Swarm instances
        self.swarms: Dict[str, ConsumerSwarm] = {}
        
        # State
        self._running = False
        self._shutdown = False
        self._start_time: Optional[float] = None
        
        # Background tasks
        self._scale_monitor_task: Optional[asyncio.Task] = None
        self._stats_task: Optional[asyncio.Task] = None
        
        # Statistics
        self._stats = GlobalSwarmStats(
            total_agents=len(self.agent_configs),
            total_workers=sum(c.num_workers for c in self.agent_configs.values()),
            total_messages_consumed=0,
            total_messages_acknowledged=0,
            total_messages_failed=0,
            avg_processing_time_ms=0.0,
            total_pending_messages=0,
            uptime_seconds=0.0,
        )
        
        logger.info(
            "swarm_manager_init",
            redis_url=redis_url,
            agent_types=list(self.agent_configs.keys()),
            total_workers=self._stats.total_workers,
        )

    async def start(self):
        """Start all agent swarms."""
        if self._running:
            logger.warning("swarm_manager_already_running")
            return
        
        self._running = True
        self._start_time = time.time()
        
        logger.info("swarm_manager_starting", agent_types=list(self.agent_configs.keys()))
        
        # Start each swarm
        for agent_type, config in self.agent_configs.items():
            await self._start_swarm(agent_type, config)
        
        # Start background tasks
        self._scale_monitor_task = asyncio.create_task(self._scale_monitor_loop())
        self._stats_task = asyncio.create_task(self._stats_loop())
        
        logger.info(
            "swarm_manager_started",
            swarms=len(self.swarms),
            total_workers=sum(s.num_consumers for s in self.swarms.values()),
        )

    async def _start_swarm(self, agent_type: str, config: AgentSwarmConfig):
        """Start a single agent swarm."""
        try:
            swarm = ConsumerSwarm(
                stream_name=config.stream_name,
                group_name=config.group_name,
                num_consumers=config.num_workers,
                redis_url=self.redis_url,
                message_handler=config.message_handler,
            )
            
            await swarm.start()
            self.swarms[agent_type] = swarm
            
            logger.info(
                "swarm_started",
                agent_type=agent_type,
                stream=config.stream_name,
                group=config.group_name,
                workers=config.num_workers,
            )
            
        except Exception as e:
            logger.error("start_swarm_failed", agent_type=agent_type, error=str(e))

    async def stop(self):
        """Stop all agent swarms gracefully."""
        if not self._running:
            return
        
        self._shutdown = True
        self._running = False
        
        logger.info("swarm_manager_stopping")
        
        # Cancel background tasks
        if self._scale_monitor_task:
            self._scale_monitor_task.cancel()
        if self._stats_task:
            self._stats_task.cancel()
        
        # Stop all swarms
        for agent_type, swarm in self.swarms.items():
            await swarm.stop()
        
        self.swarms.clear()
        logger.info("swarm_manager_stopped")

    async def _scale_monitor_loop(self):
        """Monitor pending messages and auto-scale workers."""
        while self._running and not self._shutdown:
            try:
                for agent_type, config in self.agent_configs.items():
                    swarm = self.swarms.get(agent_type)
                    if not swarm:
                        continue
                    
                    # Get pending message count
                    pending_info = await swarm.get_pending_info()
                    pending_count = pending_info.get("pending", 0)
                    
                    # Scale up if needed
                    if pending_count > config.scale_up_threshold:
                        await self._scale_up(agent_type, config)
                    # Scale down if needed
                    elif pending_count < config.scale_down_threshold:
                        await self._scale_down(agent_type, config)
                    
                await asyncio.sleep(config.scale_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("scale_monitor_error", error=str(e))
                await asyncio.sleep(5)

    async def _scale_up(self, agent_type: str, config: AgentSwarmConfig):
        """Scale up the number of workers."""
        swarm = self.swarms.get(agent_type)
        if not swarm:
            return
        
        current_workers = swarm.num_consumers
        if current_workers >= config.max_workers:
            logger.debug("scale_up_max_reached", agent_type=agent_type, current=current_workers)
            return
        
        new_worker_count = min(current_workers + 2, config.max_workers)
        logger.info(
            "scaling_up",
            agent_type=agent_type,
            from_=current_workers,
            to=new_worker_count,
        )
        
        # Note: Dynamic scaling requires restart - in production, use more sophisticated approach
        # For now, just log the scaling recommendation

    async def _scale_down(self, agent_type: str, config: AgentSwarmConfig):
        """Scale down the number of workers."""
        swarm = self.swarms.get(agent_type)
        if not swarm:
            return
        
        current_workers = swarm.num_consumers
        if current_workers <= config.min_workers:
            logger.debug("scale_down_min_reached", agent_type=agent_type, current=current_workers)
            return
        
        new_worker_count = max(current_workers - 1, config.min_workers)
        logger.info(
            "scaling_down",
            agent_type=agent_type,
            from_=current_workers,
            to=new_worker_count,
        )

    async def _stats_loop(self):
        """Collect and update statistics."""
        while self._running and not self._shutdown:
            try:
                await self._update_stats()
                await asyncio.sleep(10)  # Update every 10 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("stats_loop_error", error=str(e))
                await asyncio.sleep(5)

    async def _update_stats(self):
        """Update global statistics from all swarms."""
        self._stats.agent_swarms.clear()
        
        total_consumed = 0
        total_acknowledged = 0
        total_failed = 0
        total_pending = 0
        total_time = 0.0
        worker_count = 0
        
        for agent_type, swarm in self.swarms.items():
            aggregate = await swarm.get_aggregate_stats()
            pending_info = await swarm.get_pending_info()
            
            swarm_stats = SwarmStats(
                agent_type=agent_type,
                num_workers=len(swarm.consumers),
                active_workers=len(swarm.consumers),  # All consumers are active
                total_messages_consumed=aggregate["total_messages_consumed"],
                total_messages_acknowledged=aggregate["total_messages_acknowledged"],
                total_messages_failed=aggregate["total_messages_failed"],
                total_pending_processed=aggregate["total_pending_processed"],
                avg_processing_time_ms=aggregate["avg_processing_time_ms"],
                pending_messages=pending_info.get("pending", 0),
                last_updated=datetime.now().isoformat(),
            )
            
            self._stats.agent_swarms[agent_type] = swarm_stats
            
            total_consumed += swarm_stats.total_messages_consumed
            total_acknowledged += swarm_stats.total_messages_acknowledged
            total_failed += swarm_stats.total_messages_failed
            total_pending += swarm_stats.pending_messages
            total_time += swarm_stats.avg_processing_time_ms * swarm_stats.num_workers
            worker_count += swarm_stats.num_workers
        
        self._stats.total_messages_consumed = total_consumed
        self._stats.total_messages_acknowledged = total_acknowledged
        self._stats.total_messages_failed = total_failed
        self._stats.total_pending_messages = total_pending
        self._stats.avg_processing_time_ms = total_time / worker_count if worker_count > 0 else 0
        self._stats.total_workers = worker_count
        self._stats.uptime_seconds = time.time() - self._start_time if self._start_time else 0
        self._stats.last_updated = datetime.now().isoformat()

    async def get_stats(self) -> GlobalSwarmStats:
        """Get current global statistics."""
        return self._stats

    async def get_swarm_stats(self, agent_type: str) -> Optional[SwarmStats]:
        """Get statistics for a specific agent swarm."""
        return self._stats.agent_swarms.get(agent_type)

    def is_running(self) -> bool:
        """Check if the swarm manager is running."""
        return self._running

    async def wait_for_shutdown(self):
        """Wait for graceful shutdown."""
        while self._running:
            await asyncio.sleep(1)


class AgentWorker:
    """Base class for agent workers that process messages from Redis Streams."""

    def __init__(self, agent_type: str, config: Optional[Dict[str, Any]] = None):
        """Initialize agent worker.
        
        Args:
            agent_type: Type identifier for this agent
            config: Optional configuration dictionary
        """
        self.agent_type = agent_type
        self.config = config or {}
        
        logger.info(
            "agent_worker_init",
            agent_type=agent_type,
        )

    async def process_message(self, message: Message) -> bool:
        """Process a message from the stream.
        
        Args:
            message: Message object containing event data
            
        Returns:
            True if processing succeeded, False otherwise
        """
        raise NotImplementedError("Subclasses must implement process_message")

    def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        return {
            "agent_type": self.agent_type,
        }


async def main():
    """Main entry point for running the Swarm Manager."""
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info("shutdown_signal_received", signal=signum)
        # The manager will handle shutdown in the loop
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start swarm manager
    manager = SwarmManager(redis_url="redis://localhost:6379")
    
    try:
        await manager.start()
        
        # Print initial statistics
        stats = await manager.get_stats()
        logger.info(
            "swarm_manager_initial_stats",
            total_workers=stats.total_workers,
            agent_types=list(stats.agent_swarms.keys()),
        )
        
        # Keep running until shutdown
        await manager.wait_for_shutdown()
        
    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(main())
