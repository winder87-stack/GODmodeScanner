#!/usr/bin/env python3
"""
Supervisor Agent - Enhanced with Docker Container Spawning
Manages subordinate agent lifecycle with support for both subprocess and Docker modes
"""

import os
import sys
import json
import time
import redis
import logging
import subprocess
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.docker_spawner import DockerSpawner, ContainerConfig

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class AgentMetrics:
    """Agent performance metrics"""
    agent_id: str
    agent_type: str
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    tasks_processed: int = 0
    errors: int = 0
    uptime_seconds: float = 0.0
    last_heartbeat: Optional[str] = None

@dataclass
class SupervisorConfig:
    """Supervisor configuration"""
    supervisor_id: str
    redis_url: str
    spawn_mode: str = "subprocess"  # "subprocess" or "docker"
    max_agents: int = 50
    heartbeat_interval: int = 10
    heartbeat_timeout: int = 30
    auto_scale: bool = True
    scale_up_threshold: float = 0.8
    scale_down_threshold: float = 0.3
    min_agents_per_type: int = 1
    max_agents_per_type: int = 10
    docker_network: str = "godmode_network"
    docker_project_root: str = "/app"

class SupervisorAgent:
    """Enhanced Supervisor Agent with Docker support"""

    def __init__(self, config: SupervisorConfig):
        self.config = config
        self.redis_client = redis.from_url(config.redis_url)
        self.pubsub = self.redis_client.pubsub()
        self.running = False

        # Agent registry
        self.agents: Dict[str, AgentMetrics] = {}
        self.agent_processes: Dict[str, subprocess.Popen] = {}  # For subprocess mode

        # Docker spawner (if in docker mode)
        self.docker_spawner = None
        if config.spawn_mode == "docker":
            self.docker_spawner = DockerSpawner(project_root=config.docker_project_root)
            logger.info("🐳 Docker spawning mode enabled")
        else:
            logger.info("🔧 Subprocess spawning mode enabled")

        # Subscribe to channels
        self.pubsub.subscribe(
            'agent_heartbeat',
            'agent_metrics',
            'supervisor_commands'
        )

        logger.info(f"✅ Supervisor {config.supervisor_id} initialized")

    def spawn_agent(self, agent_type: str, agent_id: Optional[str] = None) -> Optional[str]:
        """
        Spawn a new subordinate agent

        Args:
            agent_type: Type of agent to spawn
            agent_id: Optional agent ID (auto-generated if not provided)

        Returns:
            Agent ID if successful, None otherwise
        """
        if agent_id is None:
            agent_id = f"{agent_type}_{int(time.time()*1000)}"

        try:
            if self.config.spawn_mode == "docker":
                return self._spawn_docker_agent(agent_type, agent_id)
            else:
                return self._spawn_subprocess_agent(agent_type, agent_id)
        except Exception as e:
            logger.error(f"❌ Failed to spawn agent {agent_id}: {e}")
            return None

    def _spawn_docker_agent(self, agent_type: str, agent_id: str) -> Optional[str]:
        """
        Spawn agent as Docker container

        Args:
            agent_type: Type of agent
            agent_id: Agent ID

        Returns:
            Agent ID if successful, None otherwise
        """
        if not self.docker_spawner:
            logger.error("❌ Docker spawner not initialized")
            return None

        # Get image for agent type
        image = self.docker_spawner.image_map.get(
            agent_type,
            self.docker_spawner.image_map["default"]
        )

        # Create container config
        config = ContainerConfig(
            agent_id=agent_id,
            agent_type=agent_type,
            supervisor_id=self.config.supervisor_id,
            image=image,
            network=self.config.docker_network,
            redis_url=self.config.redis_url
        )

        # Spawn container
        container_id = self.docker_spawner.spawn_container(config)

        if container_id:
            # Register agent
            self.agents[agent_id] = AgentMetrics(
                agent_id=agent_id,
                agent_type=agent_type
            )

            # Store in Redis
            self.redis_client.hset(
                f"agent:{agent_id}",
                mapping={
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "supervisor_id": self.config.supervisor_id,
                    "state": "running",
                    "spawn_mode": "docker",
                    "container_id": container_id,
                    "started_at": datetime.utcnow().isoformat()
                }
            )

            logger.info(f"✅ Spawned Docker agent {agent_id} (container: {container_id[:12]})")
            return agent_id

        return None

    def _spawn_subprocess_agent(self, agent_type: str, agent_id: str) -> Optional[str]:
        """
        Spawn agent as subprocess

        Args:
            agent_type: Type of agent
            agent_id: Agent ID

        Returns:
            Agent ID if successful, None otherwise
        """
        # Map agent type to module
        agent_modules = {
            "transaction_monitor": "agents.transaction_monitor",
            "wallet_analyzer": "agents.wallet_analyzer_agent",
            "pattern_recognition": "agents.pattern_recognition_agent",
            "sybil_detection": "agents.sybil_detection_agent",
            "risk_scoring": "agents.risk_scoring_agent",
            "alert_manager": "agents.alert_manager_agent"
        }

        module = agent_modules.get(agent_type)
        if not module:
            logger.error(f"❌ Unknown agent type: {agent_type}")
            return None

        # Spawn subprocess
        env = os.environ.copy()
        env.update({
            "AGENT_ID": agent_id,
            "AGENT_TYPE": agent_type,
            "SUPERVISOR_ID": self.config.supervisor_id,
            "REDIS_URL": self.config.redis_url
        })

        try:
            process = subprocess.Popen(
                [sys.executable, "-m", module],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            self.agent_processes[agent_id] = process

            # Register agent
            self.agents[agent_id] = AgentMetrics(
                agent_id=agent_id,
                agent_type=agent_type
            )

            # Store in Redis
            self.redis_client.hset(
                f"agent:{agent_id}",
                mapping={
                    "agent_id": agent_id,
                    "agent_type": agent_type,
                    "supervisor_id": self.config.supervisor_id,
                    "state": "running",
                    "spawn_mode": "subprocess",
                    "pid": process.pid,
                    "started_at": datetime.utcnow().isoformat()
                }
            )

            logger.info(f"✅ Spawned subprocess agent {agent_id} (PID: {process.pid})")
            return agent_id

        except Exception as e:
            logger.error(f"❌ Failed to spawn subprocess: {e}")
            return None

    def stop_agent(self, agent_id: str) -> bool:
        """
        Stop a running agent

        Args:
            agent_id: Agent ID

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.config.spawn_mode == "docker" and self.docker_spawner:
                success = self.docker_spawner.stop_container(agent_id)
                if success:
                    self.docker_spawner.remove_container(agent_id)
            else:
                process = self.agent_processes.get(agent_id)
                if process:
                    process.terminate()
                    process.wait(timeout=10)
                    del self.agent_processes[agent_id]
                    success = True
                else:
                    success = False

            if success:
                # Update Redis
                self.redis_client.hset(f"agent:{agent_id}", "state", "stopped")
                self.redis_client.hset(f"agent:{agent_id}", "stopped_at", datetime.utcnow().isoformat())

                # Remove from local registry
                if agent_id in self.agents:
                    del self.agents[agent_id]

                logger.info(f"✅ Stopped agent {agent_id}")

            return success

        except Exception as e:
            logger.error(f"❌ Failed to stop agent {agent_id}: {e}")
            return False

    def get_agent_status(self, agent_id: str) -> Optional[Dict]:
        """
        Get agent status

        Args:
            agent_id: Agent ID

        Returns:
            Status dict or None
        """
        if self.config.spawn_mode == "docker" and self.docker_spawner:
            return self.docker_spawner.get_container_status(agent_id)
        else:
            process = self.agent_processes.get(agent_id)
            if process:
                return {
                    "agent_id": agent_id,
                    "running": process.poll() is None,
                    "pid": process.pid
                }
        return None

    def handle_heartbeat(self, message: Dict):
        """
        Handle agent heartbeat

        Args:
            message: Heartbeat message
        """
        agent_id = message.get('agent_id')
        if agent_id and agent_id in self.agents:
            self.agents[agent_id].last_heartbeat = datetime.utcnow().isoformat()

    def handle_metrics(self, message: Dict):
        """
        Handle agent metrics

        Args:
            message: Metrics message
        """
        agent_id = message.get('agent_id')
        if agent_id and agent_id in self.agents:
            metrics = self.agents[agent_id]
            metrics.cpu_percent = message.get('cpu_percent', 0.0)
            metrics.memory_mb = message.get('memory_mb', 0.0)
            metrics.tasks_processed = message.get('tasks_processed', 0)
            metrics.errors = message.get('errors', 0)

    def run(self):
        """
        Main supervisor loop
        """
        self.running = True
        logger.info(f"🚀 Supervisor {self.config.supervisor_id} started")

        try:
            while self.running:
                # Process messages
                message = self.pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    channel = message['channel'].decode('utf-8')
                    data = json.loads(message['data'])

                    if channel == 'agent_heartbeat':
                        self.handle_heartbeat(data)
                    elif channel == 'agent_metrics':
                        self.handle_metrics(data)
                    elif channel == 'supervisor_commands':
                        self.handle_command(data)

                time.sleep(0.1)

        except KeyboardInterrupt:
            logger.info("⚠️ Received shutdown signal")
        finally:
            self.shutdown()

    def handle_command(self, command: Dict):
        """
        Handle supervisor command

        Args:
            command: Command dict
        """
        cmd_type = command.get('type')

        if cmd_type == 'spawn':
            agent_type = command.get('agent_type')
            self.spawn_agent(agent_type)
        elif cmd_type == 'stop':
            agent_id = command.get('agent_id')
            self.stop_agent(agent_id)
        elif cmd_type == 'status':
            self.publish_status()

    def publish_status(self):
        """
        Publish supervisor status
        """
        status = {
            'supervisor_id': self.config.supervisor_id,
            'spawn_mode': self.config.spawn_mode,
            'agent_count': len(self.agents),
            'agents': [asdict(m) for m in self.agents.values()],
            'timestamp': datetime.utcnow().isoformat()
        }

        self.redis_client.publish('supervisor_status', json.dumps(status))

    def shutdown(self):
        """
        Graceful shutdown
        """
        logger.info("🛑 Shutting down supervisor...")

        # Stop all agents
        for agent_id in list(self.agents.keys()):
            self.stop_agent(agent_id)

        # Cleanup Docker containers if needed
        if self.docker_spawner:
            self.docker_spawner.cleanup_all()

        self.running = False
        logger.info("✅ Supervisor shutdown complete")


if __name__ == "__main__":
    # Load config
    config = SupervisorConfig(
        supervisor_id=os.getenv('SUPERVISOR_ID', 'supervisor_primary'),
        redis_url=os.getenv('REDIS_URL', 'redis://localhost:6379'),
        spawn_mode=os.getenv('SPAWN_MODE', 'subprocess'),
        docker_network=os.getenv('DOCKER_NETWORK', 'godmode_network'),
        docker_project_root=os.getenv('DOCKER_PROJECT_ROOT', '/app')
    )

    # Create and run supervisor
    supervisor = SupervisorAgent(config)
    supervisor.run()
