#!/usr/bin/env python3
"""
Async Write-Back Buffer for ETERNAL MIND Memory System
======================================================
Batches FAISS writes to reduce I/O overhead and achieve
10,000+ writes per second throughput.

Author: GODMODESCANNER Async Specialist
Target: 10,000+ writes/sec, <100ms flush latency
"""

import asyncio
import logging
import time
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque
import threading

import numpy as np
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class WriteItem:
    """Single write operation in the buffer."""
    vector_id: str
    embedding: np.ndarray
    metadata: Dict
    timestamp: float = field(default_factory=time.time)
    priority: int = 0  # Higher = more urgent


@dataclass
class WriteBackMetrics:
    """Performance metrics for write-back buffer."""
    total_writes_queued: int = 0
    total_writes_flushed: int = 0
    total_batches_flushed: int = 0
    avg_batch_size: float = 0.0
    avg_flush_latency_ms: float = 0.0
    max_flush_latency_ms: float = 0.0
    current_queue_size: int = 0
    writes_per_second: float = 0.0
    last_flush_time: Optional[float] = None


class AsyncWriteBackBuffer:
    """
    Async Write-Back Buffer for batched FAISS writes.

    Replaces synchronous FAISS writes with buffered async writes:
    - Batches writes to reduce I/O overhead
    - Background flush task for periodic persistence
    - Priority queue for urgent writes
    - Backpressure handling when buffer is full

    REPLACES: Synchronous FAISS writes in memory storage
    INTEGRATES WITH: ETERNAL MIND persistence loop, ShardedFAISSIndex
    """

    def __init__(self,
                 faiss_index,
                 batch_size: int = 1000,
                 flush_interval_ms: int = 100,
                 max_queue_size: int = 100000,
                 enable_priority: bool = True,
                 on_flush_callback: Optional[Callable] = None):
        """
        Initialize async write-back buffer.

        Args:
            faiss_index: ShardedFAISSIndex instance to write to
            batch_size: Maximum items per flush batch
            flush_interval_ms: Milliseconds between auto-flushes
            max_queue_size: Maximum queue size before backpressure
            enable_priority: Whether to use priority queue
            on_flush_callback: Optional callback after each flush
        """
        self.faiss_index = faiss_index
        self.batch_size = batch_size
        self.flush_interval = flush_interval_ms / 1000.0
        self.max_queue_size = max_queue_size
        self.enable_priority = enable_priority
        self.on_flush_callback = on_flush_callback

        # Write queue (deque for O(1) append/popleft)
        self.write_queue: deque = deque(maxlen=max_queue_size)
        self.priority_queue: List[WriteItem] = []  # Heap for priority items

        # Synchronization
        self.lock = asyncio.Lock()
        self.flush_event = asyncio.Event()
        self.shutdown_event = asyncio.Event()

        # Background task
        self.flush_task: Optional[asyncio.Task] = None
        self.is_running = False

        # Metrics
        self.metrics = WriteBackMetrics()
        self.flush_latencies: List[float] = []
        self.max_latency_samples = 100
        self.writes_in_last_second: deque = deque()

        logger.info("AsyncWriteBackBuffer initialized",
                   batch_size=batch_size,
                   flush_interval_ms=flush_interval_ms,
                   max_queue_size=max_queue_size)

    async def start(self):
        """
        Start background flush task.

        Must be called before enqueueing writes.
        """
        if self.is_running:
            logger.warning("Write-back buffer already running")
            return

        self.is_running = True
        self.shutdown_event.clear()
        self.flush_task = asyncio.create_task(self._background_flush_loop())
        logger.info("Write-back buffer started")

    async def stop(self, flush_remaining: bool = True):
        """
        Stop background flush task.

        Args:
            flush_remaining: Whether to flush remaining items before stopping
        """
        if not self.is_running:
            return

        self.is_running = False
        self.shutdown_event.set()

        if self.flush_task:
            self.flush_task.cancel()
            try:
                await self.flush_task
            except asyncio.CancelledError:
                pass

        # Final flush if requested
        if flush_remaining:
            await self._flush_all()

        logger.info("Write-back buffer stopped",
                   remaining_items=len(self.write_queue))

    async def enqueue_write(self,
                            vector_id: str,
                            embedding: np.ndarray,
                            metadata: Optional[Dict] = None,
                            priority: int = 0) -> bool:
        """
        Enqueue a write operation.

        REPLACES: Direct calls to FAISS add()
        USED BY: ETERNAL MIND memory consolidation

        Args:
            vector_id: Unique identifier for the vector
            embedding: Embedding vector
            metadata: Optional metadata dict
            priority: Priority level (higher = more urgent)

        Returns:
            True if enqueued, False if queue is full (backpressure)
        """
        # Check backpressure
        if len(self.write_queue) >= self.max_queue_size:
            logger.warning("Write queue full, applying backpressure")
            # Try to flush immediately
            await self._flush_batch()
            if len(self.write_queue) >= self.max_queue_size:
                return False

        item = WriteItem(
            vector_id=vector_id,
            embedding=np.asarray(embedding).astype('float32'),
            metadata=metadata or {},
            priority=priority
        )

        async with self.lock:
            if self.enable_priority and priority > 0:
                # Add to priority queue
                import heapq
                heapq.heappush(self.priority_queue, (-priority, time.time(), item))
            else:
                # Add to regular queue
                self.write_queue.append(item)

            self.metrics.total_writes_queued += 1
            self.metrics.current_queue_size = len(self.write_queue) + len(self.priority_queue)

            # Track writes per second
            now = time.time()
            self.writes_in_last_second.append(now)
            # Remove old entries
            while self.writes_in_last_second and self.writes_in_last_second[0] < now - 1:
                self.writes_in_last_second.popleft()
            self.metrics.writes_per_second = len(self.writes_in_last_second)

        # Trigger flush if batch size reached
        if len(self.write_queue) >= self.batch_size:
            self.flush_event.set()

        return True

    async def enqueue_batch(self,
                            items: List[Tuple[str, np.ndarray, Optional[Dict]]],
                            priority: int = 0) -> int:
        """
        Enqueue multiple write operations.

        More efficient than individual enqueues for bulk operations.

        Args:
            items: List of (vector_id, embedding, metadata) tuples
            priority: Priority level for all items

        Returns:
            Number of items successfully enqueued
        """
        enqueued = 0
        for vector_id, embedding, metadata in items:
            if await self.enqueue_write(vector_id, embedding, metadata, priority):
                enqueued += 1
            else:
                break  # Backpressure hit
        return enqueued

    async def flush_now(self) -> int:
        """
        Force immediate flush of all queued writes.

        Returns:
            Number of items flushed
        """
        return await self._flush_all()

    async def _background_flush_loop(self):
        """
        Background task that periodically flushes the write queue.
        """
        logger.debug("Background flush loop started")

        while not self.shutdown_event.is_set():
            try:
                # Wait for flush interval or flush event
                try:
                    await asyncio.wait_for(
                        self.flush_event.wait(),
                        timeout=self.flush_interval
                    )
                except asyncio.TimeoutError:
                    pass

                self.flush_event.clear()

                # Flush if there are items
                if self.write_queue or self.priority_queue:
                    await self._flush_batch()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Flush loop error: {e}")
                await asyncio.sleep(0.1)  # Brief pause on error

        logger.debug("Background flush loop stopped")

    async def _flush_batch(self) -> int:
        """
        Flush a batch of writes to FAISS.

        Returns:
            Number of items flushed
        """
        start_time = time.perf_counter()
        items_to_flush: List[WriteItem] = []

        async with self.lock:
            # First, get priority items
            if self.enable_priority:
                import heapq
                while self.priority_queue and len(items_to_flush) < self.batch_size:
                    _, _, item = heapq.heappop(self.priority_queue)
                    items_to_flush.append(item)

            # Then, get regular items
            while self.write_queue and len(items_to_flush) < self.batch_size:
                items_to_flush.append(self.write_queue.popleft())

            self.metrics.current_queue_size = len(self.write_queue) + len(self.priority_queue)

        if not items_to_flush:
            return 0

        # Prepare batch data
        vector_ids = [item.vector_id for item in items_to_flush]
        embeddings = np.array([item.embedding for item in items_to_flush]).astype('float32')
        metadata_list = [item.metadata for item in items_to_flush]

        # Write to FAISS index
        try:
            if hasattr(self.faiss_index, 'add_embeddings_batch'):
                # Use batch add if available
                await self.faiss_index.add_embeddings_batch(
                    vector_ids,
                    embeddings,
                    metadata_list
                )
            else:
                # Fall back to individual adds
                for vid, emb, meta in zip(vector_ids, embeddings, metadata_list):
                    await self.faiss_index.add_embedding(vid, emb, meta)

            flushed_count = len(items_to_flush)

        except Exception as e:
            logger.error(f"Batch flush failed: {e}")
            # Re-queue failed items
            async with self.lock:
                for item in items_to_flush:
                    self.write_queue.appendleft(item)
            return 0

        # Update metrics
        flush_latency_ms = (time.perf_counter() - start_time) * 1000
        self.flush_latencies.append(flush_latency_ms)
        if len(self.flush_latencies) > self.max_latency_samples:
            self.flush_latencies = self.flush_latencies[-self.max_latency_samples:]

        self.metrics.total_writes_flushed += flushed_count
        self.metrics.total_batches_flushed += 1
        self.metrics.avg_batch_size = (
            self.metrics.total_writes_flushed / self.metrics.total_batches_flushed
        )
        self.metrics.avg_flush_latency_ms = sum(self.flush_latencies) / len(self.flush_latencies)
        self.metrics.max_flush_latency_ms = max(self.flush_latencies)
        self.metrics.last_flush_time = time.time()

        logger.debug(f"Flushed {flushed_count} items in {flush_latency_ms:.2f}ms")

        # Callback if provided
        if self.on_flush_callback:
            try:
                await self.on_flush_callback(flushed_count, flush_latency_ms)
            except Exception as e:
                logger.warning(f"Flush callback error: {e}")

        return flushed_count

    async def _flush_all(self) -> int:
        """
        Flush all remaining items in the queue.

        Returns:
            Total number of items flushed
        """
        total_flushed = 0
        while self.write_queue or self.priority_queue:
            flushed = await self._flush_batch()
            if flushed == 0:
                break
            total_flushed += flushed
        return total_flushed

    def get_metrics(self) -> WriteBackMetrics:
        """
        Get current performance metrics.

        Returns:
            WriteBackMetrics with current statistics
        """
        return WriteBackMetrics(
            total_writes_queued=self.metrics.total_writes_queued,
            total_writes_flushed=self.metrics.total_writes_flushed,
            total_batches_flushed=self.metrics.total_batches_flushed,
            avg_batch_size=round(self.metrics.avg_batch_size, 1),
            avg_flush_latency_ms=round(self.metrics.avg_flush_latency_ms, 3),
            max_flush_latency_ms=round(self.metrics.max_flush_latency_ms, 3),
            current_queue_size=len(self.write_queue) + len(self.priority_queue),
            writes_per_second=self.metrics.writes_per_second,
            last_flush_time=self.metrics.last_flush_time
        )

    def get_queue_depth(self) -> int:
        """
        Get current queue depth.

        Returns:
            Number of items waiting to be flushed
        """
        return len(self.write_queue) + len(self.priority_queue)

    async def wait_for_flush(self, timeout: float = 5.0) -> bool:
        """
        Wait for current queue to be flushed.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if queue was flushed, False if timeout
        """
        start = time.time()
        while self.get_queue_depth() > 0:
            if time.time() - start > timeout:
                return False
            await asyncio.sleep(0.01)
        return True


