
"""Memory Consolidation Agent for autonomous periodic memory processing."""

import asyncio
import signal
from typing import Optional, Dict, Any
from datetime import datetime
import structlog

from redis import Redis
from .memory.storage import MemoryStorage
from .memory.consolidators.consolidator import MemoryConsolidator
from .memory.memory_models import Memory, MemoryType, MemoryImportance

logger = structlog.get_logger(__name__)


class MemoryConsolidationAgent:
    """Autonomous agent that runs memory consolidation on a schedule.

    This agent provides the "eternal mind" capability by:
    - Processing raw memories from Redis queue (memory:raw)
    - Consolidating and merging similar patterns
    - Extracting high-level insights from episodic memories
    - Decaying old, low-value memories
    - Persisting important patterns and King Maker profiles to disk
    - Running every hour to maintain continuous learning

    The system retains knowledge across restarts through disk persistence.
    """

    def __init__(
        self,
        storage_path: Optional[str] = None,
        redis_client: Optional[Redis] = None,
        consolidation_interval_hours: int = 1
    ):
        """Initialize the Memory Consolidation Agent.

        Args:
            storage_path: Path to memory storage directory
            redis_client: Redis client for raw memory queue
            consolidation_interval_hours: Hours between consolidation runs (default: 1 hour)
        """
        # Initialize storage (loads existing memories from disk on startup)
        self.storage = MemoryStorage(storage_path=storage_path)

        # Initialize Redis client
        self.redis = redis_client or Redis(host='localhost', port=6379, db=0, decode_responses=True)

        # Initialize consolidator
        self.consolidator = MemoryConsolidator(
            storage=self.storage,
            redis_client=self.redis,
            config={
                'consolidation_interval_hours': consolidation_interval_hours,
                'importance_decay_rate': 0.95,
                'min_importance_to_keep': MemoryImportance.LOW,
                'max_memories': 10000,
                'pattern_detection_enabled': True,
                'similarity_threshold': 0.85,
                'batch_size': 100
            }
        )

        self.consolidation_interval = consolidation_interval_hours * 3600  # Convert to seconds
        self.running = False
        self.shutdown_event = asyncio.Event()
        self.consolidation_count = 0

        logger.info(
            "Memory Consolidation Agent initialized",
            storage_path=str(self.storage.storage_path),
            interval_hours=consolidation_interval_hours,
            existing_memories=len(self.storage.memories)
        )

    async def start(self):
        """Start the memory consolidation agent.

        Begins the consolidation loop that:
        1. Processes raw memories from Redis
        2. Consolidates and merges patterns
        3. Extracts insights
        4. Decays and prunes old memories
        5. Persists to disk
        6. Sleeps for configured interval

        This runs continuously until stop() is called.
        """
        if self.running:
            logger.warning("Consolidation agent already running")
            return

        self.running = True
        self.shutdown_event.clear()

        logger.info(
            "Starting Memory Consolidation Agent",
            interval_seconds=self.consolidation_interval
        )

        # Initial consolidation on startup
        logger.info("Running initial consolidation on startup...")
        await self._run_consolidation_cycle()

        # Main consolidation loop
        while self.running and not self.shutdown_event.is_set():
            try:
                # Wait for consolidation interval or shutdown signal
                await asyncio.wait_for(
                    self.shutdown_event.wait(),
                    timeout=self.consolidation_interval
                )

                if self.shutdown_event.is_set():
                    break

            except asyncio.TimeoutError:
                # Interval elapsed, run consolidation
                await self._run_consolidation_cycle()
            except Exception as e:
                logger.error(f"Consolidation loop error: {e}", exc_info=True)
                # Continue running despite errors
                await asyncio.sleep(60)  # Brief pause before retry

        logger.info("Memory Consolidation Agent stopped")

    async def _run_consolidation_cycle(self):
        """Run a single consolidation cycle."""
        cycle_start = datetime.now()
        logger.info(f"Starting consolidation cycle #{self.consolidation_count + 1}")

        try:
            # Run consolidation through the consolidator
            report = await self.consolidator.consolidate()

            self.consolidation_count += 1

            # Log detailed report
            logger.info(
                f"Consolidation cycle #{self.consolidation_count} completed",
                raw_processed=report.get('raw_memories_processed', 0),
                patterns_merged=report.get('patterns_merged', 0),
                patterns_extracted=report.get('patterns_extracted', 0),
                memories_decayed=report.get('memories_decayed', 0),
                memories_pruned=report.get('memories_pruned', 0),
                duration_seconds=(datetime.now() - cycle_start).total_seconds()
            )

            # Persist to disk (also done by consolidator, but ensure it happens)
            saved_count = self.storage.persist_memory_to_disk()
            logger.info(f"Persisted {saved_count} memories to disk")

        except Exception as e:
            logger.error(f"Consolidation cycle failed: {e}", exc_info=True)

    async def stop(self):
        """Stop the memory consolidation agent gracefully."""
        if not self.running:
            logger.warning("Consolidation agent not running")
            return

        logger.info("Stopping Memory Consolidation Agent...")
        self.running = False
        self.shutdown_event.set()

        # Run final consolidation on shutdown
        logger.info("Running final consolidation before shutdown...")
        await self._run_consolidation_cycle()

        logger.info("Memory Consolidation Agent stopped gracefully")

    def get_status(self) -> Dict[str, Any]:
        """Get current status of the consolidation agent.

        Returns:
            Status dictionary with statistics
        """
        return {
            'running': self.running,
            'consolidation_count': self.consolidation_count,
            'consolidation_interval_hours': self.consolidation_interval / 3600,
            'storage_stats': self.storage.get_statistics(),
            'storage_path': str(self.storage.storage_path),
            'redis_connected': self.redis.ping() if self.redis else False
        }

    async def add_raw_memory(self, memory_data: Dict[str, Any]):
        """Add a raw memory to the processing queue.

        This is called by other agents to add memories for consolidation.

        Args:
            memory_data: Dictionary representation of a memory
        """
        try:
            import json
            self.redis.rpush('memory:raw', json.dumps(memory_data))
            logger.debug("Added raw memory to consolidation queue")
        except Exception as e:
            logger.error(f"Failed to add raw memory: {e}")

    async def manual_consolidation(self) -> Dict[str, Any]:
        """Trigger a manual consolidation cycle.

        Returns:
            Consolidation report
        """
        logger.info("Running manual consolidation...")
        await self._run_consolidation_cycle()
        return self.get_status()


# Standalone entry point for testing/running as separate process
async def main():
    """Run the Memory Consolidation Agent as a standalone service."""
    agent = MemoryConsolidationAgent(
        storage_path="/a0/usr/projects/godmodescanner/data/memory",
        redis_client=Redis(host='localhost', port=6379, db=0, decode_responses=True),
        consolidation_interval_hours=1
    )

    # Setup graceful shutdown
    def signal_handler():
        logger.info("Shutdown signal received")
        asyncio.create_task(agent.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda s, f: signal_handler())

    # Start the agent
    await agent.start()


if __name__ == "__main__":
    asyncio.run(main())
