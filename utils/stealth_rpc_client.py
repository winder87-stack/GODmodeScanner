"""Stealth RPC Client for GODMODESCANNER

Production-ready authenticated RPC rotation system with:
- Tiered endpoint management (primary authenticated, fallback free)
- Circuit breaker pattern for fault tolerance
- Adaptive rate limiting (5-40 RPS)
- User-Agent rotation for stealth
- Request deduplication with Bloom filter
- Automatic failover and recovery
"""

import os
import asyncio
import random
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set
from datetime import datetime, timezone
from enum import Enum
import httpx
import orjson
import structlog

logger = structlog.get_logger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

class EndpointTier(Enum):
    """RPC endpoint tiers."""
    PRIMARY = "primary"      # Authenticated (Helius, Alchemy, etc.)
    SECONDARY = "secondary"  # Secondary authenticated
    FALLBACK = "fallback"    # Free public endpoints

@dataclass
class EndpointConfig:
    """Configuration for a single RPC endpoint."""
    url: str
    tier: EndpointTier
    api_key: Optional[str] = None
    rate_limit: int = 25  # RPS
    weight: int = 1  # Load balancing weight

    # Runtime state
    healthy: bool = True
    consecutive_failures: int = 0
    last_failure: Optional[float] = None
    total_requests: int = 0
    successful_requests: int = 0
    total_latency_ms: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests

    @property
    def avg_latency_ms(self) -> float:
        if self.successful_requests == 0:
            return 0.0
        return self.total_latency_ms / self.successful_requests

@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0  # seconds
    half_open_requests: int = 3

# =============================================================================
# USER AGENTS FOR STEALTH
# =============================================================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
]

# =============================================================================
# BLOOM FILTER FOR DEDUPLICATION
# =============================================================================

class BloomFilter:
    """Simple Bloom filter for request deduplication."""

    def __init__(self, size: int = 100000, hash_count: int = 7):
        self.size = size
        self.hash_count = hash_count
        self.bit_array = [False] * size
        self.count = 0

    def _hashes(self, item: str) -> List[int]:
        """Generate hash values for an item."""
        hashes = []
        for i in range(self.hash_count):
            h = hashlib.md5(f"{item}{i}".encode()).hexdigest()
            hashes.append(int(h, 16) % self.size)
        return hashes

    def add(self, item: str) -> None:
        """Add item to filter."""
        for h in self._hashes(item):
            self.bit_array[h] = True
        self.count += 1

    def contains(self, item: str) -> bool:
        """Check if item might be in filter."""
        return all(self.bit_array[h] for h in self._hashes(item))

    def clear(self) -> None:
        """Clear the filter."""
        self.bit_array = [False] * self.size
        self.count = 0

# =============================================================================
# STEALTH RPC CLIENT
# =============================================================================

