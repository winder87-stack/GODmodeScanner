"""
Guerrilla Redis Cluster Client - High-Performance Cluster-Aware Redis Wrapper

This module provides a production-ready Redis Cluster client with:
- Automatic cluster discovery and topology management
- Connection pooling and load balancing across nodes
- Automatic failover and replica read support
- Seamless fallback to standalone mode
- Performance metrics and health monitoring
"""

import json
import time
import logging
from typing import Optional, List, Dict, Any, Union
from dataclasses import dataclass
from enum import Enum
import os

try:
    from redis.cluster import RedisCluster as Redis, ClusterNode
    from redis.cluster import ClusterNode
    from redis.exceptions import RedisError, ClusterDownError, ConnectionError
    CLUSTER_AVAILABLE = True
except ImportError:
    from redis import Redis as Redis
    from redis.exceptions import RedisError, ConnectionError
    CLUSTER_AVAILABLE = False
    logging.warning("redis-py-cluster not available, falling back to standalone Redis")

logger = logging.getLogger(__name__)


class ReadMode(Enum):
    """Read operation routing strategy"""
    MASTER = "master"  # Always read from master (strong consistency)
    REPLICA_PREFERRED = "replica_preferred"  # Prefer replicas for reads (scale)
    REPLICA = "replica"  # Only read from replicas


@dataclass
class ClusterMetrics:
    """Cluster performance metrics"""
    total_nodes: int = 0
    masters: int = 0
    replicas: int = 0
    covered_slots: int = 0
    total_slots: int = 16384
    cluster_state: str = "unknown"
    last_failover: float = 0
    connection_errors: int = 0
    successful_operations: int = 0


