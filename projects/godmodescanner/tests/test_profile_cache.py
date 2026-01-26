"""Unit tests for ProfileCache two-tier caching system.

Test Coverage:
- L1 cache operations (hit, miss, eviction)
- L2 cache operations (hit, miss, TTL)
- Dataclass/dict conversion
- Datetime serialization
- Redis event publishing
- Bulk prefetch with pipeline
- Statistics tracking
- Thread safety
"""

import pytest
import asyncio
import json
import time
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

# Import ProfileCache
import sys
sys.path.insert(0, '/a0/usr/projects/godmodescanner/projects/godmodescanner')
from agents.profile_cache import ProfileCache


# Mock dataclass for testing
@dataclass
class MockWalletProfile:
    wallet_address: str
    win_rate: float
    graduation_rate: float
    risk_score: float
    severity: str
    total_trades: int = 0
    total_profit: float = 0.0
    last_updated: Optional[datetime] = None


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self):
        self.storage = {}  # In-memory storage
        self.published_events = []  # Track published events
        self.pipeline_results = []  # Track pipeline operations

    async def get(self, key: str) -> Optional[str]:
        """Mock Redis GET."""
        return self.storage.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        """Mock Redis SETEX."""
        self.storage[key] = value

    async def delete(self, key: str) -> None:
        """Mock Redis DELETE."""
        if key in self.storage:
            del self.storage[key]

    async def publish(self, channel: str, message: str) -> None:
        """Mock Redis PUBLISH."""
        self.published_events.append({
            'channel': channel,
            'message': json.loads(message)
        })

    def pipeline(self):
        """Mock Redis pipeline."""
        return MockRedisPipeline(self)


class MockRedisPipeline:
    """Mock Redis pipeline for batch operations."""

    def __init__(self, redis_client):
        self.redis = redis_client
        self.commands = []

    def get(self, key: str):
        """Queue GET command."""
        self.commands.append(('get', key))
        return self

    async def execute(self):
        """Execute all queued commands."""
        results = []
        for cmd, key in self.commands:
            if cmd == 'get':
                results.append(self.redis.storage.get(key))
        return results


