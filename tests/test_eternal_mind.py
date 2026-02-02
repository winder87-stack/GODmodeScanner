
"""Comprehensive test suite for ETERNAL MIND memory system."""

import asyncio
import json
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import pytest
import numpy as np

from agents.memory.memory_models import Memory, MemoryType, MemoryImportance
from agents.memory.storage import MemoryStorage
from agents.memory.consolidators.consolidator import MemoryConsolidator
from agents.memory_consolidation_agent import MemoryConsolidationAgent
from redis import Redis
import structlog

logger = structlog.get_logger(__name__)


class TestEternalMind:
    """Test suite for ETERNAL MIND memory system."""

    @pytest.fixture
    def temp_storage_path(self):
        """Create temporary storage directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def redis_client(self):
        """Redis client for testing."""
        redis = Redis(host='localhost', port=6379, db=15, decode_responses=True)
        redis.flushdb()  # Clean test DB
        yield redis
        redis.flushdb()

    @pytest.fixture
    def storage(self, temp_storage_path):
        """Memory storage instance."""
        return MemoryStorage(storage_path=temp_storage_path)

    @pytest.fixture
    def consolidator(self, storage, redis_client):
        """Memory consolidator instance."""
        return MemoryConsolidator(
            storage=storage,
            redis_client=redis_client,
            config={
                'consolidation_interval_hours': 24,
                'importance_decay_rate': 0.95,
                'min_importance_to_keep': MemoryImportance.LOW,
                'max_memories': 100,
                'pattern_detection_enabled': True,
                'similarity_threshold': 0.85,
                'batch_size': 50
            }
        )

    @pytest.fixture
    def agent(self, temp_storage_path, redis_client):
        """Memory consolidation agent instance."""
        return MemoryConsolidationAgent(
            storage_path=temp_storage_path,
            redis_client=redis_client,
            consolidation_interval_hours=1
        )

    # ==================== STORAGE TESTS ====================

    def test_storage_initialization(self, storage, temp_storage_path):
        """Test 1: Storage initializes with required directories."""
        assert storage.storage_path == Path(temp_storage_path)
        assert storage.patterns_dir.exists()
        assert storage.kings_dir.exists()
        assert storage.insights_dir.exists()
        print("✓ Test 1 PASSED: Storage initialization")

    def test_load_memory_from_disk(self, storage):
        """Test 2: Load memories from disk on startup."""
        # Create a pattern file
        pattern_data = {
            'memory_id': 'test-pattern-1',
            'memory_type': 'pattern',
            'content': {'pattern_type': 'early_buyer', 'confidence': 0.9},
            'metadata': {
                'created_at': datetime.now().isoformat(),
                'last_accessed': datetime.now().isoformat(),
                'access_count': 10,
                'importance': 3,  # HIGH
                'tags': ['insider', 'early_buyer'],
                'source': 'consolidator',
                'confidence': 0.9,
                'related_memories': []
            }
        }

        import gzip
        pattern_file = storage.patterns_dir / 'test-pattern-1.json.gz'
        with gzip.open(pattern_file, 'wt') as f:
            json.dump(pattern_data, f)

        # Reinitialize storage to trigger load
        storage._load_memories_from_disk()

        # Verify loaded memory
        assert 'test-pattern-1' in storage.memories
        loaded = storage.memories['test-pattern-1']
        assert loaded.memory_type == MemoryType.PATTERN
        assert loaded.metadata.importance == MemoryImportance.HIGH
        print("✓ Test 2 PASSED: Load memories from disk")

    def test_persist_memory_to_disk(self, storage):
        """Test 3: Persist important memories to disk."""
        # Create a high-confidence pattern memory
        pattern = Memory.create(
            memory_type=MemoryType.PATTERN,
            content={'pattern_type': 'early_buyer', 'description': 'Test pattern'},
            importance=MemoryImportance.HIGH,
            tags=['insider', 'early_buyer']
        )
        pattern.metadata.confidence = 0.9
        storage.memories[pattern.memory_id] = pattern

        # Persist to disk
        saved_count = storage.persist_memory_to_disk()

        assert saved_count >= 1
        assert (storage.patterns_dir / f'{pattern.memory_id}.json.gz').exists()
        print("✓ Test 3 PASSED: Persist memories to disk")

    def test_persist_king_maker_profiles(self, storage):
        """Test 4: Persist King Maker profiles."""
        # Create a King Maker wallet memory
        king_maker = Memory.create(
            memory_type=MemoryType.WALLET,
            content={'wallet_address': 'test-wallet', 'is_king_maker': True},
            importance=MemoryImportance.CRITICAL,
            tags=['king_maker', 'elite']
        )
        storage.memories[king_maker.memory_id] = king_maker

        # Persist
        saved_count = storage.persist_memory_to_disk()

        assert saved_count >= 1
        assert (storage.kings_dir / f'{king_maker.memory_id}.pkl').exists()
        print("✓ Test 4 PASSED: Persist King Maker profiles")

    # ==================== CONSOLIDATOR TESTS ====================

    @pytest.mark.asyncio
    async def test_consolidate_raw_memories(self, consolidator, redis_client):
        """Test 5: Consolidate raw memories from Redis."""
        # Add raw memories to Redis
        raw_memories = [
            {
                'memory_id': f'raw-{i}',
                'memory_type': 'episodic',
                'content': {'event': f'event-{i}', 'data': i},
                'metadata': {
                    'created_at': datetime.now().isoformat(),
                    'last_accessed': datetime.now().isoformat(),
                    'access_count': 1,
                    'importance': 2,
                    'tags': [],
                    'source': '',
                    'confidence': 1.0,
                    'related_memories': []
                }
            }
            for i in range(10)
        ]

        for raw in raw_memories:
            redis_client.rpush('memory:raw', json.dumps(raw))

        # Run consolidation
        report = await consolidator.consolidate()

        assert report['raw_memories_processed'] == 10
        print("✓ Test 5 PASSED: Consolidate raw memories from Redis")

    @pytest.mark.asyncio
    async def test_merge_similar_patterns(self, consolidator, storage):
        """Test 6: Merge similar patterns with DBSCAN."""
        # Create similar pattern memories with similar embeddings
        base_embedding = np.random.rand(128).tolist()

        for i in range(5):
            # Create slightly varied embeddings
            embedding = np.array(base_embedding) + np.random.normal(0, 0.1, 128)
            pattern = Memory.create(
                memory_type=MemoryType.PATTERN,
                content={'pattern_type': 'early_buyer', 'variant': i},
                importance=MemoryImportance.MEDIUM
            )
            pattern.embedding = embedding.tolist()
            storage.memories[pattern.memory_id] = pattern

        # Merge similar patterns
        merged_count = await consolidator.merge_similar_memories_batch()

        # Should merge into at least one consolidated pattern
        assert merged_count >= 1
        print("✓ Test 6 PASSED: Merge similar patterns with DBSCAN")

    @pytest.mark.asyncio
    async def test_extract_patterns(self, consolidator, storage):
        """Test 7: Extract patterns from episodic memories."""
        # Create episodic memories for pattern detection
        for i in range(5):
            memory = Memory.create(
                memory_type=MemoryType.EPISODIC,
                content={'seconds_after_launch': 30 + i * 10, 'event': 'early_buy'},
                importance=MemoryImportance.MEDIUM
            )
            storage.memories[memory.memory_id] = memory

        # Extract patterns
        patterns = await consolidator.extract_patterns()

        # Should detect early buyer pattern
        assert len(patterns) >= 1
        assert any(p.content.get('pattern_type') == 'early_buyer_behavior' for p in patterns)
        print("✓ Test 7 PASSED: Extract patterns from episodic memories")

    @pytest.mark.asyncio
    async def test_extract_king_maker_pattern(self, consolidator, storage):
        """Test 8: Extract King Maker pattern."""
        # Create episodic memories with high graduation rates
        for i in range(3):
            memory = Memory.create(
                memory_type=MemoryType.EPISODIC,
                content={'graduation_rate': 0.65 + i * 0.05, 'wallet': f'wallet-{i}'},
                importance=MemoryImportance.HIGH
            )
            storage.memories[memory.memory_id] = memory

        # Extract patterns
        patterns = await consolidator.extract_patterns()

        # Should detect King Maker pattern
        assert len(patterns) >= 1
        assert any(p.content.get('pattern_type') == 'king_maker_behavior' for p in patterns)
        print("✓ Test 8 PASSED: Extract King Maker pattern")

    @pytest.mark.asyncio
    async def test_decay_importance(self, consolidator, storage):
        """Test 9: Decay importance of old memories."""
        # Create old memory (10 days ago)
        old_memory = Memory.create(
            memory_type=MemoryType.PATTERN,
            content={'old_pattern': True},
            importance=MemoryImportance.HIGH
        )
        old_memory.metadata.created_at = datetime.now() - timedelta(days=10)
        storage.memories[old_memory.memory_id] = old_memory

        # Decay importance
        decayed_count = await consolidator.decay_importance()

        assert decayed_count >= 1
        # Importance should be reduced
        assert old_memory.metadata.importance.value < MemoryImportance.HIGH.value
        print("✓ Test 9 PASSED: Decay importance of old memories")

    @pytest.mark.asyncio
    async def test_prune_memories(self, consolidator, storage):
        """Test 10: Prune low-value memories."""
        # Set low max_memories to trigger pruning
        consolidator.config['max_memories'] = 5

        # Create memories
        for i in range(10):
            memory = Memory.create(
                memory_type=MemoryType.EPISODIC,
                content={'data': i},
                importance=MemoryImportance.LOW
            )
            storage.memories[memory.memory_id] = memory

        # Prune memories
        pruned_count = await consolidator.prune_memories()

        assert pruned_count >= 5
        assert len(storage.memories) <= 5
        print("✓ Test 10 PASSED: Prune low-value memories")

    def test_calculate_memory_value(self, consolidator):
        """Test 11: Calculate memory value with weighted scoring."""
        # Create memory with different characteristics
        high_value_memory = Memory.create(
            memory_type=MemoryType.PATTERN,
            content={'important': True},
            importance=MemoryImportance.CRITICAL
        )
        high_value_memory.metadata.access_count = 100
        high_value_memory.metadata.confidence = 1.0
        high_value_memory.metadata.related_memories = ['id1', 'id2', 'id3', 'id4', 'id5']

        low_value_memory = Memory.create(
            memory_type=MemoryType.EPISODIC,
            content={'boring': True},
            importance=MemoryImportance.LOW
        )
        low_value_memory.metadata.access_count = 1
        low_value_memory.metadata.confidence = 0.5
        low_value_memory.metadata.created_at = datetime.now() - timedelta(days=30)

        # Calculate values
        high_value = consolidator.calculate_memory_value(high_value_memory)
        low_value = consolidator.calculate_memory_value(low_value_memory)

        assert high_value > low_value
        assert 0.0 <= high_value <= 1.0
        assert 0.0 <= low_value <= 1.0
        print(f"✓ Test 11 PASSED: Calculate memory value (high: {high_value:.3f}, low: {low_value:.3f})")

    # ==================== AGENT TESTS ====================

    @pytest.mark.asyncio
    async def test_agent_initialization(self, agent):
        """Test 12: Agent initializes correctly."""
        assert agent.storage is not None
        assert agent.redis is not None
        assert agent.consolidation_interval == 3600  # 1 hour
        assert agent.running is False
        assert agent.consolidation_count == 0
        print("✓ Test 12 PASSED: Agent initialization")

    @pytest.mark.asyncio
    async def test_agent_add_raw_memory(self, agent, redis_client):
        """Test 13: Add raw memory to processing queue."""
        raw_data = {
            'memory_id': 'test-raw',
            'memory_type': 'episodic',
            'content': {'test': True},
            'metadata': {
                'created_at': datetime.now().isoformat(),
                'last_accessed': datetime.now().isoformat(),
                'access_count': 1,
                'importance': 2,
                'tags': [],
                'source': '',
                'confidence': 1.0,
                'related_memories': []
            }
        }

        await agent.add_raw_memory(raw_data)

        # Verify it's in Redis
        assert redis_client.llen('memory:raw') == 1
        print("✓ Test 13 PASSED: Add raw memory to queue")

    @pytest.mark.asyncio
    async def test_agent_get_status(self, agent):
        """Test 14: Get agent status."""
        status = agent.get_status()

        assert 'running' in status
        assert 'consolidation_count' in status
        assert 'storage_stats' in status
        assert 'redis_connected' in status
        assert status['redis_connected'] is True
        print("✓ Test 14 PASSED: Get agent status")

    # ==================== INTEGRATION TESTS ====================

    @pytest.mark.asyncio
    async def test_full_consolidation_cycle(self, consolidator, storage, redis_client):
        """Test 15: Full consolidation cycle."""
        # Add raw memories to Redis
        for i in range(20):
            raw = {
                'memory_id': f'cycle-{i}',
                'memory_type': 'episodic',
                'content': {
                    'seconds_after_launch': 30 if i < 5 else 100,
                    'graduation_rate': 0.7 if i < 3 else 0.4,
                    'funding_source': 'shared-funding' if i % 3 == 0 else f'funding-{i}'
                },
                'metadata': {
                    'created_at': datetime.now().isoformat(),
                    'last_accessed': datetime.now().isoformat(),
                    'access_count': 1,
                    'importance': 2,
                    'tags': [],
                    'source': '',
                    'confidence': 1.0,
                    'related_memories': []
                }
            }
            redis_client.rpush('memory:raw', json.dumps(raw))

        # Run full consolidation
        report = await consolidator.consolidate()

        # Verify all steps completed
        assert 'raw_memories_processed' in report
        assert 'patterns_merged' in report
        assert 'patterns_extracted' in report
        assert 'memories_decayed' in report
        assert 'memories_pruned' in report

        # Should have processed raw memories
        assert report['raw_memories_processed'] >= 20

        # Should have extracted patterns
        assert report['patterns_extracted'] >= 1

        print(f"✓ Test 15 PASSED: Full consolidation cycle")
        print(f"  Raw processed: {report['raw_memories_processed']}")
        print(f"  Patterns extracted: {report['patterns_extracted']}")

    @pytest.mark.asyncio
    async def test_persistence_survives_restart(self, storage, temp_storage_path):
        """Test 16: Memory persistence survives restart."""
        # Create memories in first instance
        pattern = Memory.create(
            memory_type=MemoryType.PATTERN,
            content={'pattern_type': 'early_buyer', 'description': 'Test'},
            importance=MemoryImportance.HIGH
        )
        pattern.metadata.confidence = 0.9
        storage.memories[pattern.memory_id] = pattern
        storage.persist_memory_to_disk()

        # Verify file exists
        pattern_file = storage.patterns_dir / f'{pattern.memory_id}.json.gz'
        assert pattern_file.exists()

        # Create new storage instance (simulating restart)
        storage2 = MemoryStorage(storage_path=temp_storage_path)

        # Verify memory was loaded
        assert pattern.memory_id in storage2.memories
        loaded = storage2.memories[pattern.memory_id]
        assert loaded.memory_type == MemoryType.PATTERN
        assert loaded.content['pattern_type'] == 'early_buyer'

        print("✓ Test 16 PASSED: Memory persistence survives restart")


# Run tests manually if executed directly
if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
