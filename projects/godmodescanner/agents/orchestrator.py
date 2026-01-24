#!/usr/bin/env python3
"""
GODMODESCANNER Enhanced Orchestrator

Transformed into a Supervisor Agent Factory that:
- Creates and manages supervisor agents
- Provides high-level coordination across multiple supervisors
- Implements multi-supervisor orchestration for massive scale
- Handles cross-supervisor communication and load balancing
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

try:
    import redis.asyncio as redis
except ImportError:
    import redis

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.supervisor_agent import SupervisorAgent, AgentRegistry

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OrchestratorConfig:
    """Orchestrator configuration"""

    def __init__(self, config_path: Optional[str] = None):
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: Optional[str]) -> dict:
        """Load orchestrator configuration"""
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)

        # Default configuration
        return {
            "redis_url": "redis://localhost:6379",
            "max_supervisors": 3,
            "supervisor_distribution": "round_robin",  # or "load_balanced"
            "enable_cross_supervisor_communication": True,
            "orchestrator_id": "orchestrator_main",
            "monitoring": {
                "enabled": True,
                "interval_seconds": 60,
                "metrics_retention_hours": 24
            },
            "supervisor_configs": [
                {
                    "supervisor_id": "supervisor_primary",
                    "config_path": "/a0/usr/projects/godmodescanner/config/supervisor.json",
                    "priority": 1,
                    "agent_types": ["transaction_monitor", "wallet_analyzer"]
                },
                {
                    "supervisor_id": "supervisor_secondary",
                    "config_path": "/a0/usr/projects/godmodescanner/config/supervisor.json",
                    "priority": 2,
                    "agent_types": ["pattern_recognition", "sybil_detection"]
                },
                {
                    "supervisor_id": "supervisor_tertiary",
                    "config_path": "/a0/usr/projects/godmodescanner/config/supervisor.json",
                    "priority": 3,
                    "agent_types": ["risk_scoring", "alert_manager"]
                }
            ]
        }


class SupervisorFactory:
    """Factory for creating and managing supervisor agents"""

    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.supervisors: Dict[str, SupervisorAgent] = {}
        self.supervisor_tasks: Dict[str, asyncio.Task] = {}
        self.redis_client = None
        self.registry = None

    async def initialize(self):
        """Initialize factory and Redis connection"""
        try:
            self.redis_client = redis.from_url(
                self.config.config["redis_url"],
                decode_responses=True
            )
            await self.redis_client.ping()
            self.registry = AgentRegistry(self.redis_client)
            logger.info("Supervisor factory initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize factory: {e}")
            return False

    async def create_supervisor(
        self,
        supervisor_id: str,
        config_path: Optional[str] = None,
        agent_types: Optional[List[str]] = None
    ) -> Optional[SupervisorAgent]:
        """Create a new supervisor agent"""
        try:
            # Create supervisor instance
            supervisor = SupervisorAgent(
                redis_url=self.config.config["redis_url"],
                config_path=config_path
            )

            # Override supervisor ID
            supervisor.supervisor_id = supervisor_id

            # Filter agent configs if specific types requested
            if agent_types:
                filtered_configs = {
                    k: v for k, v in supervisor.config["agent_configs"].items()
                    if k in agent_types
                }
                supervisor.config["agent_configs"] = filtered_configs

            # Initialize supervisor
            if not await supervisor.initialize():
                logger.error(f"Failed to initialize supervisor {supervisor_id}")
                return None

            # Store supervisor
            self.supervisors[supervisor_id] = supervisor

            logger.info(f"Created supervisor {supervisor_id}")
            return supervisor

        except Exception as e:
            logger.error(f"Failed to create supervisor {supervisor_id}: {e}")
            return None

    async def start_supervisor(self, supervisor_id: str) -> bool:
        """Start a supervisor agent"""
        try:
            supervisor = self.supervisors.get(supervisor_id)
            if not supervisor:
                logger.error(f"Supervisor {supervisor_id} not found")
                return False

            # Create task for supervisor
            task = asyncio.create_task(supervisor.start())
            self.supervisor_tasks[supervisor_id] = task

            logger.info(f"Started supervisor {supervisor_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to start supervisor {supervisor_id}: {e}")
            return False

    async def stop_supervisor(self, supervisor_id: str) -> bool:
        """Stop a supervisor agent"""
        try:
            supervisor = self.supervisors.get(supervisor_id)
            if supervisor:
                await supervisor.shutdown()

            task = self.supervisor_tasks.get(supervisor_id)
            if task:
                task.cancel()
                del self.supervisor_tasks[supervisor_id]

            logger.info(f"Stopped supervisor {supervisor_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop supervisor {supervisor_id}: {e}")
            return False


class Orchestrator:
    """Main orchestrator that manages multiple supervisor agents"""

    def __init__(self, config_path: Optional[str] = None):
        self.config = OrchestratorConfig(config_path)
        self.factory = SupervisorFactory(self.config)
        self.running = False
        self.orchestrator_id = self.config.config["orchestrator_id"]

        logger.info(f"Orchestrator {self.orchestrator_id} initialized")

    async def initialize(self):
        """Initialize orchestrator"""
        logger.info("Initializing orchestrator...")

        if not await self.factory.initialize():
            logger.error("Failed to initialize supervisor factory")
            return False

        # Create supervisors from config
        for supervisor_config in self.config.config["supervisor_configs"]:
            supervisor_id = supervisor_config["supervisor_id"]
            config_path = supervisor_config.get("config_path")
            agent_types = supervisor_config.get("agent_types")

            supervisor = await self.factory.create_supervisor(
                supervisor_id,
                config_path,
                agent_types
            )

            if not supervisor:
                logger.error(f"Failed to create supervisor {supervisor_id}")
                continue

        logger.info("Orchestrator initialized successfully")
        return True

    async def start_all_supervisors(self):
        """Start all configured supervisors"""
        logger.info("Starting all supervisors...")

        for supervisor_id in self.factory.supervisors.keys():
            await self.factory.start_supervisor(supervisor_id)
            await asyncio.sleep(2)  # Stagger startup

        logger.info("All supervisors started")

    async def monitor_supervisors(self):
        """Monitor supervisor health and performance"""
        logger.info("Starting supervisor monitoring...")

        while self.running:
            try:
                for supervisor_id, supervisor in self.factory.supervisors.items():
                    # Get supervisor status
                    status = await supervisor.get_system_status()

                    logger.info(
                        f"Supervisor {supervisor_id}: "
                        f"{status.get('total_agents', 0)} agents, "
                        f"States: {dict(status.get('agents_by_state', {}))}"
                    )

                # Wait before next check
                interval = self.config.config["monitoring"]["interval_seconds"]
                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Error in supervisor monitoring: {e}")
                await asyncio.sleep(10)

    async def get_global_status(self) -> dict:
        """Get status across all supervisors"""
        try:
            global_status = {
                "orchestrator_id": self.orchestrator_id,
                "timestamp": datetime.utcnow().isoformat(),
                "supervisors": {},
                "total_agents": 0,
                "agents_by_type": {},
                "agents_by_state": {}
            }

            for supervisor_id, supervisor in self.factory.supervisors.items():
                status = await supervisor.get_system_status()
                global_status["supervisors"][supervisor_id] = status
                global_status["total_agents"] += status.get("total_agents", 0)

                # Aggregate by type
                for agent_type, count in status.get("agents_by_type", {}).items():
                    global_status["agents_by_type"][agent_type] =                         global_status["agents_by_type"].get(agent_type, 0) + count

                # Aggregate by state
                for state, count in status.get("agents_by_state", {}).items():
                    global_status["agents_by_state"][state] =                         global_status["agents_by_state"].get(state, 0) + count

            return global_status

        except Exception as e:
            logger.error(f"Failed to get global status: {e}")
            return {"error": str(e)}

    async def start(self):
        """Start orchestrator"""
        logger.info("="*80)
        logger.info("GODMODESCANNER ORCHESTRATOR STARTING")
        logger.info("="*80)

        # Initialize
        if not await self.initialize():
            logger.error("Failed to initialize orchestrator")
            return

        self.running = True

        # Start all supervisors
        await self.start_all_supervisors()

        # Start monitoring if enabled
        if self.config.config["monitoring"]["enabled"]:
            monitor_task = asyncio.create_task(self.monitor_supervisors())

        logger.info("="*80)
        logger.info("ORCHESTRATOR RUNNING - Press Ctrl+C to stop")
        logger.info("="*80)

        try:
            # Keep running
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Shutdown orchestrator and all supervisors"""
        logger.info("Shutting down orchestrator...")

        self.running = False

        # Stop all supervisors
        for supervisor_id in list(self.factory.supervisors.keys()):
            await self.factory.stop_supervisor(supervisor_id)

        # Close Redis connection
        if self.factory.redis_client:
            await self.factory.redis_client.close()

        logger.info("Orchestrator shutdown complete")


if __name__ == "__main__":
    # Create and run orchestrator
    orchestrator = Orchestrator(
        config_path="/a0/usr/projects/godmodescanner/config/orchestrator.json"
    )

    try:
        asyncio.run(orchestrator.start())
    except KeyboardInterrupt:
        logger.info("Orchestrator terminated by user")
