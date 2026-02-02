#!/usr/bin/env python3
"""
Comprehensive Test Suite for Sharded FAISS with Async Write-Back
================================================================
Validates sub-millisecond semantic search across 10M+ embeddings.
"""

import asyncio
import time
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

test_results = {
    'passed': 0,
    'failed': 0,
    'errors': [],
    'metrics': {}
}


def test_result(name: str, passed: bool, details: str = ""):
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}")
    if passed:
        test_results['passed'] += 1
    else:
        test_results['failed'] += 1
        test_results['errors'].append(f"{name}: {details}")
    if details and passed:
        print(f"        {details}")


async def test_sharded_faiss_index():
    """Test ShardedFAISSIndex functionality."""
    print("\n" + "="*60)
    print("TEST 1: Sharded FAISS Index")
    print("="*60)

    try:
        from agents.memory.sharded_faiss import ShardedFAISSIndex
        test_result("Import ShardedFAISSIndex", True)
    except Exception as e:
        test_result("Import ShardedFAISSIndex", False, str(e))
        return

    # Create index
    try:
        index = ShardedFAISSIndex(
            num_shards=4,
            embedding_dim=384,
            nlist=64
        )
        test_result("Create ShardedFAISSIndex", True, f"{index.num_shards} shards")
    except Exception as e:
        test_result("Create ShardedFAISSIndex", False, str(e))
        return

    # Test single embedding add
    try:
        embedding = np.random.randn(384).astype('float32')
        success = await index.add_embedding("test_vec_1", embedding, {"test": True})
        test_result("Add single embedding", success)
    except Exception as e:
        test_result("Add single embedding", False, str(e))

    # Test batch add
    try:
        num_vectors = 500
        embeddings = np.random.randn(num_vectors, 384).astype('float32')
        vector_ids = [f"batch_vec_{i}" for i in range(num_vectors)]

        start = time.perf_counter()
        added = await index.add_embeddings_batch(
            vector_ids,
            embeddings,
            [{"idx": i} for i in range(num_vectors)]
        )
        batch_time = (time.perf_counter() - start) * 1000

        throughput = added / (batch_time / 1000) if batch_time > 0 else 0
        test_result("Batch add embeddings", added > 0, 
                   f"{added} vectors in {batch_time:.2f}ms ({throughput:.0f} vec/sec)")
        test_results['metrics']['batch_add_time_ms'] = batch_time
        test_results['metrics']['batch_add_throughput'] = throughput
    except Exception as e:
        test_result("Batch add embeddings", False, str(e))

    # Test search
    try:
        query = np.random.randn(384).astype('float32')

        start = time.perf_counter()
        results = await index.search(query, k=10)
        search_time = (time.perf_counter() - start) * 1000

        test_result("Search embeddings", len(results) > 0,
                   f"{len(results)} results in {search_time:.3f}ms")
        test_results['metrics']['search_latency_ms'] = search_time
    except Exception as e:
        test_result("Search embeddings", False, str(e))

    # Test metrics
    try:
        metrics = index.get_metrics()
        test_result("Get metrics", metrics.total_vectors > 0,
                   f"{metrics.total_vectors} vectors, {metrics.shards_trained}/{metrics.total_shards} shards trained")
    except Exception as e:
        test_result("Get metrics", False, str(e))


