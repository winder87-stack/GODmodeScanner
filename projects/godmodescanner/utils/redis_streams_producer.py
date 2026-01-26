#!/usr/bin/env python3
"""Redis Streams Producer - High-throughput event streaming with backpressure support.

This module implements Redis Streams-based event production for GODMODESCANNER,
replacing pub/sub with durable, high-throughput message streaming.

Key Features:
- XADD for high-throughput message production
- Automatic stream creation
- Configurable stream length (MAXLEN)
- Batch support for bulk operations
- Connection pooling for performance
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
import structlog

try:
    from redis.asyncio import Redis as AsyncRedis
    from redis.asyncio.connection import ConnectionPool
except ImportError:
    from redis.asyncio.client import Redis as AsyncRedis
    from redis.asyncio.connection import ConnectionPool

logger = structlog.get_logger(__name__)

# Stream names for different event types
STREAM_TRANSACTIONS = "godmode:new_transactions"
STREAM_TOKEN_LAUNCHES = "godmode:token_launches"
STREAM_TRADES = "godmode:trades"
STREAM_ALERTS = "godmode:alerts"
STREAM_RISK_SCORES = "godmode:risk_scores"


@dataclass
class StreamEvent:
    """Represents an event to be published to a Redis Stream."""
    stream_name: str
    data: Dict[str, Any]
    event_type: str = "transaction"
    timestamp: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        result["data"] = json.dumps(self.data)
        return result


class RedisStreamsProducer:
    """High-performance Redis Streams producer with connection pooling."""

    # Default configuration
    DEFAULT_STREAM_MAXLEN = 100000  # Keep last 100k messages per stream
    DEFAULT_BATCH_SIZE = 100
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        max_connections: int = 50,
        stream_maxlen: int = DEFAULT_STREAM_MAXLEN,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        """Initialize Redis Streams producer.
        
        Args:
            redis_url: Redis connection URL
            max_connections: Maximum connections in pool
            stream_maxlen: Maximum length for streams (approximate)
            batch_size: Number of events to batch for bulk operations
        """
        self.redis_url = redis_url
        self.max_connections = max_connections
        self.stream_maxlen = stream_maxlen
        self.batch_size = batch_size
        
        # Connection pool
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[AsyncRedis] = None
        
        # Statistics
        self.stats = {
            "events_published": 0,
            "errors": 0,
            "avg_latency_ms": 0.0,
            "streams_created": [],
        }
        
        logger.info(
            "redis_streams_producer_init",
            redis_url=redis_url,
            max_connections=max_connections,
            stream_maxlen=stream_maxlen,
            batch_size=batch_size,
        )

    async def connect(self) -> bool:
        """Establish connection to Redis with connection pooling."""
        try:
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                decode_responses=False,  # Keep binary for speed
            )
            self._redis = AsyncRedis(connection_pool=self._pool)
            
            # Test connection
            await self._redis.ping()
            logger.info("redis_streams_connected", url=self.redis_url)
            return True
        except Exception as e:
            logger.error("redis_streams_connect_failed", error=str(e))
            return False

    async def publish_event(
        self,
        stream_name: str,
        event_data: Dict[str, Any],
        event_type: str = "transaction",
    ) -> Optional[str]:
        """Publish a single event to a Redis Stream using XADD.
        
        Args:
            stream_name: Name of the stream
            event_data: Event payload (will be JSON serialized)
            event_type: Type identifier for the event
            
        Returns:
            Message ID if successful, None otherwise
        """
        if self._redis is None:
            logger.error("redis_not_connected")
            return None
        
        try:
            import time
            start_time = time.time()
            
            # Prepare event fields
            fields = {
                "event_type": event_type,
                "data": json.dumps(event_data),
                "timestamp": str(int(time.time() * 1000)),
            }
            
            # Use XADD with MAXLEN for automatic trimming
            message_id = await self._redis.xadd(
                stream_name,
                fields,
                maxlen=self.stream_maxlen,
            )
            
            # Update stats
            latency_ms = (time.time() - start_time) * 1000
            self.stats["events_published"] += 1
            self._update_avg_latency(latency_ms)
            
            if stream_name not in self.stats["streams_created"]:
                self.stats["streams_created"].append(stream_name)
            
            return message_id
            
        except Exception as e:
            self.stats["errors"] += 1
            logger.error("publish_event_failed", stream=stream_name, error=str(e))
            return None

    async def publish_batch(
        self,
        events: List[StreamEvent],
    ) -> List[Optional[str]]:
        """Publish multiple events in a batch for higher throughput.
        
        Args:
            events: List of StreamEvent objects
            
        Returns:
            List of message IDs (None for failed events)
        """
        if self._redis is None:
            logger.error("redis_not_connected")
            return [None] * len(events)
        
        results = []
        for event in events:
            msg_id = await self.publish_event(
                event.stream_name,
                event.data,
                event.event_type,
            )
            results.append(msg_id)
        
        return results

    async def publish_transaction(self, tx_data: Dict[str, Any]) -> Optional[str]:
        """Convenience method to publish a transaction event."""
        return await self.publish_event(STREAM_TRANSACTIONS, tx_data, "transaction")

    async def publish_token_launch(self, launch_data: Dict[str, Any]) -> Optional[str]:
        """Convenience method to publish a token launch event."""
        return await self.publish_event(STREAM_TOKEN_LAUNCHES, launch_data, "token_launch")

    async def publish_trade(self, trade_data: Dict[str, Any]) -> Optional[str]:
        """Convenience method to publish a trade event."""
        return await self.publish_event(STREAM_TRADES, trade_data, "trade")

    async def publish_alert(self, alert_data: Dict[str, Any]) -> Optional[str]:
        """Convenience method to publish an alert event."""
        return await self.publish_event(STREAM_ALERTS, alert_data, "alert")

    async def publish_risk_score(self, risk_data: Dict[str, Any]) -> Optional[str]:
        """Convenience method to publish a risk score event."""
        return await self.publish_event(STREAM_RISK_SCORES, risk_data, "risk_score")

    def _update_avg_latency(self, latency_ms: float):
        """Update moving average of latency."""
        n = self.stats["events_published"]
        current_avg = self.stats["avg_latency_ms"]
        self.stats["avg_latency_ms"] = (
            (current_avg * (n - 1) + latency_ms) / n if n > 0 else latency_ms
        )

    async def get_stream_info(self, stream_name: str) -> Dict[str, Any]:
        """Get information about a stream."""
        if self._redis is None:
            return {}
        
        try:
            info = await self._redis.xinfo_stream(stream_name)
            return {
                "length": info.get("length", 0),
                "groups": info.get("groups", 0),
                "first_entry": info.get("first-entry"),
                "last_entry": info.get("last-entry"),
            }
        except Exception as e:
            logger.error("get_stream_info_failed", stream=stream_name, error=str(e))
            return {}

    async def get_stats(self) -> Dict[str, Any]:
        """Get producer statistics."""
        return self.stats.copy()

    async def close(self):
        """Close Redis connection and clean up resources."""
        if self._redis:
            await self._redis.close()
        if self._pool:
            await self._pool.disconnect()
        logger.info("redis_streams_producer_closed")


# Singleton instance for easy access
_producer: Optional[RedisStreamsProducer] = None


async def get_producer(redis_url: str = "redis://localhost:6379") -> RedisStreamsProducer:
    """Get or create the singleton producer instance."""
    global _producer
    if _producer is None:
        _producer = RedisStreamsProducer(redis_url=redis_url)
        await _producer.connect()
    return _producer


async def close_producer():
    """Close the singleton producer instance."""
    global _producer
    if _producer:
        await _producer.close()
        _producer = None
