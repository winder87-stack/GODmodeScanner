#!/usr/bin/env python3
"""
Enhanced Storage Backend for ETERNAL MIND Memory System
=======================================================
Persistent disk storage with Sharded FAISS integration for
sub-millisecond semantic search across 10M+ embeddings.

UPDATES: Existing storage.py to use sharded FAISS
REPLACES: Simple in-memory storage with async indexed storage
INTEGRATES WITH: ShardedFAISSIndex, AsyncWriteBackBuffer

Author: GODMODESCANNER Memory Architect
"""

import asyncio
import json
import pickle
import gzip
import hashlib
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import structlog

# Import sharded FAISS components
try:
    from .sharded_faiss import ShardedFAISSIndex, SearchResult
    from .async_writeback import AsyncWriteBackBuffer
    SHARDED_FAISS_AVAILABLE = True
except ImportError:
    SHARDED_FAISS_AVAILABLE = False

# Import embedding model
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

logger = structlog.get_logger(__name__)


# ============================================================================
# Memory Models (for backward compatibility)
# ============================================================================

class MemoryType(str, Enum):
    """Types of memories stored in the system."""
    PATTERN = "pattern"      # Detected insider patterns
    WALLET = "wallet"        # Wallet profiles and behaviors
    INSIGHT = "insight"      # Analytical insights
    RULE = "rule"            # Detection rules
    SEMANTIC = "semantic"    # Semantic knowledge
    PROCEDURAL = "procedural"  # Procedural knowledge
    GENERAL = "general"      # General memories


class MemoryImportance(Enum):
    """Importance levels for memories."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class MemoryMetadata:
    """Metadata for a memory."""
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    importance: MemoryImportance = MemoryImportance.MEDIUM
    tags: List[str] = field(default_factory=list)
    source: str = ""
    confidence: float = 1.0
    related_memories: List[str] = field(default_factory=list)

    def update_access(self):
        """Update access tracking."""
        self.last_accessed = datetime.now()
        self.access_count += 1


@dataclass
class Memory:
    """A memory object stored in the system."""
    memory_id: str
    memory_type: MemoryType
    content: Any
    metadata: MemoryMetadata = field(default_factory=MemoryMetadata)
    embedding: Optional[np.ndarray] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert memory to dictionary for serialization."""
        return {
            'memory_id': self.memory_id,
            'memory_type': self.memory_type.value if isinstance(self.memory_type, MemoryType) else self.memory_type,
            'content': self.content,
            'metadata': {
                'created_at': self.metadata.created_at.isoformat(),
                'last_accessed': self.metadata.last_accessed.isoformat(),
                'access_count': self.metadata.access_count,
                'importance': self.metadata.importance.value if isinstance(self.metadata.importance, MemoryImportance) else self.metadata.importance,
                'tags': self.metadata.tags,
                'source': self.metadata.source,
                'confidence': self.metadata.confidence,
                'related_memories': self.metadata.related_memories
            },
            'embedding': self.embedding.tolist() if self.embedding is not None else None
        }


@dataclass
class MemoryQuery:
    """Query specification for memory retrieval."""
    query_text: Optional[str] = None
    memory_types: Optional[List[MemoryType]] = None
    tags: Optional[List[str]] = None
    min_importance: MemoryImportance = MemoryImportance.LOW
    similarity_threshold: float = 0.7
    limit: int = 10
    time_range: Optional[Tuple[datetime, datetime]] = None


@dataclass
class StorageMetrics:
    """Performance metrics for storage operations."""
    total_memories: int = 0
    total_disk_writes: int = 0
    total_disk_reads: int = 0
    avg_write_latency_ms: float = 0.0
    avg_read_latency_ms: float = 0.0
    disk_usage_mb: float = 0.0
    faiss_vectors: int = 0
    cache_hit_rate: float = 0.0


# ============================================================================
# Enhanced Memory Storage with Sharded FAISS
# ============================================================================

