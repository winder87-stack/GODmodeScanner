#!/usr/bin/env python3
"""
Docker Container Spawner for GODMODESCANNER
Handles dynamic agent container lifecycle management
"""

import os
import json
import subprocess
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class ContainerConfig:
    """Configuration for spawning a container"""
    agent_id: str
    agent_type: str
    supervisor_id: str
    image: str
    network: str = "godmode_network"
    redis_url: str = "redis://redis:6379"
    volumes: Optional[Dict[str, str]] = None
    environment: Optional[Dict[str, str]] = None
    restart_policy: str = "no"

class DockerSpawner:
    """Manages Docker container lifecycle for subordinate agents"""

    def __init__(self, project_root: str = "/app"):
        self.project_root = project_root
        self.containers: Dict[str, str] = {}  # agent_id -> container_id
        self.image_map = {
            "transaction_monitor": "godmode/transaction-monitor:latest",
            "wallet_analyzer": "godmode/wallet-analyzer:latest",
            "pattern_recognition": "godmode/pattern-recognition:latest",
            "sybil_detection": "godmode/agent-template:latest",
            "risk_scoring": "godmode/agent-template:latest",
            "alert_manager": "godmode/agent-template:latest",
            "default": "godmode/agent-template:latest"
        }

    def spawn_container(self, config: ContainerConfig) -> Optional[str]:
        """
        Spawn a new Docker container for an agent

        Args:
            config: Container configuration

        Returns:
            Container ID if successful, None otherwise
        """
        try:
            # Build environment variables
            env_vars = {
                "REDIS_URL": config.redis_url,
                "AGENT_ID": config.agent_id,
                "AGENT_TYPE": config.agent_type,
                "SUPERVISOR_ID": config.supervisor_id,
                "PYTHONUNBUFFERED": "1"
            }

            if config.environment:
                env_vars.update(config.environment)

            # Build docker run command
            cmd = [
                "docker", "run",
                "-d",  # Detached mode
                "--name", f"godmode_{config.agent_type}_{config.agent_id[:8]}",
                "--network", config.network,
                "--restart", config.restart_policy
            ]

            # Add environment variables
            for key, value in env_vars.items():
                cmd.extend(["-e", f"{key}={value}"])

            # Add volume mounts
            default_volumes = {
                f"{self.project_root}/config": "/app/config:ro",
                f"{self.project_root}/logs": "/app/logs",
                f"{self.project_root}/data": "/app/data"
            }

            if config.volumes:
                default_volumes.update(config.volumes)

            for host_path, container_path in default_volumes.items():
                cmd.extend(["-v", f"{host_path}:{container_path}"])

            # Add image
            cmd.append(config.image)

            # Execute docker run
            logger.info(f"Spawning container: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                container_id = result.stdout.strip()
                self.containers[config.agent_id] = container_id
                logger.info(f"✅ Spawned container {container_id[:12]} for agent {config.agent_id}")
                return container_id
            else:
                logger.error(f"❌ Failed to spawn container: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"❌ Container spawn timeout for agent {config.agent_id}")
            return None
        except Exception as e:
            logger.error(f"❌ Error spawning container: {e}")
            return None

    def stop_container(self, agent_id: str, timeout: int = 10) -> bool:
        """
        Stop a running container

        Args:
            agent_id: Agent ID
            timeout: Graceful shutdown timeout in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            container_id = self.containers.get(agent_id)
            if not container_id:
                logger.warning(f"No container found for agent {agent_id}")
                return False

            # Stop container
            result = subprocess.run(
                ["docker", "stop", "-t", str(timeout), container_id],
                capture_output=True,
                text=True,
                timeout=timeout + 5
            )

            if result.returncode == 0:
                logger.info(f"✅ Stopped container {container_id[:12]} for agent {agent_id}")
                return True
            else:
                logger.error(f"❌ Failed to stop container: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"❌ Error stopping container: {e}")
            return False

    def remove_container(self, agent_id: str, force: bool = False) -> bool:
        """
        Remove a container

        Args:
            agent_id: Agent ID
            force: Force removal even if running

        Returns:
            True if successful, False otherwise
        """
        try:
            container_id = self.containers.get(agent_id)
            if not container_id:
                logger.warning(f"No container found for agent {agent_id}")
                return False

            # Remove container
            cmd = ["docker", "rm"]
            if force:
                cmd.append("-f")
            cmd.append(container_id)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                del self.containers[agent_id]
                logger.info(f"✅ Removed container {container_id[:12]} for agent {agent_id}")
                return True
            else:
                logger.error(f"❌ Failed to remove container: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"❌ Error removing container: {e}")
            return False

    def get_container_status(self, agent_id: str) -> Optional[Dict]:
        """
        Get container status

        Args:
            agent_id: Agent ID

        Returns:
            Container status dict or None
        """
        try:
            container_id = self.containers.get(agent_id)
            if not container_id:
                return None

            # Inspect container
            result = subprocess.run(
                ["docker", "inspect", container_id],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                inspect_data = json.loads(result.stdout)
                if inspect_data:
                    state = inspect_data[0].get("State", {})
                    return {
                        "container_id": container_id,
                        "status": state.get("Status"),
                        "running": state.get("Running", False),
                        "started_at": state.get("StartedAt"),
                        "finished_at": state.get("FinishedAt"),
                        "exit_code": state.get("ExitCode")
                    }
            return None

        except Exception as e:
            logger.error(f"❌ Error getting container status: {e}")
            return None

    def get_container_logs(self, agent_id: str, tail: int = 100) -> Optional[str]:
        """
        Get container logs

        Args:
            agent_id: Agent ID
            tail: Number of lines to retrieve

        Returns:
            Log output or None
        """
        try:
            container_id = self.containers.get(agent_id)
            if not container_id:
                return None

            result = subprocess.run(
                ["docker", "logs", "--tail", str(tail), container_id],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                return result.stdout
            return None

        except Exception as e:
            logger.error(f"❌ Error getting container logs: {e}")
            return None

    def restart_container(self, agent_id: str, timeout: int = 10) -> bool:
        """
        Restart a container

        Args:
            agent_id: Agent ID
            timeout: Restart timeout in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            container_id = self.containers.get(agent_id)
            if not container_id:
                logger.warning(f"No container found for agent {agent_id}")
                return False

            result = subprocess.run(
                ["docker", "restart", "-t", str(timeout), container_id],
                capture_output=True,
                text=True,
                timeout=timeout + 5
            )

            if result.returncode == 0:
                logger.info(f"✅ Restarted container {container_id[:12]} for agent {agent_id}")
                return True
            else:
                logger.error(f"❌ Failed to restart container: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"❌ Error restarting container: {e}")
            return False

    def cleanup_all(self, force: bool = True) -> int:
        """
        Cleanup all managed containers

        Args:
            force: Force removal even if running

        Returns:
            Number of containers cleaned up
        """
        count = 0
        for agent_id in list(self.containers.keys()):
            if self.stop_container(agent_id):
                if self.remove_container(agent_id, force=force):
                    count += 1
        return count

    def list_containers(self) -> List[Dict]:
        """
        List all managed containers with their status

        Returns:
            List of container info dicts
        """
        containers = []
        for agent_id, container_id in self.containers.items():
            status = self.get_container_status(agent_id)
            if status:
                status["agent_id"] = agent_id
                containers.append(status)
        return containers


if __name__ == "__main__":
    # Test the spawner
    logging.basicConfig(level=logging.INFO)

    spawner = DockerSpawner()

    # Test spawn
    config = ContainerConfig(
        agent_id="test_agent_001",
        agent_type="transaction_monitor",
        supervisor_id="supervisor_primary",
        image="godmode/transaction-monitor:latest"
    )

    container_id = spawner.spawn_container(config)
    if container_id:
        print(f"✅ Spawned container: {container_id[:12]}")

        # Wait a bit
        time.sleep(2)

        # Check status
        status = spawner.get_container_status("test_agent_001")
        print(f"📊 Status: {status}")

        # Get logs
        logs = spawner.get_container_logs("test_agent_001", tail=20)
        print(f"📝 Logs:\n{logs}")

        # Cleanup
        spawner.cleanup_all()
        print("✅ Cleanup complete")
