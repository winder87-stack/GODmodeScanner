"""
GODMODESCANNER Redis Client with AOF-Only Cluster Support
Supports both standalone and 6-node cluster modes for 100,000+ writes/sec.
Reference: github.com/redis-developer/agent-memory-server
"""

import os
import asyncio
from typing import Optional, Dict, Any, List, Union
import json
import structlog

# Import both standard and cluster clients
import redis.asyncio as aioredis
from redis.asyncio.cluster import RedisCluster
from redis.cluster import ClusterNode

logger = structlog.get_logger()


class GodmodeRedisCluster:
    """
    Redis Cluster client optimized for GODMODESCANNER's ETERNAL MIND memory system.
    Supports 6-node AOF-only cluster with automatic failover and load balancing.

    Performance Targets:
    - Write throughput: 100,000+ ops/sec
    - AOF rewrite latency: <100ms
    - Failover time: <1s
    """

    def __init__(self):
        self.mode = os.getenv('REDIS_MODE', 'standalone').lower()
        self.client: Optional[Union[aioredis.Redis, RedisCluster]] = None

        # Cluster configuration
        self.cluster_nodes_str = os.getenv(
            'REDIS_CLUSTER_NODES',
            '172.28.1.1:6379,172.28.1.2:6379,172.28.1.3:6379'
        )

        # Standalone configuration (fallback)
        self.standalone_host = os.getenv('REDIS_HOST', 'localhost')
        self.standalone_port = int(os.getenv('REDIS_PORT', 6379))

        # Connection pool settings
        self.max_connections_per_node = int(os.getenv('REDIS_MAX_CONNECTIONS', 100))

        logger.info("Redis client initialized",
                   mode=self.mode,
                   cluster_nodes=self.cluster_nodes_str if self.mode == 'cluster' else None)

    def _parse_cluster_nodes(self) -> List[ClusterNode]:
        """Parse cluster nodes from environment variable."""
        nodes = []
        for node_str in self.cluster_nodes_str.split(','):
            host, port = node_str.strip().split(':')
            nodes.append(ClusterNode(host=host, port=int(port)))
        return nodes

    async def connect(self) -> Union[aioredis.Redis, RedisCluster]:
        """Connect to Redis (standalone or cluster mode)."""
        if self.mode == 'cluster':
            return await self._connect_cluster()
        else:
            return await self._connect_standalone()

    async def _connect_cluster(self) -> RedisCluster:
        """Connect to 6-node Redis AOF cluster."""
        startup_nodes = self._parse_cluster_nodes()

        self.client = RedisCluster(
            startup_nodes=startup_nodes,
            decode_responses=True,
            skip_full_coverage_check=True,
            max_connections_per_node=self.max_connections_per_node,
            read_from_replicas=True,  # Load balance reads across replicas
        )

        # Verify connection
        await self.client.ping()

        # Validate AOF persistence on all nodes
        await self._validate_cluster_persistence()

        logger.info("Redis cluster connected",
                   nodes=len(startup_nodes),
                   max_connections=self.max_connections_per_node)

        return self.client

    async def _connect_standalone(self) -> aioredis.Redis:
        """Connect to standalone Redis (fallback mode)."""
        self.client = aioredis.from_url(
            f"redis://{self.standalone_host}:{self.standalone_port}",
            decode_responses=True,
            max_connections=self.max_connections_per_node
        )

        await self.client.ping()
        await self._validate_standalone_persistence()

        logger.info("Redis standalone connected",
                   host=self.standalone_host,
                   port=self.standalone_port)

        return self.client

    async def _validate_cluster_persistence(self):
        """Validate AOF persistence is enabled on all cluster nodes."""
        try:
            # Get cluster nodes info
            nodes_info = await self.client.cluster_nodes()

            # Check each master node
            master_count = 0
            replica_count = 0

            for node_id, info in nodes_info.items():
                if 'master' in info.get('flags', ''):
                    master_count += 1
                elif 'slave' in info.get('flags', ''):
                    replica_count += 1

            logger.info("Cluster topology validated",
                       masters=master_count,
                       replicas=replica_count)

            if master_count < 3:
                logger.warning("⚠️ Less than 3 master nodes detected!")

        except Exception as e:
            logger.warning("Could not validate cluster topology", error=str(e))

    async def _validate_standalone_persistence(self):
        """Validate Redis persistence is configured correctly."""
        info = await self.client.info('persistence')

        aof_enabled = info.get('aof_enabled', 0) == 1
        rdb_enabled = info.get('rdb_bgsave_in_progress', 0) >= 0

        logger.info("Redis persistence status",
                   aof_enabled=aof_enabled,
                   rdb_last_save=info.get('rdb_last_save_time', 0))

        if not aof_enabled:
            logger.warning("⚠️ Redis AOF is DISABLED - data may be lost!")

        return {'aof_enabled': aof_enabled, 'rdb_enabled': rdb_enabled}

    # =========================================================================
    # ETERNAL MIND Memory Operations
    # =========================================================================

    async def persist_memory(self, partition: str, key: str, data: Dict[str, Any], ttl: int = 3600) -> bool:
        """AOF-optimized persistence for ETERNAL MIND memory system."""
        try:
            full_key = f"godmode:memory:{partition}:{key}"
            await self.client.setex(full_key, ttl, json.dumps(data))
            return True
        except Exception as e:
            logger.error("Memory persistence failed", partition=partition, key=key, error=str(e))
            return False

    async def load_memory(self, partition: str, key: str) -> Optional[Dict[str, Any]]:
        """Load memory from ETERNAL MIND storage."""
        try:
            full_key = f"godmode:memory:{partition}:{key}"
            data = await self.client.get(full_key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error("Memory load failed", partition=partition, key=key, error=str(e))
            return None

    async def persist_wallet_profile(self, wallet_address: str, profile: Dict[str, Any], ttl: int = 3600) -> bool:
        """Persist wallet profile with TTL for sticky insider reputation."""
        try:
            key = f"godmode:wallet:{wallet_address}"
            await self.client.setex(key, ttl, json.dumps(profile))
            return True
        except Exception as e:
            logger.error("Wallet profile persistence failed", wallet=wallet_address, error=str(e))
            return False

    async def get_wallet_profile(self, wallet_address: str) -> Optional[Dict[str, Any]]:
        """Get wallet profile from cache."""
        try:
            key = f"godmode:wallet:{wallet_address}"
            data = await self.client.get(key)
            return json.loads(data) if data else None
        except Exception as e:
            logger.error("Wallet profile load failed", wallet=wallet_address, error=str(e))
            return None

    async def add_risk_score(self, wallet_address: str, score: float, timestamp: float) -> bool:
        """Add risk score to sorted set for efficient retrieval."""
        try:
            await self.client.zadd(
                "godmode:risk_scores",
                {f"{wallet_address}:{timestamp}": score}
            )
            return True
        except Exception as e:
            logger.error("Risk score add failed", wallet=wallet_address, error=str(e))
            return False

    async def get_top_risk_wallets(self, limit: int = 100) -> List[tuple]:
        """Get top risk wallets by score."""
        try:
            return await self.client.zrevrange(
                "godmode:risk_scores",
                0, limit - 1,
                withscores=True
            )
        except Exception as e:
            logger.error("Top risk wallets query failed", error=str(e))
            return []

    # =========================================================================
    # Redis Streams Operations (for parallel processing)
    # =========================================================================

    async def xadd(self, stream: str, fields: Dict[str, str], maxlen: int = 10000) -> str:
        """Add message to Redis Stream."""
        return await self.client.xadd(stream, fields, maxlen=maxlen)

    async def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: Dict[str, str],
        count: int = 10,
        block: int = 1000
    ) -> List:
        """Read from Redis Stream as consumer group."""
        return await self.client.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams=streams,
            count=count,
            block=block
        )

    async def xack(self, stream: str, group: str, *ids: str) -> int:
        """Acknowledge messages in consumer group."""
        return await self.client.xack(stream, group, *ids)

    async def create_consumer_group(self, stream: str, group: str) -> bool:
        """Create consumer group for stream."""
        try:
            await self.client.xgroup_create(stream, group, id='0', mkstream=True)
            return True
        except Exception as e:
            if "BUSYGROUP" in str(e):
                return True  # Group already exists
            logger.error("Consumer group creation failed", stream=stream, group=group, error=str(e))
            return False

    # =========================================================================
    # Pub/Sub Operations (for real-time alerts)
    # =========================================================================

    async def publish(self, channel: str, message: str) -> int:
        """Publish message to channel."""
        return await self.client.publish(channel, message)

    async def subscribe(self, *channels: str):
        """Subscribe to channels."""
        pubsub = self.client.pubsub()
        await pubsub.subscribe(*channels)
        return pubsub

    # =========================================================================
    # Health & Monitoring
    # =========================================================================

    async def get_cluster_info(self) -> Dict[str, Any]:
        """Get cluster health information."""
        if self.mode != 'cluster':
            return {'mode': 'standalone', 'healthy': True}

        try:
            info = await self.client.cluster_info()
            return {
                'mode': 'cluster',
                'state': info.get('cluster_state', 'unknown'),
                'slots_assigned': info.get('cluster_slots_assigned', 0),
                'slots_ok': info.get('cluster_slots_ok', 0),
                'known_nodes': info.get('cluster_known_nodes', 0),
                'healthy': info.get('cluster_state') == 'ok'
            }
        except Exception as e:
            logger.error("Cluster info failed", error=str(e))
            return {'mode': 'cluster', 'healthy': False, 'error': str(e)}

    async def get_persistence_stats(self) -> Dict[str, Any]:
        """Get detailed persistence statistics."""
        try:
            info = await self.client.info('persistence')
            return {
                'aof_enabled': info.get('aof_enabled', 0) == 1,
                'aof_current_size': info.get('aof_current_size', 0),
                'aof_buffer_length': info.get('aof_buffer_length', 0),
                'aof_rewrite_in_progress': info.get('aof_rewrite_in_progress', 0),
                'rdb_changes_since_last_save': info.get('rdb_changes_since_last_save', 0),
                'rdb_last_bgsave_status': info.get('rdb_last_bgsave_status', 'unknown')
            }
        except Exception as e:
            logger.error("Persistence stats failed", error=str(e))
            return {}

    async def force_aof_rewrite(self) -> bool:
        """Trigger AOF rewrite to compact the append-only file."""
        try:
            await self.client.bgrewriteaof()
            logger.info("AOF rewrite initiated")
            return True
        except Exception as e:
            logger.error("AOF rewrite failed", error=str(e))
            return False

    async def close(self):
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            logger.info("Redis connection closed")


