#!/usr/bin/env python3
"""
GPU-Integrated Wallet Profiler for GODMODESCANNER
==================================================
Integrates GPU-accelerated graph analysis with existing
wallet profiling pipeline for 100x faster Sybil detection.

Replaces: NetworkX-based graph traversal
Integrates with: WalletProfilerAgent, HistoricalAnalyzer, BehaviorTracker
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import time
import os

import structlog
import pandas as pd

# Import GPU accelerator with fallback
try:
    from utils.gpu_graph_accelerator import (
        GPUWalletGraphAccelerator,
        SybilCluster,
        InfluenceScore,
        check_gpu_status
    )
    GPU_MODULE_AVAILABLE = True
except ImportError:
    GPU_MODULE_AVAILABLE = False

# Import existing profiler components
try:
    from agents.historical_analyzer import HistoricalAnalyzer
    from agents.profile_cache import ProfileCache
    from agents.risk_aggregator import RiskAggregator
except ImportError:
    pass

logger = structlog.get_logger(__name__)


@dataclass
class GPUProfilerMetrics:
    """Performance metrics for GPU-accelerated profiling."""
    total_wallets_analyzed: int = 0
    gpu_operations: int = 0
    cpu_fallback_operations: int = 0
    total_time_ms: float = 0.0
    avg_time_per_wallet_ms: float = 0.0
    sybil_clusters_detected: int = 0
    king_makers_identified: int = 0
    gpu_speedup_factor: float = 1.0


class GPUWalletProfiler:
    """
    GPU-accelerated wallet profiler integrating with GODMODESCANNER.

    Features:
    - GPU-accelerated Sybil cluster detection (100x faster)
    - PageRank-based King Maker identification
    - Funding path tracing with BFS on GPU
    - Automatic CPU fallback if GPU unavailable
    - Integration with existing WalletProfilerAgent pipeline
    """

    def __init__(self, 
                 redis_url: str = "redis://localhost:6379",
                 use_gpu: bool = True,
                 min_cluster_size: int = 5,
                 king_maker_threshold: float = 0.01):
        """
        Initialize GPU-accelerated wallet profiler.

        Args:
            redis_url: Redis connection URL for caching
            use_gpu: Whether to attempt GPU acceleration
            min_cluster_size: Minimum wallets for Sybil cluster
            king_maker_threshold: PageRank threshold for King Maker status
        """
        self.redis_url = redis_url
        self.min_cluster_size = min_cluster_size
        self.king_maker_threshold = king_maker_threshold
        self.metrics = GPUProfilerMetrics()

        # Check GPU availability
        self.gpu_available = False
        self.gpu_status = {}

        if use_gpu and GPU_MODULE_AVAILABLE:
            self.gpu_status = check_gpu_status()
            self.gpu_available = self.gpu_status.get('cuda_available', False)

            if self.gpu_available:
                self.graph_accelerator = GPUWalletGraphAccelerator(use_gpu=True)
                logger.info("GPU wallet profiler initialized",
                           device=self.gpu_status.get('device_name'),
                           memory_gb=self.gpu_status.get('memory_total_gb'))
            else:
                self.graph_accelerator = GPUWalletGraphAccelerator(use_gpu=False)
                logger.warning("GPU not available, using CPU fallback")
        else:
            self.graph_accelerator = None
            logger.warning("GPU module not available")

        # Transaction cache for graph building
        self._transaction_cache: List[Dict] = []
        self._graph_built = False

    def add_transaction(self, from_wallet: str, to_wallet: str, 
                        amount: float, timestamp: datetime = None):
        """
        Add a transaction to the graph cache.

        Args:
            from_wallet: Source wallet address
            to_wallet: Destination wallet address
            amount: Transaction amount in SOL
            timestamp: Transaction timestamp
        """
        self._transaction_cache.append({
            'from_wallet': from_wallet,
            'to_wallet': to_wallet,
            'amount': amount,
            'timestamp': timestamp or datetime.utcnow()
        })
        self._graph_built = False

    def add_transactions_batch(self, transactions: List[Dict]):
        """
        Add multiple transactions at once.

        Args:
            transactions: List of transaction dicts with from_wallet, to_wallet, amount
        """
        self._transaction_cache.extend(transactions)
        self._graph_built = False
        logger.info(f"Added {len(transactions)} transactions to cache",
                   total_cached=len(self._transaction_cache))

    def _build_graph(self):
        """Build the wallet graph from cached transactions."""
        if not self._transaction_cache:
            logger.warning("No transactions in cache to build graph")
            return False

        if self.graph_accelerator is None:
            logger.error("Graph accelerator not initialized")
            return False

        df = pd.DataFrame(self._transaction_cache)
        self.graph_accelerator.build_graph_from_transactions(df)
        self._graph_built = True

        logger.info("Wallet graph built",
                   transactions=len(self._transaction_cache),
                   gpu_accelerated=self.gpu_available)

        return True

    async def detect_sybil_networks(self, 
                                     resolution: float = 1.0) -> List[SybilCluster]:
        """
        Detect Sybil networks using GPU-accelerated Louvain clustering.

        REPLACES: NetworkX community detection in existing profiler
        PERFORMANCE: 100x faster on GPU for large graphs

        Args:
            resolution: Louvain resolution (higher = smaller clusters)

        Returns:
            List of detected SybilCluster objects
        """
        start_time = time.perf_counter()

        if not self._graph_built:
            if not self._build_graph():
                return []

        clusters = await self.graph_accelerator.detect_sybil_clusters(
            min_cluster_size=self.min_cluster_size,
            resolution=resolution
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Update metrics
        self.metrics.sybil_clusters_detected += len(clusters)
        self.metrics.total_time_ms += duration_ms
        if self.gpu_available:
            self.metrics.gpu_operations += 1
        else:
            self.metrics.cpu_fallback_operations += 1

        logger.info("Sybil detection complete",
                   clusters_found=len(clusters),
                   duration_ms=round(duration_ms, 2),
                   gpu_accelerated=self.gpu_available)

        return clusters

    async def identify_king_makers(self, 
                                    wallet_addresses: Optional[List[str]] = None) -> List[InfluenceScore]:
        """
        Identify King Maker wallets using GPU-accelerated PageRank.

        King Makers are high-influence wallets that consistently
        pick winning tokens early.

        Args:
            wallet_addresses: Specific wallets to analyze (None = all)

        Returns:
            List of InfluenceScore objects sorted by influence
        """
        start_time = time.perf_counter()

        if not self._graph_built:
            if not self._build_graph():
                return []

        scores = await self.graph_accelerator.calculate_pagerank_influence(
            wallet_addresses=wallet_addresses,
            king_maker_threshold=self.king_maker_threshold
        )

        duration_ms = (time.perf_counter() - start_time) * 1000

        # Update metrics
        king_makers = [s for s in scores if s.is_king_maker]
        self.metrics.king_makers_identified += len(king_makers)
        self.metrics.total_time_ms += duration_ms

        logger.info("King Maker identification complete",
                   wallets_analyzed=len(scores),
                   king_makers_found=len(king_makers),
                   duration_ms=round(duration_ms, 2))

        return scores

    async def trace_insider_funding(self, 
                                     suspect_wallet: str,
                                     max_depth: int = 3) -> Dict[str, Any]:
        """
        Trace funding paths from a suspect wallet using GPU BFS.

        Identifies funding sources and connected wallets that may
        be part of an insider network.

        Args:
            suspect_wallet: Wallet address to investigate
            max_depth: Maximum hops to trace

        Returns:
            Dictionary with funding path information
        """
        start_time = time.perf_counter()

        if not self._graph_built:
            if not self._build_graph():
                return {'error': 'Graph not built'}

        paths = await self.graph_accelerator.trace_funding_paths(
            source_wallet=suspect_wallet,
            max_depth=max_depth
        )

        duration_ms = (time.perf_counter() - start_time) * 1000
        self.metrics.total_time_ms += duration_ms

        # Analyze funding patterns
        paths['analysis'] = self._analyze_funding_patterns(paths)

        logger.info("Funding trace complete",
                   suspect=suspect_wallet[:16] + "...",
                   wallets_reached=paths.get('total_wallets_reached', 0),
                   duration_ms=round(duration_ms, 2))

        return paths

    def _analyze_funding_patterns(self, paths: Dict) -> Dict[str, Any]:
        """
        Analyze funding patterns for suspicious activity.

        Returns:
            Analysis results with risk indicators
        """
        analysis = {
            'risk_indicators': [],
            'funding_concentration': 0.0,
            'suspicious_patterns': []
        }

        if not paths.get('paths'):
            return analysis

        # Check for funding concentration (single source)
        depth_1_wallets = [p for p in paths['paths'] if p.get('distance') == 1]
        if len(depth_1_wallets) == 1:
            analysis['risk_indicators'].append('SINGLE_FUNDING_SOURCE')
            analysis['funding_concentration'] = 1.0
        elif len(depth_1_wallets) > 0:
            analysis['funding_concentration'] = 1.0 / len(depth_1_wallets)

        # Check for circular funding
        all_wallets = set(p.get('wallet') for p in paths['paths'])
        if paths.get('source') in all_wallets:
            analysis['risk_indicators'].append('CIRCULAR_FUNDING')
            analysis['suspicious_patterns'].append('Self-funding detected')

        # Check for rapid expansion (many wallets at same depth)
        depth_counts = {}
        for p in paths['paths']:
            d = p.get('distance', 0)
            depth_counts[d] = depth_counts.get(d, 0) + 1

        for depth, count in depth_counts.items():
            if count > 10:  # More than 10 wallets at same depth
                analysis['risk_indicators'].append(f'RAPID_EXPANSION_DEPTH_{depth}')
                analysis['suspicious_patterns'].append(
                    f'{count} wallets at depth {depth} - possible Sybil'
                )

        return analysis

    async def comprehensive_wallet_analysis(self, 
                                             wallet_address: str) -> Dict[str, Any]:
        """
        Perform comprehensive GPU-accelerated analysis on a wallet.

        Combines Sybil detection, King Maker identification, and
        funding path analysis for complete insider profiling.

        Args:
            wallet_address: Wallet to analyze

        Returns:
            Comprehensive analysis results
        """
        start_time = time.perf_counter()

        results = {
            'wallet': wallet_address,
            'timestamp': datetime.utcnow().isoformat(),
            'gpu_accelerated': self.gpu_available,
            'sybil_analysis': None,
            'influence_score': None,
            'funding_analysis': None,
            'risk_score': 0.0,
            'is_insider': False,
            'insider_type': None
        }

        # Run all analyses in parallel
        sybil_task = self.detect_sybil_networks()
        influence_task = self.identify_king_makers([wallet_address])
        funding_task = self.trace_insider_funding(wallet_address)

        sybil_clusters, influence_scores, funding_paths = await asyncio.gather(
            sybil_task, influence_task, funding_task
        )

        # Check if wallet is in any Sybil cluster
        for cluster in sybil_clusters:
            if wallet_address in cluster.wallet_addresses:
                results['sybil_analysis'] = {
                    'in_cluster': True,
                    'cluster_id': cluster.cluster_id,
                    'cluster_size': cluster.size,
                    'cluster_risk': cluster.risk_score
                }
                results['risk_score'] += cluster.risk_score * 0.4
                break
        else:
            results['sybil_analysis'] = {'in_cluster': False}

        # Get influence score
        if influence_scores:
            score = influence_scores[0]
            results['influence_score'] = {
                'pagerank': score.pagerank,
                'is_king_maker': score.is_king_maker
            }
            if score.is_king_maker:
                results['risk_score'] += 0.3

        # Analyze funding
        results['funding_analysis'] = funding_paths.get('analysis', {})
        risk_indicators = funding_paths.get('analysis', {}).get('risk_indicators', [])
        results['risk_score'] += len(risk_indicators) * 0.1

        # Determine insider status
        results['risk_score'] = min(results['risk_score'], 1.0)
        results['is_insider'] = results['risk_score'] >= 0.7

        if results['is_insider']:
            if results['sybil_analysis'].get('in_cluster'):
                results['insider_type'] = 'SYBIL_NETWORK'
            elif results['influence_score'] and results['influence_score'].get('is_king_maker'):
                results['insider_type'] = 'KING_MAKER'
            else:
                results['insider_type'] = 'SUSPICIOUS_FUNDING'

        duration_ms = (time.perf_counter() - start_time) * 1000
        results['analysis_time_ms'] = round(duration_ms, 2)

        self.metrics.total_wallets_analyzed += 1
        self.metrics.avg_time_per_wallet_ms = (
            self.metrics.total_time_ms / max(self.metrics.total_wallets_analyzed, 1)
        )

        logger.info("Comprehensive analysis complete",
                   wallet=wallet_address[:16] + "...",
                   risk_score=round(results['risk_score'], 3),
                   is_insider=results['is_insider'],
                   duration_ms=round(duration_ms, 2))

        return results

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get profiler performance metrics.

        Returns:
            Dictionary with performance statistics
        """
        return {
            'total_wallets_analyzed': self.metrics.total_wallets_analyzed,
            'gpu_operations': self.metrics.gpu_operations,
            'cpu_fallback_operations': self.metrics.cpu_fallback_operations,
            'total_time_ms': round(self.metrics.total_time_ms, 2),
            'avg_time_per_wallet_ms': round(self.metrics.avg_time_per_wallet_ms, 2),
            'sybil_clusters_detected': self.metrics.sybil_clusters_detected,
            'king_makers_identified': self.metrics.king_makers_identified,
            'gpu_available': self.gpu_available,
            'gpu_status': self.gpu_status,
            'graph_accelerator_metrics': (
                self.graph_accelerator.get_performance_summary() 
                if self.graph_accelerator else None
            )
        }

    def clear(self):
        """Clear transaction cache and reset graph."""
        self._transaction_cache.clear()
        self._graph_built = False
        if self.graph_accelerator:
            self.graph_accelerator.clear_graph()
        logger.info("GPU wallet profiler cleared")


