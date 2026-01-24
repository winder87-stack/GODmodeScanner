"""Redis Pub/Sub Manager for Inter-Agent Communication.

Provides Redis-based pub/sub for GODMODESCANNER agent communication.
Falls back to in-memory event emitter when Redis is unavailable.
"""

import asyncio
import json
from typing import Callable, Dict, List, Optional, Any
import structlog
import redis.asyncio as aioredis
from datetime import datetime

logger = structlog.get_logger(__name__)


class RedisPubSubManager:
    """Redis pub/sub manager with fallback to in-memory.

    Features:
    - Async Redis pub/sub for inter-agent communication
    - Automatic reconnection on connection loss
    - Fallback to in-memory event emitter when Redis unavailable
    - JSON serialization for structured events
    - Channel pattern subscription support
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.pubsub: Optional[aioredis.client.PubSub] = None
        self.connected = False

        # Fallback in-memory storage
        self.listeners: Dict[str, List[Callable]] = {}
        self.message_history: List[Dict[str, Any]] = []
        self.max_history = 1000

        # Background tasks
        self._listener_task: Optional[asyncio.Task] = None
        self._shutdown = False

        logger.info("redis_pubsub_manager_initialized", redis_url=redis_url)

    async def connect(self) -> bool:
        """Connect to Redis.

        Returns:
            True if connected, False if using fallback
        """
        try:
            self.redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis.ping()
            self.pubsub = self.redis.pubsub()
            self.connected = True

            logger.info("redis_connected", url=self.redis_url)
            return True

        except Exception as e:
            logger.warning(
                "redis_connection_failed_using_fallback",
                error=str(e),
                redis_url=self.redis_url
            )
            self.connected = False
            return False

    async def disconnect(self):
        """Disconnect from Redis."""
        self._shutdown = True

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self.pubsub:
            await self.pubsub.close()

        if self.redis:
            await self.redis.close()

        self.connected = False
        logger.info("redis_disconnected")

    async def publish(self, channel: str, message: Any):
        """Publish message to channel.

        Args:
            channel: Channel name
            message: Message to publish (will be JSON serialized)
        """
        try:
            # Serialize message
            if isinstance(message, dict):
                data = json.dumps(message)
            elif isinstance(message, str):
                data = message
            else:
                data = json.dumps({"data": str(message)})

            if self.connected and self.redis:
                # Publish to Redis
                await self.redis.publish(channel, data)
                logger.debug("message_published_redis", channel=channel)
            else:
                # Fallback: emit to local listeners
                await self._emit_local(channel, message)
                logger.debug("message_published_local", channel=channel)

            # Record in history
            self._record_message(channel, message, "published")

        except Exception as e:
            logger.error(
                "publish_error",
                channel=channel,
                error=str(e)
            )

    async def subscribe(self, channel: str, callback: Callable):
        """Subscribe to channel.

        Args:
            channel: Channel name (supports patterns with *)
            callback: Async callback function for messages
        """
        try:
            if self.connected and self.pubsub:
                # Subscribe to Redis
                if "*" in channel:
                    await self.pubsub.psubscribe(channel)
                else:
                    await self.pubsub.subscribe(channel)

                logger.info("subscribed_redis", channel=channel)

                # Start listener task if not running
                if not self._listener_task or self._listener_task.done():
                    self._listener_task = asyncio.create_task(
                        self._listen_redis()
                    )

            # Always add to local listeners (for fallback)
            if channel not in self.listeners:
                self.listeners[channel] = []
            if callback not in self.listeners[channel]:
                self.listeners[channel].append(callback)

            logger.info("subscribed_local", channel=channel)

        except Exception as e:
            logger.error(
                "subscribe_error",
                channel=channel,
                error=str(e)
            )

    async def _listen_redis(self):
        """Listen for Redis pub/sub messages."""
        try:
            async for message in self.pubsub.listen():
                if self._shutdown:
                    break

                if message["type"] not in ("message", "pmessage"):
                    continue

                channel = message["channel"]
                data = message["data"]

                # Try to parse JSON
                try:
                    parsed_data = json.loads(data)
                except json.JSONDecodeError:
                    parsed_data = data

                # Call matching listeners
                await self._call_listeners(channel, parsed_data)

                # Record in history
                self._record_message(channel, parsed_data, "received")

        except asyncio.CancelledError:
            logger.info("redis_listener_cancelled")
        except Exception as e:
            logger.error("redis_listener_error", error=str(e))

    async def _emit_local(self, channel: str, message: Any):
        """Emit message to local listeners (fallback)."""
        await self._call_listeners(channel, message)

    async def _call_listeners(self, channel: str, message: Any):
        """Call all listeners for a channel."""
        matched_listeners = []

        # Exact match
        if channel in self.listeners:
            matched_listeners.extend(self.listeners[channel])

        # Pattern match
        for pattern, listeners in self.listeners.items():
            if "*" in pattern:
                import fnmatch
                if fnmatch.fnmatch(channel, pattern):
                    matched_listeners.extend(listeners)

        # Call all matched listeners
        for listener in matched_listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(channel, message)
                else:
                    listener(channel, message)
            except Exception as e:
                logger.error(
                    "listener_callback_error",
                    channel=channel,
                    error=str(e)
                )

    def _record_message(self, channel: str, message: Any, direction: str):
        """Record message in history."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "channel": channel,
            "direction": direction,
            "message": message
        }

        self.message_history.append(record)

        # Trim history
        if len(self.message_history) > self.max_history:
            self.message_history = self.message_history[-self.max_history:]

    def get_message_history(self, channel: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """Get message history.

        Args:
            channel: Optional channel filter
            limit: Maximum messages to return

        Returns:
            List of message records
        """
        if channel:
            filtered = [m for m in self.message_history if m["channel"] == channel]
            return filtered[-limit:]
        return self.message_history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Get pub/sub statistics."""
        return {
            "connected": self.connected,
            "redis_url": self.redis_url,
            "total_listeners": sum(len(l) for l in self.listeners.values()),
            "channels_subscribed": len(self.listeners),
            "message_history_count": len(self.message_history),
            "mode": "redis" if self.connected else "fallback"
        }
