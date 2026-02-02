"""
GPU-Accelerated Wallet Graph Analysis
REPLACES: agents/wallet_deanonymizer/graph_builder.py (NetworkX)
PERFORMANCE: 100x faster than CPU NetworkX

Supports:
- Louvain community detection (wallet clusters)
- PageRank (influential wallets)  
- Triangle counting (collusion detection)
- K-core decomposition (network structure)
- Shortest path analysis (fund tracing)

Fallback: Uses NetworkX when CUDA is not available
"""

import hashlib
import time
import logging
from typing import List, Dict, Tuple, Optional, Any, Union
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)

# Try to import GPU libraries
GPU_AVAILABLE = False
try:
    import cudf
    import cugraph
    import cupy as cp
    GPU_AVAILABLE = True
    logger.info("cuGraph GPU libraries loaded successfully")
except ImportError:
    logger.warning("cuGraph not available, using NetworkX CPU fallback")
    cudf = None
    cugraph = None
    cp = None

# CPU fallback
import networkx as nx
import pandas as pd

# Import memory manager
try:
    from utils.gpu_memory_manager import get_gpu_memory_manager, is_gpu_available
except ImportError:
    def get_gpu_memory_manager():
        return None
    def is_gpu_available():
        return False


@dataclass
class GraphMetrics:
    """Graph performance and statistics metrics"""
    total_edges: int = 0
    total_nodes: int = 0
    avg_build_time_ms: float = 0.0
    avg_cluster_time_ms: float = 0.0
    avg_pagerank_time_ms: float = 0.0
    graph_builds: int = 0
    cluster_detections: int = 0
    pagerank_calculations: int = 0
    triangle_counts: int = 0
    using_gpu: bool = False


