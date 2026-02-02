#!/usr/bin/env python3
"""
Unified Storage Configuration for GODMODESCANNER
================================================
Single source of truth for all storage paths and Redis cluster topology.
All agents MUST import paths from this module.

Usage:
    from config.storage_config import StorageConfig
    config = StorageConfig.get_instance()

    # Access paths
    memory_path = config.memory_path
    redis_path = config.redis_data_dir

    # Access Redis cluster config
    redis_mode = config.redis_mode
    cluster_nodes = config.redis_cluster_nodes
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class RedisClusterConfig:
    """
    Redis Cluster configuration for 6-node AOF-only architecture.
    Optimized for 100,000+ writes/sec with zero I/O bottlenecks.
    """

    # Mode: 'standalone' or 'cluster'
    mode: str = field(default_factory=lambda: os.getenv('REDIS_MODE', 'standalone'))

    # Cluster nodes (3 masters + 3 replicas)
    cluster_nodes: List[str] = field(default_factory=lambda: [
        node.strip() for node in os.getenv(
            'REDIS_CLUSTER_NODES',
            '172.28.1.1:6379,172.28.1.2:6379,172.28.1.3:6379'
        ).split(',')
    ])

    # Master nodes (for write operations)
    master_nodes: List[str] = field(default_factory=lambda: [
        '172.28.1.1:6379',  # redis-master-1
        '172.28.1.2:6379',  # redis-master-2
        '172.28.1.3:6379',  # redis-master-3
    ])

    # Replica nodes (for read operations)
    replica_nodes: List[str] = field(default_factory=lambda: [
        '172.28.1.4:6379',  # redis-replica-1
        '172.28.1.5:6379',  # redis-replica-2
        '172.28.1.6:6379',  # redis-replica-3
    ])

    # Standalone fallback
    standalone_host: str = field(default_factory=lambda: os.getenv('REDIS_HOST', 'localhost'))
    standalone_port: int = field(default_factory=lambda: int(os.getenv('REDIS_PORT', 6379)))

    # Connection pool settings
    max_connections_per_node: int = field(default_factory=lambda: int(os.getenv('REDIS_MAX_CONNECTIONS', 100)))

    # Cluster settings
    cluster_node_timeout: int = 5000  # ms
    read_from_replicas: bool = True
    skip_full_coverage_check: bool = True

    # AOF persistence settings
    aof_enabled: bool = True
    aof_fsync: str = 'everysec'  # 'always', 'everysec', 'no'
    aof_rewrite_percentage: int = 100
    aof_rewrite_min_size: str = '64mb'

    # Memory settings
    maxmemory: str = '1800mb'
    maxmemory_policy: str = 'allkeys-lru'

    def get_startup_nodes(self) -> List[Dict[str, Any]]:
        """Get startup nodes for RedisCluster client."""
        nodes = []
        for node_str in self.cluster_nodes:
            host, port = node_str.split(':')
            nodes.append({'host': host, 'port': int(port)})
        return nodes

    def get_connection_url(self) -> str:
        """Get Redis connection URL (for standalone mode)."""
        return f"redis://{self.standalone_host}:{self.standalone_port}"

    def to_dict(self) -> Dict[str, Any]:
        """Export configuration as dictionary."""
        return {
            'mode': self.mode,
            'cluster_nodes': self.cluster_nodes,
            'master_nodes': self.master_nodes,
            'replica_nodes': self.replica_nodes,
            'standalone_host': self.standalone_host,
            'standalone_port': self.standalone_port,
            'max_connections_per_node': self.max_connections_per_node,
            'aof_enabled': self.aof_enabled,
            'aof_fsync': self.aof_fsync,
            'maxmemory': self.maxmemory,
            'maxmemory_policy': self.maxmemory_policy,
        }


@dataclass
class StorageConfig:
    """
    Centralized storage configuration with environment variable overrides.
    Uses singleton pattern to ensure consistency across all agents.

    Now includes Redis cluster topology for 6-node AOF-only architecture.
    """

    # Base paths
    data_dir: Path = field(default_factory=lambda: Path(os.getenv('DATA_DIR', '/data')))
    project_root: Path = field(default_factory=lambda: Path('/a0/usr/projects/godmodescanner/projects/godmodescanner'))

    # Memory paths
    memory_path: Path = field(default=None)
    memory_patterns_path: Path = field(default=None)
    memory_insights_path: Path = field(default=None)
    memory_wallets_path: Path = field(default=None)
    memory_rules_path: Path = field(default=None)

    # Redis paths
    redis_data_dir: Path = field(default=None)

    # Redis cluster configuration
    redis_config: RedisClusterConfig = field(default=None)

    # Other data paths
    graph_data_path: Path = field(default=None)
    models_path: Path = field(default=None)
    knowledge_path: Path = field(default=None)
    log_path: Path = field(default=None)

    # Singleton instance
    _instance: Optional['StorageConfig'] = None

    def __post_init__(self):
        """Initialize paths from environment variables with fallbacks."""
        # Memory paths
        self.memory_path = Path(os.getenv('MEMORY_STORAGE_PATH', str(self.data_dir / 'memory')))
        self.memory_patterns_path = Path(os.getenv('MEMORY_PATTERNS_PATH', str(self.memory_path / 'patterns')))
        self.memory_insights_path = Path(os.getenv('MEMORY_INSIGHTS_PATH', str(self.memory_path / 'insights')))
        self.memory_wallets_path = Path(os.getenv('MEMORY_WALLETS_PATH', str(self.memory_path / 'wallets')))
        self.memory_rules_path = Path(os.getenv('MEMORY_RULES_PATH', str(self.memory_path / 'rules')))

        # Redis paths
        self.redis_data_dir = Path(os.getenv('REDIS_DATA_DIR', str(self.data_dir / 'redis')))

        # Initialize Redis cluster configuration
        self.redis_config = RedisClusterConfig()

        # Other paths
        self.graph_data_path = Path(os.getenv('GRAPH_DATA_PATH', str(self.data_dir / 'graph_data')))
        self.models_path = Path(os.getenv('MODELS_PATH', str(self.data_dir / 'models')))
        self.knowledge_path = Path(os.getenv('KNOWLEDGE_PATH', str(self.data_dir / 'knowledge')))
        self.log_path = Path(os.getenv('LOG_PATH', '/var/log/godmodescanner'))

        # Ensure all directories exist
        self._ensure_directories()

    # =========================================================================
    # Redis Cluster Properties (convenience accessors)
    # =========================================================================

    @property
    def redis_mode(self) -> str:
        """Get Redis mode: 'standalone' or 'cluster'."""
        return self.redis_config.mode

    @property
    def redis_cluster_nodes(self) -> List[str]:
        """Get list of Redis cluster nodes."""
        return self.redis_config.cluster_nodes

    @property
    def redis_master_nodes(self) -> List[str]:
        """Get list of Redis master nodes."""
        return self.redis_config.master_nodes

    @property
    def redis_replica_nodes(self) -> List[str]:
        """Get list of Redis replica nodes."""
        return self.redis_config.replica_nodes

    @property
    def redis_max_connections(self) -> int:
        """Get max connections per Redis node."""
        return self.redis_config.max_connections_per_node

    def get_redis_startup_nodes(self) -> List[Dict[str, Any]]:
        """Get Redis cluster startup nodes for client initialization."""
        return self.redis_config.get_startup_nodes()

    def get_redis_url(self) -> str:
        """Get Redis connection URL (for standalone mode)."""
        return self.redis_config.get_connection_url()

    # =========================================================================
    # Directory Management
    # =========================================================================

    def _ensure_directories(self):
        """Create all required directories if they don't exist."""
        directories = [
            self.memory_path,
            self.memory_patterns_path,
            self.memory_insights_path,
            self.memory_wallets_path,
            self.memory_rules_path,
            self.redis_data_dir,
            self.graph_data_path,
            self.models_path,
            self.knowledge_path,
            self.log_path,
        ]

        # Add Redis cluster data directories
        for i in range(1, 4):
            directories.append(self.redis_data_dir / f'm{i}')  # Master nodes
            directories.append(self.redis_data_dir / f'r{i}')  # Replica nodes

        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                logger.warning(f"Cannot create directory (permission denied): {directory}")
            except Exception as e:
                logger.warning(f"Cannot create directory {directory}: {e}")

    @classmethod
    def get_instance(cls) -> 'StorageConfig':
        """Get singleton instance of StorageConfig."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton instance (useful for testing)."""
        cls._instance = None

    def get_memory_partition_path(self, partition: str) -> Path:
        """
        Get path for a specific memory partition.

        Args:
            partition: One of 'patterns', 'insights', 'wallets', 'rules'

        Returns:
            Path to the partition directory
        """
        partitions = {
            'patterns': self.memory_patterns_path,
            'insights': self.memory_insights_path,
            'wallets': self.memory_wallets_path,
            'rules': self.memory_rules_path,
        }
        return partitions.get(partition, self.memory_path / partition)

    def get_redis_node_data_path(self, node_type: str, node_num: int) -> Path:
        """
        Get data path for a specific Redis cluster node.

        Args:
            node_type: 'm' for master, 'r' for replica
            node_num: Node number (1-3)

        Returns:
            Path to the node's data directory
        """
        return self.redis_data_dir / f'{node_type}{node_num}'

    def validate(self) -> dict:
        """
        Validate storage configuration.

        Returns:
            Dict with validation results
        """
        results = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'paths': {},
            'redis': {}
        }

        paths_to_check = [
            ('data_dir', self.data_dir),
            ('memory_path', self.memory_path),
            ('memory_patterns_path', self.memory_patterns_path),
            ('memory_insights_path', self.memory_insights_path),
            ('memory_wallets_path', self.memory_wallets_path),
            ('memory_rules_path', self.memory_rules_path),
            ('redis_data_dir', self.redis_data_dir),
            ('graph_data_path', self.graph_data_path),
            ('models_path', self.models_path),
            ('knowledge_path', self.knowledge_path),
        ]

        for name, path in paths_to_check:
            path_info = {
                'path': str(path),
                'exists': path.exists(),
                'writable': False
            }

            if path.exists():
                try:
                    test_file = path / '.write_test'
                    test_file.write_text('test')
                    test_file.unlink()
                    path_info['writable'] = True
                except:
                    results['warnings'].append(f"{name} is not writable")
            else:
                results['errors'].append(f"{name} does not exist: {path}")
                results['valid'] = False

            results['paths'][name] = path_info

        # Validate Redis cluster configuration
        results['redis'] = {
            'mode': self.redis_mode,
            'cluster_nodes': self.redis_cluster_nodes,
            'max_connections': self.redis_max_connections,
        }

        if self.redis_mode == 'cluster' and len(self.redis_cluster_nodes) < 3:
            results['warnings'].append("Redis cluster has fewer than 3 nodes")

        return results

    def to_dict(self) -> dict:
        """Export configuration as dictionary."""
        return {
            'data_dir': str(self.data_dir),
            'memory_path': str(self.memory_path),
            'memory_patterns_path': str(self.memory_patterns_path),
            'memory_insights_path': str(self.memory_insights_path),
            'memory_wallets_path': str(self.memory_wallets_path),
            'memory_rules_path': str(self.memory_rules_path),
            'redis_data_dir': str(self.redis_data_dir),
            'redis_config': self.redis_config.to_dict(),
            'graph_data_path': str(self.graph_data_path),
            'models_path': str(self.models_path),
            'knowledge_path': str(self.knowledge_path),
            'log_path': str(self.log_path),
        }

    def __repr__(self):
        return f"StorageConfig(data_dir={self.data_dir}, redis_mode={self.redis_mode})"


