#!/usr/bin/env python3
"""Redis Streams Consumer Group Worker - Fault-tolerant backpressure processing.

This module implements Redis Streams consumer groups for GODMODESCANNER,
providing fault tolerance, load distribution, and backpressure support.

Key Features:
- XGROUP CREATE for consumer group initialization
- XREADGROUP for message consumption with backpressure
- XACK for acknowledging processed messages
- Automatic pending message recovery
- Consumer crash detection and message reprocessing
- Multiple consumers per group for horizontal scaling
"""

import asyncio
import json
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import structlog
import uuid

try:
    from redis.asyncio import Redis as AsyncRedis
    from redis.asyncio.connection import ConnectionPool
except ImportError:
    from redis.asyncio.client import Redis as AsyncRedis
    from redis.asyncio.connection import ConnectionPool

logger = structlog.get_logger(__name__)

# Stream names matching the producer
STREAM_TRANSACTIONS = "godmode:new_transactions"
STREAM_TOKEN_LAUNCHES = "godmode:token_launches"
STREAM_TRADES = "godmode:trades"
STREAM_ALERTS = "godmode:alerts"
STREAM_RISK_SCORES = "godmode:risk_scores"


@dataclass
class ConsumerConfig:
    """Configuration for a consumer worker."""
    stream_name: str
    group_name: str
    consumer_id: Optional[str] = None
    count_per_read: int = 10
    block_ms: int = 100  # 100ms blocking
    idle_ms: int = 5000  # 5ms idle time before pending claim
    retry_ms: int = 1000  # 1s retry interval for processing failures
    auto_ack: bool = True  # Auto-acknowledge on successful processing
    
    def __post_init__(self):
        if self.consumer_id is None:
            self.consumer_id = f"consumer-{uuid.uuid4().hex[:8]}"


@dataclass
class Message:
    """Represents a message from a Redis Stream."""
    message_id: str
    stream_name: str
    data: Dict[str, Any]
    event_type: str
    timestamp: str
    delivery_count: int = 0
    
    def get_payload(self) -> Dict[str, Any]:
        """Get the parsed event payload."""
        return self.data


