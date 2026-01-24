#!/usr/bin/env python3
"""
GODMODESCANNER Agent Base Class

Base class for all subordinate agents that provides:
- Automatic heartbeat reporting to supervisor
- Metrics collection and reporting
- Redis pub/sub integration
- Graceful shutdown handling
- Health monitoring
"""

import asyncio
import json
import logging
import os
import signal
import sys
from abc import ABC, abstractmethod
from collections import deque
from datetime import datetime
from typing import Optional, Dict, Any

try:
    import redis.asyncio as redis
except ImportError:
    import redis

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class AgentMetrics:
    """Agent metrics tracker"""

    def __init__(self):
        self.tasks_processed = 0
        self.tasks_queued = 0
        self.tasks_failed = 0
        self.processing_times = deque(maxlen=100)
        self.error_count = 0
        self.start_time = datetime.utcnow()

    def record_task_start(self):
        """Record task start"""
        self.tasks_queued += 1

    def record_task_complete(self, processing_time_ms: float):
        """Record task completion"""
        self.tasks_processed += 1
        self.tasks_queued = max(0, self.tasks_queued - 1)
        self.processing_times.append(processing_time_ms)

    def record_task_failed(self):
        """Record task failure"""
        self.tasks_failed += 1
        self.tasks_queued = max(0, self.tasks_queued - 1)
        self.error_count += 1

    def get_avg_processing_time(self) -> float:
        """Get average processing time"""
        if not self.processing_times:
            return 0.0
        return sum(self.processing_times) / len(self.processing_times)

    def get_uptime_seconds(self) -> int:
        """Get uptime in seconds"""
        return int((datetime.utcnow() - self.start_time).total_seconds())

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "tasks_processed": self.tasks_processed,
            "tasks_queued": self.tasks_queued,
            "tasks_failed": self.tasks_failed,
            "avg_processing_time": self.get_avg_processing_time(),
            "error_count": self.error_count,
            "uptime_seconds": self.get_uptime_seconds(),
            "last_updated": datetime.utcnow().isoformat()
        }


class BaseAgent(ABC):
    """Base class for all GODMODESCANNER subordinate agents"""

    def __init__(
        self,
        agent_type: str,
        redis_url: str = "redis://localhost:6379",
        heartbeat_interval: int = 30
    ):
        # Agent identification
        self.agent_id = os.getenv("AGENT_ID", f"{agent_type}_{os.getpid()}")
        self.agent_type = os.getenv("AGENT_TYPE", agent_type)
        self.supervisor_id = os.getenv("SUPERVISOR_ID", "supervisor_unknown")

        # Redis connection
        self.redis_url = redis_url
        self.redis_client = None
        self.pubsub = None

        # Metrics and monitoring
        self.metrics = AgentMetrics()
        self.heartbeat_interval = heartbeat_interval
        self.running = False

        # Logging
        self.logger = logging.getLogger(f"{agent_type}:{self.agent_id}")

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        self.logger.info(f"Agent {self.agent_id} initialized")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    async def initialize(self) -> bool:
        """Initialize agent (connect to Redis, etc.)"""
        try:
            # Connect to Redis
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            await self.redis_client.ping()
            self.logger.info("Connected to Redis")

            # Initialize pubsub
            self.pubsub = self.redis_client.pubsub()

            # Call agent-specific initialization
            if not await self.agent_initialize():
                self.logger.error("Agent-specific initialization failed")
                return False

            self.logger.info("Agent initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to initialize agent: {e}")
            return False

    @abstractmethod
    async def agent_initialize(self) -> bool:
        """Agent-specific initialization (override in subclass)"""
        pass

    @abstractmethod
    async def process_message(self, channel: str, message: dict) -> bool:
        """Process incoming message (override in subclass)"""
        pass

    async def send_heartbeat(self):
        """Send heartbeat to supervisor"""
        try:
            heartbeat_key = f"godmode:agent_heartbeat:{self.agent_id}"
            await self.redis_client.setex(
                heartbeat_key,
                120,  # 2 minute TTL
                datetime.utcnow().isoformat()
            )
        except Exception as e:
            self.logger.error(f"Failed to send heartbeat: {e}")

    async def report_metrics(self):
        """Report metrics to supervisor"""
        try:
            metrics_key = f"godmode:agent_metrics:{self.agent_id}"
            metrics_data = {
                "agent_id": self.agent_id,
                "agent_type": self.agent_type,
                "state": "running",
                "cpu_usage": 0.0,  # TODO: Implement actual CPU monitoring
                "memory_usage": 0.0,  # TODO: Implement actual memory monitoring
                **self.metrics.to_dict()
            }

            await self.redis_client.setex(
                metrics_key,
                300,  # 5 minute TTL
                json.dumps(metrics_data)
            )
        except Exception as e:
            self.logger.error(f"Failed to report metrics: {e}")

    async def heartbeat_loop(self):
        """Continuous heartbeat loop"""
        while self.running:
            try:
                await self.send_heartbeat()
                await self.report_metrics()
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                self.logger.error(f"Error in heartbeat loop: {e}")
                await asyncio.sleep(5)

    async def publish_message(self, channel: str, message: dict):
        """Publish message to Redis channel"""
        try:
            await self.redis_client.publish(channel, json.dumps(message))
        except Exception as e:
            self.logger.error(f"Failed to publish to {channel}: {e}")

    async def subscribe_to_channels(self, channels: list):
        """Subscribe to Redis channels"""
        try:
            await self.pubsub.subscribe(*channels)
            self.logger.info(f"Subscribed to channels: {channels}")
        except Exception as e:
            self.logger.error(f"Failed to subscribe to channels: {e}")

    async def message_loop(self):
        """Main message processing loop"""
        self.logger.info("Starting message loop...")

        while self.running:
            try:
                message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)

                if message and message["type"] == "message":
                    channel = message["channel"]
                    data = json.loads(message["data"])

                    # Record task start
                    self.metrics.record_task_start()
                    start_time = datetime.utcnow()

                    try:
                        # Process message
                        success = await self.process_message(channel, data)

                        # Record completion
                        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000

                        if success:
                            self.metrics.record_task_complete(processing_time)
                        else:
                            self.metrics.record_task_failed()

                    except Exception as e:
                        self.logger.error(f"Error processing message: {e}")
                        self.metrics.record_task_failed()

                await asyncio.sleep(0.01)  # Small delay to prevent CPU spinning

            except Exception as e:
                self.logger.error(f"Error in message loop: {e}")
                await asyncio.sleep(1)

    async def start(self):
        """Start agent"""
        self.logger.info(f"Starting agent {self.agent_id}...")

        # Initialize
        if not await self.initialize():
            self.logger.error("Failed to initialize agent")
            return

        self.running = True

        # Start heartbeat loop
        heartbeat_task = asyncio.create_task(self.heartbeat_loop())

        # Start message loop
        message_task = asyncio.create_task(self.message_loop())

        self.logger.info(f"Agent {self.agent_id} started successfully")

        try:
            # Wait for tasks
            await asyncio.gather(heartbeat_task, message_task)
        except Exception as e:
            self.logger.error(f"Error in agent execution: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Shutdown agent gracefully"""
        self.logger.info("Shutting down agent...")

        self.running = False

        # Unsubscribe from channels
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()

        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()

        self.logger.info("Agent shutdown complete")
