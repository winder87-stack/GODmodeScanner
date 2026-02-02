
"""
Wallet Graph Builder - Transaction-Based Relationship Graph Construction
========================================================================

Builds and maintains a directed graph of wallet relationships based on
Solana transaction data, optimized for insider network detection.

Features:
- Real-time graph updates from transaction stream
- Edge weighting based on transaction patterns
- Temporal relationship tracking
- Memory-efficient sparse graph representation
- Integration with Redis for persistence
"""

import asyncio
import time
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import structlog

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = structlog.get_logger(__name__)


class EdgeType(Enum):
    """Types of relationships between wallets."""
    TRANSFER = "transfer"           # Direct SOL/token transfer
    FUNDING = "funding"             # Funding relationship
    SWAP = "swap"                   # DEX swap interaction
    TOKEN_MINT = "token_mint"       # Token minting relationship
    PROGRAM_INTERACTION = "program" # Shared program interaction
    TEMPORAL = "temporal"           # Time-correlated activity


@dataclass
class WalletNode:
    """Represents a wallet in the graph."""
    address: str
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    # Activity metrics
    transaction_count: int = 0
    total_volume_sol: float = 0.0
    unique_interactions: int = 0

    # Classification
    is_known_insider: bool = False
    is_seed_node: bool = False
    cluster_id: Optional[str] = None

    # Risk indicators
    early_buyer_count: int = 0
    sniper_score: float = 0.0

    def update_activity(self, volume: float = 0.0):
        """Update activity metrics."""
        self.transaction_count += 1
        self.total_volume_sol += volume
        self.last_seen = time.time()


@dataclass
class WalletEdge:
    """Represents a relationship between two wallets."""
    source: str
    target: str
    edge_type: EdgeType

    # Relationship strength
    weight: float = 1.0
    transaction_count: int = 1
    total_volume: float = 0.0

    # Temporal data
    first_interaction: float = field(default_factory=time.time)
    last_interaction: float = field(default_factory=time.time)

    # Pattern indicators
    avg_time_between_txs: float = 0.0
    is_bidirectional: bool = False

    def update(self, volume: float = 0.0):
        """Update edge with new interaction."""
        now = time.time()

        # Update time average
        if self.transaction_count > 0:
            time_diff = now - self.last_interaction
            self.avg_time_between_txs = (
                (self.avg_time_between_txs * self.transaction_count + time_diff) /
                (self.transaction_count + 1)
            )

        self.transaction_count += 1
        self.total_volume += volume
        self.last_interaction = now

        # Increase weight based on frequency
        self.weight = min(10.0, 1.0 + (self.transaction_count * 0.1))


@dataclass
class GraphMetrics:
    """Metrics for the wallet graph."""
    total_nodes: int = 0
    total_edges: int = 0
    seed_nodes: int = 0
    known_insiders: int = 0

    # Graph properties
    density: float = 0.0
    avg_degree: float = 0.0
    max_degree: int = 0

    # Cluster metrics
    cluster_count: int = 0
    largest_cluster_size: int = 0

    # Performance
    last_update: float = 0.0
    updates_per_second: float = 0.0