class RedisStreamsConsumer:
    """Redis Streams consumer group worker with backpressure support.
    
    This class implements a robust consumer that:
    - Creates consumer groups on first startup
    - Reads messages using XREADGROUP
    - Acknowledges processed messages with XACK
    - Handles pending messages from crashed consumers
    - Provides backpressure by controlling consumption rate
    - Supports horizontal scaling (multiple consumers per group)
    """

    def __init__(
        self,
        config: ConsumerConfig,
        redis_url: str = "redis://localhost:6379",
        message_handler: Optional[Callable[[Message], Any]] = None,
    ):
        """Initialize Redis Streams consumer.
        
        Args:
            config: Consumer configuration
            redis_url: Redis connection URL
            message_handler: Async callback function to process messages
        """
        self.config = config
        self.redis_url = redis_url
        self.message_handler = message_handler
        
        # Connection
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[AsyncRedis] = None
        
        # State
        self._running = False
        self._consumer_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.stats = {
            "messages_consumed": 0,
            "messages_acknowledged": 0,
            "messages_failed": 0,
            "pending_processed": 0,
            "processing_time_ms": 0.0,
            "idle_time_ms": 0.0,
        }
        
        logger.info(
            "redis_streams_consumer_init",
            stream=config.stream_name,
            group=config.group_name,
            consumer=config.consumer_id,
            count=config.count_per_read,
            block_ms=config.block_ms,
        )

    async def connect(self) -> bool:
        """Establish connection to Redis."""
        try:
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=20,
                decode_responses=False,  # Keep binary for speed
            )
            self._redis = AsyncRedis(connection_pool=self._pool)
            
            # Test connection
            await self._redis.ping()
            
            # Create consumer group if not exists
            await self._ensure_consumer_group()
            
            logger.info(
                "redis_streams_consumer_connected",
                stream=self.config.stream_name,
                group=self.config.group_name,
                consumer=self.config.consumer_id,
            )
            return True
        except Exception as e:
            logger.error("redis_streams_consumer_connect_failed", error=str(e))
            return False

    async def _ensure_consumer_group(self):
        """Ensure consumer group exists, creating if necessary."""
        try:
            # Try to create group (fails if exists)
            await self._redis.xgroup_create(
                name=self.config.stream_name,
                groupname=self.config.group_name,
                id="0",  # Start from beginning for new groups
                mkstream=True,  # Create stream if doesn't exist
            )
            logger.info(
                "consumer_group_created",
                stream=self.config.stream_name,
                group=self.config.group_name,
            )
        except Exception as e:
            # Group already exists is OK
            if "BUSYGROUP" not in str(e):
                logger.warning("ensure_consumer_group_warning", error=str(e))

    async def start(self):
        """Start consuming messages in the background."""
        if self._running:
            logger.warning("consumer_already_running")
            return
        
        self._running = True
        self._consumer_task = asyncio.create_task(self._consume_loop())
        logger.info(
            "consumer_started",
            stream=self.config.stream_name,
            group=self.config.group_name,
            consumer=self.config.consumer_id,
        )

    async def stop(self):
        """Stop consuming messages gracefully."""
        self._running = False
        if self._consumer_task:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        logger.info(
            "consumer_stopped",
            stream=self.config.stream_name,
            group=self.config.group_name,
            consumer=self.config.consumer_id,
        )

    async def _consume_loop(self):
        """Main consumption loop."""
        last_id = ">"  ">" means new messages only
        
        while self._running:
            try:
                # First check for pending messages from crashed consumers
                await self._process_pending_messages()
                
                # Then read new messages
                await self._process_new_messages(last_id)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("consume_loop_error", error=str(e))
                await asyncio.sleep(1)  # Back off on error

    async def _process_new_messages(self, last_id: str):
        """Process new messages from the stream."""
        try:
            messages = await self._redis.xreadgroup(
                groupname=self.config.group_name,
                consumername=self.config.consumer_id,
                streams={self.config.stream_name: last_id},
                count=self.config.count_per_read,
                block=self.config.block_ms,
            )
            
            for stream, stream_messages in messages:
                for message_id, fields in stream_messages:
                    await self._process_message(message_id, fields)
                    
        except Exception as e:
            logger.error("process_new_messages_error", error=str(e))

    async def _process_pending_messages(self):
        """Process pending messages from crashed consumers."""
        try:
            # Get list of pending messages
            pending = await self._redis.xpending(
                name=self.config.stream_name,
                groupname=self.config.group_name,
            )
            
            if pending is None:
                return
            
            pending_count = pending.get("pending", 0)
            if pending_count == 0:
                return
            
            # Claim idle pending messages
            claimed = await self._redis.xautoclaim(
                name=self.config.stream_name,
                groupname=self.config.group_name,
                consumername=self.config.consumer_id,
                min_idle_time=self.config.idle_ms,
                count=self.config.count_per_read,
            )
            
            # Process claimed messages
            if claimed:
                next_id, messages = claimed
                for message_id, fields in messages:
                    self.stats["pending_processed"] += 1
                    await self._process_message(message_id, fields)
                    
        except Exception as e:
            logger.error("process_pending_messages_error", error=str(e))

    async def _process_message(self, message_id: str, fields: Dict[bytes, bytes]):
        """Process a single message."""
        try:
            # Parse message
            decoded_fields = {k.decode(): v.decode() for k, v in fields.items()}
            event_type = decoded_fields.get("event_type", "unknown")
            timestamp = decoded_fields.get("timestamp", str(int(time.time() * 1000)))
            
            try:
                data = json.loads(decoded_fields["data"])
            except:
                data = decoded_fields["data"]
            
            message = Message(
                message_id=message_id,
                stream_name=self.config.stream_name,
                data=data,
                event_type=event_type,
                timestamp=timestamp,
            )
            
            self.stats["messages_consumed"] += 1
            
            # Process message
            start_time = time.time()
            success = True
            
            if self.message_handler:
                try:
                    result = await self.message_handler(message)
                    if result is False:
                        success = False
                except Exception as e:
                    logger.error("message_handler_error", message_id=message_id, error=str(e))
                    success = False
            
            processing_time_ms = (time.time() - start_time) * 1000
            self._update_avg_time("processing_time_ms", processing_time_ms)
            
            # Acknowledge message on success
            if success and self.config.auto_ack:
                await self._acknowledge(message_id)
            elif not success:
                self.stats["messages_failed"] += 1
                
        except Exception as e:
            logger.error("process_message_error", message_id=message_id, error=str(e))
            self.stats["messages_failed"] += 1

    async def _acknowledge(self, message_id: str):
        """Acknowledge a processed message."""
        try:
            await self._redis.xack(
                name=self.config.stream_name,
                groupname=self.config.group_name,
                id=message_id,
            )
            self.stats["messages_acknowledged"] += 1
        except Exception as e:
            logger.error("acknowledge_error", message_id=message_id, error=str(e))

    def _update_avg_time(self, key: str, value_ms: float):
        """Update moving average of timing metric."""
        current_avg = self.stats[key]
        count = self.stats["messages_consumed"]
        if count > 0:
            self.stats[key] = ((current_avg * (count - 1)) + value_ms) / count
        else:
            self.stats[key] = value_ms

    async def get_pending_info(self) -> Dict[str, Any]:
        """Get information about pending messages."""
        try:
            pending = await self._redis.xpending(
                name=self.config.stream_name,
                groupname=self.config.group_name,
            )
            
            if pending is None:
                return {"pending": 0, "min_id": None, "max_id": None, "consumers": []}
            
            return {
                "pending": pending.get("pending", 0),
                "min_id": pending.get("min"),
                "max_id": pending.get("max"),
                "consumers": pending.get("consumers", []),
            }
        except Exception as e:
            logger.error("get_pending_info_error", error=str(e))
            return {}

    async def get_consumer_info(self) -> List[Dict[str, Any]]:
        """Get information about all consumers in the group."""
        try:
            consumers = await self._redis.xinfo_groups(self.config.stream_name)
            # Find our group
            for group in consumers:
                if group["name"] == self.config.group_name:
                    return group.get("consumers", [])
            return []
        except Exception as e:
            logger.error("get_consumer_info_error", error=str(e))
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """Get consumer statistics."""
        stats = self.stats.copy()
        stats["config"] = {
            "stream": self.config.stream_name,
            "group": self.config.group_name,
            "consumer": self.config.consumer_id,
            "running": self._running,
        }
        return stats

    async def close(self):
        """Close Redis connection and clean up resources."""
        await self.stop()
        if self._redis:
            await self._redis.close()
        if self._pool:
            await self._pool.disconnect()
        logger.info("redis_streams_consumer_closed")


