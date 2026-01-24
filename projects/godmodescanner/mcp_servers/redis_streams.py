#!/usr/bin/env python3
"""
Redis Streams Manager for GODMODESCANNER
Upgrade from Pub/Sub to Redis Streams for persistent agent coordination
"""

import os
import json
import asyncio
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime
import redis.asyncio as redis

class RedisStreamsManager:
    """
    Redis Streams manager for persistent message queuing

    Advantages over Pub/Sub:
    - Message persistence (not lost if consumer offline)
    - Consumer groups for load balancing
    - Message acknowledgment and retry
    - Message history and replay
    - Automatic message ID generation
    """

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.consumers: Dict[str, asyncio.Task] = {}
        self.running = False

    async def initialize(self):
        """Initialize Redis connection"""
        self.redis_client = await redis.from_url(self.redis_url, decode_responses=True)
        self.running = True
        print(f"✅ Redis Streams Manager initialized: {self.redis_url}")

    async def create_stream(
        self,
        stream_name: str,
        consumer_group: str = "default"
    ):
        """
        Create a stream and consumer group

        Args:
            stream_name: Name of the stream
            consumer_group: Name of consumer group
        """
        try:
            # Create consumer group (starts from beginning if new)
            await self.redis_client.xgroup_create(
                stream_name,
                consumer_group,
                id='0',
                mkstream=True
            )
            print(f"✅ Created stream '{stream_name}' with group '{consumer_group}'")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                print(f"ℹ️  Consumer group '{consumer_group}' already exists for '{stream_name}'")
            else:
                raise

    async def publish(
        self,
        stream_name: str,
        data: Dict[str, Any],
        max_len: Optional[int] = 10000
    ) -> str:
        """
        Publish message to stream

        Args:
            stream_name: Name of the stream
            data: Message data (will be JSON serialized)
            max_len: Maximum stream length (FIFO eviction)

        Returns:
            Message ID
        """
        # Serialize all values to strings
        serialized_data = {
            k: json.dumps(v) if not isinstance(v, str) else v
            for k, v in data.items()
        }

        # Add timestamp if not present
        if 'timestamp' not in serialized_data:
            serialized_data['timestamp'] = datetime.utcnow().isoformat()

        # Publish to stream with max length
        message_id = await self.redis_client.xadd(
            stream_name,
            serialized_data,
            maxlen=max_len,
            approximate=True
        )

        return message_id

    async def consume(
        self,
        stream_name: str,
        consumer_group: str,
        consumer_name: str,
        callback: Callable[[Dict[str, Any]], Any],
        batch_size: int = 10,
        block_ms: int = 5000
    ):
        """
        Consume messages from stream

        Args:
            stream_name: Name of the stream
            consumer_group: Consumer group name
            consumer_name: Unique consumer name
            callback: Async function to process messages
            batch_size: Number of messages to read at once
            block_ms: Milliseconds to block waiting for messages
        """
        print(f"🔄 Starting consumer '{consumer_name}' for stream '{stream_name}'")

        while self.running:
            try:
                # Read messages from stream
                messages = await self.redis_client.xreadgroup(
                    groupname=consumer_group,
                    consumername=consumer_name,
                    streams={stream_name: '>'},
                    count=batch_size,
                    block=block_ms
                )

                if not messages:
                    continue

                # Process messages
                for stream, stream_messages in messages:
                    for message_id, data in stream_messages:
                        try:
                            # Deserialize data
                            deserialized_data = {
                                k: json.loads(v) if v.startswith(('{', '[', '"')) else v
                                for k, v in data.items()
                            }

                            # Call callback
                            await callback(deserialized_data)

                            # Acknowledge message
                            await self.redis_client.xack(
                                stream_name,
                                consumer_group,
                                message_id
                            )

                        except Exception as e:
                            print(f"❌ Error processing message {message_id}: {e}")
                            # Don't acknowledge - will be retried

            except asyncio.CancelledError:
                print(f"🛑 Consumer '{consumer_name}' cancelled")
                break
            except Exception as e:
                print(f"❌ Consumer error: {e}")
                await asyncio.sleep(1)

    async def start_consumer(
        self,
        stream_name: str,
        consumer_group: str,
        consumer_name: str,
        callback: Callable[[Dict[str, Any]], Any],
        batch_size: int = 10
    ) -> str:
        """
        Start a consumer in background

        Returns:
            Consumer task ID
        """
        # Ensure stream and group exist
        await self.create_stream(stream_name, consumer_group)

        # Start consumer task
        task_id = f"{stream_name}:{consumer_group}:{consumer_name}"
        task = asyncio.create_task(
            self.consume(
                stream_name,
                consumer_group,
                consumer_name,
                callback,
                batch_size
            )
        )

        self.consumers[task_id] = task
        return task_id

    async def stop_consumer(self, task_id: str):
        """Stop a consumer task"""
        if task_id in self.consumers:
            self.consumers[task_id].cancel()
            try:
                await self.consumers[task_id]
            except asyncio.CancelledError:
                pass
            del self.consumers[task_id]
            print(f"✅ Stopped consumer: {task_id}")

    async def get_stream_info(self, stream_name: str) -> Dict[str, Any]:
        """Get information about a stream"""
        info = await self.redis_client.xinfo_stream(stream_name)
        return {
            'length': info['length'],
            'first_entry': info['first-entry'],
            'last_entry': info['last-entry'],
            'groups': info['groups']
        }

    async def get_pending_messages(
        self,
        stream_name: str,
        consumer_group: str
    ) -> List[Dict[str, Any]]:
        """
        Get pending (unacknowledged) messages

        Useful for monitoring and retry logic
        """
        pending = await self.redis_client.xpending(
            stream_name,
            consumer_group
        )

        return [
            {
                'message_id': msg[0],
                'consumer': msg[1],
                'idle_time_ms': msg[2],
                'delivery_count': msg[3]
            }
            for msg in pending
        ]

    async def claim_pending_messages(
        self,
        stream_name: str,
        consumer_group: str,
        consumer_name: str,
        min_idle_time_ms: int = 60000
    ) -> List[tuple]:
        """
        Claim pending messages that have been idle too long

        Useful for handling failed consumers

        Args:
            stream_name: Stream name
            consumer_group: Consumer group
            consumer_name: Consumer claiming the messages
            min_idle_time_ms: Minimum idle time before claiming

        Returns:
            List of claimed messages
        """
        # Get pending messages
        pending = await self.redis_client.xpending_range(
            stream_name,
            consumer_group,
            min='-',
            max='+',
            count=100
        )

        # Filter by idle time and claim
        claimed = []
        for msg in pending:
            if msg['time_since_delivered'] >= min_idle_time_ms:
                result = await self.redis_client.xclaim(
                    stream_name,
                    consumer_group,
                    consumer_name,
                    min_idle_time_ms,
                    [msg['message_id']]
                )
                claimed.extend(result)

        return claimed

    async def trim_stream(
        self,
        stream_name: str,
        max_len: int = 10000
    ):
        """
        Trim stream to maximum length

        Args:
            stream_name: Stream to trim
            max_len: Maximum number of messages to keep
        """
        await self.redis_client.xtrim(
            stream_name,
            maxlen=max_len,
            approximate=True
        )

    async def close(self):
        """Close all consumers and Redis connection"""
        self.running = False

        # Stop all consumers
        for task_id in list(self.consumers.keys()):
            await self.stop_consumer(task_id)

        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()

        print("✅ Redis Streams Manager closed")