class WriteBackPool:
    """
    Pool of write-back buffers for parallel writes.

    Distributes writes across multiple buffers for higher throughput.
    """

    def __init__(self,
                 faiss_index,
                 num_buffers: int = 4,
                 **buffer_kwargs):
        """
        Initialize write-back pool.

        Args:
            faiss_index: ShardedFAISSIndex to write to
            num_buffers: Number of parallel buffers
            **buffer_kwargs: Arguments for AsyncWriteBackBuffer
        """
        self.num_buffers = num_buffers
        self.buffers = [
            AsyncWriteBackBuffer(faiss_index, **buffer_kwargs)
            for _ in range(num_buffers)
        ]
        self.round_robin_idx = 0
        self.lock = asyncio.Lock()

    async def start(self):
        """Start all buffers."""
        await asyncio.gather(*[b.start() for b in self.buffers])

    async def stop(self, flush_remaining: bool = True):
        """Stop all buffers."""
        await asyncio.gather(*[b.stop(flush_remaining) for b in self.buffers])

    async def enqueue_write(self,
                            vector_id: str,
                            embedding: np.ndarray,
                            metadata: Optional[Dict] = None,
                            priority: int = 0) -> bool:
        """
        Enqueue write to next available buffer (round-robin).
        """
        async with self.lock:
            buffer = self.buffers[self.round_robin_idx]
            self.round_robin_idx = (self.round_robin_idx + 1) % self.num_buffers

        return await buffer.enqueue_write(vector_id, embedding, metadata, priority)

    def get_total_queue_depth(self) -> int:
        """Get total queue depth across all buffers."""
        return sum(b.get_queue_depth() for b in self.buffers)

    def get_aggregate_metrics(self) -> Dict:
        """Get aggregated metrics from all buffers."""
        metrics = [b.get_metrics() for b in self.buffers]
        return {
            'total_writes_queued': sum(m.total_writes_queued for m in metrics),
            'total_writes_flushed': sum(m.total_writes_flushed for m in metrics),
            'total_batches_flushed': sum(m.total_batches_flushed for m in metrics),
            'avg_flush_latency_ms': sum(m.avg_flush_latency_ms for m in metrics) / len(metrics),
            'total_queue_depth': self.get_total_queue_depth(),
            'writes_per_second': sum(m.writes_per_second for m in metrics)
        }