class ConsumerSwarm:
    """Manages a swarm of consumers for high-throughput parallel processing.
    
    This class allows you to create multiple consumers for the same group,
    achieving horizontal scaling and automatic load distribution.
    """

    def __init__(
        self,
        stream_name: str,
        group_name: str,
        num_consumers: int = 10,
        redis_url: str = "redis://localhost:6379",
        message_handler: Optional[Callable[[Message], Any]] = None,
    ):
        """Initialize consumer swarm.
        
        Args:
            stream_name: Name of the stream to consume from
            group_name: Name of the consumer group
            num_consumers: Number of parallel consumers to spawn
            redis_url: Redis connection URL
            message_handler: Async callback function to process messages
        """
        self.stream_name = stream_name
        self.group_name = group_name
        self.num_consumers = num_consumers
        self.redis_url = redis_url
        self.message_handler = message_handler
        
        self.consumers: List[RedisStreamsConsumer] = []
        self._running = False
        
        logger.info(
            "consumer_swarm_init",
            stream=stream_name,
            group=group_name,
            consumers=num_consumers,
        )

    async def start(self):
        """Start all consumers in the swarm."""
        self._running = True
        
        for i in range(self.num_consumers):
            config = ConsumerConfig(
                stream_name=self.stream_name,
                group_name=self.group_name,
                consumer_id=f"consumer-{i}-{uuid.uuid4().hex[:6]}",
            )
            
            consumer = RedisStreamsConsumer(
                config=config,
                redis_url=self.redis_url,
                message_handler=self.message_handler,
            )
            
            await consumer.connect()
            await consumer.start()
            self.consumers.append(consumer)
            
            logger.info(
                "swarm_consumer_started",
                consumer=config.consumer_id,
                index=i,
                total=self.num_consumers,
            )
        
        logger.info(
            "consumer_swarm_started",
            stream=self.stream_name,
            group=self.group_name,
            consumers=len(self.consumers),
        )

    async def stop(self):
        """Stop all consumers in the swarm."""
        self._running = False
        
        for consumer in self.consumers:
            await consumer.stop()
            await consumer.close()
        
        self.consumers.clear()
        logger.info(
            "consumer_swarm_stopped",
            stream=self.stream_name,
            group=self.group_name,
        )

    async def get_aggregate_stats(self) -> Dict[str, Any]:
        """Get aggregate statistics from all consumers."""
        aggregate = {
            "stream": self.stream_name,
            "group": self.group_name,
            "num_consumers": len(self.consumers),
            "total_messages_consumed": 0,
            "total_messages_acknowledged": 0,
            "total_messages_failed": 0,
            "total_pending_processed": 0,
            "avg_processing_time_ms": 0.0,
            "consumers": [],
        }
        
        for consumer in self.consumers:
            stats = await consumer.get_stats()
            aggregate["consumers"].append(stats)
            aggregate["total_messages_consumed"] += stats["messages_consumed"]
            aggregate["total_messages_acknowledged"] += stats["messages_acknowledged"]
            aggregate["total_messages_failed"] += stats["messages_failed"]
            aggregate["total_pending_processed"] += stats["pending_processed"]
        
        # Calculate average processing time
        total_time = sum(c.stats["processing_time_ms"] for c in self.consumers)
        aggregate["avg_processing_time_ms"] = total_time / len(self.consumers) if self.consumers else 0
        
        return aggregate

    async def get_pending_info(self) -> Dict[str, Any]:
        """Get pending message information from the first consumer."""
        if self.consumers:
            return await self.consumers[0].get_pending_info()
        return {}

    def is_running(self) -> bool:
        """Check if the swarm is running."""
        return self._running and any(c.stats.get("config", {}).get("running") for c in self.consumers)