# Convenience functions for GODMODESCANNER agents

class AgentStreamsClient:
    """
    High-level client for agents to use Redis Streams
    """

    def __init__(self, agent_id: str, agent_type: str, redis_url: str = "redis://localhost:6379"):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.manager = RedisStreamsManager(redis_url)

    async def initialize(self):
        """Initialize the client"""
        await self.manager.initialize()

        # Create standard streams for this agent
        await self.manager.create_stream(
            f"mcp:stream:tasks:{self.agent_type}",
            f"group_{self.agent_type}"
        )

        await self.manager.create_stream(
            f"mcp:stream:results:{self.agent_type}",
            "results_group"
        )

    async def listen_for_tasks(
        self,
        callback: Callable[[Dict[str, Any]], Any],
        batch_size: int = 10
    ):
        """
        Listen for tasks assigned to this agent

        Args:
            callback: Async function to process tasks
            batch_size: Number of tasks to process at once
        """
        await self.manager.start_consumer(
            stream_name=f"mcp:stream:tasks:{self.agent_type}",
            consumer_group=f"group_{self.agent_type}",
            consumer_name=self.agent_id,
            callback=callback,
            batch_size=batch_size
        )

    async def publish_result(
        self,
        task_id: str,
        result: Dict[str, Any]
    ):
        """
        Publish task result

        Args:
            task_id: Original task ID
            result: Task result data
        """
        await self.manager.publish(
            f"mcp:stream:results:{self.agent_type}",
            {
                'task_id': task_id,
                'agent_id': self.agent_id,
                'result': result,
                'timestamp': datetime.utcnow().isoformat()
            }
        )

        # Also store in Redis for quick lookup
        await self.manager.redis_client.setex(
            f"mcp:result:{task_id}",
            300,  # 5 minute TTL
            json.dumps(result)
        )

    async def publish_event(
        self,
        event_type: str,
        data: Dict[str, Any]
    ):
        """
        Publish an event to the event stream

        Args:
            event_type: Type of event
            data: Event data
        """
        await self.manager.publish(
            "mcp:stream:events",
            {
                'event_type': event_type,
                'agent_id': self.agent_id,
                'agent_type': self.agent_type,
                'data': data
            }
        )

    async def close(self):
        """Close the client"""
        await self.manager.close()


if __name__ == "__main__":
    async def test_streams():
        """Test Redis Streams"""
        manager = RedisStreamsManager()
        await manager.initialize()

        # Create test stream
        await manager.create_stream("test_stream", "test_group")

        # Publish messages
        for i in range(5):
            msg_id = await manager.publish(
                "test_stream",
                {
                    'message': f'Test message {i}',
                    'value': i * 10
                }
            )
            print(f"Published message: {msg_id}")

        # Consumer callback
        async def process_message(data: Dict[str, Any]):
            print(f"Received: {data}")

        # Start consumer
        task_id = await manager.start_consumer(
            "test_stream",
            "test_group",
            "consumer_1",
            process_message
        )

        # Let it run for a bit
        await asyncio.sleep(2)

        # Get stream info
        info = await manager.get_stream_info("test_stream")
        print(f"
Stream info: {info}")

        # Close
        await manager.close()

    asyncio.run(test_streams())