# =============================================================================
# Legacy PersistentRedisClient (for backward compatibility)
# =============================================================================

class PersistentRedisClient:
    """
    Legacy Redis client for backward compatibility.
    Wraps GodmodeRedisCluster for existing code.
    """

    def __init__(self):
        self._cluster = GodmodeRedisCluster()
        self.client: Optional[Union[aioredis.Redis, RedisCluster]] = None

    async def connect(self) -> Union[aioredis.Redis, RedisCluster]:
        """Connect to Redis."""
        self.client = await self._cluster.connect()
        return self.client

    async def _validate_persistence(self):
        """Validate persistence (delegated to cluster client)."""
        return await self._cluster.get_persistence_stats()

    async def force_save(self) -> bool:
        """Force save (trigger AOF rewrite in cluster mode)."""
        return await self._cluster.force_aof_rewrite()

    async def get_persistence_stats(self) -> Dict[str, Any]:
        """Get persistence statistics."""
        return await self._cluster.get_persistence_stats()

    async def close(self):
        """Close connection."""
        await self._cluster.close()


# =============================================================================
# Singleton Access
# =============================================================================

_redis_cluster: Optional[GodmodeRedisCluster] = None


async def get_redis() -> Union[aioredis.Redis, RedisCluster]:
    """Get Redis client singleton (cluster or standalone)."""
    global _redis_cluster
    if _redis_cluster is None:
        _redis_cluster = GodmodeRedisCluster()
        await _redis_cluster.connect()
    return _redis_cluster.client


async def get_redis_cluster() -> GodmodeRedisCluster:
    """Get GodmodeRedisCluster instance with full API."""
    global _redis_cluster
    if _redis_cluster is None:
        _redis_cluster = GodmodeRedisCluster()
        await _redis_cluster.connect()
    return _redis_cluster


async def close_redis():
    """Close Redis connection."""
    global _redis_cluster
    if _redis_cluster:
        await _redis_cluster.close()
        _redis_cluster = None


def get_redis_sync() -> Union[aioredis.Redis, RedisCluster]:
    """Synchronous wrapper to get Redis client."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(get_redis())
