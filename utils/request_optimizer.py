
"""
Request Optimizer - Intelligent Request Routing and Optimization
================================================================

Advanced request optimization system for maximizing RPC throughput
while minimizing latency and errors.

Features:
- Priority-based request queuing
- Request deduplication with caching
- Batch request optimization
- Predictive pre-fetching
- Intelligent endpoint routing
- Request coalescing
"""

import asyncio
import time
import hashlib
from typing import Dict, List, Optional, Any, Callable, Tuple, Set
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import heapq
import structlog

try:
    import orjson
    json_dumps = lambda obj: orjson.dumps(obj).decode()
    json_loads = orjson.loads
except ImportError:
    import json
    json_dumps = json.dumps
    json_loads = json.loads

logger = structlog.get_logger(__name__)


class RequestPriority(Enum):
    """Request priority levels."""
    CRITICAL = 0    # Immediate execution, bypass queue
    HIGH = 1        # Next available slot
    NORMAL = 2      # Standard queue
    LOW = 3         # Background processing
    BULK = 4        # Batch when idle


class RequestType(Enum):
    """Types of RPC requests for optimization."""
    READ = "read"           # Read-only, cacheable
    WRITE = "write"         # State-changing
    SUBSCRIBE = "subscribe" # WebSocket subscription
    BATCH = "batch"         # Batch request


@dataclass(order=True)
class PrioritizedRequest:
    """Request with priority for queue ordering."""
    priority: int
    timestamp: float
    request: Any = field(compare=False)
    future: asyncio.Future = field(compare=False, default=None)


@dataclass
class CachedResult:
    """Cached request result."""
    result: Any
    timestamp: float
    ttl_seconds: float
    hit_count: int = 0

    def is_valid(self) -> bool:
        """Check if cache entry is still valid."""
        return time.time() - self.timestamp < self.ttl_seconds

    def get(self) -> Any:
        """Get cached result and increment hit count."""
        self.hit_count += 1
        return self.result


@dataclass
class RequestMetrics:
    """Metrics for request optimization."""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    deduplicated: int = 0
    batched: int = 0
    prefetched: int = 0
    coalesced: int = 0

    queue_depth: int = 0
    avg_queue_time_ms: float = 0.0

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0


