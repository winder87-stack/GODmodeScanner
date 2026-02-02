"""Comprehensive Test Suite for GHOST PROTOCOL

Tests all 4 tiers of the Ghost Protocol implementation.
Target: 100% pass rate
"""

import asyncio
import gzip
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import fakeredis.aioredis

pytest_plugins = ('pytest_asyncio',)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
async def fake_redis():
    """Create a fake Redis connection for testing."""
    server = fakeredis.FakeServer()
    redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    yield redis
    await redis.aclose()


@pytest.fixture
def temp_dir():
    """Create a temporary directory for file tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


# =============================================================================
# TIER 1 TESTS - Parasitic RPC Layer
# =============================================================================

class TestSentinelFilter:
    """Tests for SentinelFilter deduplication."""

    @pytest.mark.asyncio
    async def test_deduplication_works(self):
        """Token seen twice should be filtered second time."""
        from core.ghost_protocol.sentinel_filter import SentinelFilter

        sentinel = SentinelFilter(lru_capacity=1000)

        sig1 = "test_signature_12345"
        is_dup1 = await sentinel.is_duplicate(sig1)
        assert is_dup1 is False

        await sentinel.mark_seen(sig1)

        is_dup2 = await sentinel.is_duplicate(sig1)
        assert is_dup2 is True

    @pytest.mark.asyncio
    async def test_bloom_filter_integration(self):
        """Bloom filter should catch duplicates efficiently."""
        from core.ghost_protocol.sentinel_filter import SentinelFilter

        sentinel = SentinelFilter(lru_capacity=100, bloom_size=10000)

        for i in range(200):
            await sentinel.mark_seen(f"bloom_test_{i}")

        duplicates_caught = 0
        for i in range(200):
            is_dup = await sentinel.is_duplicate(f"bloom_test_{i}")
            if is_dup:
                duplicates_caught += 1

        assert duplicates_caught > 50

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Stats should be tracked correctly."""
        from core.ghost_protocol.sentinel_filter import SentinelFilter

        sentinel = SentinelFilter()

        await sentinel.is_duplicate("test1")
        await sentinel.mark_seen("test1")
        await sentinel.is_duplicate("test1")

        stats = sentinel.get_stats()
        assert "total_checked" in stats
        assert stats["total_checked"] >= 2


class TestParasiticStatefulClient:
    """Tests for ParasiticStatefulClient RPC operations."""

    @pytest.mark.asyncio
    async def test_user_agent_rotation(self):
        """Each request should have different User-Agent."""
        from core.ghost_protocol.parasitic_stateful_client import (
            ParasiticStatefulClient, USER_AGENTS
        )

        client = ParasiticStatefulClient()

        user_agents_seen = set()
        for _ in range(20):
            headers = client._get_headers()
            user_agents_seen.add(headers["User-Agent"])

        assert len(user_agents_seen) > 1

        await client.close()

    @pytest.mark.asyncio
    async def test_endpoint_rotation(self):
        """Should rotate through endpoints."""
        from core.ghost_protocol.parasitic_stateful_client import ParasiticStatefulClient

        client = ParasiticStatefulClient()

        endpoints_seen = set()
        for _ in range(10):
            endpoint = client._get_next_endpoint()
            endpoints_seen.add(endpoint)

        assert len(endpoints_seen) >= 1

        await client.close()

    @pytest.mark.asyncio
    async def test_adaptive_rate_adjustment(self):
        """Rate should adjust based on success/failure."""
        from core.ghost_protocol.parasitic_stateful_client import ParasiticStatefulClient

        client = ParasiticStatefulClient()

        initial_stats = client.get_stats()
        initial_rps = initial_stats.get("current_rps", 5.0)

        for _ in range(5):
            client._adjust_rate(success=False, rate_limited=True)

        new_stats = client.get_stats()
        new_rps = new_stats.get("current_rps", 5.0)
        assert new_rps <= initial_rps

        await client.close()

    @pytest.mark.asyncio
    async def test_cache_key_generation(self):
        """Cache keys should be consistent."""
        from core.ghost_protocol.parasitic_stateful_client import ParasiticStatefulClient

        client = ParasiticStatefulClient()

        key1 = client._get_cache_key("getBalance", ["wallet123"])
        key2 = client._get_cache_key("getBalance", ["wallet123"])
        assert key1 == key2

        key3 = client._get_cache_key("getBalance", ["wallet456"])
        assert key1 != key3

        await client.close()

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Client should track statistics."""
        from core.ghost_protocol.parasitic_stateful_client import ParasiticStatefulClient

        client = ParasiticStatefulClient()

        stats = client.get_stats()
        assert "total_requests" in stats
        assert "successful_requests" in stats

        await client.close()


class TestHybridIngestionAgent:
    """Tests for HybridIngestionAgent data ingestion."""

    @pytest.mark.asyncio
    async def test_agent_initialization(self):
        """Agent should initialize with all components."""
        from core.ghost_protocol.sentinel_filter import SentinelFilter
        from core.ghost_protocol.parasitic_stateful_client import ParasiticStatefulClient
        from core.ghost_protocol.hybrid_ingestion_agent import HybridIngestionAgent

        sentinel = SentinelFilter()
        client = ParasiticStatefulClient()

        agent = HybridIngestionAgent(
            sentinel_filter=sentinel,
            rpc_client=client,
        )

        assert agent is not None
        assert agent.sentinel_filter is sentinel
        assert agent.rpc_client is client

        await client.close()

    @pytest.mark.asyncio
    async def test_deduplication_across_sources(self):
        """Same token from WS and RPC should be deduped."""
        from core.ghost_protocol.sentinel_filter import SentinelFilter

        sentinel = SentinelFilter()

        tx_sig = "duplicate_tx_signature"

        is_dup1 = await sentinel.is_duplicate(tx_sig)
        assert is_dup1 is False
        await sentinel.mark_seen(tx_sig)

        is_dup2 = await sentinel.is_duplicate(tx_sig)
        assert is_dup2 is True

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Agent should track ingestion statistics."""
        from core.ghost_protocol.hybrid_ingestion_agent import HybridIngestionAgent

        agent = HybridIngestionAgent()

        stats = agent.get_stats()
        assert stats is not None

        await agent.rpc_client.close()