if __name__ == "__main__":
    # Quick test
    import asyncio

    class MockFAISSIndex:
        """Mock FAISS index for testing."""
        def __init__(self):
            self.vectors = []

        async def add_embedding(self, vid, emb, meta):
            self.vectors.append((vid, emb, meta))

        async def add_embeddings_batch(self, vids, embs, metas):
            for vid, emb, meta in zip(vids, embs, metas):
                self.vectors.append((vid, emb, meta))

    async def test():
        print("Async Write-Back Buffer Test")
        print("=" * 40)

        # Create mock index and buffer
        mock_index = MockFAISSIndex()
        buffer = AsyncWriteBackBuffer(
            mock_index,
            batch_size=100,
            flush_interval_ms=50
        )

        # Start buffer
        await buffer.start()

        # Enqueue writes
        num_writes = 1000
        print(f"Enqueueing {num_writes} writes...")
        start = time.perf_counter()

        for i in range(num_writes):
            embedding = np.random.randn(384).astype('float32')
            await buffer.enqueue_write(
                f"vec_{i}",
                embedding,
                {'content': f'test_{i}'}
            )

        enqueue_time = (time.perf_counter() - start) * 1000
        print(f"Enqueued in {enqueue_time:.2f}ms ({num_writes / (enqueue_time/1000):.0f} writes/sec)")

        # Wait for flush
        print("Waiting for flush...")
        await buffer.wait_for_flush(timeout=5.0)

        # Stop buffer
        await buffer.stop()

        # Check results
        print(f"Vectors in index: {len(mock_index.vectors)}")

        # Metrics
        metrics = buffer.get_metrics()
        print(f"Metrics:")
        print(f"  Total queued: {metrics.total_writes_queued}")
        print(f"  Total flushed: {metrics.total_writes_flushed}")
        print(f"  Batches: {metrics.total_batches_flushed}")
        print(f"  Avg batch size: {metrics.avg_batch_size:.1f}")
        print(f"  Avg flush latency: {metrics.avg_flush_latency_ms:.3f}ms")

    asyncio.run(test())
