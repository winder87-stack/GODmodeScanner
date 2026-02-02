
"""
Cluster Detector - Graph-Based Wallet Cluster Identification
=============================================================

Identifies clusters of related wallets using graph algorithms
optimized for detecting insider networks on pump.fun.

Algorithms:
- Connected Components for basic clustering
- Louvain Community Detection for modularity-based clustering
- DBSCAN for density-based clustering
- Daisy Chain Detection for sequential patterns
- Funding Hub Analysis for centralized funding sources
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
    from networkx.algorithms import community
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False

try:
    from sklearn.cluster import DBSCAN
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# GPU-accelerated graph builder (100x faster when CUDA available)
try:
    from agents.wallet_deanonymizer.gpu_graph_builder import (
        GPUWalletGraphBuilder,
        GPU_AVAILABLE as CUGRAPH_AVAILABLE,
        create_graph_builder
    )
except ImportError:
    CUGRAPH_AVAILABLE = False
    GPUWalletGraphBuilder = None
    create_graph_builder = None

logger = structlog.get_logger(__name__)


class ClusterType(Enum):
    """Types of detected clusters."""
    CONNECTED_COMPONENT = "connected_component"
    COMMUNITY = "community"
    DAISY_CHAIN = "daisy_chain"
    FUNDING_HUB = "funding_hub"
    TEMPORAL = "temporal"
    SYBIL_NETWORK = "sybil_network"


@dataclass
class WalletCluster:
    """Represents a detected wallet cluster."""
    cluster_id: str
    cluster_type: ClusterType
    members: Set[str] = field(default_factory=set)

    # Cluster properties
    size: int = 0
    density: float = 0.0
    avg_degree: float = 0.0

    # Risk indicators
    seed_node_count: int = 0
    insider_count: int = 0
    risk_score: float = 0.0

    # Temporal properties
    first_activity: float = 0.0
    last_activity: float = 0.0
    activity_span_hours: float = 0.0

    # Detection metadata
    detected_at: float = field(default_factory=time.time)
    detection_method: str = ""
    confidence: float = 0.0

    def add_member(self, address: str):
        """Add a member to the cluster."""
        self.members.add(address)
        self.size = len(self.members)

    def merge_with(self, other: 'WalletCluster'):
        """Merge another cluster into this one."""
        self.members |= other.members
        self.size = len(self.members)
        self.seed_node_count += other.seed_node_count
        self.insider_count += other.insider_count
        self.first_activity = min(self.first_activity, other.first_activity) if self.first_activity else other.first_activity
        self.last_activity = max(self.last_activity, other.last_activity)


@dataclass
class DaisyChain:
    """Represents a detected daisy chain pattern."""
    chain_id: str
    wallets: List[str] = field(default_factory=list)

    # Chain properties
    length: int = 0
    total_volume: float = 0.0
    avg_time_between_hops: float = 0.0

    # Risk indicators
    starts_from_seed: bool = False
    ends_at_exchange: bool = False

    def add_hop(self, wallet: str):
        """Add a wallet to the chain."""
        self.wallets.append(wallet)
        self.length = len(self.wallets)


@dataclass
class FundingHub:
    """Represents a centralized funding source."""
    hub_address: str
    funded_wallets: Set[str] = field(default_factory=set)

    # Hub properties
    total_funded: int = 0
    total_volume: float = 0.0
    avg_funding_amount: float = 0.0

    # Temporal properties
    funding_start: float = 0.0
    funding_end: float = 0.0
    funding_frequency: float = 0.0  # Fundings per hour

    # Risk indicators
    is_known_insider: bool = False
    funded_insider_count: int = 0


@dataclass
class DetectionMetrics:
    """Metrics for cluster detection."""
    total_clusters: int = 0
    total_daisy_chains: int = 0
    total_funding_hubs: int = 0

    largest_cluster_size: int = 0
    longest_daisy_chain: int = 0
    most_funded_hub: int = 0

    detection_time_ms: float = 0.0
    last_detection: float = 0.0


class ClusterDetector:
    """
    Detects wallet clusters using multiple graph algorithms.

    Features:
    - Connected component analysis
    - Community detection (Louvain)
    - Daisy chain pattern detection
    - Funding hub identification
    - Temporal correlation analysis
    - Sybil network detection
    """

    def __init__(
        self,
        min_cluster_size: int = 3,
        max_cluster_size: int = 1000,
        daisy_chain_min_length: int = 3,
        funding_hub_min_funded: int = 5,
        temporal_window_seconds: float = 300.0,  # 5 minutes
    ):
        """
        Initialize the cluster detector.

        Args:
            min_cluster_size: Minimum wallets to form a cluster
            max_cluster_size: Maximum cluster size to track
            daisy_chain_min_length: Minimum chain length
            funding_hub_min_funded: Minimum funded wallets for hub
            temporal_window_seconds: Window for temporal correlation
        """
        self.min_cluster_size = min_cluster_size
        self.max_cluster_size = max_cluster_size
        self.daisy_chain_min_length = daisy_chain_min_length
        self.funding_hub_min_funded = funding_hub_min_funded
        self.temporal_window_seconds = temporal_window_seconds

        # Detected structures
        self.clusters: Dict[str, WalletCluster] = {}
        self.daisy_chains: Dict[str, DaisyChain] = {}
        self.funding_hubs: Dict[str, FundingHub] = {}

        # Wallet to cluster mapping
        self.wallet_to_cluster: Dict[str, str] = {}

        # Metrics
        self.metrics = DetectionMetrics()

        # Counter for IDs
        self._cluster_counter = 0
        self._chain_counter = 0

        logger.info(
            "ClusterDetector initialized",
            min_cluster_size=min_cluster_size,
            networkx=NETWORKX_AVAILABLE,
            sklearn=SKLEARN_AVAILABLE,
        )

    async def detect_all(
        self,
        graph: Any,  # NetworkX DiGraph or adjacency dict
        nodes: Dict[str, Any],
        edges: Dict[Tuple[str, str], Any],
        seed_nodes: Set[str],
    ) -> Dict[str, Any]:
        """
        Run all detection algorithms.

        Args:
            graph: NetworkX graph or adjacency structure
            nodes: Node data dictionary
            edges: Edge data dictionary
            seed_nodes: Known insider wallet addresses

        Returns:
            Detection results dictionary
        """
        start_time = time.time()

        results = {
            "clusters": [],
            "daisy_chains": [],
            "funding_hubs": [],
            "metrics": {},
        }

        # Run detection algorithms
        if NETWORKX_AVAILABLE and isinstance(graph, nx.DiGraph):
            # Connected components
            components = await self._detect_connected_components(graph, nodes, seed_nodes)
            results["clusters"].extend(components)

            # Community detection
            communities = await self._detect_communities(graph, nodes, seed_nodes)
            results["clusters"].extend(communities)

            # Daisy chains
            chains = await self._detect_daisy_chains(graph, edges, seed_nodes)
            results["daisy_chains"] = chains

            # Funding hubs
            hubs = await self._detect_funding_hubs(graph, nodes, edges, seed_nodes)
            results["funding_hubs"] = hubs

        # Update metrics
        elapsed_ms = (time.time() - start_time) * 1000
        self.metrics.detection_time_ms = elapsed_ms
        self.metrics.last_detection = time.time()
        self.metrics.total_clusters = len(self.clusters)
        self.metrics.total_daisy_chains = len(self.daisy_chains)
        self.metrics.total_funding_hubs = len(self.funding_hubs)

        results["metrics"] = {
            "detection_time_ms": round(elapsed_ms, 2),
            "total_clusters": self.metrics.total_clusters,
            "total_daisy_chains": self.metrics.total_daisy_chains,
            "total_funding_hubs": self.metrics.total_funding_hubs,
        }

        logger.info(
            "Detection complete",
            clusters=len(results["clusters"]),
            chains=len(results["daisy_chains"]),
            hubs=len(results["funding_hubs"]),
            time_ms=round(elapsed_ms, 2),
        )

        return results

    async def _detect_connected_components(
        self,
        graph: nx.DiGraph,
        nodes: Dict[str, Any],
        seed_nodes: Set[str],
    ) -> List[WalletCluster]:
        """
        Detect connected components in the graph.
        """
        clusters = []

        # Convert to undirected for component analysis
        undirected = graph.to_undirected()

        for component in nx.connected_components(undirected):
            if len(component) < self.min_cluster_size:
                continue
            if len(component) > self.max_cluster_size:
                continue

            cluster_id = self._generate_cluster_id()
            cluster = WalletCluster(
                cluster_id=cluster_id,
                cluster_type=ClusterType.CONNECTED_COMPONENT,
                members=component,
                size=len(component),
                detection_method="connected_components",
            )

            # Calculate properties
            subgraph = graph.subgraph(component)
            cluster.density = nx.density(subgraph)
            degrees = [d for _, d in subgraph.degree()]
            cluster.avg_degree = sum(degrees) / len(degrees) if degrees else 0

            # Count seed nodes and insiders
            cluster.seed_node_count = len(component & seed_nodes)
            cluster.insider_count = sum(
                1 for addr in component
                if addr in nodes and getattr(nodes[addr], 'is_known_insider', False)
            )

            # Calculate confidence based on seed presence
            cluster.confidence = min(1.0, cluster.seed_node_count / max(1, len(component) * 0.1))

            # Store cluster
            self.clusters[cluster_id] = cluster
            for addr in component:
                self.wallet_to_cluster[addr] = cluster_id

            clusters.append(cluster)

            if len(component) > self.metrics.largest_cluster_size:
                self.metrics.largest_cluster_size = len(component)

        return clusters

    async def _detect_communities(
        self,
        graph: nx.DiGraph,
        nodes: Dict[str, Any],
        seed_nodes: Set[str],
    ) -> List[WalletCluster]:
        """
        Detect communities using Louvain algorithm.
        """
        clusters = []

        if len(graph) < self.min_cluster_size:
            return clusters

        try:
            # Convert to undirected for community detection
            undirected = graph.to_undirected()

            # Run Louvain community detection
            communities_generator = community.louvain_communities(
                undirected,
                resolution=1.0,
            )

            for comm in communities_generator:
                if len(comm) < self.min_cluster_size:
                    continue
                if len(comm) > self.max_cluster_size:
                    continue

                cluster_id = self._generate_cluster_id()
                cluster = WalletCluster(
                    cluster_id=cluster_id,
                    cluster_type=ClusterType.COMMUNITY,
                    members=comm,
                    size=len(comm),
                    detection_method="louvain",
                )

                # Calculate properties
                subgraph = graph.subgraph(comm)
                cluster.density = nx.density(subgraph)

                # Count seed nodes
                cluster.seed_node_count = len(comm & seed_nodes)
                cluster.confidence = min(1.0, cluster.seed_node_count / max(1, len(comm) * 0.1))

                self.clusters[cluster_id] = cluster
                clusters.append(cluster)

        except Exception as e:
            logger.warning("Community detection failed", error=str(e))

        return clusters

    async def _detect_daisy_chains(
        self,
        graph: nx.DiGraph,
        edges: Dict[Tuple[str, str], Any],
        seed_nodes: Set[str],
    ) -> List[DaisyChain]:
        """
        Detect daisy chain patterns (sequential wallet chains).

        A daisy chain is a sequence of wallets where funds flow
        linearly: A -> B -> C -> D
        """
        chains = []
        visited = set()

        # Find potential chain starts (nodes with in-degree 0 or 1, out-degree 1)
        for node in graph.nodes():
            if node in visited:
                continue

            in_degree = graph.in_degree(node)
            out_degree = graph.out_degree(node)

            # Potential chain start
            if in_degree <= 1 and out_degree == 1:
                chain = await self._trace_daisy_chain(graph, node, visited)

                if chain and len(chain.wallets) >= self.daisy_chain_min_length:
                    # Check if starts from seed
                    chain.starts_from_seed = chain.wallets[0] in seed_nodes

                    # Calculate total volume
                    for i in range(len(chain.wallets) - 1):
                        edge_key = (chain.wallets[i], chain.wallets[i + 1])
                        if edge_key in edges:
                            chain.total_volume += getattr(edges[edge_key], 'total_volume', 0)

                    self.daisy_chains[chain.chain_id] = chain
                    chains.append(chain)

                    if chain.length > self.metrics.longest_daisy_chain:
                        self.metrics.longest_daisy_chain = chain.length

        return chains

    async def _trace_daisy_chain(
        self,
        graph: nx.DiGraph,
        start: str,
        visited: Set[str],
    ) -> Optional[DaisyChain]:
        """
        Trace a daisy chain from a starting node.
        """
        chain_id = self._generate_chain_id()
        chain = DaisyChain(chain_id=chain_id)

        current = start
        while current and current not in visited:
            visited.add(current)
            chain.add_hop(current)

            # Get next hop (single outgoing edge)
            successors = list(graph.successors(current))
            if len(successors) == 1:
                next_node = successors[0]
                # Check if next node has single incoming edge
                if graph.in_degree(next_node) == 1:
                    current = next_node
                else:
                    break
            else:
                break

        return chain if chain.length >= 2 else None

    async def _detect_funding_hubs(
        self,
        graph: nx.DiGraph,
        nodes: Dict[str, Any],
        edges: Dict[Tuple[str, str], Any],
        seed_nodes: Set[str],
    ) -> List[FundingHub]:
        """
        Detect centralized funding sources (hubs).

        A funding hub is a wallet that funds many other wallets.
        """
        hubs = []

        for node in graph.nodes():
            out_degree = graph.out_degree(node)

            if out_degree >= self.funding_hub_min_funded:
                funded_wallets = set(graph.successors(node))

                hub = FundingHub(
                    hub_address=node,
                    funded_wallets=funded_wallets,
                    total_funded=len(funded_wallets),
                )

                # Calculate total volume
                for target in funded_wallets:
                    edge_key = (node, target)
                    if edge_key in edges:
                        hub.total_volume += getattr(edges[edge_key], 'total_volume', 0)

                hub.avg_funding_amount = hub.total_volume / hub.total_funded if hub.total_funded > 0 else 0

                # Check if hub is known insider
                hub.is_known_insider = node in seed_nodes

                # Count funded insiders
                hub.funded_insider_count = len(funded_wallets & seed_nodes)

                self.funding_hubs[node] = hub
                hubs.append(hub)

                if hub.total_funded > self.metrics.most_funded_hub:
                    self.metrics.most_funded_hub = hub.total_funded

        return hubs

    async def detect_sybil_network(
        self,
        graph: nx.DiGraph,
        nodes: Dict[str, Any],
        seed_nodes: Set[str],
        similarity_threshold: float = 0.8,
    ) -> List[WalletCluster]:
        """
        Detect Sybil networks based on behavioral similarity.

        Sybil wallets often exhibit:
        - Similar transaction timing
        - Similar transaction amounts
        - Common funding sources
        - Coordinated activity patterns
        """
        if not SKLEARN_AVAILABLE:
            logger.warning("sklearn not available for Sybil detection")
            return []

        clusters = []

        # Build feature vectors for wallets
        wallet_features = []
        wallet_addresses = []

        for addr, node in nodes.items():
            if not hasattr(node, 'transaction_count'):
                continue

            features = [
                getattr(node, 'transaction_count', 0),
                getattr(node, 'total_volume_sol', 0),
                getattr(node, 'unique_interactions', 0),
                getattr(node, 'early_buyer_count', 0),
                getattr(node, 'sniper_score', 0),
            ]

            wallet_features.append(features)
            wallet_addresses.append(addr)

        if len(wallet_features) < self.min_cluster_size:
            return clusters

        # Normalize features
        features_array = np.array(wallet_features)
        if features_array.max() > 0:
            features_array = features_array / features_array.max(axis=0, keepdims=True)
            features_array = np.nan_to_num(features_array)

        # Run DBSCAN clustering
        clustering = DBSCAN(
            eps=1 - similarity_threshold,
            min_samples=self.min_cluster_size,
        ).fit(features_array)

        # Extract clusters
        labels = clustering.labels_
        unique_labels = set(labels) - {-1}  # Exclude noise

        for label in unique_labels:
            member_indices = np.where(labels == label)[0]
            members = {wallet_addresses[i] for i in member_indices}

            if len(members) < self.min_cluster_size:
                continue

            cluster_id = self._generate_cluster_id()
            cluster = WalletCluster(
                cluster_id=cluster_id,
                cluster_type=ClusterType.SYBIL_NETWORK,
                members=members,
                size=len(members),
                detection_method="dbscan_behavioral",
            )

            cluster.seed_node_count = len(members & seed_nodes)
            cluster.confidence = 0.7 + (0.3 * cluster.seed_node_count / max(1, len(members)))

            self.clusters[cluster_id] = cluster
            clusters.append(cluster)

        return clusters

    async def detect_temporal_clusters(
        self,
        transactions: List[Dict[str, Any]],
        seed_nodes: Set[str],
    ) -> List[WalletCluster]:
        """
        Detect clusters based on temporal correlation.

        Wallets that transact within a short time window
        on the same token are likely coordinated.
        """
        clusters = []

        # Group transactions by token and time window
        token_windows: Dict[str, Dict[int, Set[str]]] = defaultdict(lambda: defaultdict(set))

        for tx in transactions:
            token = tx.get("token_mint", "")
            timestamp = tx.get("timestamp", 0)
            wallet = tx.get("sender", "") or tx.get("receiver", "")

            if not token or not wallet:
                continue

            # Calculate time window
            window = int(timestamp // self.temporal_window_seconds)
            token_windows[token][window].add(wallet)

        # Find clusters in each window
        for token, windows in token_windows.items():
            for window, wallets in windows.items():
                if len(wallets) < self.min_cluster_size:
                    continue

                cluster_id = self._generate_cluster_id()
                cluster = WalletCluster(
                    cluster_id=cluster_id,
                    cluster_type=ClusterType.TEMPORAL,
                    members=wallets,
                    size=len(wallets),
                    detection_method="temporal_correlation",
                )

                cluster.seed_node_count = len(wallets & seed_nodes)
                cluster.confidence = 0.6 + (0.4 * cluster.seed_node_count / max(1, len(wallets)))

                self.clusters[cluster_id] = cluster
                clusters.append(cluster)

        return clusters

    def get_cluster(self, cluster_id: str) -> Optional[WalletCluster]:
        """Get cluster by ID."""
        return self.clusters.get(cluster_id)

    def get_wallet_cluster(self, address: str) -> Optional[WalletCluster]:
        """Get cluster containing a wallet."""
        cluster_id = self.wallet_to_cluster.get(address)
        if cluster_id:
            return self.clusters.get(cluster_id)
        return None

    def get_daisy_chain(self, chain_id: str) -> Optional[DaisyChain]:
        """Get daisy chain by ID."""
        return self.daisy_chains.get(chain_id)

    def get_funding_hub(self, address: str) -> Optional[FundingHub]:
        """Get funding hub by address."""
        return self.funding_hubs.get(address)

    def _generate_cluster_id(self) -> str:
        """Generate unique cluster ID."""
        self._cluster_counter += 1
        return f"cluster_{self._cluster_counter}_{int(time.time())}"

    def _generate_chain_id(self) -> str:
        """Generate unique chain ID."""
        self._chain_counter += 1
        return f"chain_{self._chain_counter}_{int(time.time())}"

    def get_metrics(self) -> Dict[str, Any]:
        """Get detection metrics."""
        return {
            "total_clusters": self.metrics.total_clusters,
            "total_daisy_chains": self.metrics.total_daisy_chains,
            "total_funding_hubs": self.metrics.total_funding_hubs,
            "largest_cluster_size": self.metrics.largest_cluster_size,
            "longest_daisy_chain": self.metrics.longest_daisy_chain,
            "most_funded_hub": self.metrics.most_funded_hub,
            "detection_time_ms": round(self.metrics.detection_time_ms, 2),
        }

    def get_summary(self) -> Dict[str, Any]:
        """Get detection summary."""
        return {
            "clusters": [
                {
                    "id": c.cluster_id,
                    "type": c.cluster_type.value,
                    "size": c.size,
                    "seed_nodes": c.seed_node_count,
                    "confidence": round(c.confidence, 2),
                }
                for c in self.clusters.values()
            ],
            "daisy_chains": [
                {
                    "id": d.chain_id,
                    "length": d.length,
                    "volume": round(d.total_volume, 2),
                    "starts_from_seed": d.starts_from_seed,
                }
                for d in self.daisy_chains.values()
            ],
            "funding_hubs": [
                {
                    "address": h.hub_address[:16] + "...",
                    "funded_count": h.total_funded,
                    "volume": round(h.total_volume, 2),
                    "is_insider": h.is_known_insider,
                }
                for h in self.funding_hubs.values()
            ],
        }