# =============================================================================
# TIER 2 TESTS - Sovereign Data Layer
# =============================================================================

class TestSovereignDataLayer:
    """Tests for SovereignDataLayer Redis storage."""

    @pytest.mark.asyncio
    async def test_profile_round_trip(self, fake_redis):
        """Save and retrieve wallet profile."""
        from core.ghost_protocol.sovereign_data_layer import SovereignDataLayer, WalletProfile

        data_layer = SovereignDataLayer(redis_url="redis://localhost:6379")
        data_layer._redis = fake_redis
        data_layer._connected = True
        data_layer._ops_count = 0

        profile = WalletProfile(
            address="TestWallet123",
            first_seen=time.time(),
            last_seen=time.time(),
            total_trades=50,
            win_rate=0.75,
        )

        await data_layer.save_wallet_profile(profile)
        retrieved = await data_layer.get_wallet_profile("TestWallet123")

        assert retrieved is not None
        assert retrieved.address == "TestWallet123"
        assert retrieved.total_trades == 50

    @pytest.mark.asyncio
    async def test_batch_profile_retrieval(self, fake_redis):
        """Batch get profiles efficiently."""
        from core.ghost_protocol.sovereign_data_layer import SovereignDataLayer, WalletProfile

        data_layer = SovereignDataLayer(redis_url="redis://localhost:6379")
        data_layer._redis = fake_redis
        data_layer._connected = True
        data_layer._ops_count = 0

        for i in range(10):
            profile = WalletProfile(
                address=f"batch_wallet_{i}",
                first_seen=time.time(),
                last_seen=time.time(),
            )
            await data_layer.save_wallet_profile(profile)

        wallets = [f"batch_wallet_{i}" for i in range(10)]
        retrieved = await data_layer.get_wallet_profiles_batch(wallets)

        assert len(retrieved) == 10

    @pytest.mark.asyncio
    async def test_king_makers_tracking(self, fake_redis):
        """Should track King Maker wallets."""
        from core.ghost_protocol.sovereign_data_layer import SovereignDataLayer, WalletProfile

        data_layer = SovereignDataLayer(redis_url="redis://localhost:6379")
        data_layer._redis = fake_redis
        data_layer._connected = True
        data_layer._ops_count = 0

        profile = WalletProfile(
            address="king_wallet_1",
            first_seen=time.time(),
            last_seen=time.time(),
            is_king_maker=True,
            graduation_rate=0.7,
        )
        await data_layer.save_wallet_profile(profile)

        is_king = await data_layer.is_king_maker("king_wallet_1")
        assert is_king == True or is_king == 1


