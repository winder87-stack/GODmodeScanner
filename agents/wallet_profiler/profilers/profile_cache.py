#!/usr/bin/env python3
"""
Profile Cache - Redis-backed Wallet Profile Storage

This module implements a high-performance caching layer for wallet profiles
to minimize database load and enable sub-second profile retrieval.

Key Features:
- Redis Hash-based storage for structured data
- 1-hour TTL for sticky insider reputation
- Batch retrieval using Redis pipelines
- Automatic serialization of datetime and decimal types

Author: GODMODESCANNER Team
Date: 2026-01-25
"""

import json
import structlog
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone
from decimal import Decimal
import redis.asyncio as redis

logger = structlog.get_logger(__name__)

# Cache configuration
CACHE_KEY_PREFIX = "godmode:profile"
DEFAULT_TTL = 3600  # 1 hour (insider reputation is sticky)


class ProfileCache:
    """
    Redis-backed cache for wallet profiles with automatic serialization.

    This class provides high-performance caching for wallet profiles using
    Redis Hashes. Profiles are cached for 1 hour to reduce database load
    while maintaining reasonably fresh data.

    Key Format: godmode:profile:{wallet_address}
    TTL: 3600 seconds (1 hour)
    """

    def __init__(self, redis_client: redis.Redis, ttl: int = DEFAULT_TTL):
        """
        Initialize the profile cache.

        Args:
            redis_client: Async Redis client instance
            ttl: Time-to-live in seconds (default: 3600)
        """
        self.redis = redis_client
        self.ttl = ttl
        self.logger = logger.bind(component="ProfileCache")

        self.logger.info(
            "profile_cache_initialized",
            ttl=ttl,
            key_prefix=CACHE_KEY_PREFIX
        )

    def _make_key(self, wallet: str) -> str:
        """
        Generate Redis key for wallet profile.

        Args:
            wallet: Wallet address

        Returns:
            Redis key string
        """
        return f"{CACHE_KEY_PREFIX}:{wallet}"

    def _serialize_value(self, value: Any) -> str:
        """
        Serialize value for Redis storage.

        Handles datetime, Decimal, and other complex types.

        Args:
            value: Value to serialize

        Returns:
            JSON-serialized string
        """
        if isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, dict):
            return json.dumps({k: self._serialize_value(v) for k, v in value.items()})
        elif isinstance(value, list):
            return json.dumps([self._serialize_value(v) for v in value])
        else:
            return str(value)

    def _deserialize_value(self, value: str, field_name: str) -> Any:
        """
        Deserialize value from Redis storage.

        Args:
            value: Serialized value
            field_name: Field name for type inference

        Returns:
            Deserialized value
        """
        # Handle datetime fields
        if 'timestamp' in field_name.lower() or 'time' in field_name.lower():
            try:
                return datetime.fromisoformat(value)
            except (ValueError, AttributeError):
                pass

        # Handle numeric fields
        if any(x in field_name.lower() for x in ['score', 'rate', 'total', 'count']):
            try:
                return float(value)
            except (ValueError, TypeError):
                pass

        # Handle JSON fields
        if value.startswith('{') or value.startswith('['):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass

        return value

    async def get(self, wallet: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve wallet profile from cache.

        Args:
            wallet: Wallet address

        Returns:
            Profile dictionary or None if not cached
        """
        key = self._make_key(wallet)

        try:
            # Get all fields from hash
            profile_data = await self.redis.hgetall(key)

            if not profile_data:
                self.logger.debug("cache_miss", wallet=wallet)
                return None

            # Deserialize values
            profile = {
                k.decode('utf-8'): self._deserialize_value(v.decode('utf-8'), k.decode('utf-8'))
                for k, v in profile_data.items()
            }

            self.logger.info(
                "cache_hit",
                wallet=wallet,
                fields=len(profile)
            )

            return profile

        except Exception as e:
            self.logger.error(
                "cache_get_error",
                wallet=wallet,
                error=str(e)
            )
            return None

    async def set(
        self,
        wallet: str,
        profile: Dict[str, Any],
        ttl: Optional[int] = None
    ) -> bool:
        """
        Store wallet profile in cache.

        Args:
            wallet: Wallet address
            profile: Profile dictionary
            ttl: Optional custom TTL (default: use instance TTL)

        Returns:
            True if successful, False otherwise
        """
        key = self._make_key(wallet)
        ttl = ttl or self.ttl

        try:
            # Serialize all values
            serialized_profile = {
                k: self._serialize_value(v)
                for k, v in profile.items()
            }

            # Use pipeline for atomic operation
            async with self.redis.pipeline(transaction=True) as pipe:
                # Set hash fields
                await pipe.hset(key, mapping=serialized_profile)
                # Set TTL
                await pipe.expire(key, ttl)
                # Execute pipeline
                await pipe.execute()

            self.logger.info(
                "cache_set",
                wallet=wallet,
                fields=len(profile),
                ttl=ttl
            )

            return True

        except Exception as e:
            self.logger.error(
                "cache_set_error",
                wallet=wallet,
                error=str(e)
            )
            return False

    async def batch_get(self, wallets: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """
        Retrieve multiple wallet profiles using Redis pipeline.

        This method provides high-performance batch retrieval by using
        Redis pipelining to minimize round-trip latency.

        Args:
            wallets: List of wallet addresses

        Returns:
            Dictionary mapping wallet addresses to profiles (or None if not cached)
        """
        if not wallets:
            return {}

        self.logger.info(
            "batch_get_start",
            wallet_count=len(wallets)
        )

        try:
            # Build pipeline
            async with self.redis.pipeline(transaction=False) as pipe:
                for wallet in wallets:
                    key = self._make_key(wallet)
                    await pipe.hgetall(key)

                # Execute all commands
                results = await pipe.execute()

            # Process results
            profiles = {}
            hits = 0
            misses = 0

            for wallet, profile_data in zip(wallets, results):
                if profile_data:
                    # Deserialize
                    profile = {
                        k.decode('utf-8'): self._deserialize_value(v.decode('utf-8'), k.decode('utf-8'))
                        for k, v in profile_data.items()
                    }
                    profiles[wallet] = profile
                    hits += 1
                else:
                    profiles[wallet] = None
                    misses += 1

            self.logger.info(
                "batch_get_complete",
                wallet_count=len(wallets),
                hits=hits,
                misses=misses,
                hit_rate=f"{(hits / len(wallets) * 100):.1f}%"
            )

            return profiles

        except Exception as e:
            self.logger.error(
                "batch_get_error",
                wallet_count=len(wallets),
                error=str(e)
            )
            # Return all None on error
            return {wallet: None for wallet in wallets}

    async def invalidate(self, wallet: str) -> bool:
        """
        Invalidate (delete) a wallet profile from cache.

        Args:
            wallet: Wallet address

        Returns:
            True if deleted, False otherwise
        """
        key = self._make_key(wallet)

        try:
            deleted = await self.redis.delete(key)

            self.logger.info(
                "cache_invalidate",
                wallet=wallet,
                deleted=bool(deleted)
            )

            return bool(deleted)

        except Exception as e:
            self.logger.error(
                "cache_invalidate_error",
                wallet=wallet,
                error=str(e)
            )
            return False

    async def batch_invalidate(self, wallets: List[str]) -> int:
        """
        Invalidate multiple wallet profiles using Redis pipeline.

        Args:
            wallets: List of wallet addresses

        Returns:
            Number of profiles deleted
        """
        if not wallets:
            return 0

        try:
            keys = [self._make_key(wallet) for wallet in wallets]
            deleted = await self.redis.delete(*keys)

            self.logger.info(
                "batch_invalidate",
                wallet_count=len(wallets),
                deleted=deleted
            )

            return deleted

        except Exception as e:
            self.logger.error(
                "batch_invalidate_error",
                wallet_count=len(wallets),
                error=str(e)
            )
            return 0

    async def warm_cache(
        self,
        profiles: Dict[str, Dict[str, Any]],
        ttl: Optional[int] = None
    ) -> int:
        """
        Warm cache with multiple profiles using Redis pipeline.

        This method is useful for pre-loading high-priority wallets
        during system startup or after cache invalidation.

        Args:
            profiles: Dictionary mapping wallet addresses to profiles
            ttl: Optional custom TTL (default: use instance TTL)

        Returns:
            Number of profiles successfully cached
        """
        if not profiles:
            return 0

        ttl = ttl or self.ttl

        self.logger.info(
            "warm_cache_start",
            profile_count=len(profiles),
            ttl=ttl
        )

        try:
            success_count = 0

            # Use pipeline for batch operations
            async with self.redis.pipeline(transaction=False) as pipe:
                for wallet, profile in profiles.items():
                    key = self._make_key(wallet)

                    # Serialize profile
                    serialized_profile = {
                        k: self._serialize_value(v)
                        for k, v in profile.items()
                    }

                    # Add to pipeline
                    await pipe.hset(key, mapping=serialized_profile)
                    await pipe.expire(key, ttl)

                # Execute all commands
                results = await pipe.execute()

                # Count successes (every 2 results = 1 profile)
                success_count = sum(1 for i in range(0, len(results), 2) if results[i])

            self.logger.info(
                "warm_cache_complete",
                profile_count=len(profiles),
                success_count=success_count
            )

            return success_count

        except Exception as e:
            self.logger.error(
                "warm_cache_error",
                profile_count=len(profiles),
                error=str(e)
            )
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        try:
            # Count keys matching pattern
            pattern = f"{CACHE_KEY_PREFIX}:*"
            cursor = 0
            key_count = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor=cursor,
                    match=pattern,
                    count=100
                )
                key_count += len(keys)

                if cursor == 0:
                    break

            # Get Redis info
            info = await self.redis.info('memory')

            stats = {
                'cached_profiles': key_count,
                'ttl': self.ttl,
                'key_prefix': CACHE_KEY_PREFIX,
                'memory_used_mb': info.get('used_memory', 0) / (1024 * 1024),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            self.logger.info("cache_stats", **stats)

            return stats

        except Exception as e:
            self.logger.error("cache_stats_error", error=str(e))
            return {'error': str(e)}


if __name__ == "__main__":
    import asyncio

    async def test_profile_cache():
        """Test profile cache functionality."""

        # Initialize Redis client
        redis_client = await redis.from_url(
            "redis://localhost:6379",
            encoding="utf-8",
            decode_responses=False
        )

        # Initialize cache
        cache = ProfileCache(redis_client, ttl=300)  # 5 minutes for testing

        print("\n=== Test 1: Set and Get ===")
        test_profile = {
            'wallet': 'TestWallet123',
            'win_rate': 0.85,
            'graduation_rate': 0.75,
            'total_trades': 50,
            'total_profit': 250.5,
            'risk_score': 0.92,
            'is_king_maker': True,
            'timestamp': datetime.now(timezone.utc)
        }

        await cache.set('TestWallet123', test_profile)
        retrieved = await cache.get('TestWallet123')
        print(f"Set and retrieved profile: {retrieved is not None}")
        print(f"Win rate: {retrieved.get('win_rate')}")
        print(f"Is King Maker: {retrieved.get('is_king_maker')}")

        print("\n=== Test 2: Batch Get ===")
        wallets = ['TestWallet123', 'NonExistent1', 'NonExistent2']
        batch_results = await cache.batch_get(wallets)
        print(f"Batch results: {len(batch_results)} wallets")
        print(f"Hits: {sum(1 for v in batch_results.values() if v is not None)}")
        print(f"Misses: {sum(1 for v in batch_results.values() if v is None)}")

        print("\n=== Test 3: Cache Stats ===")
        stats = await cache.get_stats()
        print(f"Cached profiles: {stats.get('cached_profiles')}")
        print(f"TTL: {stats.get('ttl')} seconds")

        print("\n=== Test 4: Invalidate ===")
        await cache.invalidate('TestWallet123')
        retrieved_after = await cache.get('TestWallet123')
        print(f"Profile after invalidation: {retrieved_after}")

        # Cleanup
        await redis_client.close()

    # Run tests
    asyncio.run(test_profile_cache())
