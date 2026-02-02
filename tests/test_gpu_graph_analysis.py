#!/usr/bin/env python3
"""
Comprehensive Test Suite for GPU-Accelerated Graph Analysis
============================================================
Tests both GPU and CPU fallback paths for wallet graph analysis.

Run: pytest tests/test_gpu_graph_analysis.py -v
"""

import pytest
import asyncio
import pandas as pd
import random
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestGPUGraphAccelerator:
    """Tests for GPUWalletGraphAccelerator."""

    @pytest.fixture
    def sample_transactions(self):
        """Generate sample transaction data."""
        wallets = [f"wallet_{i}" for i in range(50)]
        transactions = []

        for _ in range(200):
            from_w = random.choice(wallets)
            to_w = random.choice(wallets)
            if from_w != to_w:
                transactions.append({
                    'from_wallet': from_w,
                    'to_wallet': to_w,
                    'amount': random.uniform(0.1, 100),
                    'timestamp': datetime.utcnow() - timedelta(hours=random.randint(0, 72))
                })

        return pd.DataFrame(transactions)

    @pytest.fixture
    def accelerator(self):
        """Create accelerator instance (CPU fallback mode for testing)."""
        from utils.gpu_graph_accelerator import GPUWalletGraphAccelerator
        return GPUWalletGraphAccelerator(use_gpu=False)  # Force CPU for testing

    def test_accelerator_initialization(self, accelerator):
        """Test accelerator initializes correctly."""
        assert accelerator is not None
        assert hasattr(accelerator, 'graph')
        assert hasattr(accelerator, 'node_map')
        assert hasattr(accelerator, 'metrics')

    def test_build_graph_from_transactions(self, accelerator, sample_transactions):
        """Test graph building from transaction DataFrame."""
        graph = accelerator.build_graph_from_transactions(sample_transactions)

        assert graph is not None
        assert len(accelerator.node_map) > 0
        assert len(accelerator.reverse_map) > 0
        assert len(accelerator.metrics) == 1  # One operation recorded

    @pytest.mark.asyncio
    async def test_detect_sybil_clusters(self, accelerator, sample_transactions):
        """Test Sybil cluster detection."""
        accelerator.build_graph_from_transactions(sample_transactions)

        clusters = await accelerator.detect_sybil_clusters(min_cluster_size=3)

        assert isinstance(clusters, list)
        # May or may not find clusters depending on random data
        for cluster in clusters:
            assert hasattr(cluster, 'cluster_id')
            assert hasattr(cluster, 'wallet_addresses')
            assert hasattr(cluster, 'size')
            assert cluster.size >= 3

    @pytest.mark.asyncio
    async def test_calculate_pagerank(self, accelerator, sample_transactions):
        """Test PageRank influence calculation."""
        accelerator.build_graph_from_transactions(sample_transactions)

        scores = await accelerator.calculate_pagerank_influence()

        assert isinstance(scores, list)
        assert len(scores) > 0

        # Check scores are sorted by PageRank
        for i in range(len(scores) - 1):
            assert scores[i].pagerank >= scores[i + 1].pagerank

    @pytest.mark.asyncio
    async def test_trace_funding_paths(self, accelerator, sample_transactions):
        """Test funding path tracing."""
        accelerator.build_graph_from_transactions(sample_transactions)

        # Get a wallet from the graph
        source_wallet = list(accelerator.node_map.keys())[0]

        paths = await accelerator.trace_funding_paths(source_wallet, max_depth=2)

        assert 'source' in paths
        assert 'paths' in paths
        assert 'total_wallets_reached' in paths
        assert paths['source'] == source_wallet

    @pytest.mark.asyncio
    async def test_find_connected_components(self, accelerator, sample_transactions):
        """Test connected components detection."""
        accelerator.build_graph_from_transactions(sample_transactions)

        components = await accelerator.find_connected_components()

        assert isinstance(components, list)
        assert len(components) > 0
        # Components should be sorted by size
        for i in range(len(components) - 1):
            assert len(components[i]) >= len(components[i + 1])

    def test_performance_summary(self, accelerator, sample_transactions):
        """Test performance metrics collection."""
        accelerator.build_graph_from_transactions(sample_transactions)

        summary = accelerator.get_performance_summary()

        assert 'total_operations' in summary
        assert 'total_time_ms' in summary
        assert summary['total_operations'] >= 1

    def test_clear_graph(self, accelerator, sample_transactions):
        """Test graph clearing."""
        accelerator.build_graph_from_transactions(sample_transactions)
        assert len(accelerator.node_map) > 0

        accelerator.clear_graph()

        assert len(accelerator.node_map) == 0
        assert len(accelerator.reverse_map) == 0