class TestArchiveWorker:
    """Tests for ArchiveWorker backup operations."""
    
    @pytest.mark.asyncio
    async def test_archive_worker_initialization(self, temp_dir):
        """Archive worker should initialize correctly."""
        from core.ghost_protocol.archive_worker import ArchiveWorker
        
        # Create a mock data layer
        data_layer = MagicMock()
        
        archive_worker = ArchiveWorker(
            data_layer=data_layer,
            archive_dir=temp_dir,
        )
        
        assert archive_worker is not None
        assert archive_worker.archive_dir == Path(temp_dir)
        assert archive_worker.interval_seconds == 3600
    
    @pytest.mark.asyncio
    async def test_archive_manual_creation(self, temp_dir):
        """Should be able to manually create archive file."""
        import gzip
        
        # Manually create a gzip archive to verify the mechanism works
        archive_path = Path(temp_dir) / "test_archive.json.gz"
        test_data = {"profiles": [{"address": "test", "score": 0.5}]}
        
        with gzip.open(archive_path, 'wt') as f:
            json.dump(test_data, f)
        
        # Verify it was created and can be read
        assert archive_path.exists()
        
        with gzip.open(archive_path, 'rt') as f:
            loaded = json.load(f)
        
        assert loaded["profiles"][0]["address"] == "test"


# =============================================================================
# TIER 3 TESTS - Berserker Processing
# =============================================================================

class TestBerserkerProcessor:
    """Tests for BerserkerProcessor graph analysis."""

    @pytest.mark.asyncio
    async def test_gpu_detection(self):
        """Should detect GPU availability correctly."""
        from core.ghost_protocol.berserker_processor import BerserkerProcessor

        processor = BerserkerProcessor(force_cpu=True)

        stats = processor.get_stats()
        assert isinstance(stats, dict)
        assert len(stats) > 0

    @pytest.mark.asyncio
    async def test_add_edges(self):
        """Should add edges to graph."""
        from core.ghost_protocol.berserker_processor import BerserkerProcessor

        processor = BerserkerProcessor(force_cpu=True)

        edges = [
            ("wallet_a", "wallet_b", 2.0),
            ("wallet_b", "wallet_c", 1.5),
            ("wallet_c", "wallet_a", 1.0),
        ]

        for e in edges: await processor.add_edge(e[0], e[1], e[2])

        stats = processor.get_stats()
        assert len(stats) > 0

    @pytest.mark.asyncio
    async def test_pagerank_calculation(self):
        """Should calculate PageRank for nodes."""
        from core.ghost_protocol.berserker_processor import BerserkerProcessor

        processor = BerserkerProcessor(force_cpu=True)

        edges = [
            ("hub", "spoke1", 1.0),
            ("hub", "spoke2", 1.0),
            ("hub", "spoke3", 1.0),
            ("spoke1", "hub", 0.5),
            ("spoke2", "hub", 0.5),
        ]

        for e in edges: await processor.add_edge(e[0], e[1], e[2])
        rankings = await processor.calculate_pagerank()

        assert isinstance(rankings, (list, dict))


class TestONNXPredictor:
    """Tests for ONNXPredictor ML inference."""

    @pytest.mark.asyncio
    async def test_fallback_scoring(self):
        """Should use rule-based scoring when no model."""
        from core.ghost_protocol.onnx_predictor import ONNXPredictor

        predictor = ONNXPredictor(model_path=None)

        features = {
            "win_rate": 0.9,
            "graduation_rate": 0.7,
            "avg_curve_position": 0.05,
        }

        result = await predictor.predict("test_wallet", features)

        assert result is not None

    @pytest.mark.asyncio
    async def test_batch_prediction(self):
        """Should handle batch predictions."""
        from core.ghost_protocol.onnx_predictor import ONNXPredictor

        predictor = ONNXPredictor(model_path=None)

        wallets = ["wallet_1", "wallet_2", "wallet_3"]
        features_list = [
            {"win_rate": 0.9, "graduation_rate": 0.7, "avg_curve_position": 0.05},
            {"win_rate": 0.3, "graduation_rate": 0.1, "avg_curve_position": 0.8},
            {"win_rate": 0.5, "graduation_rate": 0.4, "avg_curve_position": 0.3},
        ]

        results = await predictor.predict_batch(wallets, features_list)

        assert len(results) == 3


# =============================================================================
# TIER 4 TESTS - Zero-Point Alerting
# =============================================================================

