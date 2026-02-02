#!/usr/bin/env python3
"""GODMODESCANNER Main Entry Point

Integrates:
- MCP Orchestrator (existing multi-agent coordination)
- PumpFunDetectorAgent (native RPC-based pump.fun monitoring)
- Redis Cluster (high-throughput data streams)
- Backpressure Monitor (load management)

NO-COST Pump.fun Engine Enabled
"""

import asyncio
import signal
import sys
from pathlib import Path

import structlog

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from agents.pump_fun_detector_agent import PumpFunDetectorAgent
from agents.orchestrator import Orchestrator
from utils.redis_cluster_client import GuerrillaRedisCluster as RedisClusterClient
from utils.backpressure_monitor import BackpressureMonitor

logger = structlog.get_logger(__name__)


class GODMODESCANNERMain:
    """GODMODESCANNER Main Orchestrator
    
    Coordinates all system components:
    - MCP Orchestrator: Manages 47+ specialized agents
    - PumpFunDetectorAgent: Native RPC pump.fun monitoring
    - Redis Cluster: High-throughput data streams
    - Backpressure Monitor: Load management
    """

    def __init__(self):
        self.orchestrator = Orchestrator()  # Existing MCP orchestrator
        self.pump_fun_detector = PumpFunDetectorAgent()  # New pump.fun detector
        self.redis_cluster = RedisClusterClient()  # Guerrilla Redis Cluster
        self.backpressure_monitor = BackpressureMonitor()  # Backpressure monitoring
        self.shutdown_event = asyncio.Event()
        self._tasks = []

    async def start(self):
        """Start GODMODESCANNER with pump.fun detection."""
        logger.info(
            "godmode_starting",
            version="GODMODESCANNER Elite",
            components=[
                "MCP Orchestrator",
                "PumpFunDetectorAgent (Native RPC)",
                "Guerrilla Redis Cluster (6 nodes)",
                "Backpressure Monitor"
            ]
        )

        # Initialize Redis Cluster connection
        try:
            await self.redis_cluster.initialize()
            logger.info("redis_cluster_connected", nodes=6)
        except Exception as e:
            logger.error("redis_cluster_init_failed", error=str(e))
            raise

        # Create consumer groups for streams
        await self._setup_redis_streams()

        # Start all components
        self._tasks = [
            asyncio.create_task(self.orchestrator.start()),  # Existing MCP orchestration
            asyncio.create_task(self.pump_fun_detector.run()),  # New pump.fun detector
            asyncio.create_task(self._run_backpressure_monitor()),  # Backpressure monitoring wrapper
            asyncio.create_task(self.shutdown_handler())  # Graceful shutdown
        ]

        logger.info(
            "godmode_running",
            monitoring="ALL pump.fun tokens",
            detection_latency="<1 second",
            alert_latency="~15.65μs"
        )

        # Wait for any task to complete (usually shutdown)
        done, pending = await asyncio.wait(
            self._tasks,
            return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel pending tasks on shutdown
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _run_backpressure_monitor(self):
        """Wrapper for backpressure monitor start."""
        await self.backpressure_monitor.connect()
        await self.backpressure_monitor.start()

    async def _setup_redis_streams(self):
        """Setup Redis Streams consumer groups."""
        logger.info("setting_up_redis_streams")

        streams_config = {
            "godmode:new_transactions": [
                "wallet-analyzer-group",
                "pattern-recognition-group",
                "sybil-detection-group"
            ],
            "godmode:new_tokens": [
                "early-detection-group",
                "funding-hub-group"
            ],
            "godmode:early_detection": [
                "graph-traversal-group",
                "risk-scoring-group"
            ]
        }

        for stream, groups in streams_config.items():
            for group in groups:
                try:
                    await self.redis_cluster.create_consumer_group(
                        stream=stream,
                        group_name=group
                    )
                    logger.info(
                        "consumer_group_created",
                        stream=stream,
                        group=group
                    )
                except Exception as e:
                    if "BUSYGROUP" not in str(e):
                        logger.warning(
                            "consumer_group_error",
                            stream=stream,
                            group=group,
                            error=str(e)
                        )

    async def shutdown_handler(self):
        """Graceful shutdown on SIGINT/SIGTERM."""
        loop = asyncio.get_event_loop()

        def signal_handler():
            logger.info("shutdown_signal_received")
            self.shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        await self.shutdown_event.wait()

        logger.info("graceful_shutdown_initiated")

        # Stop all components
        await self.orchestrator.shutdown()
        await self.pump_fun_detector.stop()
        await self.backpressure_monitor.stop()
        await self.redis_cluster.close()

        logger.info("godmode_stopped_gracefully")

    async def stop(self):
        """Manually stop the system."""
        self.shutdown_event.set()


async def main():
    """Main entry point."""
    godmode = GODMODESCANNERMain()
    
    try:
        await godmode.start()
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
        await godmode.stop()
    except Exception as e:
        logger.error("fatal_error", error=str(e), exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