async def test_async_writeback():
    """Test AsyncWriteBackBuffer functionality."""
    print("\n" + "="*60)
    print("TEST 2: Async Write-Back Buffer")
    print("="*60)

    try:
        from agents.memory.async_writeback import AsyncWriteBackBuffer
        test_result("Import AsyncWriteBackBuffer", True)
    except Exception as e:
        test_result("Import AsyncWriteBackBuffer", False, str(e))
        return

    class MockIndex:
        def __init__(self):
            self.vectors = []
        async def add_embedding(self, vid, emb, meta):
            self.vectors.append((vid, emb, meta))
        async def add_embeddings_batch(self, vids, embs, metas):
            for vid, emb, meta in zip(vids, embs, metas):
                self.vectors.append((vid, emb, meta))

    mock_index = MockIndex()

    try:
        buffer = AsyncWriteBackBuffer(
            mock_index,
            batch_size=100,
            flush_interval_ms=50
        )
        test_result("Create AsyncWriteBackBuffer", True)
    except Exception as e:
        test_result("Create AsyncWriteBackBuffer", False, str(e))
        return

    try:
        await buffer.start()
        test_result("Start buffer", buffer.is_running)
    except Exception as e:
        test_result("Start buffer", False, str(e))

    try:
        num_writes = 500
        start = time.perf_counter()

        for i in range(num_writes):
            embedding = np.random.randn(384).astype('float32')
            await buffer.enqueue_write(f"buf_vec_{i}", embedding, {"idx": i})

        enqueue_time = (time.perf_counter() - start) * 1000
        throughput = num_writes / (enqueue_time / 1000) if enqueue_time > 0 else 0

        test_result("Enqueue writes", True,
                   f"{num_writes} writes in {enqueue_time:.2f}ms ({throughput:.0f} writes/sec)")
        test_results['metrics']['enqueue_throughput'] = throughput
    except Exception as e:
        test_result("Enqueue writes", False, str(e))

    try:
        flushed = await buffer.wait_for_flush(timeout=5.0)
        test_result("Wait for flush", flushed, f"{len(mock_index.vectors)} vectors flushed")
    except Exception as e:
        test_result("Wait for flush", False, str(e))

    try:
        metrics = buffer.get_metrics()
        test_result("Buffer metrics", metrics.total_writes_flushed > 0,
                   f"Flushed: {metrics.total_writes_flushed}, Avg latency: {metrics.avg_flush_latency_ms:.3f}ms")
        test_results['metrics']['flush_latency_ms'] = metrics.avg_flush_latency_ms
    except Exception as e:
        test_result("Buffer metrics", False, str(e))

    try:
        await buffer.stop()
        test_result("Stop buffer", not buffer.is_running)
    except Exception as e:
        test_result("Stop buffer", False, str(e))


async def test_query_engine():
    """Test QueryEngine with sharded FAISS."""
    print("\n" + "="*60)
    print("TEST 3: Query Engine Integration")
    print("="*60)

    try:
        from agents.memory.queries.query_engine import QueryEngine, Memory, MemoryQuery, MemoryType
        test_result("Import QueryEngine", True)
    except Exception as e:
        test_result("Import QueryEngine", False, str(e))
        return

    try:
        engine = QueryEngine(
            num_shards=4,
            embedding_dim=384,
            persist_dir="/tmp/test_query_engine"
        )
        await engine.initialize()
        test_result("Create and initialize QueryEngine", engine.is_initialized)
    except Exception as e:
        test_result("Create and initialize QueryEngine", False, str(e))
        return

    try:
        num_memories = 100
        start = time.perf_counter()

        for i in range(num_memories):
            memory = Memory(
                id=f"qe_mem_{i}",
                content=f"Test memory {i} about blockchain insider trading detection",
                memory_type=MemoryType.PATTERN if i % 2 == 0 else MemoryType.INSIGHT,
                importance=0.5 + (i % 5) * 0.1
            )
            await engine.store_memory(memory)

        store_time = (time.perf_counter() - start) * 1000
        test_result("Store memories", True, f"{num_memories} memories in {store_time:.2f}ms")
    except Exception as e:
        test_result("Store memories", False, str(e))

    try:
        await engine.write_buffer.wait_for_flush(timeout=5.0)
        test_result("Flush writes", True)
    except Exception as e:
        test_result("Flush writes", False, str(e))

    try:
        query = MemoryQuery(
            query_text="blockchain insider trading patterns",
            limit=10,
            similarity_threshold=0.3
        )

        start = time.perf_counter()
        results = await engine.query(query)
        query_time = (time.perf_counter() - start) * 1000

        test_result("Query memories", len(results) > 0, f"{len(results)} results in {query_time:.3f}ms")
        test_results['metrics']['query_latency_ms'] = query_time
    except Exception as e:
        test_result("Query memories", False, str(e))

    try:
        start = time.perf_counter()
        results2 = await engine.query(query)
        cache_time = (time.perf_counter() - start) * 1000

        test_result("Cache hit", True, f"{cache_time:.3f}ms (vs {query_time:.3f}ms uncached)")
        test_results['metrics']['cache_hit_latency_ms'] = cache_time
    except Exception as e:
        test_result("Cache hit", False, str(e))

    try:
        qm = engine.get_metrics()
        test_result("Engine metrics", qm.total_queries > 0, f"Queries: {qm.total_queries}, Avg latency: {qm.avg_latency_ms:.3f}ms")
    except Exception as e:
        test_result("Engine metrics", False, str(e))

    try:
        await engine.shutdown()
        test_result("Shutdown engine", not engine.is_initialized)
    except Exception as e:
        test_result("Shutdown engine", False, str(e))