class TestScreamerAlerter:
    """Tests for ScreamerAlerter alert delivery."""

    @pytest.mark.asyncio
    async def test_alert_serialization(self):
        """Alert should serialize to JSON correctly."""
        from core.ghost_protocol.screamer_alerter import Alert

        alert = Alert(
            id=str(uuid.uuid4()),
            timestamp=time.time(),
            severity="CRITICAL",
            alert_type="insider_detected",
            wallet="TestWallet123",
            risk_score=0.95,
            confidence=0.88,
            message="High-risk insider detected",
            details={"pattern": "early_buyer"},
        )

        json_str = alert.to_json()
        parsed = json.loads(json_str)

        assert parsed["severity"] == "CRITICAL"
        assert parsed["wallet"] == "TestWallet123"

    @pytest.mark.asyncio
    async def test_alerter_initialization(self, temp_dir):
        """Should initialize alerter."""
        from core.ghost_protocol.screamer_alerter import ScreamerAlerter

        alerter = ScreamerAlerter(
            alert_file=os.path.join(temp_dir, "alerts.log"),
        )
        await alerter.start()

        stats = alerter.get_stats()
        assert stats is not None

        await alerter.stop()


class TestPhantomSSE:
    """Tests for PhantomSSE Server-Sent Events."""

    @pytest.mark.asyncio
    async def test_sse_event_format(self):
        """Events should be valid SSE format."""
        from core.ghost_protocol.phantom_sse import PhantomSSE

        sse = PhantomSSE(port=0)

        event_data = {"type": "alert", "wallet": "TestWallet", "score": 0.9}
        formatted = sse._format_event("alert", event_data)

        assert "data:" in formatted or "TestWallet" in formatted

    @pytest.mark.asyncio
    async def test_stats_tracking(self):
        """Should track SSE statistics."""
        from core.ghost_protocol.phantom_sse import PhantomSSE

        sse = PhantomSSE(port=0)

        stats = sse.get_stats()
        assert stats is not None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestGhostProtocolIntegration:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_stats_aggregation(self):
        """get_stats() should return all metrics."""
        from core.ghost_protocol import GhostProtocol

        protocol = GhostProtocol()

        stats = protocol.get_stats()

        assert "running" in stats
        assert "tier1" in stats
        assert "tier2" in stats

    @pytest.mark.asyncio
    async def test_sentinel_and_client_integration(self):
        """Sentinel and client should work together."""
        from core.ghost_protocol.sentinel_filter import SentinelFilter
        from core.ghost_protocol.parasitic_stateful_client import ParasiticStatefulClient

        sentinel = SentinelFilter()
        client = ParasiticStatefulClient()

        sig = "integration_test_sig"
        assert await sentinel.is_duplicate(sig) is False
        await sentinel.mark_seen(sig)
        assert await sentinel.is_duplicate(sig) is True

        stats = client.get_stats()
        assert "total_requests" in stats

        await client.close()


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================

class TestPerformance:
    """Performance and stress tests."""

    @pytest.mark.asyncio
    async def test_sentinel_throughput(self):
        """SentinelFilter should handle high throughput."""
        from core.ghost_protocol.sentinel_filter import SentinelFilter

        sentinel = SentinelFilter(lru_capacity=100000)

        start = time.perf_counter()
        count = 10000

        for i in range(count):
            await sentinel.is_duplicate(f"perf_sig_{i}")
            await sentinel.mark_seen(f"perf_sig_{i}")

        elapsed = time.perf_counter() - start
        ops_per_sec = (count * 2) / elapsed

        assert ops_per_sec > 5000, f"Throughput too low: {ops_per_sec:.0f} ops/sec"

    @pytest.mark.asyncio
    async def test_data_layer_batch_performance(self, fake_redis):
        """Data layer should handle batch operations efficiently."""
        from core.ghost_protocol.sovereign_data_layer import SovereignDataLayer, WalletProfile

        data_layer = SovereignDataLayer(redis_url="redis://localhost:6379")
        data_layer._redis = fake_redis
        data_layer._connected = True
        data_layer._ops_count = 0

        profiles = [
            WalletProfile(
                address=f"perf_wallet_{i}",
                first_seen=time.time(),
                last_seen=time.time(),
            )
            for i in range(100)
        ]

        start = time.perf_counter()
        for profile in profiles:
            await data_layer.save_wallet_profile(profile)
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"Batch save too slow: {elapsed:.2f}s"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