class TestProfileCache:
    """Test suite for ProfileCache."""

    @pytest.fixture
    def redis_client(self):
        """Create mock Redis client."""
        return MockRedisClient()

    @pytest.fixture
    def cache(self, redis_client):
        """Create ProfileCache instance."""
        return ProfileCache(
            redis_client=redis_client,
            l1_max_size=5,  # Small size for testing eviction
            l2_ttl=300
        )

    # ========================================================================
    # Test 1: L1 Cache Hit Path
    # ========================================================================

    @pytest.mark.asyncio
    async def test_l1_cache_hit(self, cache):
        """Test L1 cache hit path (<1ms latency)."""
        # Setup: Pre-populate L1 cache
        test_wallet = "TEST_WALLET_L1_HIT"
        test_profile = {
            'wallet_address': test_wallet,
            'win_rate': 0.75,
            'risk_score': 0.85
        }

        await cache._l1_set(test_wallet, test_profile)

        # Execute: Get profile (should hit L1)
        start = time.time()
        result = await cache.get_profile(test_wallet)
        latency_ms = (time.time() - start) * 1000

        # Verify
        assert result is not None
        assert result['wallet_address'] == test_wallet
        assert result['win_rate'] == 0.75
        assert latency_ms < 1.0  # <1ms target
        assert cache.stats['l1_hits'] == 1
        assert cache.stats['l2_hits'] == 0
        assert cache.stats['misses'] == 0

        print(f"✅ L1 hit latency: {latency_ms:.3f}ms (target: <1ms)")

    # ========================================================================
    # Test 2: L2 Cache Hit Path
    # ========================================================================

    @pytest.mark.asyncio
    async def test_l2_cache_hit(self, cache, redis_client):
        """Test L2 cache hit path (<5ms latency)."""
        # Setup: Pre-populate L2 cache (Redis) only
        test_wallet = "TEST_WALLET_L2_HIT"
        test_profile = {
            'wallet_address': test_wallet,
            'win_rate': 0.60,
            'risk_score': 0.70
        }

        redis_key = f"profile:{test_wallet}"
        redis_client.storage[redis_key] = json.dumps(test_profile)

        # Execute: Get profile (should miss L1, hit L2)
        start = time.time()
        result = await cache.get_profile(test_wallet)
        latency_ms = (time.time() - start) * 1000

        # Verify
        assert result is not None
        assert result['wallet_address'] == test_wallet
        assert result['win_rate'] == 0.60
        assert latency_ms < 5.0  # <5ms target
        assert cache.stats['l1_hits'] == 0
        assert cache.stats['l2_hits'] == 1
        assert cache.stats['misses'] == 0

        # Verify promotion to L1
        assert test_wallet in cache.l1_cache

        print(f"✅ L2 hit latency: {latency_ms:.3f}ms (target: <5ms)")

    # ========================================================================
    # Test 3: Cache Miss Path
    # ========================================================================

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache):
        """Test cache miss (not in L1 or L2)."""
        test_wallet = "TEST_WALLET_MISS"

        # Execute: Get profile (should miss both L1 and L2)
        result = await cache.get_profile(test_wallet)

        # Verify
        assert result is None
        assert cache.stats['l1_hits'] == 0
        assert cache.stats['l2_hits'] == 0
        assert cache.stats['misses'] == 1

        print("✅ Cache miss handled correctly")

    # ========================================================================
    # Test 4: LRU Eviction
    # ========================================================================

    @pytest.mark.asyncio
    async def test_lru_eviction(self, cache):
        """Test LRU eviction when L1 cache is full."""
        # Setup: Fill L1 cache to max capacity (5 items)
        for i in range(5):
            wallet = f"WALLET_{i}"
            profile = {'wallet_address': wallet, 'win_rate': 0.5}
            await cache._l1_set(wallet, profile)

        assert len(cache.l1_cache) == 5
        assert cache.stats['evictions'] == 0

        # Execute: Add 6th item (should evict WALLET_0)
        new_wallet = "WALLET_NEW"
        new_profile = {'wallet_address': new_wallet, 'win_rate': 0.8}
        await cache._l1_set(new_wallet, new_profile)

        # Verify
        assert len(cache.l1_cache) == 5  # Still at max
        assert cache.stats['evictions'] == 1
        assert "WALLET_0" not in cache.l1_cache  # Oldest evicted
        assert new_wallet in cache.l1_cache  # New item added

        print("✅ LRU eviction working correctly")

    # ========================================================================
    # Test 5: Update Profile with Dataclass
    # ========================================================================

    @pytest.mark.asyncio
    async def test_update_profile_dataclass(self, cache, redis_client):
        """Test update_profile() with dataclass input."""
        # Setup: Create dataclass profile
        test_wallet = "TEST_WALLET_DATACLASS"
        profile = MockWalletProfile(
            wallet_address=test_wallet,
            win_rate=0.75,
            graduation_rate=0.65,
            risk_score=0.85,
            severity='CRITICAL',
            total_trades=25,
            total_profit=500.0,
            last_updated=datetime.now()
        )

        # Execute: Update profile
        await cache.update_profile(test_wallet, profile)

        # Verify L1 cache
        assert test_wallet in cache.l1_cache
        l1_profile = cache.l1_cache[test_wallet]
        assert l1_profile['wallet_address'] == test_wallet
        assert l1_profile['win_rate'] == 0.75

        # Verify L2 cache (Redis)
        redis_key = f"profile:{test_wallet}"
        assert redis_key in redis_client.storage
        l2_profile = json.loads(redis_client.storage[redis_key])
        assert l2_profile['wallet_address'] == test_wallet

        # Verify datetime serialization
        assert isinstance(l2_profile['last_updated'], str)  # Serialized to string

        # Verify event published
        assert len(redis_client.published_events) == 1
        event = redis_client.published_events[0]
        assert event['channel'] == 'godmode:profile_updates'
        assert event['message']['wallet'] == test_wallet

        # Verify stats
        assert cache.stats['writes'] == 1

        print("✅ Dataclass update with datetime serialization working")

    # ========================================================================
    # Test 6: Update Profile with Dict
    # ========================================================================

    @pytest.mark.asyncio
    async def test_update_profile_dict(self, cache, redis_client):
        """Test update_profile() with dict input."""
        test_wallet = "TEST_WALLET_DICT"
        profile = {
            'wallet_address': test_wallet,
            'win_rate': 0.60,
            'risk_score': 0.70
        }

        # Execute
        await cache.update_profile(test_wallet, profile)

        # Verify
        assert test_wallet in cache.l1_cache
        assert cache.stats['writes'] == 1

        print("✅ Dict update working correctly")

    # ========================================================================
    # Test 7: Invalidate Profile
    # ========================================================================

    @pytest.mark.asyncio
    async def test_invalidate(self, cache, redis_client):
        """Test invalidate() removes from both L1 and L2."""
        # Setup: Add profile to both caches
        test_wallet = "TEST_WALLET_INVALIDATE"
        profile = {'wallet_address': test_wallet, 'win_rate': 0.5}

        await cache.update_profile(test_wallet, profile)

        # Verify profile exists
        assert test_wallet in cache.l1_cache
        assert f"profile:{test_wallet}" in redis_client.storage

        # Execute: Invalidate
        await cache.invalidate(test_wallet)

        # Verify removal
        assert test_wallet not in cache.l1_cache
        assert f"profile:{test_wallet}" not in redis_client.storage

        print("✅ Invalidation working correctly")

    # ========================================================================
    # Test 8: Bulk Prefetch
    # ========================================================================

    @pytest.mark.asyncio
    async def test_bulk_prefetch(self, cache, redis_client):
        """Test bulk_prefetch() with Redis pipeline."""
        # Setup: Pre-populate L2 cache with 3 profiles
        wallets = [f"WALLET_{i}" for i in range(3)]
        for wallet in wallets:
            profile = {'wallet_address': wallet, 'win_rate': 0.5}
            redis_key = f"profile:{wallet}"
            redis_client.storage[redis_key] = json.dumps(profile)

        # Execute: Bulk prefetch
        results = await cache.bulk_prefetch(wallets)

        # Verify
        assert len(results) == 3
        for wallet in wallets:
            assert wallet in results
            assert results[wallet]['wallet_address'] == wallet
            # Verify promotion to L1
            assert wallet in cache.l1_cache

        # Verify stats
        assert cache.stats['l2_hits'] == 3

        print("✅ Bulk prefetch working correctly")

    # ========================================================================
    # Test 9: Bulk Prefetch with Partial Misses
    # ========================================================================

    @pytest.mark.asyncio
    async def test_bulk_prefetch_partial_miss(self, cache, redis_client):
        """Test bulk_prefetch() with some wallets missing."""
        # Setup: Only add 2 out of 4 wallets to L2
        wallets = [f"WALLET_{i}" for i in range(4)]
        for i in [0, 2]:  # Only add WALLET_0 and WALLET_2
            wallet = wallets[i]
            profile = {'wallet_address': wallet, 'win_rate': 0.5}
            redis_key = f"profile:{wallet}"
            redis_client.storage[redis_key] = json.dumps(profile)

        # Execute
        results = await cache.bulk_prefetch(wallets)

        # Verify
        assert len(results) == 2  # Only 2 found
        assert "WALLET_0" in results
        assert "WALLET_2" in results
        assert "WALLET_1" not in results  # Missing
        assert "WALLET_3" not in results  # Missing

        # Verify stats
        assert cache.stats['l2_hits'] == 2
        assert cache.stats['misses'] == 2

        print("✅ Bulk prefetch with partial misses working")

    # ========================================================================
    # Test 10: Get Statistics
    # ========================================================================

    @pytest.mark.asyncio
    async def test_get_stats(self, cache):
        """Test get_stats() calculation."""
        # Setup: Simulate various cache operations
        # 3 L1 hits
        for i in range(3):
            wallet = f"L1_WALLET_{i}"
            profile = {'wallet_address': wallet}
            await cache._l1_set(wallet, profile)
            await cache.get_profile(wallet)  # L1 hit

        # 2 L2 hits (mock)
        cache.stats['l2_hits'] = 2

        # 1 miss (mock)
        cache.stats['misses'] = 1

        # Execute
        stats = cache.get_stats()

        # Verify calculations
        assert stats['l1_hits'] == 3
        assert stats['l2_hits'] == 2
        assert stats['misses'] == 1

        # Total requests = 3 + 2 + 1 = 6
        # Total hits = 3 + 2 = 5
        # Hit rate = 5/6 = 0.8333...
        assert abs(stats['hit_rate'] - 0.8333) < 0.01

        # L1 hit rate = 3/6 = 0.5
        assert abs(stats['l1_hit_rate'] - 0.5) < 0.01

        assert stats['l1_size'] == 3
        assert stats['l1_max_size'] == 5
        assert stats['l2_ttl'] == 300

        print(f"✅ Statistics: hit_rate={stats['hit_rate']:.2%}, l1_hit_rate={stats['l1_hit_rate']:.2%}")

    # ========================================================================
    # Test 11: Thread Safety (Concurrent Operations)
    # ========================================================================

    @pytest.mark.asyncio
    async def test_thread_safety(self, cache):
        """Test thread safety with concurrent L1 operations."""
        # Execute: Concurrent writes to L1
        async def write_profile(i):
            wallet = f"CONCURRENT_WALLET_{i}"
            profile = {'wallet_address': wallet, 'win_rate': 0.5}
            await cache._l1_set(wallet, profile)

        # Run 10 concurrent writes
        await asyncio.gather(*[write_profile(i) for i in range(10)])

        # Verify: L1 cache should have 5 items (max capacity)
        # No race conditions or corruption
        assert len(cache.l1_cache) == 5
        assert cache.stats['evictions'] == 5  # 10 writes - 5 capacity = 5 evictions

        print("✅ Thread safety verified with concurrent operations")

    # ========================================================================
    # Test 12: Empty Bulk Prefetch
    # ========================================================================

    @pytest.mark.asyncio
    async def test_bulk_prefetch_empty(self, cache):
        """Test bulk_prefetch() with empty wallet list."""
        results = await cache.bulk_prefetch([])

        assert results == {}
        assert cache.stats['l2_hits'] == 0
        assert cache.stats['misses'] == 0

        print("✅ Empty bulk prefetch handled correctly")


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v', '--asyncio-mode=auto'])