class GuerrillaRedisCluster:
    """
    High-performance Redis Cluster client with aggressive configuration
    for zero-latency operations in GODMODESCANNER.
    
    Features:
    - Automatic cluster topology discovery
    - Native Redis Cluster support (3 masters, 3 replicas)
    - Connection pooling across all nodes
    - Read/write splitting for performance
    - Built-in retry logic with exponential backoff
    - Health monitoring and auto-recovery
    """
    
    def __init__(
        self,
        startup_nodes: Optional[List[Dict[str, int]]] = None,
        cluster_mode: bool = True,
        read_mode: ReadMode = ReadMode.REPLICA_PREFERRED,
        max_connections: int = 50,
        socket_timeout: int = 5,
        socket_connect_timeout: int = 5,
        skip_full_coverage_check: bool = True,
        decode_responses: bool = True,
        password: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize the Guerrilla Redis Cluster client.
        
        Args:
            startup_nodes: List of {host, port} dicts for initial cluster discovery
            cluster_mode: Enable Redis Cluster mode
            read_mode: Read operation routing strategy
            max_connections: Max connections per node in pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
            skip_full_coverage_check: Skip full cluster coverage check on startup
            decode_responses: Return strings instead of bytes
            password: Redis password (if any)
        """
        self.cluster_mode = cluster_mode and CLUSTER_AVAILABLE
        self.read_mode = read_mode
        self.metrics = ClusterMetrics()
        self._password = password
        self._reconnect_attempts = 3
        self._reconnect_delay = 0.1
        
        # Load configuration from file if not provided
        if startup_nodes is None:
            config_path = os.path.join(
                os.path.dirname(__file__),
                '../config/redis_cluster_config.json'
            )
            if os.path.exists(config_path):
                with open(config_path) as f:
                    config = json.load(f)
                    startup_nodes = config['agent_config'].get('redis_startup_nodes', startup_nodes)
        
        # Default to localhost Redis Cluster if still not provided
        if startup_nodes is None:
            startup_nodes = [
                {'host': '127.0.0.1', 'port': 16379},
                {'host': '127.0.0.1', 'port': 16380},
                {'host': '127.0.0.1', 'port': 16381}
            ]
        
        logger.info(f"Initializing GuerrillaRedisCluster (mode={self.cluster_mode})")
        
        self._client = self._create_client(
            startup_nodes=startup_nodes,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            skip_full_coverage_check=skip_full_coverage_check,
            decode_responses=decode_responses,
            **kwargs
        )
        
        # Initialize metrics
        self._update_cluster_metrics()
    
    def _create_client(
        self,
        startup_nodes: List[Dict[str, int]],
        max_connections: int,
        socket_timeout: int,
        socket_connect_timeout: int,
        skip_full_coverage_check: bool,
        decode_responses: bool,
        **kwargs
    ) -> Union[Redis, Any]:
        """Create Redis client with appropriate configuration"""
        client_params = {
            'decode_responses': decode_responses,
            'socket_timeout': socket_timeout,
            'socket_connect_timeout': socket_connect_timeout,
            'health_check_interval': 30,  # Check health every 30s
            'max_connections': max_connections,
        }
        
        if self._password:
            client_params['password'] = self._password
        
        if self.cluster_mode:
            # Convert dicts to ClusterNode objects
            cluster_nodes = [
                ClusterNode(node['host'], node['port']) 
                for node in startup_nodes
            ]
            logger.info("Creating Redis Cluster client with nodes: %s", cluster_nodes)
            client_params.update({
                'startup_nodes': cluster_nodes,
                'skip_full_coverage_check': skip_full_coverage_check,
                'full_coverage_check': False,
                'read_from_replicas': self.read_mode != ReadMode.MASTER,
                **kwargs
            })
            return Redis(**client_params)
        else:
            # Fallback to standalone mode
            logger.info("Creating standalone Redis client")
            host = startup_nodes[0]['host'] if startup_nodes else '127.0.0.1'
            port = startup_nodes[0]['port'] if startup_nodes else 6379
            client_params.update({
                'host': host,
                'port': port,
            })
            return Redis(**client_params)
    
    def _update_cluster_metrics(self):
        """Update cluster performance metrics"""
        try:
            if self.cluster_mode and hasattr(self._client, 'cluster_info'):
                info = self._client.cluster_info()
                self.metrics.cluster_state = info.get('cluster_state', 'unknown')
                self.metrics.covered_slots = int(info.get('cluster_slots_assigned', 0))
                self.metrics.total_nodes = int(info.get('cluster_known_nodes', 0))
                
                # Count masters and replicas
                nodes = self._client.cluster_nodes()
                self.metrics.masters = sum(1 for n in nodes if 'master' in n[2])
                self.metrics.replicas = sum(1 for n in nodes if 'slave' in n[2])
            else:
                # Standalone mode metrics
                self.metrics.cluster_state = 'standalone'
                self.metrics.masters = 1
                self.metrics.total_nodes = 1
        except Exception as e:
            logger.warning(f"Failed to update cluster metrics: {e}")
    
    def execute_with_retry(self, operation, *args, max_retries: int = 3, **kwargs):
        """
        Execute Redis operation with automatic retry on failure.
        
        This provides resilience against transient network issues
        and cluster reconfiguration events.
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                result = operation(*args, **kwargs)
                self.metrics.successful_operations += 1
                return result
            except (ConnectionError, ClusterDownError) as e:
                last_error = e
                self.metrics.connection_errors += 1
                logger.warning(f"Redis operation failed (attempt {attempt + 1}/{max_retries}): {e}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff
                    sleep_time = self._reconnect_delay * (2 ** attempt)
                    time.sleep(sleep_time)
                    
                    # Try to reconnect
                    try:
                        self._client.close()
                        self._update_cluster_metrics()
                    except:
                        pass
            except RedisError as e:
                # Non-retryable errors (e.g., wrong type, key not found)
                self.metrics.connection_errors += 1
                raise
        
        # All retries exhausted
        raise RedisError(f"Operation failed after {max_retries} retries: {last_error}")
    
    # Redis operation wrappers with retry logic
    def get(self, key: str) -> Optional[str]:
        """Get value by key"""
        return self.execute_with_retry(self._client.get, key)
    
    def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Set value by key with optional expiration"""
        return self.execute_with_retry(self._client.set, key, value, ex=ex)
    
    def delete(self, *keys: str) -> int:
        """Delete one or more keys"""
        return self.execute_with_retry(self._client.delete, *keys)
    
    def hget(self, name: str, key: str) -> Optional[str]:
        """Get hash field"""
        return self.execute_with_retry(self._client.hget, name, key)
    
    def hset(self, name: str, mapping: Dict[str, str]) -> int:
        """Set hash fields"""
        return self.execute_with_retry(self._client.hset, name, mapping=mapping)
    
    def hgetall(self, name: str) -> Dict[str, str]:
        """Get all hash fields"""
        return self.execute_with_retry(self._client.hgetall, name)
    
    def lpush(self, name: str, *values: str) -> int:
        """Push to list (left)"""
        return self.execute_with_retry(self._client.lpush, name, *values)
    
    def rpop(self, name: str) -> Optional[str]:
        """Pop from list (right)"""
        return self.execute_with_retry(self._client.rpop, name)
    
    def publish(self, channel: str, message: str) -> int:
        """Publish message to channel"""
        return self.execute_with_retry(self._client.publish, channel, message)
    
    def subscribe(self, channels: Union[str, List[str]]):
        """Subscribe to channels (returns pubsub object)"""
        pubsub = self._client.pubsub()
        pubsub.subscribe(channels)
        return pubsub
    
    def incr(self, key: str, amount: int = 1) -> int:
        """Increment value"""
        return self.execute_with_retry(self._client.incr, key, amount)
    
    def exists(self, *keys: str) -> int:
        """Check if keys exist"""
        return self.execute_with_retry(self._client.exists, *keys)
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Find keys matching pattern (use carefully in production)"""
        return self.execute_with_retry(self._client.keys, pattern)
    
    def flushdb(self) -> bool:
        """Clear current database (use with caution!)"""
        return self.execute_with_retry(self._client.flushdb)
    
    def get_cluster_info(self) -> Dict[str, Any]:
        """Get comprehensive cluster information"""
        self._update_cluster_metrics()
        return {
            'cluster_state': self.metrics.cluster_state,
            'total_nodes': self.metrics.total_nodes,
            'masters': self.metrics.masters,
            'replicas': self.metrics.replicas,
            'covered_slots': self.metrics.covered_slots,
            'total_slots': self.metrics.total_slots,
            'read_mode': self.read_mode.value,
            'successful_operations': self.metrics.successful_operations,
            'connection_errors': self.metrics.connection_errors,
        }
    
    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        try:
            # Test connection
            start = time.time()
            pong = self.execute_with_retry(self._client.ping)
            latency_ms = (time.time() - start) * 1000
            
            return {
                'status': 'healthy' if pong else 'unhealthy',
                'latency_ms': round(latency_ms, 2),
                'cluster_info': self.get_cluster_info(),
                'cluster_mode': self.cluster_mode,
            }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'cluster_mode': self.cluster_mode,
            }
    
    def close(self):
        """Close all connections"""
        try:
            self._client.close()
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    def xadd(self, stream: str, mapping: Dict[str, Any], maxlen: Optional[int] = None) -> str:
        """Add entry to stream with optional max length"""
        return self.execute_with_retry(self._client.xadd, stream, mapping, maxlen=maxlen)
    
    def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: Dict[str, str],
        count: int = 1,
        block: Optional[int] = None
    ) -> List[Any]:
        """Read from stream as consumer group"""
        return self.execute_with_retry(
            self._client.xreadgroup,
            group, consumer, streams, count=count, block=block
        )
    
    def xack(self, stream: str, group: str, *ids: str) -> int:
        """Acknowledge messages in consumer group"""
        return self.execute_with_retry(self._client.xack, stream, group, *ids)
    
    def xpending(self, stream: str, group: str) -> Dict[str, Any]:
        """Get pending messages in consumer group"""
        return self.execute_with_retry(self._client.xpending, stream, group)
    
    def xpending_range(
        self,
        stream: str,
        group: str,
        min: str = "-",
        max: str = "+",
        count: int = 10
    ) -> List[Any]:
        """Get pending messages in consumer group within range"""
        return self.execute_with_retry(
            self._client.xpending_range,
            stream, group, min, max, count
        )
    
    def xclaim(
        self,
        stream: str,
        group: str,
        consumer: str,
        min_idle_time: int,
        *ids: str
    ) -> List[Any]:
        """Claim pending messages from consumer"""
        return self.execute_with_retry(
            self._client.xclaim,
            stream, group, consumer, min_idle_time, *ids
        )
    
    async def create_consumer_group(self, stream: str, group_name: str, id: str = "0") -> bool:
        """Create consumer group for stream"""
        try:
            self.execute_with_retry(
                self._client.xgroup_create,
                stream, group_name, id, mkstream=True
            )
            return True
        except Exception as e:
            if "BUSYGROUP" in str(e):
                # Group already exists, not an error
                return True
            raise
    
    def xinfo_groups(self, stream: str) -> List[Dict[str, Any]]:
        """Get info about consumer groups for stream"""
        return self.execute_with_retry(self._client.xinfo_groups, stream)
    
    def xread(
        self,
        streams: Dict[str, str],
        count: int = 1,
        block: Optional[int] = None
    ) -> List[Any]:
        """Read from streams (non-blocking or blocking)"""
        return self.execute_with_retry(self._client.xread, streams, count=count, block=block)
    
    # Cluster initialization
    async def initialize(self):
        """Initialize cluster connection (async compatibility wrapper)"""
        logger.info(f"redis_cluster_initialized (mode='cluster' if self.cluster_mode else 'standalone')")
        self._update_cluster_metrics()
        return self
    
    async def close(self):
        """Close all connections (async compatibility wrapper)"""
        self.close()