# Convenience function for quick access
def get_storage_config() -> StorageConfig:
    """Get the singleton StorageConfig instance."""
    return StorageConfig.get_instance()


def get_redis_config() -> RedisClusterConfig:
    """Get the Redis cluster configuration."""
    return StorageConfig.get_instance().redis_config


class Paths:
    """Lazy-loaded path constants."""

    @property
    def DATA_DIR(self) -> Path:
        return get_storage_config().data_dir

    @property
    def MEMORY_PATH(self) -> Path:
        return get_storage_config().memory_path

    @property
    def MEMORY_PATTERNS(self) -> Path:
        return get_storage_config().memory_patterns_path

    @property
    def MEMORY_INSIGHTS(self) -> Path:
        return get_storage_config().memory_insights_path

    @property
    def MEMORY_WALLETS(self) -> Path:
        return get_storage_config().memory_wallets_path

    @property
    def MEMORY_RULES(self) -> Path:
        return get_storage_config().memory_rules_path

    @property
    def REDIS_DATA(self) -> Path:
        return get_storage_config().redis_data_dir

    @property
    def GRAPH_DATA(self) -> Path:
        return get_storage_config().graph_data_path

    @property
    def MODELS(self) -> Path:
        return get_storage_config().models_path

    @property
    def KNOWLEDGE(self) -> Path:
        return get_storage_config().knowledge_path

    @property
    def LOGS(self) -> Path:
        return get_storage_config().log_path