class StealthRPCClient:
    """Production-ready stealth RPC client with authenticated endpoint rotation."""

    def __init__(
        self,
        initial_rps: float = 5.0,
        max_rps: float = 40.0,
        min_rps: float = 1.0,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None
    ):
        self.initial_rps = initial_rps
        self.max_rps = max_rps
        self.min_rps = min_rps
        self.current_rps = initial_rps
        self.circuit_breaker = circuit_breaker_config or CircuitBreakerConfig()

        # Endpoint management
        self.endpoints: List[EndpointConfig] = []
        self.current_endpoint_idx = 0

        # Rate limiting
        self.last_request_time = 0.0
        self.consecutive_successes = 0

        # Deduplication
        self.bloom_filter = BloomFilter()
        self.recent_requests: Set[str] = set()

        # HTTP client
        self.client: Optional[httpx.AsyncClient] = None

        # Stats
        self.total_requests = 0
        self.successful_requests = 0
        self.deduplicated_requests = 0
        self.failovers = 0

        # Load endpoints from environment
        self._load_endpoints()

    def _load_endpoints(self) -> None:
        """Load RPC endpoints from environment variables."""
        # Primary tier - Authenticated endpoints
        primary_urls = os.getenv("SOLANA_RPC_PRIMARY", "").split(",")
        for url in primary_urls:
            url = url.strip()
            if url:
                self.endpoints.append(EndpointConfig(
                    url=url,
                    tier=EndpointTier.PRIMARY,
                    rate_limit=50  # Higher limit for authenticated
                ))

        # Secondary tier
        secondary_urls = os.getenv("SOLANA_RPC_SECONDARY", "").split(",")
        for url in secondary_urls:
            url = url.strip()
            if url:
                self.endpoints.append(EndpointConfig(
                    url=url,
                    tier=EndpointTier.SECONDARY,
                    rate_limit=30
                ))

        # Fallback tier - Free public endpoints
        fallback_urls = os.getenv(
            "SOLANA_RPC_FALLBACK",
            "https://api.mainnet-beta.solana.com,https://solana-mainnet.g.alchemy.com/v2/demo"
        ).split(",")
        for url in fallback_urls:
            url = url.strip()
            if url:
                self.endpoints.append(EndpointConfig(
                    url=url,
                    tier=EndpointTier.FALLBACK,
                    rate_limit=10  # Conservative for free
                ))

        if not self.endpoints:
            # Default fallback
            self.endpoints.append(EndpointConfig(
                url="https://api.mainnet-beta.solana.com",
                tier=EndpointTier.FALLBACK,
                rate_limit=10
            ))

        logger.info(f"Loaded {len(self.endpoints)} RPC endpoints", 
                   primary=sum(1 for e in self.endpoints if e.tier == EndpointTier.PRIMARY),
                   secondary=sum(1 for e in self.endpoints if e.tier == EndpointTier.SECONDARY),
                   fallback=sum(1 for e in self.endpoints if e.tier == EndpointTier.FALLBACK))

    async def __aenter__(self):
        """Async context manager entry."""
        self.client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.client:
            await self.client.aclose()

    def _get_healthy_endpoint(self) -> Optional[EndpointConfig]:
        """Get next healthy endpoint using weighted selection."""
        # Try endpoints in tier order
        for tier in [EndpointTier.PRIMARY, EndpointTier.SECONDARY, EndpointTier.FALLBACK]:
            tier_endpoints = [e for e in self.endpoints if e.tier == tier and e.healthy]
            if tier_endpoints:
                # Weighted random selection
                total_weight = sum(e.weight for e in tier_endpoints)
                r = random.uniform(0, total_weight)
                cumulative = 0
                for endpoint in tier_endpoints:
                    cumulative += endpoint.weight
                    if r <= cumulative:
                        return endpoint

        # Try to recover unhealthy endpoints
        now = time.time()
        for endpoint in self.endpoints:
            if not endpoint.healthy and endpoint.last_failure:
                if now - endpoint.last_failure > self.circuit_breaker.recovery_timeout:
                    endpoint.healthy = True
                    endpoint.consecutive_failures = 0
                    logger.info(f"Endpoint recovered: {endpoint.url[:50]}...")
                    return endpoint

        return None

    def _mark_endpoint_failure(self, endpoint: EndpointConfig) -> None:
        """Mark endpoint as failed."""
        endpoint.consecutive_failures += 1
        endpoint.last_failure = time.time()

        if endpoint.consecutive_failures >= self.circuit_breaker.failure_threshold:
            endpoint.healthy = False
            self.failovers += 1
            logger.warning(f"Endpoint circuit breaker opened: {endpoint.url[:50]}...",
                          failures=endpoint.consecutive_failures)

    def _mark_endpoint_success(self, endpoint: EndpointConfig, latency_ms: float) -> None:
        """Mark endpoint as successful."""
        endpoint.consecutive_failures = 0
        endpoint.total_requests += 1
        endpoint.successful_requests += 1
        endpoint.total_latency_ms += latency_ms

    async def _rate_limit(self) -> None:
        """Apply adaptive rate limiting."""
        min_interval = 1.0 / self.current_rps
        elapsed = time.time() - self.last_request_time

        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)

        self.last_request_time = time.time()

    def _adapt_rate(self, success: bool) -> None:
        """Adapt rate based on success/failure."""
        if success:
            self.consecutive_successes += 1
            # Increase rate after 50 consecutive successes
            if self.consecutive_successes >= 50:
                self.current_rps = min(self.current_rps * 1.1, self.max_rps)
                self.consecutive_successes = 0
        else:
            # Immediately reduce rate on failure
            self.current_rps = max(self.current_rps * 0.5, self.min_rps)
            self.consecutive_successes = 0

    def _get_request_hash(self, method: str, params: Any) -> str:
        """Generate hash for request deduplication."""
        data = orjson.dumps({"method": method, "params": params})
        return hashlib.sha256(data).hexdigest()[:16]

    async def request(
        self,
        method: str,
        params: Any = None,
        deduplicate: bool = True
    ) -> Dict[str, Any]:
        """Make RPC request with stealth features."""
        if not self.client:
            raise RuntimeError("Client not initialized. Use async context manager.")

        # Deduplication check
        if deduplicate:
            request_hash = self._get_request_hash(method, params)
            if self.bloom_filter.contains(request_hash) and request_hash in self.recent_requests:
                self.deduplicated_requests += 1
                logger.debug(f"Deduplicated request: {method}")
                return {"deduplicated": True, "method": method}
            self.bloom_filter.add(request_hash)
            self.recent_requests.add(request_hash)
            # Limit recent requests set size
            if len(self.recent_requests) > 10000:
                self.recent_requests = set(list(self.recent_requests)[-5000:])

        # Rate limiting
        await self._rate_limit()

        # Get healthy endpoint
        endpoint = self._get_healthy_endpoint()
        if not endpoint:
            raise RuntimeError("No healthy RPC endpoints available")

        # Build request
        payload = {
            "jsonrpc": "2.0",
            "id": self.total_requests + 1,
            "method": method,
            "params": params or []
        }

        headers = {
            "Content-Type": "application/json",
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache"
        }

        self.total_requests += 1
        start_time = time.perf_counter()

        try:
            response = await self.client.post(
                endpoint.url,
                json=payload,
                headers=headers
            )

            latency_ms = (time.perf_counter() - start_time) * 1000

            if response.status_code == 429:
                # Rate limited
                self._mark_endpoint_failure(endpoint)
                self._adapt_rate(False)
                logger.warning(f"Rate limited by {endpoint.url[:50]}...")

                # Retry with different endpoint
                return await self.request(method, params, deduplicate=False)

            if response.status_code == 403:
                # Forbidden - endpoint may be blocking us
                self._mark_endpoint_failure(endpoint)
                self._adapt_rate(False)
                logger.warning(f"Forbidden by {endpoint.url[:50]}...")

                return await self.request(method, params, deduplicate=False)

            response.raise_for_status()

            result = response.json()

            if "error" in result:
                self._mark_endpoint_failure(endpoint)
                self._adapt_rate(False)
                return result

            # Success
            self._mark_endpoint_success(endpoint, latency_ms)
            self._adapt_rate(True)
            self.successful_requests += 1

            return result

        except httpx.TimeoutException:
            self._mark_endpoint_failure(endpoint)
            self._adapt_rate(False)
            logger.warning(f"Timeout from {endpoint.url[:50]}...")
            return await self.request(method, params, deduplicate=False)

        except Exception as e:
            self._mark_endpoint_failure(endpoint)
            self._adapt_rate(False)
            logger.error(f"RPC error: {e}")
            raise

    # ==========================================================================
    # CONVENIENCE METHODS
    # ==========================================================================

    async def get_slot(self) -> int:
        """Get current slot."""
        result = await self.request("getSlot")
        return result.get("result", 0)

    async def get_block_height(self) -> int:
        """Get current block height."""
        result = await self.request("getBlockHeight")
        return result.get("result", 0)

    async def get_balance(self, address: str) -> int:
        """Get account balance in lamports."""
        result = await self.request("getBalance", [address])
        return result.get("result", {}).get("value", 0)

    async def get_account_info(self, address: str) -> Optional[Dict]:
        """Get account info."""
        result = await self.request("getAccountInfo", [
            address,
            {"encoding": "jsonParsed"}
        ])
        return result.get("result", {}).get("value")

    async def get_transaction(self, signature: str) -> Optional[Dict]:
        """Get transaction details."""
        result = await self.request("getTransaction", [
            signature,
            {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
        ])
        return result.get("result")

    async def get_signatures_for_address(
        self,
        address: str,
        limit: int = 100,
        before: Optional[str] = None
    ) -> List[Dict]:
        """Get transaction signatures for address."""
        params = [address, {"limit": limit}]
        if before:
            params[1]["before"] = before
        result = await self.request("getSignaturesForAddress", params)
        return result.get("result", [])

    async def get_program_accounts(
        self,
        program_id: str,
        filters: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """Get program accounts."""
        params = [program_id, {"encoding": "jsonParsed"}]
        if filters:
            params[1]["filters"] = filters
        result = await self.request("getProgramAccounts", params)
        return result.get("result", [])

    # ==========================================================================
    # STATS & MONITORING
    # ==========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "success_rate": self.successful_requests / max(1, self.total_requests),
            "deduplicated_requests": self.deduplicated_requests,
            "failovers": self.failovers,
            "current_rps": self.current_rps,
            "endpoints": [
                {
                    "url": e.url[:50] + "..." if len(e.url) > 50 else e.url,
                    "tier": e.tier.value,
                    "healthy": e.healthy,
                    "success_rate": e.success_rate,
                    "avg_latency_ms": e.avg_latency_ms,
                    "total_requests": e.total_requests
                }
                for e in self.endpoints
            ]
        }

    def reset_stats(self) -> None:
        """Reset statistics."""
        self.total_requests = 0
        self.successful_requests = 0
        self.deduplicated_requests = 0
        self.failovers = 0
        self.bloom_filter.clear()
        self.recent_requests.clear()
        for endpoint in self.endpoints:
            endpoint.total_requests = 0
            endpoint.successful_requests = 0
            endpoint.total_latency_ms = 0.0


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_client_instance: Optional[StealthRPCClient] = None

def get_stealth_client() -> StealthRPCClient:
    """Get singleton stealth RPC client."""
    global _client_instance
    if _client_instance is None:
        _client_instance = StealthRPCClient()
    return _client_instance


# =============================================================================
# TESTING
# =============================================================================

async def test_client():
    """Test the stealth RPC client."""
    async with StealthRPCClient() as client:
        print("\n🔱 Testing Stealth RPC Client...")

        # Test basic requests
        try:
            slot = await client.get_slot()
            print(f"✅ Current slot: {slot:,}")

            height = await client.get_block_height()
            print(f"✅ Block height: {height:,}")

            # Test deduplication
            await client.get_slot()
            await client.get_slot()

            stats = client.get_stats()
            print(f"\n📊 Stats:")
            print(f"   Total requests: {stats['total_requests']}")
            print(f"   Success rate: {stats['success_rate']:.1%}")
            print(f"   Deduplicated: {stats['deduplicated_requests']}")
            print(f"   Current RPS: {stats['current_rps']:.1f}")

        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_client())