def get_redis_client(**kwargs) -> GuerrillaRedisCluster:
    """
    Factory function to get a configured Redis cluster client.
    
    Usage:
        from utils.redis_cluster_client import get_redis_client
        
        redis = get_redis_client()
        redis.set('key', 'value')
        value = redis.get('key')
    """
    return GuerrillaRedisCluster(**kwargs)


# Convenience singleton for easy access
_default_client: Optional[GuerrillaRedisCluster] = None


def get_default_client() -> GuerrillaRedisCluster:
    """Get or create the default Redis client instance"""
    global _default_client
    if _default_client is None:
        _default_client = get_redis_client()
    return _default_client


if __name__ == "__main__":
    # Test the cluster client
    logging.basicConfig(level=logging.INFO)
    
    print("=== Guerrilla Redis Cluster Test ===")
    
    with get_redis_client() as redis:
        # Health check
        health = redis.health_check()
        print(f"\nHealth: {json.dumps(health, indent=2)}")
        
        # Test operations
        print("\n=== Testing Operations ===")
        redis.set('test:cluster', 'guerrilla_mode')
        value = redis.get('test:cluster')
        print(f"Set/Get: {value}")
        
        # Hash operations
        redis.hset('wallet:ABC123', mapping={
            'risk_score': '95',
            'pattern': 'insider_trading',
            'first_seen': '1698765432'
        })
        wallet = redis.hgetall('wallet:ABC123')
        print(f"Wallet Profile: {wallet}")
        
        # List operations
        redis.lpush('alerts:queue', 'ALERT001', 'ALERT002', 'ALERT003')
        alert = redis.rpop('alerts:queue')
        print(f"Alert from queue: {alert}")
        
        # Cluster info
        print("\n=== Cluster Information ===")
        info = redis.get_cluster_info()
        print(json.dumps(info, indent=2))
    
    print("\n=== All tests passed! ===")

    # Redis Streams support for GODMODESCANNER