class WalletGraphBuilder:
    """
    Builds and maintains a wallet relationship graph for insider detection.

    The graph is constructed from transaction data and used to identify
    clusters of related wallets that may indicate coordinated insider activity.

    Features:
    - Real-time graph updates
    - Multiple edge types for different relationships
    - Seed node initialization for known insiders
    - Redis persistence for graph state
    - Memory-efficient sparse representation
    """

    # Known pump.fun related addresses
    PUMP_FUN_PROGRAM = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

    def __init__(
        self,
        redis_url: Optional[str] = None,
        max_nodes: int = 100000,
        max_edges_per_node: int = 1000,
        edge_ttl_hours: float = 168.0,  # 7 days
        enable_persistence: bool = True,
    ):
        """
        Initialize the graph builder.

        Args:
            redis_url: Redis connection URL for persistence
            max_nodes: Maximum nodes to track
            max_edges_per_node: Maximum edges per node
            edge_ttl_hours: Edge expiration time
            enable_persistence: Enable Redis persistence
        """
        self.redis_url = redis_url
        self.max_nodes = max_nodes
        self.max_edges_per_node = max_edges_per_node
        self.edge_ttl_seconds = edge_ttl_hours * 3600
        self.enable_persistence = enable_persistence

        # Initialize graph
        if NETWORKX_AVAILABLE:
            self.graph = nx.DiGraph()
        else:
            # Fallback to simple adjacency list
            self.graph = None
            self._adjacency: Dict[str, Dict[str, WalletEdge]] = defaultdict(dict)

        # Node and edge storage
        self.nodes: Dict[str, WalletNode] = {}
        self.edges: Dict[Tuple[str, str], WalletEdge] = {}

        # Seed nodes (known insiders)
        self.seed_nodes: Set[str] = set()

        # Redis client
        self.redis: Optional[redis.Redis] = None

        # Metrics
        self.metrics = GraphMetrics()
        self._update_count = 0
        self._last_metrics_update = time.time()

        # Locks
        self._lock = asyncio.Lock()

        logger.info(
            "WalletGraphBuilder initialized",
            max_nodes=max_nodes,
            edge_ttl_hours=edge_ttl_hours,
            networkx=NETWORKX_AVAILABLE,
        )

    async def initialize(self):
        """Initialize connections and load state."""
        # Connect to Redis
        if self.enable_persistence and REDIS_AVAILABLE and self.redis_url:
            try:
                self.redis = redis.from_url(self.redis_url)
                await self.redis.ping()
                logger.info("Connected to Redis for graph persistence")

                # Load existing graph state
                await self._load_from_redis()
            except Exception as e:
                logger.warning("Redis connection failed", error=str(e))
                self.redis = None

    async def close(self):
        """Close connections and save state."""
        if self.redis:
            await self._save_to_redis()
            await self.redis.close()

    def add_seed_node(self, address: str, is_known_insider: bool = True):
        """
        Add a seed node (known insider wallet).

        Args:
            address: Wallet address
            is_known_insider: Whether this is a confirmed insider
        """
        self.seed_nodes.add(address)

        if address not in self.nodes:
            self.nodes[address] = WalletNode(
                address=address,
                is_known_insider=is_known_insider,
                is_seed_node=True,
            )
        else:
            self.nodes[address].is_known_insider = is_known_insider
            self.nodes[address].is_seed_node = True

        # Add to NetworkX graph
        if NETWORKX_AVAILABLE and self.graph is not None:
            self.graph.add_node(
                address,
                is_seed=True,
                is_insider=is_known_insider,
            )

        self.metrics.seed_nodes = len(self.seed_nodes)
        logger.info("Added seed node", address=address[:16] + "...")

    def add_seed_nodes_batch(self, addresses: List[str]):
        """Add multiple seed nodes."""
        for addr in addresses:
            self.add_seed_node(addr)

    async def process_transaction(
        self,
        signature: str,
        sender: str,
        receiver: str,
        amount_sol: float,
        token_mint: Optional[str] = None,
        program_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ):
        """
        Process a transaction and update the graph.

        Args:
            signature: Transaction signature
            sender: Sender wallet address
            receiver: Receiver wallet address
            amount_sol: Transaction amount in SOL
            token_mint: Token mint address if token transfer
            program_id: Program ID if program interaction
            timestamp: Transaction timestamp
        """
        async with self._lock:
            timestamp = timestamp or time.time()

            # Determine edge type
            if program_id == self.PUMP_FUN_PROGRAM:
                edge_type = EdgeType.SWAP
            elif token_mint:
                edge_type = EdgeType.TOKEN_MINT
            elif amount_sol > 0:
                edge_type = EdgeType.TRANSFER
            else:
                edge_type = EdgeType.PROGRAM_INTERACTION

            # Update or create nodes
            self._ensure_node(sender)
            self._ensure_node(receiver)

            self.nodes[sender].update_activity(amount_sol)
            self.nodes[receiver].update_activity(amount_sol)
            self.nodes[sender].unique_interactions += 1
            self.nodes[receiver].unique_interactions += 1

            # Update or create edge
            edge_key = (sender, receiver)
            if edge_key in self.edges:
                self.edges[edge_key].update(amount_sol)
            else:
                self.edges[edge_key] = WalletEdge(
                    source=sender,
                    target=receiver,
                    edge_type=edge_type,
                    total_volume=amount_sol,
                    first_interaction=timestamp,
                    last_interaction=timestamp,
                )

            # Check for bidirectional relationship
            reverse_key = (receiver, sender)
            if reverse_key in self.edges:
                self.edges[edge_key].is_bidirectional = True
                self.edges[reverse_key].is_bidirectional = True

            # Update NetworkX graph
            if NETWORKX_AVAILABLE and self.graph is not None:
                self.graph.add_edge(
                    sender,
                    receiver,
                    weight=self.edges[edge_key].weight,
                    edge_type=edge_type.value,
                    volume=amount_sol,
                )

            # Update metrics
            self._update_count += 1
            self._update_metrics()

    async def process_transactions_batch(
        self,
        transactions: List[Dict[str, Any]],
    ):
        """
        Process multiple transactions in batch.

        Args:
            transactions: List of transaction dictionaries
        """
        for tx in transactions:
            await self.process_transaction(
                signature=tx.get("signature", ""),
                sender=tx.get("sender", ""),
                receiver=tx.get("receiver", ""),
                amount_sol=tx.get("amount_sol", 0.0),
                token_mint=tx.get("token_mint"),
                program_id=tx.get("program_id"),
                timestamp=tx.get("timestamp"),
            )

    def _ensure_node(self, address: str):
        """Ensure node exists in graph."""
        if address not in self.nodes:
            # Check capacity
            if len(self.nodes) >= self.max_nodes:
                self._evict_oldest_nodes()

            self.nodes[address] = WalletNode(address=address)

            if NETWORKX_AVAILABLE and self.graph is not None:
                self.graph.add_node(address)

    def _evict_oldest_nodes(self, count: int = 1000):
        """Evict oldest nodes to make room."""
        # Sort by last_seen and remove oldest
        sorted_nodes = sorted(
            self.nodes.items(),
            key=lambda x: x[1].last_seen
        )

        for address, _ in sorted_nodes[:count]:
            # Don't evict seed nodes
            if address in self.seed_nodes:
                continue

            # Remove node
            del self.nodes[address]

            # Remove associated edges
            edges_to_remove = [
                k for k in self.edges.keys()
                if k[0] == address or k[1] == address
            ]
            for k in edges_to_remove:
                del self.edges[k]

            # Remove from NetworkX
            if NETWORKX_AVAILABLE and self.graph is not None:
                if address in self.graph:
                    self.graph.remove_node(address)

        logger.debug(f"Evicted {count} oldest nodes")

    def _update_metrics(self):
        """Update graph metrics."""
        now = time.time()
        elapsed = now - self._last_metrics_update

        if elapsed >= 1.0:  # Update every second
            self.metrics.total_nodes = len(self.nodes)
            self.metrics.total_edges = len(self.edges)
            self.metrics.updates_per_second = self._update_count / elapsed
            self.metrics.last_update = now

            if NETWORKX_AVAILABLE and self.graph is not None and len(self.graph) > 0:
                self.metrics.density = nx.density(self.graph)
                degrees = [d for _, d in self.graph.degree()]
                self.metrics.avg_degree = sum(degrees) / len(degrees) if degrees else 0
                self.metrics.max_degree = max(degrees) if degrees else 0

            self._update_count = 0
            self._last_metrics_update = now

    def get_node(self, address: str) -> Optional[WalletNode]:
        """Get node by address."""
        return self.nodes.get(address)

    def get_neighbors(self, address: str, direction: str = "both") -> List[str]:
        """
        Get neighboring wallets.

        Args:
            address: Wallet address
            direction: "in", "out", or "both"

        Returns:
            List of neighbor addresses
        """
        if NETWORKX_AVAILABLE and self.graph is not None:
            if address not in self.graph:
                return []

            if direction == "in":
                return list(self.graph.predecessors(address))
            elif direction == "out":
                return list(self.graph.successors(address))
            else:
                return list(set(
                    list(self.graph.predecessors(address)) +
                    list(self.graph.successors(address))
                ))
        else:
            # Fallback implementation
            neighbors = set()
            for (src, tgt) in self.edges.keys():
                if direction in ["out", "both"] and src == address:
                    neighbors.add(tgt)
                if direction in ["in", "both"] and tgt == address:
                    neighbors.add(src)
            return list(neighbors)

    def get_edge(self, source: str, target: str) -> Optional[WalletEdge]:
        """Get edge between two wallets."""
        return self.edges.get((source, target))

    def get_path(
        self,
        source: str,
        target: str,
        max_hops: int = 5,
    ) -> Optional[List[str]]:
        """
        Find shortest path between two wallets.

        Args:
            source: Source wallet address
            target: Target wallet address
            max_hops: Maximum path length

        Returns:
            List of addresses in path or None
        """
        if not NETWORKX_AVAILABLE or self.graph is None:
            return None

        if source not in self.graph or target not in self.graph:
            return None

        try:
            path = nx.shortest_path(
                self.graph,
                source=source,
                target=target,
            )
            if len(path) <= max_hops + 1:
                return path
            return None
        except nx.NetworkXNoPath:
            return None

    def get_subgraph(
        self,
        center: str,
        hops: int = 2,
    ) -> Dict[str, Any]:
        """
        Get subgraph around a wallet.

        Args:
            center: Center wallet address
            hops: Number of hops to include

        Returns:
            Dictionary with nodes and edges
        """
        if not NETWORKX_AVAILABLE or self.graph is None:
            return {"nodes": [], "edges": []}

        if center not in self.graph:
            return {"nodes": [], "edges": []}

        # BFS to find nodes within hops
        visited = {center}
        frontier = {center}

        for _ in range(hops):
            next_frontier = set()
            for node in frontier:
                neighbors = set(self.graph.predecessors(node)) | set(self.graph.successors(node))
                next_frontier |= neighbors - visited
            visited |= next_frontier
            frontier = next_frontier

        # Extract subgraph
        subgraph = self.graph.subgraph(visited)

        return {
            "nodes": [
                {
                    "address": n,
                    "is_center": n == center,
                    "is_seed": n in self.seed_nodes,
                    **(self.nodes[n].__dict__ if n in self.nodes else {}),
                }
                for n in subgraph.nodes()
            ],
            "edges": [
                {
                    "source": u,
                    "target": v,
                    **(self.edges[(u, v)].__dict__ if (u, v) in self.edges else {}),
                }
                for u, v in subgraph.edges()
            ],
        }

    def find_connected_to_seeds(
        self,
        max_hops: int = 3,
    ) -> Dict[str, int]:
        """
        Find all wallets connected to seed nodes within max_hops.

        Args:
            max_hops: Maximum distance from seed nodes

        Returns:
            Dictionary of address -> minimum hops to seed
        """
        if not NETWORKX_AVAILABLE or self.graph is None:
            return {}

        connected = {}

        for seed in self.seed_nodes:
            if seed not in self.graph:
                continue

            # BFS from seed
            visited = {seed: 0}
            frontier = {seed}

            for hop in range(1, max_hops + 1):
                next_frontier = set()
                for node in frontier:
                    neighbors = set(self.graph.predecessors(node)) | set(self.graph.successors(node))
                    for neighbor in neighbors:
                        if neighbor not in visited:
                            visited[neighbor] = hop
                            next_frontier.add(neighbor)
                frontier = next_frontier

            # Update connected with minimum hops
            for addr, hops in visited.items():
                if addr not in connected or hops < connected[addr]:
                    connected[addr] = hops

        return connected

    async def _save_to_redis(self):
        """Save graph state to Redis."""
        if not self.redis:
            return

        try:
            import json

            # Save nodes
            nodes_data = {
                addr: {
                    "address": node.address,
                    "first_seen": node.first_seen,
                    "last_seen": node.last_seen,
                    "transaction_count": node.transaction_count,
                    "is_known_insider": node.is_known_insider,
                    "is_seed_node": node.is_seed_node,
                }
                for addr, node in self.nodes.items()
            }
            await self.redis.set(
                "godmode:graph:nodes",
                json.dumps(nodes_data),
            )

            # Save seed nodes
            await self.redis.sadd("godmode:graph:seeds", *self.seed_nodes) if self.seed_nodes else None

            logger.info(
                "Saved graph to Redis",
                nodes=len(self.nodes),
                edges=len(self.edges),
            )
        except Exception as e:
            logger.error("Failed to save graph to Redis", error=str(e))

    async def _load_from_redis(self):
        """Load graph state from Redis."""
        if not self.redis:
            return

        try:
            import json

            # Load nodes
            nodes_data = await self.redis.get("godmode:graph:nodes")
            if nodes_data:
                nodes_dict = json.loads(nodes_data)
                for addr, data in nodes_dict.items():
                    self.nodes[addr] = WalletNode(
                        address=data["address"],
                        first_seen=data.get("first_seen", time.time()),
                        last_seen=data.get("last_seen", time.time()),
                        transaction_count=data.get("transaction_count", 0),
                        is_known_insider=data.get("is_known_insider", False),
                        is_seed_node=data.get("is_seed_node", False),
                    )

                    if NETWORKX_AVAILABLE and self.graph is not None:
                        self.graph.add_node(addr)

            # Load seed nodes
            seeds = await self.redis.smembers("godmode:graph:seeds")
            if seeds:
                self.seed_nodes = {s.decode() if isinstance(s, bytes) else s for s in seeds}

            logger.info(
                "Loaded graph from Redis",
                nodes=len(self.nodes),
                seeds=len(self.seed_nodes),
            )
        except Exception as e:
            logger.error("Failed to load graph from Redis", error=str(e))

    def get_metrics(self) -> Dict[str, Any]:
        """Get graph metrics."""
        return {
            "total_nodes": self.metrics.total_nodes,
            "total_edges": self.metrics.total_edges,
            "seed_nodes": self.metrics.seed_nodes,
            "density": round(self.metrics.density, 4),
            "avg_degree": round(self.metrics.avg_degree, 2),
            "max_degree": self.metrics.max_degree,
            "updates_per_second": round(self.metrics.updates_per_second, 1),
        }