class RequestCache:
    """
    LRU cache for request results with TTL support.
    """

    def __init__(self, max_size: int = 10000, default_ttl: float = 5.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: Dict[str, CachedResult] = {}
        self.access_order: List[str] = []
        self._lock = asyncio.Lock()

    def _make_key(self, method: str, params: List[Any]) -> str:
        """Generate cache key from request."""
        content = json_dumps({"method": method, "params": params})
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def get(self, method: str, params: List[Any]) -> Optional[Any]:
        """Get cached result if available."""
        key = self._make_key(method, params)

        async with self._lock:
            if key in self.cache:
                entry = self.cache[key]
                if entry.is_valid():
                    # Move to end of access order
                    if key in self.access_order:
                        self.access_order.remove(key)
                    self.access_order.append(key)
                    return entry.get()
                else:
                    # Remove expired entry
                    del self.cache[key]
                    if key in self.access_order:
                        self.access_order.remove(key)

        return None

    async def set(
        self,
        method: str,
        params: List[Any],
        result: Any,
        ttl: Optional[float] = None
    ):
        """Cache a result."""
        key = self._make_key(method, params)
        ttl = ttl or self.default_ttl

        async with self._lock:
            # Evict if at capacity
            while len(self.cache) >= self.max_size and self.access_order:
                oldest_key = self.access_order.pop(0)
                if oldest_key in self.cache:
                    del self.cache[oldest_key]

            self.cache[key] = CachedResult(
                result=result,
                timestamp=time.time(),
                ttl_seconds=ttl,
            )
            self.access_order.append(key)

    async def invalidate(self, method: str, params: List[Any]):
        """Invalidate a cache entry."""
        key = self._make_key(method, params)

        async with self._lock:
            if key in self.cache:
                del self.cache[key]
            if key in self.access_order:
                self.access_order.remove(key)

    async def clear(self):
        """Clear all cache entries."""
        async with self._lock:
            self.cache.clear()
            self.access_order.clear()

    def get_stats(self) -> Dict:
        """Get cache statistics."""
        valid_entries = sum(1 for e in self.cache.values() if e.is_valid())
        total_hits = sum(e.hit_count for e in self.cache.values())

        return {
            "size": len(self.cache),
            "valid_entries": valid_entries,
            "total_hits": total_hits,
            "max_size": self.max_size,
        }


class RequestDeduplicator:
    """
    Deduplicates in-flight requests to prevent redundant RPC calls.
    """

    def __init__(self, window_seconds: float = 1.0):
        self.window_seconds = window_seconds
        self.in_flight: Dict[str, Tuple[float, asyncio.Future]] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, method: str, params: List[Any]) -> str:
        """Generate dedup key from request."""
        content = json_dumps({"method": method, "params": params})
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def check_or_register(
        self,
        method: str,
        params: List[Any]
    ) -> Tuple[bool, Optional[asyncio.Future]]:
        """
        Check if request is in-flight or register it.

        Returns:
            Tuple of (is_duplicate, future_to_await)
        """
        key = self._make_key(method, params)
        now = time.time()

        async with self._lock:
            # Clean expired entries
            expired = [
                k for k, (ts, _) in self.in_flight.items()
                if now - ts > self.window_seconds
            ]
            for k in expired:
                del self.in_flight[k]

            # Check if in-flight
            if key in self.in_flight:
                _, future = self.in_flight[key]
                return True, future

            # Register new request
            future = asyncio.Future()
            self.in_flight[key] = (now, future)
            return False, future

    async def complete(self, method: str, params: List[Any], result: Any):
        """Mark request as complete and notify waiters."""
        key = self._make_key(method, params)

        async with self._lock:
            if key in self.in_flight:
                _, future = self.in_flight[key]
                if not future.done():
                    future.set_result(result)
                del self.in_flight[key]

    async def fail(self, method: str, params: List[Any], error: Exception):
        """Mark request as failed and notify waiters."""
        key = self._make_key(method, params)

        async with self._lock:
            if key in self.in_flight:
                _, future = self.in_flight[key]
                if not future.done():
                    future.set_exception(error)
                del self.in_flight[key]


