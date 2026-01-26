#!/usr/bin/env python3
"""Swarm Manager - Coordinate parallel worker instances.

This module manages the lifecycle of parallel worker instances:
- Creates consumer groups for worker types
- Spawns multiple worker instances
- Manages worker health and restarts
- Provides worker statistics aggregation
- Handles graceful shutdown
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
import structlog

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agents.workers.wallet_analyzer_worker import WalletAnalyzerWorker
from agents.workers.pattern_recognition_worker import PatternRecognitionWorker
from agents.workers.sybil_detection_worker import SybilDetectionWorker
from utils.redis_streams_consumer import AgentWorker
from utils.redis_streams_producer import RedisStreamsProducer

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger(__name__)

# Worker types mapping
WORKER_TYPES = {
    "wallet-analyzer": WalletAnalyzerWorker,
    "pattern-recognition": PatternRecognitionWorker,
    "sybil-detection": SybilDetectionWorker,
}

# Consumer group names
CONSUMER_GROUPS = {
    "wallet-analyzer": "wallet-analyzer-group",
    "pattern-recognition": "pattern-recognition-group",
    "sybil-detection": "sybil-detection-group",
}


class SwarmManager:
    """Manage a swarm of parallel workers.
    
    This class manages the lifecycle of worker instances:
    - Creates consumer groups if needed
    - Spawns multiple worker instances
    - Manages worker health and restarts
    - Provides worker statistics aggregation
    - Handles graceful shutdown
    """

    def __init__(self, worker_type: str, redis_url: str = "redis://localhost:6379"):
        """Initialize swarm manager.
        
        Args:
            worker_type: Type of workers to manage (wallet-analyzer, pattern-recognition, sybil-detection)
            redis_url: Redis connection URL
        """
        self.worker_type = worker_type
        self.redis_url = redis_url
        self.consumer_group = CONSUMER_GROUPS.get(worker_type)
        
        # Worker class
        self.worker_class = WORKER_TYPES.get(worker_type)
        if not self.worker_class:
            raise ValueError(f"Unknown worker type: {worker_type}")
        
        # Workers
        self.workers: List[AgentWorker] = []
        
        # Stats
        self.stats = {
            "worker_type": worker_type,
            "worker_count": 0,
            "active_workers": 0,
            "total_processed": 0,
            "total_errors": 0,
        }
        
        # State
        self._running = False
        self._health_task: Optional[asyncio.Task] = None
        
        logger.info(
            "swarm_manager_init",
            worker_type=worker_type,
            consumer_group=self.consumer_group,
            redis_url=redis_url,
        )

    async def create_consumer_group(self):
        """Create consumer group if it doesn't exist."""
        try:
            from redis.asyncio import Redis as AsyncRedis
            from redis.asyncio.connection import ConnectionPool
            
            pool = ConnectionPool.from_url(self.redis_url, decode_responses=False)
            redis = AsyncRedis(connection_pool=pool)
            
            # Try to create consumer group
            try:
                await redis.xgroup_create(
                    "godmode:new_transactions",
                    self.consumer_group,
                    id="0",
                    mkstream=True
                )
                logger.info("consumer_group_created", group=self.consumer_group)
            except Exception as e:
                if "BUSYGROUP" not in str(e):
                    raise
                logger.info("consumer_group_exists", group=self.consumer_group)
            
            await redis.close()
            await pool.disconnect()
        
        except Exception as e:
            logger.error("create_consumer_group_error", error=str(e))

    async def spawn_workers(self, count: int, offset: int = 1):
        """Spawn worker instances.
        
        Args:
            count: Number of workers to spawn
            offset: Starting ID offset
        """
        logger.info("spawning_workers", count=count, offset=offset)
        
        for i in range(count):
            worker_id = f"{self.worker_type}-{offset + i}"
            worker = self.worker_class(worker_id=worker_id, redis_url=self.redis_url)
            self.workers.append(worker)
        
        self.stats["worker_count"] = len(self.workers)
        logger.info("workers_spawned", total=len(self.workers))

    async def start(self):
        """Start all workers."""
        logger.info("starting_swarm", workers=len(self.workers))
        
        # Initialize all workers
        for worker in self.workers:
            await worker.initialize()
        
        # Start processing loops
        tasks = [worker.run() for worker in self.workers]
        self._running = True
        
        # Start health monitoring
        self._health_task = asyncio.create_task(self._health_loop())
        
        # Wait for all workers
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _health_loop(self):
        """Monitor worker health."""
        while self._running:
            try:
                active = sum(1 for w in self.workers if w.is_running())
                self.stats["active_workers"] = active
                
                total_processed = sum(
                    (await w.get_stats()).get("transactions_processed", 0)
                    for w in self.workers
                )
                self.stats["total_processed"] = total_processed
                
                logger.debug(
                    "swarm_health",
                    active=active,
                    total=len(self.workers),
                    processed=total_processed,
                )
                
                await asyncio.sleep(10)
            
            except Exception as e:
                logger.error("health_loop_error", error=str(e))
                await asyncio.sleep(10)

    async def stop(self):
        """Stop all workers."""
        logger.info("stopping_swarm")
        self._running = False
        
        # Cancel health task
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        
        # Stop all workers
        for worker in self.workers:
            await worker.close()
        
        logger.info("swarm_stopped")

    async def get_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics."""
        return self.stats.copy()

    async def get_worker_stats(self) -> List[Dict[str, Any]]:
        """Get statistics for each worker."""
        return [await w.get_stats() for w in self.workers]


async def start_worker_swarm(worker_type: str, redis_url: str, count: int = 1, offset: int = 1):
    """Convenience function to start a worker swarm.
    
    Args:
        worker_type: Type of workers (wallet-analyzer, pattern-recognition, sybil-detection)
        redis_url: Redis connection URL
        count: Number of workers
        offset: Starting ID offset
    """
    manager = SwarmManager(worker_type=worker_type, redis_url=redis_url)
    
    try:
        # Create consumer group
        await manager.create_consumer_group()
        
        # Spawn workers
        await manager.spawn_workers(count=count, offset=offset)
        
        # Start workers
        await manager.start()
    
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    finally:
        await manager.stop()


async def main():
    """Main entry point for testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Swarm Manager")
    parser.add_argument("worker-type", choices=["wallet-analyzer", "pattern-recognition", "sybil-detection"])
    parser.add_argument("--redis-url", default="redis://localhost:6379")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--offset", type=int, default=1)
    args = parser.parse_args()
    
    await start_worker_swarm(
        worker_type=getattr(args, "worker_type"),
        redis_url=args.redis_url,
        count=args.count,
        offset=args.offset,
    )


if __name__ == "__main__":
    asyncio.run(main())