class TestGPUWalletProfiler:
    """Tests for GPUWalletProfiler integration."""

    @pytest.fixture
    def profiler(self):
        """Create profiler instance."""
        from agents.wallet_profiler.gpu_wallet_profiler import GPUWalletProfiler
        return GPUWalletProfiler(use_gpu=False)  # Force CPU for testing

    @pytest.fixture
    def sample_transactions(self):
        """Generate sample transactions."""
        wallets = [f"wallet_{i}" for i in range(30)]
        transactions = []

        for _ in range(100):
            from_w = random.choice(wallets)
            to_w = random.choice(wallets)
            if from_w != to_w:
                transactions.append({
                    'from_wallet': from_w,
                    'to_wallet': to_w,
                    'amount': random.uniform(0.1, 50),
                    'timestamp': datetime.utcnow()
                })

        return transactions

    def test_profiler_initialization(self, profiler):
        """Test profiler initializes correctly."""
        assert profiler is not None
        assert hasattr(profiler, 'gpu_available')
        assert hasattr(profiler, 'metrics')

    def test_add_transaction(self, profiler):
        """Test adding single transaction."""
        profiler.add_transaction("wallet_a", "wallet_b", 100.0)

        assert len(profiler._transaction_cache) == 1
        assert profiler._graph_built == False

    def test_add_transactions_batch(self, profiler, sample_transactions):
        """Test adding batch of transactions."""
        profiler.add_transactions_batch(sample_transactions)

        assert len(profiler._transaction_cache) == len(sample_transactions)

    @pytest.mark.asyncio
    async def test_detect_sybil_networks(self, profiler, sample_transactions):
        """Test Sybil network detection through profiler."""
        profiler.add_transactions_batch(sample_transactions)

        clusters = await profiler.detect_sybil_networks()

        assert isinstance(clusters, list)

    @pytest.mark.asyncio
    async def test_identify_king_makers(self, profiler, sample_transactions):
        """Test King Maker identification."""
        profiler.add_transactions_batch(sample_transactions)

        scores = await profiler.identify_king_makers()

        assert isinstance(scores, list)

    @pytest.mark.asyncio
    async def test_trace_insider_funding(self, profiler, sample_transactions):
        """Test insider funding trace."""
        profiler.add_transactions_batch(sample_transactions)

        paths = await profiler.trace_insider_funding("wallet_0", max_depth=2)

        # Handle case where graph accelerator is not initialized
        if 'error' in paths:
            assert paths['error'] == 'Graph not built'
        else:
            assert 'source' in paths
            assert 'analysis' in paths

    @pytest.mark.asyncio
    async def test_comprehensive_wallet_analysis(self, profiler, sample_transactions):
        """Test comprehensive wallet analysis."""
        profiler.add_transactions_batch(sample_transactions)

        result = await profiler.comprehensive_wallet_analysis("wallet_0")

        assert 'wallet' in result
        assert 'risk_score' in result
        assert 'is_insider' in result
        assert 'sybil_analysis' in result
        assert 'influence_score' in result
        assert 'funding_analysis' in result
        assert 0.0 <= result['risk_score'] <= 1.0

    def test_get_metrics(self, profiler, sample_transactions):
        """Test metrics retrieval."""
        profiler.add_transactions_batch(sample_transactions)

        metrics = profiler.get_metrics()

        assert 'total_wallets_analyzed' in metrics
        assert 'gpu_operations' in metrics
        assert 'cpu_fallback_operations' in metrics
        assert 'gpu_available' in metrics

    def test_clear(self, profiler, sample_transactions):
        """Test profiler clearing."""
        profiler.add_transactions_batch(sample_transactions)
        assert len(profiler._transaction_cache) > 0

        profiler.clear()

        assert len(profiler._transaction_cache) == 0
        assert profiler._graph_built == False