class BatchOptimizer:
    """
    Optimizes requests by batching compatible ones together.
    """

    # Methods that can be batched
    BATCHABLE_METHODS = {
        "getAccountInfo",
        "getBalance",
        "getTokenAccountBalance",
        "getMultipleAccounts",
        "getSignaturesForAddress",
        "getTransaction",
        "getSlot",
        "getBlockHeight",
    }

    def __init__(
        self,
        max_batch_size: int = 10,
        batch_timeout_ms: float = 50.0,
    ):
        self.max_batch_size = max_batch_size
        self.batch_timeout_ms = batch_timeout_ms

        self.pending_batches: Dict[str, List[Tuple[List[Any], asyncio.Future]]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._batch_tasks: Dict[str, asyncio.Task] = {}

    def can_batch(self, method: str) -> bool:
        """Check if method can be batched."""
        return method in self.BATCHABLE_METHODS

    async def add_to_batch(
        self,
        method: str,
        params: List[Any],
    ) -> asyncio.Future:
        """
        Add request to batch queue.

        Returns:
            Future that will contain the result
        """
        future = asyncio.Future()

        async with self._lock:
            self.pending_batches[method].append((params, future))

            # Start batch timer if first request
            if len(self.pending_batches[method]) == 1:
                self._batch_tasks[method] = asyncio.create_task(
                    self._batch_timer(method)
                )

            # Flush if batch is full
            if len(self.pending_batches[method]) >= self.max_batch_size:
                if method in self._batch_tasks:
                    self._batch_tasks[method].cancel()
                await self._flush_batch(method)

        return future

    async def _batch_timer(self, method: str):
        """Timer to flush batch after timeout."""
        try:
            await asyncio.sleep(self.batch_timeout_ms / 1000)
            async with self._lock:
                await self._flush_batch(method)
        except asyncio.CancelledError:
            pass

    async def _flush_batch(self, method: str):
        """Flush pending batch for method."""
        if method not in self.pending_batches or not self.pending_batches[method]:
            return

        batch = self.pending_batches[method]
        self.pending_batches[method] = []

        # Return batch for execution
        # The actual execution is handled by the caller
        return batch

    async def get_pending_batch(self, method: str) -> Optional[List[Tuple[List[Any], asyncio.Future]]]:
        """Get and clear pending batch for method."""
        async with self._lock:
            if method in self.pending_batches and self.pending_batches[method]:
                batch = self.pending_batches[method]
                self.pending_batches[method] = []
                return batch
        return None

    def get_stats(self) -> Dict:
        """Get batch optimizer statistics."""
        return {
            "pending_methods": list(self.pending_batches.keys()),
            "pending_counts": {
                m: len(b) for m, b in self.pending_batches.items()
            },
        }


class PrefetchEngine:
    """
    Predictive pre-fetching based on access patterns.
    """

    def __init__(self, max_prefetch_queue: int = 100):
        self.max_prefetch_queue = max_prefetch_queue

        # Access pattern tracking
        self.access_patterns: Dict[str, List[str]] = defaultdict(list)
        self.pattern_counts: Dict[Tuple[str, str], int] = defaultdict(int)

        # Prefetch queue
        self.prefetch_queue: asyncio.Queue = asyncio.Queue(maxsize=max_prefetch_queue)

        # Statistics
        self.prefetch_hits: int = 0
        self.prefetch_misses: int = 0

    def record_access(self, method: str, params: List[Any]):
        """Record an access for pattern learning."""
        key = f"{method}:{json_dumps(params)[:50]}"

        # Track sequential patterns
        for prev_key in self.access_patterns.get("_last", [])[-5:]:
            self.pattern_counts[(prev_key, key)] += 1

        # Update last accessed
        if "_last" not in self.access_patterns:
            self.access_patterns["_last"] = []
        self.access_patterns["_last"].append(key)
        if len(self.access_patterns["_last"]) > 100:
            self.access_patterns["_last"] = self.access_patterns["_last"][-50:]

    def predict_next(self, method: str, params: List[Any]) -> List[Tuple[str, List[Any]]]:
        """
        Predict likely next requests based on patterns.

        Returns:
            List of (method, params) tuples to prefetch
        """
        key = f"{method}:{json_dumps(params)[:50]}"
        predictions = []

        # Find patterns starting with this key
        for (prev, next_key), count in self.pattern_counts.items():
            if prev == key and count >= 3:  # Minimum pattern threshold
                try:
                    parts = next_key.split(":", 1)
                    if len(parts) == 2:
                        next_method = parts[0]
                        next_params = json_loads(parts[1]) if parts[1] else []
                        predictions.append((next_method, next_params, count))
                except:
                    pass

        # Sort by frequency and return top predictions
        predictions.sort(key=lambda x: x[2], reverse=True)
        return [(m, p) for m, p, _ in predictions[:3]]

    async def queue_prefetch(self, method: str, params: List[Any]):
        """Queue a prefetch request."""
        try:
            self.prefetch_queue.put_nowait((method, params))
        except asyncio.QueueFull:
            pass  # Drop if queue is full

    async def get_prefetch(self) -> Optional[Tuple[str, List[Any]]]:
        """Get next prefetch request."""
        try:
            return self.prefetch_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def get_stats(self) -> Dict:
        """Get prefetch statistics."""
        return {
            "pattern_count": len(self.pattern_counts),
            "prefetch_queue_size": self.prefetch_queue.qsize(),
            "prefetch_hits": self.prefetch_hits,
            "prefetch_misses": self.prefetch_misses,
        }


class RequestCoalescer:
    """
    Coalesces similar requests to reduce RPC calls.

    For example, multiple getAccountInfo calls for different accounts
    can be coalesced into a single getMultipleAccounts call.
    """

    # Coalescing rules: single method -> batch method
    COALESCE_RULES = {
        "getAccountInfo": "getMultipleAccounts",
        "getBalance": None,  # Can batch but no multi-method
    }

    def __init__(self, coalesce_window_ms: float = 10.0, max_coalesce: int = 100):
        self.coalesce_window_ms = coalesce_window_ms
        self.max_coalesce = max_coalesce

        self.pending: Dict[str, List[Tuple[List[Any], asyncio.Future, float]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def can_coalesce(self, method: str) -> bool:
        """Check if method can be coalesced."""
        return method in self.COALESCE_RULES

    async def add(
        self,
        method: str,
        params: List[Any],
    ) -> Tuple[bool, asyncio.Future]:
        """
        Add request for potential coalescing.

        Returns:
            Tuple of (was_coalesced, future)
        """
        future = asyncio.Future()
        now = time.time()

        async with self._lock:
            self.pending[method].append((params, future, now))

            # Check if we should flush
            if len(self.pending[method]) >= self.max_coalesce:
                return True, future

        return True, future

    async def get_coalesced(
        self,
        method: str
    ) -> Optional[Tuple[str, List[Any], List[asyncio.Future]]]:
        """
        Get coalesced request if ready.

        Returns:
            Tuple of (coalesced_method, combined_params, futures) or None
        """
        async with self._lock:
            if method not in self.pending or not self.pending[method]:
                return None

            now = time.time()

            # Check if window has elapsed for oldest request
            oldest_time = self.pending[method][0][2]
            if (now - oldest_time) * 1000 < self.coalesce_window_ms:
                return None

            # Get all pending requests
            requests = self.pending[method]
            self.pending[method] = []

            # Coalesce based on method
            if method == "getAccountInfo":
                # Combine into getMultipleAccounts
                accounts = [r[0][0] for r in requests]  # First param is account
                futures = [r[1] for r in requests]

                # Get encoding from first request
                encoding = requests[0][0][1] if len(requests[0][0]) > 1 else {"encoding": "base64"}

                return "getMultipleAccounts", [accounts, encoding], futures

            # Default: return as batch
            return method, [r[0] for r in requests], [r[1] for r in requests]


class RequestOptimizer:
    """
    Main request optimization engine combining all optimization strategies.

    Features:
    - Priority-based queuing
    - Result caching
    - Request deduplication
    - Batch optimization
    - Predictive pre-fetching
    - Request coalescing
    """

    def __init__(
        self,
        cache_size: int = 10000,
        cache_ttl: float = 5.0,
        enable_caching: bool = True,
        enable_deduplication: bool = True,
        enable_batching: bool = True,
        enable_prefetching: bool = True,
        enable_coalescing: bool = True,
        max_batch_size: int = 10,
        batch_timeout_ms: float = 50.0,
    ):
        self.enable_caching = enable_caching
        self.enable_deduplication = enable_deduplication
        self.enable_batching = enable_batching
        self.enable_prefetching = enable_prefetching
        self.enable_coalescing = enable_coalescing

        # Components
        self.cache = RequestCache(max_size=cache_size, default_ttl=cache_ttl)
        self.deduplicator = RequestDeduplicator()
        self.batch_optimizer = BatchOptimizer(
            max_batch_size=max_batch_size,
            batch_timeout_ms=batch_timeout_ms,
        )
        self.prefetch_engine = PrefetchEngine()
        self.coalescer = RequestCoalescer()

        # Priority queue
        self.priority_queue: List[PrioritizedRequest] = []
        self._queue_lock = asyncio.Lock()

        # Metrics
        self.metrics = RequestMetrics()

        # Executor callback
        self._executor: Optional[Callable] = None

        logger.info(
            "RequestOptimizer initialized",
            caching=enable_caching,
            deduplication=enable_deduplication,
            batching=enable_batching,
            prefetching=enable_prefetching,
            coalescing=enable_coalescing,
        )

    def set_executor(self, executor: Callable):
        """Set the request executor callback."""
        self._executor = executor

    async def optimize_request(
        self,
        method: str,
        params: List[Any],
        priority: RequestPriority = RequestPriority.NORMAL,
        request_type: RequestType = RequestType.READ,
        cache_ttl: Optional[float] = None,
        skip_cache: bool = False,
    ) -> Any:
        """
        Optimize and execute a request.

        Args:
            method: RPC method name
            params: Method parameters
            priority: Request priority
            request_type: Type of request
            cache_ttl: Custom cache TTL
            skip_cache: Skip cache lookup

        Returns:
            Request result
        """
        self.metrics.total_requests += 1
        params = params or []

        # 1. Check cache (for read requests)
        if self.enable_caching and request_type == RequestType.READ and not skip_cache:
            cached = await self.cache.get(method, params)
            if cached is not None:
                self.metrics.cache_hits += 1
                return cached
            self.metrics.cache_misses += 1

        # 2. Check deduplication
        if self.enable_deduplication:
            is_dup, future = await self.deduplicator.check_or_register(method, params)
            if is_dup:
                self.metrics.deduplicated += 1
                return await future

        # 3. Record access pattern for prefetching
        if self.enable_prefetching:
            self.prefetch_engine.record_access(method, params)

            # Queue predicted prefetches
            predictions = self.prefetch_engine.predict_next(method, params)
            for pred_method, pred_params in predictions:
                await self.prefetch_engine.queue_prefetch(pred_method, pred_params)

        # 4. Execute request
        try:
            result = await self._execute(method, params, priority)

            # Cache result
            if self.enable_caching and request_type == RequestType.READ:
                await self.cache.set(method, params, result, cache_ttl)

            # Complete deduplication
            if self.enable_deduplication:
                await self.deduplicator.complete(method, params, result)

            return result

        except Exception as e:
            if self.enable_deduplication:
                await self.deduplicator.fail(method, params, e)
            raise

    async def _execute(
        self,
        method: str,
        params: List[Any],
        priority: RequestPriority,
    ) -> Any:
        """Execute request through configured executor."""
        if self._executor is None:
            raise RuntimeError("No executor configured")

        # Check if can batch
        if self.enable_batching and self.batch_optimizer.can_batch(method):
            if priority not in [RequestPriority.CRITICAL, RequestPriority.HIGH]:
                future = await self.batch_optimizer.add_to_batch(method, params)
                self.metrics.batched += 1
                return await future

        # Direct execution
        return await self._executor(method, params)

    async def queue_request(
        self,
        method: str,
        params: List[Any],
        priority: RequestPriority = RequestPriority.NORMAL,
    ) -> asyncio.Future:
        """
        Queue a request for later execution.

        Returns:
            Future that will contain the result
        """
        future = asyncio.Future()
        request = PrioritizedRequest(
            priority=priority.value,
            timestamp=time.time(),
            request={"method": method, "params": params},
            future=future,
        )

        async with self._queue_lock:
            heapq.heappush(self.priority_queue, request)
            self.metrics.queue_depth = len(self.priority_queue)

        return future

    async def process_queue(self, max_requests: int = 10) -> int:
        """
        Process queued requests.

        Args:
            max_requests: Maximum requests to process

        Returns:
            Number of requests processed
        """
        processed = 0

        async with self._queue_lock:
            while self.priority_queue and processed < max_requests:
                request = heapq.heappop(self.priority_queue)

                try:
                    result = await self.optimize_request(
                        request.request["method"],
                        request.request["params"],
                    )
                    if not request.future.done():
                        request.future.set_result(result)
                except Exception as e:
                    if not request.future.done():
                        request.future.set_exception(e)

                processed += 1

            self.metrics.queue_depth = len(self.priority_queue)

        return processed

    async def process_prefetch(self) -> int:
        """Process prefetch queue."""
        processed = 0

        while True:
            prefetch = await self.prefetch_engine.get_prefetch()
            if prefetch is None:
                break

            method, params = prefetch

            # Check if already cached
            if self.enable_caching:
                cached = await self.cache.get(method, params)
                if cached is not None:
                    self.prefetch_engine.prefetch_hits += 1
                    continue

            # Execute prefetch
            try:
                result = await self._execute(method, params, RequestPriority.LOW)
                if self.enable_caching:
                    await self.cache.set(method, params, result)
                self.metrics.prefetched += 1
                processed += 1
            except:
                self.prefetch_engine.prefetch_misses += 1

        return processed

    def get_statistics(self) -> Dict:
        """Get optimizer statistics."""
        return {
            "metrics": {
                "total_requests": self.metrics.total_requests,
                "cache_hits": self.metrics.cache_hits,
                "cache_misses": self.metrics.cache_misses,
                "cache_hit_rate": f"{self.metrics.cache_hit_rate*100:.1f}%",
                "deduplicated": self.metrics.deduplicated,
                "batched": self.metrics.batched,
                "prefetched": self.metrics.prefetched,
                "queue_depth": self.metrics.queue_depth,
            },
            "cache": self.cache.get_stats(),
            "batch": self.batch_optimizer.get_stats(),
            "prefetch": self.prefetch_engine.get_stats(),
        }

    async def clear_cache(self):
        """Clear the request cache."""
        await self.cache.clear()
        logger.info("Request cache cleared")
