
"""Memory consolidator for managing memory lifecycle and consolidation."""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import asyncio
import numpy as np
from sklearn.cluster import DBSCAN
from concurrent.futures import ThreadPoolExecutor
import structlog
import uuid
import hashlib

from ..memory_models import Memory, MemoryType, MemoryImportance
from ..storage import MemoryStorage
from redis import Redis

logger = structlog.get_logger(__name__)


class MemoryConsolidator:
    """Consolidates and manages agent memories over time."""

    def __init__(self, storage: MemoryStorage, redis_client: Redis, config: Optional[Dict[str, Any]] = None):
        """Initialize the memory consolidator.

        Args:
            storage: Memory storage backend
            redis_client: Redis client for raw memory queue
            config: Configuration for consolidation
        """
        self.storage = storage
        self.redis = redis_client
        self.config = config or {
            'consolidation_interval_hours': 24,
            'importance_decay_rate': 0.95,
            'min_importance_to_keep': MemoryImportance.LOW,
            'max_memories': 10000,
            'pattern_detection_enabled': True,
            'similarity_threshold': 0.85,
            'batch_size': 100
        }

        # Thread pool for blocking CPU operations
        self.thread_pool = ThreadPoolExecutor(max_workers=2)

    async def consolidate(self) -> Dict[str, Any]:
        """Run memory consolidation process.

        Main loop that:
        - Fetches raw, unprocessed memories from Redis list (memory:raw)
        - Merges similar memories
        - Decays importance over time
        - Removes low-value memories
        - Extracts patterns from episodic memories
        - Updates memory relationships

        Returns:
            Consolidation report with statistics
        """
        report = {
            'timestamp': datetime.now().isoformat(),
            'raw_memories_processed': 0,
            'patterns_merged': 0,
            'patterns_extracted': 0,
            'memories_decayed': 0,
            'memories_pruned': 0
        }

        try:
            # Step 1: Fetch raw memories from Redis
            raw_memories = []
            for _ in range(self.config['batch_size']):
                raw_data = self.redis.lpop('memory:raw')
                if not raw_data:
                    break
                try:
                    import json
                    memory_dict = json.loads(raw_data)
                    memory = self._dict_to_memory(memory_dict)
                    if memory:
                        await self.storage.store(memory)
                        raw_memories.append(memory)
                        report['raw_memories_processed'] += 1
                except Exception as e:
                    logger.warning(f"Failed to process raw memory: {e}")

            # Step 2: Merge similar patterns
            merged_count = await self.merge_similar_memories_batch()
            report['patterns_merged'] = merged_count

            # Step 3: Extract new patterns from episodic memories
            new_patterns = await self.extract_patterns()
            report['patterns_extracted'] = len(new_patterns)

            # Step 4: Decay importance of old memories
            decayed_count = await self.decay_importance()
            report['memories_decayed'] = decayed_count

            # Step 5: Prune low-value memories
            pruned_count = await self.prune_memories()
            report['memories_pruned'] = pruned_count

            # Step 6: Persist important memories to disk
            self.storage.persist_memory_to_disk()

            logger.info("Consolidation complete", **report)
            return report

        except Exception as e:
            logger.error(f"Consolidation failed: {e}", exc_info=True)
            raise

    async def merge_similar_memories(self, memories: List[Memory]) -> Optional[Memory]:
        """Merge similar memories into a consolidated memory.

        Args:
            memories: List of similar memories to merge

        Returns:
            Consolidated memory
        """
        if not memories:
            return None

        if len(memories) == 1:
            return memories[0]

        # Combine content from all memories
        combined_content = {}
        for memory in memories:
            combined_content.update(memory.content)

        # Average embeddings if present
        combined_embedding = None
        embeddings = [m.embedding for m in memories if m.embedding]
        if embeddings:
            combined_embedding = np.mean(embeddings, axis=0).tolist()

        # Merge metadata
        all_tags = set()
        all_sources = set()
        total_confidence = 0.0
        max_importance = MemoryImportance.LOW

        for memory in memories:
            all_tags.update(memory.metadata.tags)
            if memory.metadata.source:
                all_sources.add(memory.metadata.source)
            total_confidence += memory.metadata.confidence
            if memory.metadata.importance.value > max_importance.value:
                max_importance = memory.metadata.importance

        # Create consolidated memory
        consolidated = Memory.create(
            memory_type=MemoryType.PATTERN,
            content=combined_content,
            importance=max_importance,
            tags=list(all_tags)
        )

        # Set merged properties
        consolidated.metadata.confidence = total_confidence / len(memories)
        consolidated.metadata.source = f"consolidated_from_{len(memories)}_memories"
        consolidated.embedding = combined_embedding

        # Track source memory IDs
        consolidated.metadata.related_memories = [m.memory_id for m in memories]

        logger.info(f"Merged {len(memories)} memories into {consolidated.memory_id}")
        return consolidated

    async def merge_similar_memories_batch(self) -> int:
        """Batch merge similar pattern memories using clustering.

        Returns:
            Number of patterns merged
        """
        pattern_memories = [
            m for m in self.storage.memories.values()
            if m.memory_type == MemoryType.PATTERN and m.embedding
        ][:self.config['batch_size']]

        if len(pattern_memories) < 2:
            return 0

        # Extract embeddings for clustering
        embeddings = np.array([m.embedding for m in pattern_memories])
        memory_ids = [m.memory_id for m in pattern_memories]

        # Use DBSCAN to find similar patterns (thread pool for blocking operation)
        try:
            loop = asyncio.get_event_loop()
            dbscan = DBSCAN(eps=1.0 - self.config['similarity_threshold'], min_samples=2)
            labels = await loop.run_in_executor(
                self.thread_pool,
                dbscan.fit_predict,
                embeddings
            )
        except Exception as e:
            logger.warning(f"Clustering failed: {e}")
            return 0

        # Group memories by cluster
        clusters = {}
        for idx, label in enumerate(labels):
            if label >= 0:  # Noise points (-1) are ignored
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(pattern_memories[idx])

        # Merge each cluster
        merged_count = 0
        for cluster_id, cluster_memories in clusters.items():
            if len(cluster_memories) >= 2:
                consolidated = await self.merge_similar_memories(cluster_memories)
                if consolidated:
                    # Store consolidated memory
                    await self.storage.store(consolidated)
                    # Remove original memories
                    for memory in cluster_memories:
                        await self.storage.delete(memory.memory_id)
                    merged_count += 1

        return merged_count

    async def extract_patterns(self) -> List[Memory]:
        """Extract patterns from episodic memories.

        Analyzes episodic memories, identifies recurring patterns,
        creates pattern memories, and links to source episodes.

        Returns:
            List of pattern memories
        """
        pattern_memories = []

        try:
            # Get episodic memories
            episodic_memories = [
                m for m in self.storage.memories.values()
                if m.memory_type == MemoryType.EPISODIC
            ][:self.config['batch_size']]

            if not episodic_memories:
                return pattern_memories

            # Pattern 1: Early buyer detection (wallets buying within 60s)
            early_buyers = []
            for memory in episodic_memories:
                content = memory.content
                if 'seconds_after_launch' in content and content['seconds_after_launch'] < 60:
                    early_buyers.append(memory)

            if len(early_buyers) >= 3:
                pattern = Memory.create(
                    memory_type=MemoryType.PATTERN,
                    content={
                        'pattern_type': 'early_buyer_behavior',
                        'description': 'Wallets that consistently buy tokens within 60 seconds of launch',
                        'occurrence_count': len(early_buyers),
                        'avg_seconds': np.mean([m.content.get('seconds_after_launch', 0) for m in early_buyers])
                    },
                    importance=MemoryImportance.HIGH,
                    tags=['insider', 'early_buyer', 'suspicious']
                )
                pattern.metadata.related_memories = [m.memory_id for m in early_buyers]
                pattern_memories.append(pattern)

            # Pattern 2: King Maker detection (high graduation rate)
            king_maker_candidates = []
            for memory in episodic_memories:
                content = memory.content
                if 'graduation_rate' in content and content['graduation_rate'] > 0.6:
                    king_maker_candidates.append(memory)

            if len(king_maker_candidates) >= 2:
                pattern = Memory.create(
                    memory_type=MemoryType.PATTERN,
                    content={
                        'pattern_type': 'king_maker_behavior',
                        'description': 'Wallets with >60% token graduation rate',
                        'occurrence_count': len(king_maker_candidates),
                        'avg_graduation_rate': np.mean([m.content.get('graduation_rate', 0) for m in king_maker_candidates])
                    },
                    importance=MemoryImportance.CRITICAL,
                    tags=['king_maker', 'elite', 'insider']
                )
                pattern.metadata.related_memories = [m.memory_id for m in king_maker_candidates]
                pattern_memories.append(pattern)

            # Pattern 3: Sybil network (common funding source)
            funding_groups = {}
            for memory in episodic_memories:
                content = memory.content
                if 'funding_source' in content:
                    funding = content['funding_source']
                    if funding not in funding_groups:
                        funding_groups[funding] = []
                    funding_groups[funding].append(memory)

            for funding, group_memories in funding_groups.items():
                if len(group_memories) >= 3:
                    pattern = Memory.create(
                        memory_type=MemoryType.PATTERN,
                        content={
                            'pattern_type': 'sybil_network',
                            'description': f'Coordinated wallets funded from {funding}',
                            'funding_source': funding,
                            'wallet_count': len(group_memories)
                        },
                        importance=MemoryImportance.HIGH,
                        tags=['sybil', 'coordinated', 'suspicious']
                    )
                    pattern.metadata.related_memories = [m.memory_id for m in group_memories]
                    pattern_memories.append(pattern)

            # Store extracted patterns
            for pattern in pattern_memories:
                await self.storage.store(pattern)

            logger.info(f"Extracted {len(pattern_memories)} patterns")

        except Exception as e:
            logger.error(f"Pattern extraction failed: {e}", exc_info=True)

        return pattern_memories

    async def decay_importance(self) -> int:
        """Decay importance of old memories.

        Calculates time-based decay, updates importance scores,
        removes memories below threshold.

        Returns:
            Number of memories decayed
        """
        decayed_count = 0
        decay_rate = self.config['importance_decay_rate']
        min_importance = self.config['min_importance_to_keep'].value

        now = datetime.now()
        memories_to_delete = []

        for memory in self.storage.memories.values():
            # Calculate age in days
            age_days = (now - memory.metadata.created_at).total_seconds() / 86400

            if age_days >= 7:  # Only decay memories older than 7 days
                # Decay importance score
                old_importance = memory.metadata.importance.value

                # Calculate decayed importance
                decayed_importance = max(
                    min_importance,
                    int(old_importance * (decay_rate ** (age_days / 7)))
                )

                if decayed_importance < old_importance:
                    memory.metadata.importance = MemoryImportance(decayed_importance)
                    decayed_count += 1

                # Mark for deletion if below threshold
                if decayed_importance < min_importance:
                    memories_to_delete.append(memory.memory_id)

        # Delete memories below threshold
        for memory_id in memories_to_delete:
            await self.storage.delete(memory_id)
            decayed_count += 1

        logger.info(f"Decayed {decayed_count} memories")
        return decayed_count

    async def prune_memories(self) -> int:
        """Remove low-value memories to maintain storage limits.

        Sorts by value/importance, keeps most valuable memories,
        removes low-value memories.

        Returns:
            Number of memories pruned
        """
        pruned_count = 0
        max_memories = self.config['max_memories']

        current_count = len(self.storage.memories)
        if current_count <= max_memories:
            return 0

        # Calculate value scores for all memories
        memory_values = []
        for memory_id, memory in self.storage.memories.items():
            value = self.calculate_memory_value(memory)
            memory_values.append((value, memory_id))

        # Sort by value (ascending) - lowest value first
        memory_values.sort(key=lambda x: x[0])

        # Prune lowest value memories to stay under limit
        num_to_prune = current_count - max_memories
        for _, memory_id in memory_values[:num_to_prune]:
            await self.storage.delete(memory_id)
            pruned_count += 1

        logger.info(f"Pruned {pruned_count} memories to stay under limit")
        return pruned_count

    def calculate_memory_value(self, memory: Memory) -> float:
        """Calculate the value score of a memory.

        Value calculation based on:
        - Importance weight (40%)
        - Access frequency weight (25%)
        - Recency weight (20%)
        - Relationship weight (15%)

        Args:
            memory: Memory to evaluate

        Returns:
            Value score (0.0 to 1.0)
        """
        # 1. Importance weight (40%)
        importance_score = memory.metadata.importance.value / 4.0  # Normalize to 0-1
        importance_weight = 0.40

        # 2. Access frequency weight (25%)
        # Logarithmic scale to prevent excessive weighting
        access_score = min(1.0, np.log1p(memory.metadata.access_count) / 5.0)
        access_weight = 0.25

        # 3. Recency weight (20%)
        age_hours = (datetime.now() - memory.metadata.created_at).total_seconds() / 3600
        # Newer memories get higher scores
        recency_score = max(0.0, 1.0 - (age_hours / 168.0))  # Decay over 7 days
        recency_weight = 0.20

        # 4. Relationship weight (15%)
        # Memories with more relationships are more valuable
        relationship_score = min(1.0, len(memory.metadata.related_memories) / 10.0)
        relationship_weight = 0.15

        # Confidence modifier (0.5 to 1.5 multiplier)
        confidence_modifier = 0.5 + memory.metadata.confidence

        # Calculate weighted sum
        value = (
            importance_score * importance_weight +
            access_score * access_weight +
            recency_score * recency_weight +
            relationship_score * relationship_weight
        ) * confidence_modifier

        return min(1.0, value)

    def _dict_to_memory(self, data: Dict[str, Any]) -> Optional[Memory]:
        """Convert dictionary to Memory object."""
        try:
            metadata = data['metadata']
            memory_metadata = type('Metadata', (), {
                'created_at': datetime.fromisoformat(metadata['created_at']),
                'last_accessed': datetime.fromisoformat(metadata['last_accessed']),
                'access_count': metadata.get('access_count', 0),
                'importance': MemoryImportance(metadata.get('importance', 2)),
                'tags': metadata.get('tags', []),
                'source': metadata.get('source', ''),
                'confidence': metadata.get('confidence', 1.0),
                'related_memories': metadata.get('related_memories', []),
                'update_access': lambda: None
            })()

            return Memory(
                memory_id=data['memory_id'],
                memory_type=MemoryType(data['memory_type']),
                content=data['content'],
                metadata=memory_metadata,
                embedding=data.get('embedding')
            )
        except Exception as e:
            logger.warning(f"Failed to convert dict to memory: {e}")
            return None