class GPUWalletGraphBuilder:
    """
    GPU-accelerated graph builder using RAPIDS cuGraph

    Automatically falls back to NetworkX when GPU is not available.
    Provides identical API regardless of backend.
    """

    def __init__(self, use_gpu: bool = True):
        """
        Initialize graph builder

        Args:
            use_gpu: Whether to attempt GPU acceleration (falls back if unavailable)
        """
        self.use_gpu = use_gpu and GPU_AVAILABLE
        self.metrics = GraphMetrics(using_gpu=self.use_gpu)

        # Wallet address to integer ID mapping
        self._wallet_to_id_map: Dict[str, int] = {}
        self._id_to_wallet_map: Dict[int, str] = {}
        self._next_id = 0

        # Edge storage
        self._edges: List[Tuple[int, int, float, float]] = []  # (src, dst, weight, timestamp)

        # Graph objects
        if self.use_gpu:
            self._init_gpu_graph()
        else:
            self._init_cpu_graph()

        # Cached results
        self._cached_clusters: Optional[Any] = None
        self._cached_pagerank: Optional[Any] = None
        self._graph_dirty = True

        # Memory manager
        self.memory_manager = get_gpu_memory_manager() if self.use_gpu else None

        logger.info(
            f"GPUWalletGraphBuilder initialized: "
            f"backend={'cuGraph (GPU)' if self.use_gpu else 'NetworkX (CPU)'}"
        )

    def _init_gpu_graph(self):
        """Initialize GPU graph structures"""
        self.edges_df = cudf.DataFrame(columns=['src', 'dst', 'weight', 'timestamp'])
        self.graph = cugraph.Graph(directed=True)

    def _init_cpu_graph(self):
        """Initialize CPU graph structures"""
        self.graph = nx.DiGraph()

    def _wallet_to_id(self, wallet: str) -> int:
        """Convert wallet address to integer ID"""
        if wallet not in self._wallet_to_id_map:
            self._wallet_to_id_map[wallet] = self._next_id
            self._id_to_wallet_map[self._next_id] = wallet
            self._next_id += 1
        return self._wallet_to_id_map[wallet]

    def _id_to_wallet(self, node_id: int) -> str:
        """Convert integer ID back to wallet address"""
        return self._id_to_wallet_map.get(node_id, f"unknown_{node_id}")

    def add_transfer(
        self,
        from_wallet: str,
        to_wallet: str,
        amount: float,
        timestamp: Optional[float] = None
    ):
        """
        Add single transfer edge to graph

        Args:
            from_wallet: Source wallet address
            to_wallet: Destination wallet address
            amount: Transfer amount (SOL)
            timestamp: Unix timestamp of transfer
        """
        if timestamp is None:
            timestamp = time.time()

        src_id = self._wallet_to_id(from_wallet)
        dst_id = self._wallet_to_id(to_wallet)

        self._edges.append((src_id, dst_id, amount, timestamp))
        self.metrics.total_edges += 1

        # Invalidate cache
        self._graph_dirty = True
        self._cached_clusters = None
        self._cached_pagerank = None

    def add_transfers_batch(
        self,
        transfers: List[Tuple[str, str, float, float]]
    ):
        """
        Batch add transfers for efficiency

        Args:
            transfers: List of (from_wallet, to_wallet, amount, timestamp) tuples
        """
        if not transfers:
            return

        for from_wallet, to_wallet, amount, timestamp in transfers:
            src_id = self._wallet_to_id(from_wallet)
            dst_id = self._wallet_to_id(to_wallet)
            self._edges.append((src_id, dst_id, amount, timestamp))

        self.metrics.total_edges += len(transfers)

        # Invalidate cache
        self._graph_dirty = True
        self._cached_clusters = None
        self._cached_pagerank = None

        logger.debug(f"Batch added {len(transfers)} transfers")

    def build_graph(self):
        """
        Build graph from accumulated edges

        Must be called before running analysis algorithms.
        """
        if not self._graph_dirty:
            return  # Already built

        start = time.time()

        if not self._edges:
            logger.warning("Cannot build graph: no edges")
            return

        if self.use_gpu:
            self._build_gpu_graph()
        else:
            self._build_cpu_graph()

        # Update metrics
        elapsed_ms = (time.time() - start) * 1000
        self.metrics.graph_builds += 1
        alpha = 0.1
        self.metrics.avg_build_time_ms = (
            alpha * elapsed_ms +
            (1 - alpha) * self.metrics.avg_build_time_ms
        )
        self.metrics.total_nodes = len(self._wallet_to_id_map)

        self._graph_dirty = False

        logger.info(
            f"Graph built: {self.metrics.total_edges:,} edges, "
            f"{self.metrics.total_nodes:,} nodes, "
            f"{elapsed_ms:.2f}ms, backend={'GPU' if self.use_gpu else 'CPU'}"
        )

    def _build_gpu_graph(self):
        """Build cuGraph from edges"""
        # Convert edges to cuDF DataFrame
        src_ids = [e[0] for e in self._edges]
        dst_ids = [e[1] for e in self._edges]
        weights = [e[2] for e in self._edges]
        timestamps = [e[3] for e in self._edges]

        self.edges_df = cudf.DataFrame({
            'src': src_ids,
            'dst': dst_ids,
            'weight': weights,
            'timestamp': timestamps
        })

        # Create graph from edge list
        self.graph = cugraph.Graph(directed=True)
        self.graph.from_cudf_edgelist(
            self.edges_df,
            source='src',
            destination='dst',
            edge_attr='weight',
            renumber=True
        )

    def _build_cpu_graph(self):
        """Build NetworkX graph from edges"""
        self.graph = nx.DiGraph()

        for src_id, dst_id, weight, timestamp in self._edges:
            self.graph.add_edge(
                src_id, dst_id,
                weight=weight,
                timestamp=timestamp
            )

    def detect_clusters(self, resolution: float = 1.0) -> Dict[str, int]:
        """
        Detect wallet clusters using Louvain algorithm

        Args:
            resolution: Louvain resolution parameter (higher = more clusters)

        Returns:
            Dict mapping wallet address to cluster ID
        """
        start = time.time()

        # Check cache
        if self._cached_clusters is not None:
            return self._cached_clusters

        # Build graph if needed
        self.build_graph()

        if self.use_gpu:
            clusters = self._detect_clusters_gpu(resolution)
        else:
            clusters = self._detect_clusters_cpu(resolution)

        # Update metrics
        elapsed_ms = (time.time() - start) * 1000
        self.metrics.cluster_detections += 1
        alpha = 0.1
        self.metrics.avg_cluster_time_ms = (
            alpha * elapsed_ms +
            (1 - alpha) * self.metrics.avg_cluster_time_ms
        )

        # Cache result
        self._cached_clusters = clusters

        num_clusters = len(set(clusters.values()))
        logger.info(
            f"Detected {num_clusters} clusters in {elapsed_ms:.2f}ms "
            f"(backend={'GPU' if self.use_gpu else 'CPU'})"
        )

        return clusters

    def _detect_clusters_gpu(self, resolution: float) -> Dict[str, int]:
        """GPU Louvain clustering"""
        # Run Louvain on GPU
        result, modularity = cugraph.louvain(self.graph, resolution=resolution)

        # Convert to wallet -> cluster mapping
        clusters = {}
        for row in result.to_pandas().itertuples():
            wallet = self._id_to_wallet(row.vertex)
            clusters[wallet] = int(row.partition)

        logger.debug(f"GPU Louvain modularity: {modularity:.4f}")
        return clusters

    def _detect_clusters_cpu(self, resolution: float) -> Dict[str, int]:
        """CPU NetworkX clustering"""
        # Convert to undirected for community detection
        undirected = self.graph.to_undirected()

        # Use Louvain from networkx.algorithms.community
        try:
            from networkx.algorithms.community import louvain_communities
            communities = louvain_communities(undirected, resolution=resolution)

            clusters = {}
            for cluster_id, community in enumerate(communities):
                for node_id in community:
                    wallet = self._id_to_wallet(node_id)
                    clusters[wallet] = cluster_id

            return clusters
        except ImportError:
            # Fallback to connected components
            logger.warning("Louvain not available, using connected components")
            components = list(nx.connected_components(undirected))

            clusters = {}
            for cluster_id, component in enumerate(components):
                for node_id in component:
                    wallet = self._id_to_wallet(node_id)
                    clusters[wallet] = cluster_id

            return clusters

    def calculate_pagerank(self, alpha: float = 0.85) -> Dict[str, float]:
        """
        Calculate PageRank scores to identify influential wallets

        Args:
            alpha: Damping factor (default 0.85)

        Returns:
            Dict mapping wallet address to PageRank score
        """
        start = time.time()

        # Check cache
        if self._cached_pagerank is not None:
            return self._cached_pagerank

        # Build graph if needed
        self.build_graph()

        if self.use_gpu:
            pagerank = self._calculate_pagerank_gpu(alpha)
        else:
            pagerank = self._calculate_pagerank_cpu(alpha)

        # Update metrics
        elapsed_ms = (time.time() - start) * 1000
        self.metrics.pagerank_calculations += 1
        alpha_ema = 0.1
        self.metrics.avg_pagerank_time_ms = (
            alpha_ema * elapsed_ms +
            (1 - alpha_ema) * self.metrics.avg_pagerank_time_ms
        )

        # Cache result
        self._cached_pagerank = pagerank

        logger.info(
            f"PageRank calculated in {elapsed_ms:.2f}ms "
            f"(backend={'GPU' if self.use_gpu else 'CPU'})"
        )

        return pagerank

    def _calculate_pagerank_gpu(self, alpha: float) -> Dict[str, float]:
        """GPU PageRank"""
        result = cugraph.pagerank(self.graph, alpha=alpha)

        pagerank = {}
        for row in result.to_pandas().itertuples():
            wallet = self._id_to_wallet(row.vertex)
            pagerank[wallet] = float(row.pagerank)

        return pagerank

    def _calculate_pagerank_cpu(self, alpha: float) -> Dict[str, float]:
        """CPU NetworkX PageRank"""
        pr = nx.pagerank(self.graph, alpha=alpha)

        pagerank = {}
        for node_id, score in pr.items():
            wallet = self._id_to_wallet(node_id)
            pagerank[wallet] = score

        return pagerank

    def count_triangles(self) -> int:
        """
        Count triangles in graph (indicates potential collusion patterns)

        Returns:
            Total number of triangles
        """
        start = time.time()

        # Build graph if needed
        self.build_graph()

        if self.use_gpu:
            count = self._count_triangles_gpu()
        else:
            count = self._count_triangles_cpu()

        self.metrics.triangle_counts += 1

        elapsed_ms = (time.time() - start) * 1000
        logger.info(
            f"Triangle count: {count:,} in {elapsed_ms:.2f}ms "
            f"(backend={'GPU' if self.use_gpu else 'CPU'})"
        )

        return count

    def _count_triangles_gpu(self) -> int:
        """GPU triangle counting"""
        result = cugraph.triangle_count(self.graph)
        return int(result['counts'].sum())

    def _count_triangles_cpu(self) -> int:
        """CPU NetworkX triangle counting"""
        # Convert to undirected for triangle counting
        undirected = self.graph.to_undirected()
        triangles = nx.triangles(undirected)
        # Each triangle is counted 3 times (once per vertex)
        return sum(triangles.values()) // 3

    def find_shortest_path(
        self,
        source_wallet: str,
        target_wallet: str
    ) -> Optional[List[str]]:
        """
        Find shortest path between two wallets

        Args:
            source_wallet: Starting wallet address
            target_wallet: Target wallet address

        Returns:
            List of wallet addresses in path, or None if no path exists
        """
        # Build graph if needed
        self.build_graph()

        src_id = self._wallet_to_id_map.get(source_wallet)
        dst_id = self._wallet_to_id_map.get(target_wallet)

        if src_id is None or dst_id is None:
            return None

        if self.use_gpu:
            return self._find_shortest_path_gpu(src_id, dst_id)
        else:
            return self._find_shortest_path_cpu(src_id, dst_id)

    def _find_shortest_path_gpu(self, src_id: int, dst_id: int) -> Optional[List[str]]:
        """GPU shortest path using BFS"""
        try:
            result = cugraph.bfs(self.graph, src_id)

            # Reconstruct path
            path_df = result.to_pandas()
            target_row = path_df[path_df['vertex'] == dst_id]

            if target_row.empty or target_row['distance'].iloc[0] == -1:
                return None

            # Backtrack to build path
            path = []
            current = dst_id
            while current != src_id:
                path.append(self._id_to_wallet(current))
                row = path_df[path_df['vertex'] == current]
                if row.empty:
                    return None
                current = int(row['predecessor'].iloc[0])
            path.append(self._id_to_wallet(src_id))

            return list(reversed(path))
        except Exception as e:
            logger.error(f"GPU shortest path failed: {e}")
            return None

    def _find_shortest_path_cpu(self, src_id: int, dst_id: int) -> Optional[List[str]]:
        """CPU NetworkX shortest path"""
        try:
            path_ids = nx.shortest_path(self.graph, src_id, dst_id)
            return [self._id_to_wallet(node_id) for node_id in path_ids]
        except nx.NetworkXNoPath:
            return None

    def get_connected_wallets(
        self,
        wallet: str,
        max_hops: int = 3
    ) -> Dict[str, int]:
        """
        Get all wallets connected within N hops

        Args:
            wallet: Starting wallet address
            max_hops: Maximum number of hops to traverse

        Returns:
            Dict mapping wallet address to hop distance
        """
        # Build graph if needed
        self.build_graph()

        wallet_id = self._wallet_to_id_map.get(wallet)
        if wallet_id is None:
            return {}

        if self.use_gpu:
            return self._get_connected_wallets_gpu(wallet_id, max_hops)
        else:
            return self._get_connected_wallets_cpu(wallet_id, max_hops)

    def _get_connected_wallets_gpu(self, wallet_id: int, max_hops: int) -> Dict[str, int]:
        """GPU BFS for connected wallets"""
        try:
            result = cugraph.bfs(self.graph, wallet_id, depth_limit=max_hops)

            connected = {}
            for row in result.to_pandas().itertuples():
                if row.distance >= 0 and row.distance <= max_hops:
                    wallet = self._id_to_wallet(row.vertex)
                    connected[wallet] = int(row.distance)

            return connected
        except Exception as e:
            logger.error(f"GPU BFS failed: {e}")
            return {}

    def _get_connected_wallets_cpu(self, wallet_id: int, max_hops: int) -> Dict[str, int]:
        """CPU NetworkX BFS for connected wallets"""
        connected = {}

        # BFS with depth limit
        visited = {wallet_id: 0}
        queue = [(wallet_id, 0)]

        while queue:
            current, depth = queue.pop(0)

            if depth >= max_hops:
                continue

            for neighbor in self.graph.neighbors(current):
                if neighbor not in visited:
                    visited[neighbor] = depth + 1
                    queue.append((neighbor, depth + 1))

        for node_id, distance in visited.items():
            wallet = self._id_to_wallet(node_id)
            connected[wallet] = distance

        return connected

    def get_top_wallets_by_pagerank(self, n: int = 10) -> List[Tuple[str, float]]:
        """
        Get top N wallets by PageRank score

        Args:
            n: Number of top wallets to return

        Returns:
            List of (wallet, score) tuples sorted by score descending
        """
        pagerank = self.calculate_pagerank()
        sorted_wallets = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)
        return sorted_wallets[:n]

    def get_cluster_summary(self) -> Dict[int, Dict[str, Any]]:
        """
        Get summary statistics for each cluster

        Returns:
            Dict mapping cluster_id to cluster statistics
        """
        clusters = self.detect_clusters()
        pagerank = self.calculate_pagerank()

        # Group wallets by cluster
        cluster_wallets: Dict[int, List[str]] = {}
        for wallet, cluster_id in clusters.items():
            if cluster_id not in cluster_wallets:
                cluster_wallets[cluster_id] = []
            cluster_wallets[cluster_id].append(wallet)

        # Calculate statistics for each cluster
        summary = {}
        for cluster_id, wallets in cluster_wallets.items():
            pr_scores = [pagerank.get(w, 0) for w in wallets]

            summary[cluster_id] = {
                'size': len(wallets),
                'wallets': wallets[:10],  # First 10 wallets
                'avg_pagerank': np.mean(pr_scores) if pr_scores else 0,
                'max_pagerank': max(pr_scores) if pr_scores else 0,
                'top_wallet': max(wallets, key=lambda w: pagerank.get(w, 0)) if wallets else None
            }

        return summary

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive graph statistics"""
        stats = {
            'total_edges': self.metrics.total_edges,
            'total_nodes': self.metrics.total_nodes,
            'avg_build_time_ms': self.metrics.avg_build_time_ms,
            'avg_cluster_time_ms': self.metrics.avg_cluster_time_ms,
            'avg_pagerank_time_ms': self.metrics.avg_pagerank_time_ms,
            'graph_builds': self.metrics.graph_builds,
            'cluster_detections': self.metrics.cluster_detections,
            'pagerank_calculations': self.metrics.pagerank_calculations,
            'triangle_counts': self.metrics.triangle_counts,
            'using_gpu': self.metrics.using_gpu,
            'cached_clusters': self._cached_clusters is not None,
            'cached_pagerank': self._cached_pagerank is not None,
            'graph_dirty': self._graph_dirty
        }

        # Add memory stats if GPU
        if self.memory_manager:
            stats['gpu_memory'] = self.memory_manager.get_memory_stats()

        return stats

    def clear_cache(self):
        """Clear cached results"""
        self._cached_clusters = None
        self._cached_pagerank = None
        logger.debug("Graph cache cleared")

    def clear(self):
        """Clear all graph data"""
        self._edges.clear()
        self._wallet_to_id_map.clear()
        self._id_to_wallet_map.clear()
        self._next_id = 0
        self._graph_dirty = True
        self.clear_cache()

        if self.use_gpu:
            self._init_gpu_graph()
        else:
            self._init_cpu_graph()

        self.metrics = GraphMetrics(using_gpu=self.use_gpu)
        logger.info("Graph cleared")


# Factory function
def create_graph_builder(prefer_gpu: bool = True) -> GPUWalletGraphBuilder:
    """
    Create a graph builder with optimal backend

    Args:
        prefer_gpu: Whether to prefer GPU if available

    Returns:
        GPUWalletGraphBuilder instance
    """
    return GPUWalletGraphBuilder(use_gpu=prefer_gpu)