class MemoryStorage:
    """
    Enhanced Memory Storage with Sharded FAISS Integration.

    UPDATES: Original MemoryStorage with async FAISS indexing
    REPLACES: Simple in-memory dict with indexed vector storage
    INTEGRATES WITH: ShardedFAISSIndex, AsyncWriteBackBuffer

    Features:
    - Persistent disk storage with compression
    - Sharded FAISS for sub-millisecond semantic search
    - Async write-back for high-throughput indexing
    - Automatic embedding generation
    - Memory importance-based persistence
    """

    def __init__(self, 
                 storage_path: Optional[str] = None,
                 num_shards: int = 8,
                 embedding_dim: int = 384,
                 enable_faiss: bool = True):
        """
        Initialize memory storage.

        Args:
            storage_path: Path to storage directory
            num_shards: Number of FAISS shards
            embedding_dim: Embedding vector dimension
            enable_faiss: Whether to enable FAISS indexing
        """
        self.storage_path = Path(storage_path or "/a0/usr/projects/godmodescanner/data/memory")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories for different memory types
        self.patterns_dir = self.storage_path / "patterns"
        self.kings_dir = self.storage_path / "king_makers"
        self.insights_dir = self.storage_path / "insights"
        self.wallets_dir = self.storage_path / "wallets"
        self.rules_dir = self.storage_path / "rules"
        self.faiss_dir = self.storage_path / "faiss_index"

        for dir_path in [self.patterns_dir, self.kings_dir, self.insights_dir,
                         self.wallets_dir, self.rules_dir, self.faiss_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # In-memory storage
        self.memories: Dict[str, Memory] = {}
        self.embeddings_cache: Dict[str, np.ndarray] = {}

        # FAISS integration
        self.enable_faiss = enable_faiss and SHARDED_FAISS_AVAILABLE
        self.embedding_dim = embedding_dim
        self.num_shards = num_shards

        # Initialize sharded FAISS
        if self.enable_faiss:
            self.vector_store = ShardedFAISSIndex(
                num_shards=num_shards,
                embedding_dim=embedding_dim,
                persist_dir=str(self.faiss_dir)
            )
            self.write_buffer = AsyncWriteBackBuffer(
                self.vector_store,
                batch_size=1000,
                flush_interval_ms=100
            )
            logger.info("Sharded FAISS enabled", num_shards=num_shards)
        else:
            self.vector_store = None
            self.write_buffer = None
            logger.warning("FAISS disabled or not available")

        # Embedding model
        self.embedding_model = None
        self._init_embedding_model()

        # Metrics
        self.metrics = StorageMetrics()
        self.write_latencies: List[float] = []
        self.read_latencies: List[float] = []

        # Running state
        self.is_initialized = False

        # Load existing memories
        self._load_memories_from_disk()

        logger.info("MemoryStorage initialized",
                   storage_path=str(self.storage_path),
                   faiss_enabled=self.enable_faiss,
                   memories_loaded=len(self.memories))

    def _init_embedding_model(self):
        """Initialize the embedding model."""
        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("Loaded sentence-transformers embedding model")
            except Exception as e:
                logger.warning(f"Failed to load embedding model: {e}")
        else:
            logger.warning("sentence-transformers not available")

    async def initialize(self):
        """
        Start async components.

        Must be called before using async methods.
        """
        if self.is_initialized:
            return

        if self.write_buffer:
            await self.write_buffer.start()

        self.is_initialized = True
        logger.info("MemoryStorage async components started")

    async def shutdown(self):
        """
        Stop async components and persist data.
        """
        if not self.is_initialized:
            return

        if self.write_buffer:
            await self.write_buffer.stop(flush_remaining=True)

        if self.vector_store:
            await self.vector_store.persist()

        self.persist_memory_to_disk()
        self.is_initialized = False
        logger.info("MemoryStorage shutdown complete")

    def _generate_embedding(self, content: Any) -> np.ndarray:
        """
        Generate embedding for content.

        Args:
            content: Content to embed (string or dict)

        Returns:
            Embedding vector
        """
        # Convert content to string
        if isinstance(content, dict):
            text = json.dumps(content, default=str)
        else:
            text = str(content)

        if self.embedding_model is not None:
            embedding = self.embedding_model.encode(text, convert_to_numpy=True)
            return embedding.astype('float32')
        else:
            # Fallback: deterministic pseudo-random embedding
            hash_bytes = hashlib.sha256(text.encode()).digest()
            np.random.seed(int.from_bytes(hash_bytes[:4], 'big'))
            return np.random.randn(self.embedding_dim).astype('float32')

    def _load_memories_from_disk(self):
        """
        Load memories from disk storage on startup.

        Loads serialized memories from disk and populates the in-memory
        cache. Prioritizes high-value memories (patterns, King Makers).
        """
        try:
            loaded_count = 0

            # Load pattern memories (high-value insights)
            for pattern_file in self.patterns_dir.glob("*.json.gz"):
                try:
                    with gzip.open(pattern_file, 'rt') as f:
                        pattern_data = json.load(f)
                        memory = self._dict_to_memory(pattern_data)
                        if memory:
                            self.memories[memory.memory_id] = memory
                            loaded_count += 1
                except Exception as e:
                    logger.warning(f"Failed to load pattern {pattern_file}: {e}")

            # Load King Maker profiles (elite insiders)
            for king_file in self.kings_dir.glob("*.pkl"):
                try:
                    with open(king_file, 'rb') as f:
                        king_data = pickle.load(f)
                        if isinstance(king_data, Memory):
                            self.memories[king_data.memory_id] = king_data
                            loaded_count += 1
                except Exception as e:
                    logger.warning(f"Failed to load King Maker {king_file}: {e}")

            # Load general insights
            for insight_file in self.insights_dir.glob("*.json"):
                try:
                    with open(insight_file, 'r') as f:
                        insight_data = json.load(f)
                        memory = self._dict_to_memory(insight_data)
                        if memory:
                            self.memories[memory.memory_id] = memory
                            loaded_count += 1
                except Exception as e:
                    logger.warning(f"Failed to load insight {insight_file}: {e}")

            # Load wallet profiles
            for wallet_file in self.wallets_dir.glob("*.json.gz"):
                try:
                    with gzip.open(wallet_file, 'rt') as f:
                        wallet_data = json.load(f)
                        memory = self._dict_to_memory(wallet_data)
                        if memory:
                            self.memories[memory.memory_id] = memory
                            loaded_count += 1
                except Exception as e:
                    logger.warning(f"Failed to load wallet {wallet_file}: {e}")

            self.metrics.total_memories = loaded_count
            self.metrics.total_disk_reads = loaded_count
            logger.info(f"Loaded {loaded_count} memories from disk",
                       storage_path=str(self.storage_path))

        except Exception as e:
            logger.error(f"Failed to load memories from disk: {e}")

    def _dict_to_memory(self, data: Dict[str, Any]) -> Optional[Memory]:
        """
        Convert dictionary to Memory object.

        Args:
            data: Dictionary with memory data

        Returns:
            Memory object or None if conversion fails
        """
        try:
            metadata_dict = data.get('metadata', {})

            # Parse importance
            importance_val = metadata_dict.get('importance', 2)
            if isinstance(importance_val, int):
                importance = MemoryImportance(importance_val)
            else:
                importance = MemoryImportance.MEDIUM

            metadata = MemoryMetadata(
                created_at=datetime.fromisoformat(metadata_dict.get('created_at', datetime.now().isoformat())),
                last_accessed=datetime.fromisoformat(metadata_dict.get('last_accessed', datetime.now().isoformat())),
                access_count=metadata_dict.get('access_count', 0),
                importance=importance,
                tags=metadata_dict.get('tags', []),
                source=metadata_dict.get('source', ''),
                confidence=metadata_dict.get('confidence', 1.0),
                related_memories=metadata_dict.get('related_memories', [])
            )

            # Parse memory type
            memory_type_str = data.get('memory_type', 'general')
            try:
                memory_type = MemoryType(memory_type_str)
            except ValueError:
                memory_type = MemoryType.GENERAL

            # Parse embedding
            embedding = None
            if data.get('embedding'):
                embedding = np.array(data['embedding'], dtype='float32')

            return Memory(
                memory_id=data['memory_id'],
                memory_type=memory_type,
                content=data['content'],
                metadata=metadata,
                embedding=embedding
            )

        except Exception as e:
            logger.warning(f"Failed to convert dict to memory: {e}")
            return None

    async def store(self, memory: Memory) -> bool:
        """
        Store a memory with async FAISS indexing.

        UPDATES: Adds async FAISS indexing alongside in-memory storage

        Args:
            memory: Memory object to store

        Returns:
            True if stored successfully
        """
        start_time = time.perf_counter()

        try:
            # Generate embedding if not provided
            if memory.embedding is None:
                memory.embedding = self._generate_embedding(memory.content)

            # Store in memory
            self.memories[memory.memory_id] = memory
            self.embeddings_cache[memory.memory_id] = memory.embedding

            # Index in FAISS if enabled
            if self.enable_faiss and self.write_buffer:
                metadata = {
                    'memory_type': memory.memory_type.value if isinstance(memory.memory_type, MemoryType) else memory.memory_type,
                    'importance': memory.metadata.importance.value if isinstance(memory.metadata.importance, MemoryImportance) else memory.metadata.importance,
                    'created_at': memory.metadata.created_at.isoformat(),
                    'tags': memory.metadata.tags,
                    'confidence': memory.metadata.confidence
                }

                # Add content preview for retrieval
                if isinstance(memory.content, str):
                    metadata['content_preview'] = memory.content[:200]
                elif isinstance(memory.content, dict):
                    metadata['content_preview'] = json.dumps(memory.content, default=str)[:200]

                await self.write_buffer.enqueue_write(
                    memory.memory_id,
                    memory.embedding,
                    metadata
                )

            # Update metrics
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.write_latencies.append(latency_ms)
            if len(self.write_latencies) > 1000:
                self.write_latencies = self.write_latencies[-1000:]
            self.metrics.avg_write_latency_ms = sum(self.write_latencies) / len(self.write_latencies)
            self.metrics.total_memories = len(self.memories)

            logger.debug(f"Stored memory {memory.memory_id}", latency_ms=round(latency_ms, 2))
            return True

        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return False

    async def store_batch(self, memories: List[Memory]) -> int:
        """
        Store multiple memories in batch.

        More efficient than individual stores for bulk operations.

        Args:
            memories: List of Memory objects

        Returns:
            Number of memories stored
        """
        stored = 0
        items = []

        for memory in memories:
            # Generate embedding if needed
            if memory.embedding is None:
                memory.embedding = self._generate_embedding(memory.content)

            # Store in memory
            self.memories[memory.memory_id] = memory
            self.embeddings_cache[memory.memory_id] = memory.embedding

            # Prepare for FAISS batch
            if self.enable_faiss:
                metadata = {
                    'memory_type': memory.memory_type.value if isinstance(memory.memory_type, MemoryType) else memory.memory_type,
                    'importance': memory.metadata.importance.value if isinstance(memory.metadata.importance, MemoryImportance) else memory.metadata.importance,
                    'created_at': memory.metadata.created_at.isoformat()
                }
                items.append((memory.memory_id, memory.embedding, metadata))

            stored += 1

        # Batch enqueue to FAISS
        if self.enable_faiss and self.write_buffer and items:
            await self.write_buffer.enqueue_batch(items)

        self.metrics.total_memories = len(self.memories)
        logger.debug(f"Stored {stored} memories in batch")

        return stored

    async def retrieve(self, memory_id: str) -> Optional[Memory]:
        """
        Retrieve a memory by ID.

        Args:
            memory_id: Memory ID to retrieve

        Returns:
            Memory object or None if not found
        """
        start_time = time.perf_counter()

        memory = self.memories.get(memory_id)

        if memory:
            memory.metadata.update_access()

            # Update metrics
            latency_ms = (time.perf_counter() - start_time) * 1000
            self.read_latencies.append(latency_ms)
            if len(self.read_latencies) > 1000:
                self.read_latencies = self.read_latencies[-1000:]
            self.metrics.avg_read_latency_ms = sum(self.read_latencies) / len(self.read_latencies)

        return memory

    async def query(self, query: MemoryQuery) -> List[Memory]:
        """
        Query memories with optional semantic search.

        UPDATES: Uses sharded FAISS for semantic search

        Args:
            query: Query specification

        Returns:
            List of matching memories
        """
        results = []

        # Semantic search if query text provided and FAISS enabled
        if query.query_text and self.enable_faiss and self.vector_store:
            query_embedding = self._generate_embedding(query.query_text)

            search_results = await self.vector_store.search(
                query_embedding,
                k=query.limit * 2,  # Get more for filtering
                include_metadata=True
            )

            # Convert to memories
            for result in search_results:
                similarity = 1.0 / (1.0 + result.distance)
                if similarity < query.similarity_threshold:
                    continue

                # Find memory by ID
                for mid, memory in self.memories.items():
                    if hashlib.md5(mid.encode()).digest()[:8] == result.vector_id.to_bytes(8, 'big', signed=True) if result.vector_id >= 0 else False:
                        results.append(memory)
                        break
        else:
            # Fall back to in-memory filtering
            results = list(self.memories.values())

        # Filter by memory type
        if query.memory_types:
            results = [m for m in results if m.memory_type in query.memory_types]

        # Filter by tags
        if query.tags:
            results = [m for m in results if any(t in m.metadata.tags for t in query.tags)]

        # Filter by importance
        results = [m for m in results if m.metadata.importance.value >= query.min_importance.value]

        # Filter by time range
        if query.time_range:
            start_time, end_time = query.time_range
            results = [m for m in results if start_time <= m.metadata.created_at <= end_time]

        # Sort by importance and recency
        results.sort(key=lambda m: (m.metadata.importance.value, m.metadata.created_at), reverse=True)

        return results[:query.limit]

    async def delete(self, memory_id: str) -> bool:
        """
        Delete a memory.

        Args:
            memory_id: ID of memory to delete

        Returns:
            True if deleted
        """
        if memory_id in self.memories:
            del self.memories[memory_id]
            self.embeddings_cache.pop(memory_id, None)

            if self.vector_store:
                await self.vector_store.remove_embedding(memory_id)

            self.metrics.total_memories = len(self.memories)
            return True
        return False

    def persist_memory_to_disk(self):
        """
        Persist important memories to disk storage.

        Called by the consolidator to save high-value memories
        to persistent storage. Uses compressed formats for efficiency.
        """
        try:
            saved_count = 0

            for memory in self.memories.values():
                try:
                    # Determine storage location based on type and importance
                    if memory.memory_type == MemoryType.PATTERN:
                        if (memory.metadata.importance.value >= MemoryImportance.HIGH.value and
                            memory.metadata.confidence >= 0.8):
                            file_path = self.patterns_dir / f"{memory.memory_id}.json.gz"
                            with gzip.open(file_path, 'wt') as f:
                                json.dump(memory.to_dict(), f)
                            saved_count += 1

                    elif memory.memory_type == MemoryType.WALLET:
                        content = memory.content
                        if isinstance(content, dict) and content.get('is_king_maker', False):
                            # King Makers get pickle for full fidelity
                            file_path = self.kings_dir / f"{memory.memory_id}.pkl"
                            with open(file_path, 'wb') as f:
                                pickle.dump(memory, f)
                            saved_count += 1
                        elif memory.metadata.importance.value >= MemoryImportance.MEDIUM.value:
                            # Regular wallets get compressed JSON
                            file_path = self.wallets_dir / f"{memory.memory_id}.json.gz"
                            with gzip.open(file_path, 'wt') as f:
                                json.dump(memory.to_dict(), f)
                            saved_count += 1

                    elif memory.memory_type in [MemoryType.SEMANTIC, MemoryType.PROCEDURAL, MemoryType.INSIGHT]:
                        if memory.metadata.importance.value >= MemoryImportance.MEDIUM.value:
                            file_path = self.insights_dir / f"{memory.memory_id}.json"
                            with open(file_path, 'w') as f:
                                json.dump(memory.to_dict(), f)
                            saved_count += 1

                    elif memory.memory_type == MemoryType.RULE:
                        file_path = self.rules_dir / f"{memory.memory_id}.json"
                        with open(file_path, 'w') as f:
                            json.dump(memory.to_dict(), f)
                        saved_count += 1

                except Exception as e:
                    logger.warning(f"Failed to persist memory {memory.memory_id}: {e}")

            self.metrics.total_disk_writes += saved_count
            logger.info(f"Persisted {saved_count} memories to disk")

        except Exception as e:
            logger.error(f"Failed to persist memories: {e}")

    async def persist_memory_to_disk_async(self, partition: str, memory_id: str, 
                                           data: Dict, embedding: Optional[np.ndarray] = None):
        """
        Async version of memory persistence with FAISS indexing.

        UPDATES: Add async FAISS indexing alongside disk persistence

        Args:
            partition: Memory partition (patterns, insights, wallets, rules)
            memory_id: Unique memory ID
            data: Memory data to persist
            embedding: Optional embedding vector
        """
        # Persist to disk
        try:
            if partition == 'patterns':
                file_path = self.patterns_dir / f"{memory_id}.json.gz"
                with gzip.open(file_path, 'wt') as f:
                    json.dump(data, f)
            elif partition == 'wallets':
                file_path = self.wallets_dir / f"{memory_id}.json.gz"
                with gzip.open(file_path, 'wt') as f:
                    json.dump(data, f)
            elif partition == 'insights':
                file_path = self.insights_dir / f"{memory_id}.json"
                with open(file_path, 'w') as f:
                    json.dump(data, f)
            elif partition == 'rules':
                file_path = self.rules_dir / f"{memory_id}.json"
                with open(file_path, 'w') as f:
                    json.dump(data, f)

            self.metrics.total_disk_writes += 1

        except Exception as e:
            logger.error(f"Failed to persist {memory_id} to disk: {e}")

        # Index in FAISS if embedding provided
        if embedding is not None and self.enable_faiss and self.write_buffer:
            await self.write_buffer.enqueue_write(
                f"{partition}:{memory_id}",
                np.array(embedding).astype('float32'),
                data
            )

    def get_metrics(self) -> StorageMetrics:
        """
        Get storage performance metrics.

        Returns:
            StorageMetrics with current statistics
        """
        # Calculate disk usage
        disk_usage = 0
        for dir_path in [self.patterns_dir, self.kings_dir, self.insights_dir,
                         self.wallets_dir, self.rules_dir, self.faiss_dir]:
            for file_path in dir_path.glob("**/*"):
                if file_path.is_file():
                    disk_usage += file_path.stat().st_size

        # Get FAISS vector count
        faiss_vectors = 0
        if self.vector_store:
            faiss_metrics = self.vector_store.get_metrics()
            faiss_vectors = faiss_metrics.total_vectors

        return StorageMetrics(
            total_memories=len(self.memories),
            total_disk_writes=self.metrics.total_disk_writes,
            total_disk_reads=self.metrics.total_disk_reads,
            avg_write_latency_ms=round(self.metrics.avg_write_latency_ms, 3),
            avg_read_latency_ms=round(self.metrics.avg_read_latency_ms, 3),
            disk_usage_mb=round(disk_usage / 1e6, 2),
            faiss_vectors=faiss_vectors,
            cache_hit_rate=0.0  # TODO: Implement cache hit tracking
        )

    def get_memory_count(self) -> int:
        """Get total number of memories."""
        return len(self.memories)

    def get_memories_by_type(self, memory_type: MemoryType) -> List[Memory]:
        """Get all memories of a specific type."""
        return [m for m in self.memories.values() if m.memory_type == memory_type]


# Backward compatibility alias
EternalMemoryStorage = MemoryStorage


if __name__ == "__main__":
    # Quick test
    import asyncio

    async def test():
        print("Memory Storage Test")
        print("=" * 40)

        # Create storage
        storage = MemoryStorage(
            storage_path="/tmp/test_memory_storage",
            num_shards=4,
            embedding_dim=384
        )
        await storage.initialize()

        # Store some memories
        print("Storing memories...")
        for i in range(100):
            memory = Memory(
                memory_id=f"test_mem_{i}",
                memory_type=MemoryType.PATTERN if i % 2 == 0 else MemoryType.INSIGHT,
                content=f"Test memory content {i} about blockchain analysis",
                metadata=MemoryMetadata(
                    importance=MemoryImportance.HIGH if i % 3 == 0 else MemoryImportance.MEDIUM,
                    tags=["test", "blockchain"],
                    confidence=0.9
                )
            )
            await storage.store(memory)

        # Wait for writes to flush
        if storage.write_buffer:
            await storage.write_buffer.wait_for_flush()

        # Query
        print("Querying...")
        query = MemoryQuery(
            query_text="blockchain analysis patterns",
            limit=10,
            similarity_threshold=0.3
        )
        results = await storage.query(query)
        print(f"Found {len(results)} results")

        # Metrics
        print("\nMetrics:")
        metrics = storage.get_metrics()
        print(f"  Total memories: {metrics.total_memories}")
        print(f"  FAISS vectors: {metrics.faiss_vectors}")
        print(f"  Avg write latency: {metrics.avg_write_latency_ms:.3f}ms")
        print(f"  Disk usage: {metrics.disk_usage_mb:.2f}MB")

        # Shutdown
        await storage.shutdown()
        print("\nTest complete!")

    asyncio.run(test())
