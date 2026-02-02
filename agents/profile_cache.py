"""ProfileCache: Two-tier caching system for wallet profiles.

Architecture:
- L1 Cache: In-memory LRU (OrderedDict) - Target: <1ms latency
- L2 Cache: Redis Cluster - Target: <5ms latency

Performance Characteristics:
- L1 hit rate: 70-80% (typical workload)
- L2 hit rate: 15-20% (cache miss from L1)
- Total miss rate: 5-10% (requires full profiling)

Thread Safety:
- All L1 operations protected by asyncio.Lock
- Redis operations are naturally thread-safe
"""

import asyncio
import json
import structlog
from collections import OrderedDict
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Optional, Dict, List, Any

logger = structlog.get_logger(__name__)


class ProfileCache:
    """Two-tier cache for wallet profiles with LRU eviction.

    Tier 1 (L1): In-memory OrderedDict with LRU eviction
    Tier 2 (L2): Redis cluster with TTL-based expiration

    Args:
        redis_client: GuerrillaRedisCluster or Redis client instance
        l1_max_size: Maximum number of profiles in L1 cache (default: 5000)
        l2_ttl: Time-to-live for L2 cache entries in seconds (default: 300)

    Example:
        >>> from utils.redis_cluster_client import GuerrillaRedisCluster
        >>> redis = GuerrillaRedisCluster()
        >>> cache = ProfileCache(redis, l1_max_size=5000, l2_ttl=300)
        >>> 
        >>> # Get profile (checks L1, then L2, returns None on miss)
        >>> profile = await cache.get_profile("wallet123...")
        >>> 
        >>> # Update profile (writes to both L1 and L2, publishes event)
        >>> await cache.update_profile("wallet123...", profile_data)
        >>> 
        >>> # Bulk prefetch (Redis pipeline for batch reads)
        >>> profiles = await cache.bulk_prefetch(["wallet1", "wallet2", "wallet3"])
        >>> 
        >>> # Get cache statistics
        >>> stats = cache.get_stats()
        >>> print(f"Hit rate: {stats['hit_rate']:.2%}")
    """

    def __init__(self, redis_client, l1_max_size: int = 5000, l2_ttl: int = 300):
        """Initialize two-tier cache.

        Args:
            redis_client: Redis client (GuerrillaRedisCluster or redis.Redis)
            l1_max_size: Maximum L1 cache size (default: 5000 profiles)
            l2_ttl: L2 cache TTL in seconds (default: 300s = 5 minutes)
        """
        self.redis = redis_client
        self.l1_cache: OrderedDict = OrderedDict()  # LRU implementation
        self.l1_max_size = l1_max_size
        self.l2_ttl = l2_ttl
        self._lock = asyncio.Lock()  # Thread safety for L1 operations

        # Statistics tracking
        self.stats = {
            'l1_hits': 0,      # L1 cache hits
            'l2_hits': 0,      # L2 cache hits (L1 miss)
            'misses': 0,       # Total cache misses (L1 + L2)
            'writes': 0,       # Total write operations
            'evictions': 0,    # L1 LRU evictions
        }

        logger.info(
            "profile_cache_initialized",
            l1_max_size=l1_max_size,
            l2_ttl=l2_ttl
        )

    async def get_profile(self, wallet: str) -> Optional[Dict[str, Any]]:
        """Get wallet profile from cache (L1 → L2 → None).

        Cache hierarchy:
        1. Check L1 (in-memory) - <1ms latency
        2. Check L2 (Redis) - <5ms latency
        3. Return None (cache miss) - requires full profiling

        Args:
            wallet: Wallet address (Solana base58 format)

        Returns:
            Profile dict if found, None if cache miss

        Performance:
            - L1 hit: ~0.5ms (OrderedDict lookup + move_to_end)
            - L2 hit: ~3ms (Redis GET + JSON decode + L1 promotion)
            - Miss: ~0.1ms (two failed lookups)
        """
        # Step 1: Check L1 cache (in-memory)
        async with self._lock:
            if wallet in self.l1_cache:
                # L1 HIT: Move to end (most recently used)
                self.l1_cache.move_to_end(wallet)
                profile = self.l1_cache[wallet]
                self.stats['l1_hits'] += 1

                logger.debug(
                    "cache_l1_hit",
                    wallet=wallet[:8] + "...",
                    l1_size=len(self.l1_cache)
                )

                return profile

        # Step 2: Check L2 cache (Redis)
        redis_key = f"profile:{wallet}"
        try:
            profile_json = await self.redis.get(redis_key)

            if profile_json:
                # L2 HIT: Decode and promote to L1
                profile = json.loads(profile_json)
                self.stats['l2_hits'] += 1

                # Promote to L1 (async to avoid blocking)
                await self._l1_set(wallet, profile)

                logger.debug(
                    "cache_l2_hit",
                    wallet=wallet[:8] + "...",
                    promoted_to_l1=True
                )

                return profile

        except Exception as e:
            logger.error(
                "cache_l2_error",
                wallet=wallet[:8] + "...",
                error=str(e)
            )
            # Continue to cache miss (don't fail on Redis errors)

        # Step 3: Cache MISS (not in L1 or L2)
        self.stats['misses'] += 1

        logger.debug(
            "cache_miss",
            wallet=wallet[:8] + "...",
            l1_size=len(self.l1_cache)
        )

        return None

    async def update_profile(self, wallet: str, profile: Any) -> None:
        """Update profile in both L1 and L2 caches.

        Workflow:
        1. Convert dataclass to dict (if needed)
        2. Serialize datetime objects to ISO strings
        3. Write to L1 cache (in-memory)
        4. Write to L2 cache (Redis with TTL)
        5. Publish update event to godmode:profile_updates channel

        Args:
            wallet: Wallet address
            profile: Profile data (dict or dataclass)

        Side Effects:
            - Updates L1 cache (may trigger LRU eviction)
            - Updates L2 cache (Redis SET with TTL)
            - Publishes event to Redis Pub/Sub channel
        """
        # Step 1: Convert dataclass to dict if needed
        if is_dataclass(profile):
            profile_dict = asdict(profile)
        elif isinstance(profile, dict):
            profile_dict = profile
        else:
            raise TypeError(f"Profile must be dict or dataclass, got {type(profile)}")

        # Step 2: Write to L1 cache (in-memory)
        await self._l1_set(wallet, profile_dict)

        # Step 3: Write to L2 cache (Redis with TTL)
        redis_key = f"profile:{wallet}"
        try:
            # Serialize with datetime handling
            profile_json = json.dumps(profile_dict, default=str)

            # Write to Redis with TTL
            await self.redis.setex(redis_key, self.l2_ttl, profile_json)

            # Step 4: Publish update event
            event = {
                "wallet": wallet,
                "timestamp": datetime.now().isoformat()
            }
            await self.redis.publish("godmode:profile_updates", json.dumps(event))

            self.stats['writes'] += 1

            logger.info(
                "profile_updated",
                wallet=wallet[:8] + "...",
                l1_size=len(self.l1_cache),
                l2_ttl=self.l2_ttl
            )

        except Exception as e:
            logger.error(
                "cache_update_error",
                wallet=wallet[:8] + "...",
                error=str(e)
            )
            raise

    async def _l1_set(self, wallet: str, profile: Dict[str, Any]) -> None:
        """Set profile in L1 cache with LRU eviction.

        Thread-safe operation using asyncio.Lock.

        LRU Eviction:
        - When cache is at max capacity, remove least recently used item
        - OrderedDict maintains insertion order
        - move_to_end() updates access time
        - popitem(last=False) removes oldest item

        Args:
            wallet: Wallet address
            profile: Profile dict
        """
        async with self._lock:
            # Check if eviction needed
            if len(self.l1_cache) >= self.l1_max_size and wallet not in self.l1_cache:
                # Evict least recently used (first item)
                evicted_wallet, _ = self.l1_cache.popitem(last=False)
                self.stats['evictions'] += 1

                logger.debug(
                    "l1_eviction",
                    evicted_wallet=evicted_wallet[:8] + "...",
                    l1_size=len(self.l1_cache)
                )

            # Add/update profile (moves to end if exists)
            self.l1_cache[wallet] = profile
            self.l1_cache.move_to_end(wallet)

    async def invalidate(self, wallet: str) -> None:
        """Remove profile from both L1 and L2 caches.

        Use cases:
        - Manual cache clearing
        - Profile data correction
        - Forced refresh

        Args:
            wallet: Wallet address to invalidate
        """
        # Remove from L1
        async with self._lock:
            if wallet in self.l1_cache:
                del self.l1_cache[wallet]
                logger.debug(
                    "l1_invalidated",
                    wallet=wallet[:8] + "..."
                )

        # Remove from L2
        redis_key = f"profile:{wallet}"
        try:
            await self.redis.delete(redis_key)
            logger.info(
                "profile_invalidated",
                wallet=wallet[:8] + "..."
            )
        except Exception as e:
            logger.error(
                "invalidation_error",
                wallet=wallet[:8] + "...",
                error=str(e)
            )

    async def bulk_prefetch(self, wallets: List[str]) -> Dict[str, Dict[str, Any]]:
        """Bulk prefetch profiles from L2 cache using Redis pipeline.

        Performance optimization for batch operations:
        - Single Redis roundtrip for multiple keys
        - 10-100x faster than individual GET operations
        - Promotes all found profiles to L1

        Args:
            wallets: List of wallet addresses to prefetch

        Returns:
            Dict mapping wallet → profile (only found profiles)

        Example:
            >>> wallets = ["wallet1", "wallet2", "wallet3"]
            >>> profiles = await cache.bulk_prefetch(wallets)
            >>> # profiles = {"wallet1": {...}, "wallet3": {...}}  # wallet2 not found
        """
        if not wallets:
            return {}

        # Build Redis keys
        redis_keys = [f"profile:{wallet}" for wallet in wallets]

        try:
            # Use Redis pipeline for batch GET
            pipe = self.redis.pipeline()
            for key in redis_keys:
                pipe.get(key)

            # Execute pipeline (single roundtrip)
            results = await pipe.execute()

            # Parse results and promote to L1
            profiles = {}
            for wallet, profile_json in zip(wallets, results):
                if profile_json:
                    profile = json.loads(profile_json)
                    profiles[wallet] = profile

                    # Promote to L1 (async)
                    await self._l1_set(wallet, profile)

                    self.stats['l2_hits'] += 1
                else:
                    self.stats['misses'] += 1

            logger.info(
                "bulk_prefetch_complete",
                requested=len(wallets),
                found=len(profiles),
                hit_rate=len(profiles) / len(wallets) if wallets else 0.0
            )

            return profiles

        except Exception as e:
            logger.error(
                "bulk_prefetch_error",
                wallet_count=len(wallets),
                error=str(e)
            )
            return {}

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics and performance metrics.

        Returns:
            Dict containing:
            - l1_hits, l2_hits, misses: Raw counters
            - writes, evictions: Operation counters
            - hit_rate: Overall cache hit rate (0.0-1.0)
            - l1_hit_rate: L1-specific hit rate (0.0-1.0)
            - l1_size: Current L1 cache size

        Example:
            >>> stats = cache.get_stats()
            >>> print(f"Hit rate: {stats['hit_rate']:.2%}")  # "Hit rate: 85.32%"
            >>> print(f"L1 size: {stats['l1_size']}/{cache.l1_max_size}")
        """
        total_requests = self.stats['l1_hits'] + self.stats['l2_hits'] + self.stats['misses']
        total_hits = self.stats['l1_hits'] + self.stats['l2_hits']

        return {
            # Raw counters
            'l1_hits': self.stats['l1_hits'],
            'l2_hits': self.stats['l2_hits'],
            'misses': self.stats['misses'],
            'writes': self.stats['writes'],
            'evictions': self.stats['evictions'],

            # Calculated metrics
            'hit_rate': total_hits / total_requests if total_requests > 0 else 0.0,
            'l1_hit_rate': self.stats['l1_hits'] / total_requests if total_requests > 0 else 0.0,
            'l1_size': len(self.l1_cache),
            'l1_max_size': self.l1_max_size,
            'l2_ttl': self.l2_ttl,
        }