class TestGPUStatusCheck:
    """Tests for GPU status checking."""

    def test_check_gpu_status(self):
        """Test GPU status check function."""
        from utils.gpu_graph_accelerator import check_gpu_status

        status = check_gpu_status()

        assert isinstance(status, dict)
        assert 'gpu_available' in status
        assert 'cuda_available' in status

    def test_factory_function(self):
        """Test profiler factory function."""
        from agents.wallet_profiler.gpu_wallet_profiler import create_gpu_profiler

        profiler = create_gpu_profiler(use_gpu=False)

        assert profiler is not None
        assert profiler.gpu_available == False


class TestCPUFallback:
    """Tests for CPU fallback behavior."""

    @pytest.fixture
    def cpu_accelerator(self):
        """Create CPU-only accelerator."""
        from utils.gpu_graph_accelerator import GPUWalletGraphAccelerator
        return GPUWalletGraphAccelerator(use_gpu=False)

    def test_cpu_fallback_uses_networkx(self, cpu_accelerator):
        """Test that CPU fallback uses NetworkX."""
        import networkx as nx

        assert cpu_accelerator.use_gpu == False
        assert isinstance(cpu_accelerator.graph, nx.DiGraph)

    @pytest.mark.asyncio
    async def test_cpu_fallback_full_pipeline(self, cpu_accelerator):
        """Test full pipeline works with CPU fallback."""
        # Create test data
        transactions = pd.DataFrame({
            'from_wallet': ['A', 'A', 'B', 'C', 'D'],
            'to_wallet': ['B', 'C', 'C', 'D', 'E'],
            'amount': [100, 200, 150, 300, 50],
            'timestamp': [datetime.utcnow()] * 5
        })

        # Build graph
        cpu_accelerator.build_graph_from_transactions(transactions)

        # Run all operations
        clusters = await cpu_accelerator.detect_sybil_clusters(min_cluster_size=2)
        scores = await cpu_accelerator.calculate_pagerank_influence()
        paths = await cpu_accelerator.trace_funding_paths('A', max_depth=3)
        components = await cpu_accelerator.find_connected_components()

        # All should complete without error
        assert isinstance(clusters, list)
        assert isinstance(scores, list)
        assert isinstance(paths, dict)
        assert isinstance(components, list)


class TestPerformanceMetrics:
    """Tests for performance metrics tracking."""

    @pytest.fixture
    def accelerator_with_ops(self):
        """Create accelerator with some operations."""
        from utils.gpu_graph_accelerator import GPUWalletGraphAccelerator

        acc = GPUWalletGraphAccelerator(use_gpu=False)

        # Add some transactions and build graph
        transactions = pd.DataFrame({
            'from_wallet': ['A', 'B', 'C'],
            'to_wallet': ['B', 'C', 'A'],
            'amount': [100, 200, 150],
            'timestamp': [datetime.utcnow()] * 3
        })
        acc.build_graph_from_transactions(transactions)

        return acc

    def test_metrics_recorded(self, accelerator_with_ops):
        """Test that metrics are recorded for operations."""
        assert len(accelerator_with_ops.metrics) >= 1

        metric = accelerator_with_ops.metrics[0]
        assert metric.operation == 'build_graph'
        assert metric.duration_ms > 0
        assert metric.node_count > 0

    def test_performance_summary_structure(self, accelerator_with_ops):
        """Test performance summary structure."""
        summary = accelerator_with_ops.get_performance_summary()

        assert 'total_operations' in summary
        assert 'total_time_ms' in summary
        assert 'average_time_ms' in summary
        assert 'max_gpu_memory_mb' in summary
        assert 'gpu_accelerated' in summary
        assert 'operations' in summary

        assert isinstance(summary['operations'], list)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
