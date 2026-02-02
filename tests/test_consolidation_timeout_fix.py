
"""Test fixed memory consolidation with timeout prevention."""

import asyncio
import time
import sys
from pathlib import Path
from datetime import datetime
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.memory.memory_models import Memory, MemoryType, MemoryImportance, MemoryMetadata
from agents.memory.consolidators.enhanced_consolidator import EnhancedMemoryConsolidator, CONSOLIDATION_BATCH_SIZE


class MockEnhancedStorage:
    def __init__(self, num_memories=50):
        self.memories = {}
        self._create_test_memories(num_memories)

    def _create_test_memories(self, count):
        for i in range(count):
            memory = Memory(
                memory_id=f"mem_{i}",
                memory_type=MemoryType.PATTERN,
                content={"pattern_type": f"pattern_{i % 5}", "occurrences": np.random.randint(1, 10)},
                metadata=MemoryMetadata(
                    created_at=datetime.now(),
                    confidence=np.random.uniform(0.2, 0.9),
                    importance=MemoryImportance.HIGH,
                    tags=[f"tag_{i % 5}"]
                )
            )
            memory.embedding = np.random.rand(384).tolist()
            self.memories[memory.memory_id] = memory

    async def reorganize_tiers(self):
        await asyncio.sleep(0.01)

    async def prune_old_memories(self, max_age_days):
        await asyncio.sleep(0.01)

    async def store(self, memory):
        self.memories[memory.memory_id] = memory

    async def delete(self, memory_id):
        if memory_id in self.memories:
            del self.memories[memory_id]

    def get_statistics(self):
        return {"total_memories": len(self.memories)}


async def test_consolidation_performance():
    print("TEST 1: Consolidation Performance")
    storage = MockEnhancedStorage(num_memories=150)
    consolidator = EnhancedMemoryConsolidator(storage)
    print(f"Batch size limit: {CONSOLIDATION_BATCH_SIZE}")
    print(f"Total memories: {len(storage.memories)}")

    start_time = time.perf_counter()
    report = await consolidator.consolidate()
    total_duration = time.perf_counter() - start_time

    print(f"Consolidation completed in {total_duration:.3f}s")
    print(f"Patterns merged: {report.get('patterns_merged', 0)}")

    assert total_duration < 5.0, f"Consolidation took {total_duration:.3f}s, expected <5.0s"
    print("PASSED: Consolidation completed within timeout")
    return True


async def test_batch_size_limit():
    print("
TEST 2: Batch Size Limit Enforcement")
    storage = MockEnhancedStorage(num_memories=500)
    consolidator = EnhancedMemoryConsolidator(storage)

    processed_count = 0
    original_merge = consolidator.merge_similar_patterns

    async def tracked_merge():
        nonlocal processed_count
        pattern_memories = [m for m in storage.memories.values() if m.memory_type == MemoryType.PATTERN]
        processed_count = len(pattern_memories)
        return await original_merge()

    consolidator.merge_similar_patterns = tracked_merge
    await consolidator.consolidate()

    print(f"Memories processed: {processed_count}")
    assert processed_count <= CONSOLIDATION_BATCH_SIZE, f"Processed {processed_count} memories, expected <= {CONSOLIDATION_BATCH_SIZE}"
    print("PASSED: Batch size limit respected")
    return True


async def test_thread_pool_usage():
    print("
TEST 3: Thread Pool for Blocking Operations")
    storage = MockEnhancedStorage(num_memories=100)
    consolidator = EnhancedMemoryConsolidator(storage)

    assert consolidator.thread_pool is not None, "Thread pool not initialized"
    print(f"Thread pool initialized with {consolidator.thread_pool._max_workers} workers")

    start_time = time.perf_counter()
    report = await consolidator.consolidate()
    duration = time.perf_counter() - start_time
    print(f"Consolidation completed in {duration:.3f}s with thread pool")
    print("PASSED: Thread pool properly configured")
    return True


async def test_large_dataset_no_timeout():
    print("
TEST 4: Large Dataset No Timeout")
    storage = MockEnhancedStorage(num_memories=1000)
    consolidator = EnhancedMemoryConsolidator(storage)

    print(f"Large dataset: {len(storage.memories)} memories")

    timeout_threshold = 5.0
    start_time = time.perf_counter()

    try:
        report = await asyncio.wait_for(consolidator.consolidate(), timeout=timeout_threshold)
        duration = time.perf_counter() - start_time
        print(f"Consolidation completed in {duration:.3f}s (timeout: {timeout_threshold}s)")
        print("PASSED: No timeout with large dataset")
        return True
    except asyncio.TimeoutError:
        duration = time.perf_counter() - start_time
        print(f"FAILED: Timeout after {duration:.3f}s")
        return False


async def run_all_tests():
    print("
" + "="*60)
    print("GODMODESCANNER - MEMORY CONSOLIDATION TIMEOUT FIX TEST")
    print("="*60)

    tests = [
        ("Consolidation Performance", test_consolidation_performance),
        ("Batch Size Limit Enforcement", test_batch_size_limit),
        ("Thread Pool Usage", test_thread_pool_usage),
        ("Large Dataset No Timeout", test_large_dataset_no_timeout)
    ]

    results = []
    start_time = time.perf_counter()

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result, None))
        except Exception as e:
            print(f"
FAILED: {test_name}")
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False, str(e)))

    total_duration = time.perf_counter() - start_time

    print("
" + "="*60)
    print("TEST SUMMARY")
    print("="*60)

    passed = sum(1 for _, result, _ in results if result)
    total = len(results)

    for test_name, result, error in results:
        status = "PASSED" if result else "FAILED"
        print(f"{status}: {test_name}")
        if error:
            print(f"    Error: {error}")

    print(f"
Total: {passed}/{total} tests passed")
    print(f"Total time: {total_duration:.3f}s")

    if passed == total:
        print("
ALL TESTS PASSED! Memory consolidation timeout is FIXED.")
        return 0
    else:
        print(f"
{total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