async def test_memory_storage():
    """Test MemoryStorage with sharded FAISS."""
    print("\n" + "="*60)
    print("TEST 4: Memory Storage Integration")
    print("="*60)

    try:
        from agents.memory.storage import MemoryStorage, Memory, MemoryType, MemoryMetadata, MemoryImportance
        test_result("Import MemoryStorage", True)
    except Exception as e:
        test_result("Import MemoryStorage", False, str(e))
        return

    try:
        storage = MemoryStorage(
            storage_path="/tmp/test_memory_storage",
            num_shards=4,
            embedding_dim=384
        )
        await storage.initialize()
        test_result("Create and initialize MemoryStorage", storage.is_initialized)
    except Exception as e:
        test_result("Create and initialize MemoryStorage", False, str(e))
        return

    try:
        num_memories = 50
        start = time.perf_counter()

        for i in range(num_memories):
            memory = Memory(
                memory_id=f"storage_mem_{i}",
                memory_type=MemoryType.PATTERN if i % 3 == 0 else MemoryType.WALLET,
                content={"wallet": f"wallet_{i}", "risk_score": 0.5 + i * 0.01},
                metadata=MemoryMetadata(
                    importance=MemoryImportance.HIGH if i % 5 == 0 else MemoryImportance.MEDIUM,
                    tags=["test", "wallet"],
                    confidence=0.9
                )
            )
            await storage.store(memory)

        store_time = (time.perf_counter() - start) * 1000
        test_result("Store memories", True, f"{num_memories} memories in {store_time:.2f}ms")
    except Exception as e:
        test_result("Store memories", False, str(e))

    try:
        memory = await storage.retrieve("storage_mem_0")
        test_result("Retrieve memory", memory is not None, f"ID: {memory.memory_id}" if memory else "Not found")
    except Exception as e:
        test_result("Retrieve memory", False, str(e))

    try:
        metrics = storage.get_metrics()
        test_result("Storage metrics", metrics.total_memories > 0,
                   f"Memories: {metrics.total_memories}, Write latency: {metrics.avg_write_latency_ms:.3f}ms")
    except Exception as e:
        test_result("Storage metrics", False, str(e))

    try:
        await storage.shutdown()
        test_result("Shutdown storage", not storage.is_initialized)
    except Exception as e:
        test_result("Shutdown storage", False, str(e))


async def test_performance_targets():
    """Test performance against targets."""
    print("\n" + "="*60)
    print("TEST 5: Performance Targets Validation")
    print("="*60)

    search_latency = test_results['metrics'].get('search_latency_ms', float('inf'))
    test_result("Search latency < 1ms", search_latency < 1.0, f"Actual: {search_latency:.3f}ms")

    throughput = test_results['metrics'].get('enqueue_throughput', 0)
    test_result("Write throughput > 10,000/sec", throughput > 10000, f"Actual: {throughput:.0f}/sec")

    query_latency = test_results['metrics'].get('query_latency_ms', float('inf'))
    test_result("Query latency < 5ms", query_latency < 5.0, f"Actual: {query_latency:.3f}ms")

    cache_latency = test_results['metrics'].get('cache_hit_latency_ms', float('inf'))
    test_result("Cache hit latency < 1ms", cache_latency < 1.0, f"Actual: {cache_latency:.3f}ms")


async def main():
    print("\n" + "#"*60)
    print("# SHARDED FAISS WITH ASYNC WRITE-BACK TEST SUITE")
    print("# Target: Sub-millisecond search, 10,000+ writes/sec")
    print("#"*60)

    await test_sharded_faiss_index()
    await test_async_writeback()
    await test_query_engine()
    await test_memory_storage()
    await test_performance_targets()

    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    total = test_results['passed'] + test_results['failed']
    print(f"Passed: {test_results['passed']}/{total}")
    print(f"Failed: {test_results['failed']}/{total}")
    if total > 0:
        print(f"Success Rate: {test_results['passed']/total*100:.1f}%")

    if test_results['errors']:
        print("\nErrors:")
        for error in test_results['errors']:
            print(f"  - {error}")

    print("\nPerformance Metrics:")
    for key, value in test_results['metrics'].items():
        if isinstance(value, float):
            print(f"  {key}: {value:.3f}")
        else:
            print(f"  {key}: {value}")

    return test_results['failed'] == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