class Redis:
    """Lazy-loaded Redis configuration constants."""

    @property
    def MODE(self) -> str:
        return get_redis_config().mode

    @property
    def CLUSTER_NODES(self) -> List[str]:
        return get_redis_config().cluster_nodes

    @property
    def MASTER_NODES(self) -> List[str]:
        return get_redis_config().master_nodes

    @property
    def REPLICA_NODES(self) -> List[str]:
        return get_redis_config().replica_nodes

    @property
    def MAX_CONNECTIONS(self) -> int:
        return get_redis_config().max_connections_per_node

    @property
    def STANDALONE_URL(self) -> str:
        return get_redis_config().get_connection_url()


# Singleton instances
paths = Paths()
redis = Redis()


if __name__ == "__main__":
    # Test the configuration
    config = StorageConfig.get_instance()
    print("GODMODESCANNER Storage Configuration")
    print("=" * 60)

    print("
📁 Storage Paths:")
    for name, path in config.to_dict().items():
        if name != 'redis_config':
            exists = "✅" if Path(path).exists() else "❌"
            print(f"  {exists} {name}: {path}")

    print("
🔴 Redis Cluster Configuration:")
    redis_cfg = config.redis_config.to_dict()
    print(f"  Mode: {redis_cfg['mode']}")
    print(f"  Cluster Nodes: {redis_cfg['cluster_nodes']}")
    print(f"  Master Nodes: {redis_cfg['master_nodes']}")
    print(f"  Replica Nodes: {redis_cfg['replica_nodes']}")
    print(f"  Max Connections/Node: {redis_cfg['max_connections_per_node']}")
    print(f"  AOF Enabled: {redis_cfg['aof_enabled']}")
    print(f"  AOF Fsync: {redis_cfg['aof_fsync']}")
    print(f"  Max Memory: {redis_cfg['maxmemory']}")
    print(f"  Eviction Policy: {redis_cfg['maxmemory_policy']}")

    print("
🔍 Validation Results:")
    validation = config.validate()
    print(f"  Valid: {validation['valid']}")
    if validation['errors']:
        print(f"  Errors: {validation['errors']}")
    if validation['warnings']:
        print(f"  Warnings: {validation['warnings']}")