# Factory function for easy integration
def create_gpu_profiler(use_gpu: bool = True, **kwargs) -> GPUWalletProfiler:
    """
    Factory function to create GPU-accelerated wallet profiler.

    Args:
        use_gpu: Whether to attempt GPU acceleration
        **kwargs: Additional arguments for GPUWalletProfiler

    Returns:
        Configured GPUWalletProfiler instance
    """
    # Check environment variable override
    env_gpu = os.environ.get('GPU_ENABLED', 'true').lower() == 'true'
    use_gpu = use_gpu and env_gpu

    return GPUWalletProfiler(use_gpu=use_gpu, **kwargs)


if __name__ == "__main__":
    # Quick test
    import random

    print("GPU Wallet Profiler Test")
    print("=" * 40)

    # Create profiler
    profiler = create_gpu_profiler()
    print(f"GPU Available: {profiler.gpu_available}")
    print(f"GPU Status: {profiler.gpu_status}")

    # Generate test transactions
    wallets = [f"wallet_{i}" for i in range(100)]
    transactions = []

    for _ in range(500):
        from_w = random.choice(wallets)
        to_w = random.choice(wallets)
        if from_w != to_w:
            transactions.append({
                'from_wallet': from_w,
                'to_wallet': to_w,
                'amount': random.uniform(0.1, 100),
                'timestamp': datetime.utcnow()
            })

    profiler.add_transactions_batch(transactions)
    print(f"Added {len(transactions)} test transactions")

    # Run async tests
    async def run_tests():
        # Detect Sybil networks
        clusters = await profiler.detect_sybil_networks()
        print(f"Sybil Clusters Found: {len(clusters)}")
        for c in clusters[:3]:
            print(f"  - Cluster {c.cluster_id}: {c.size} wallets, risk={c.risk_score:.3f}")

        # Identify King Makers
        scores = await profiler.identify_king_makers()
        print("Top Influencers:")
        for s in scores[:5]:
            km = "[KM]" if s.is_king_maker else ""
            print(f"  - {s.wallet_address}: PageRank={s.pagerank:.6f} {km}")

        # Comprehensive analysis
        result = await profiler.comprehensive_wallet_analysis(wallets[0])
        print(f"Comprehensive Analysis for {wallets[0]}:")
        print(f"  Risk Score: {result['risk_score']:.3f}")
        print(f"  Is Insider: {result['is_insider']}")
        print(f"  Insider Type: {result['insider_type']}")
        print(f"  Analysis Time: {result['analysis_time_ms']:.2f}ms")

        # Print metrics
        print("Performance Metrics:")
        metrics = profiler.get_metrics()
        print(f"  GPU Operations: {metrics['gpu_operations']}")
        print(f"  CPU Fallback: {metrics['cpu_fallback_operations']}")
        print(f"  Total Time: {metrics['total_time_ms']:.2f}ms")
        print(f"  Avg per Wallet: {metrics['avg_time_per_wallet_ms']:.2f}ms")

    asyncio.run(run_tests())
