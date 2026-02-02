"""Enhanced memory consolidator with automatic pattern learning and consolidation."""

import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import asyncio
import numpy as np
from sklearn.cluster import DBSCAN
from collections import defaultdict
import json
from pathlib import Path
import structlog

from ..memory_models import Memory, MemoryType, MemoryImportance
from ..enhanced_storage import EnhancedMemoryStorage
from concurrent.futures import ThreadPoolExecutor


# FIXED: Add batch size to control workload and prevent timeouts
CONSOLIDATION_BATCH_SIZE = 100

logger = structlog.get_logger()


class ConsolidationMetrics:
    """Metrics for tracking consolidation performance."""

    def __init__(self):
        self.consolidations_performed = 0
        self.patterns_merged = 0
        self.false_positives_removed = 0
        self.memories_pruned = 0
        self.accuracy_improvements = []
        self.last_consolidation = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'consolidations_performed': self.consolidations_performed,
            'patterns_merged': self.patterns_merged,
            'false_positives_removed': self.false_positives_removed,
            'memories_pruned': self.memories_pruned,
            'avg_accuracy_improvement': np.mean(self.accuracy_improvements) if self.accuracy_improvements else 0.0,
            'last_consolidation': self.last_consolidation.isoformat() if self.last_consolidation else None
        }


class EnhancedMemoryConsolidator:
    """Enhanced memory consolidator with automatic pattern learning and consolidation."""

    def __init__(self, storage: EnhancedMemoryStorage, config: Optional[Dict[str, Any]] = None):
        """Initialize the enhanced memory consolidator.

        Args:
            storage: Enhanced memory storage backend
            config: Configuration for consolidation
        """
        self.storage = storage
        self.config = config or {
            'consolidation_interval_hours': 24,
            'similarity_threshold': 0.85,  # High threshold for merging
            'min_cluster_size': 2,
            'max_age_days': 30,
            'false_positive_threshold': 0.3,  # Confidence threshold
            'pattern_weight_decay': 0.95,
            'auto_consolidation_enabled': True
        }

        self.metrics = ConsolidationMetrics()
        self.consolidation_log_path = Path("/a0/usr/projects/godmodescanner/data/memory/consolidation_log.json")
        self._load_metrics()

        # FIXED: Add thread pool for blocking CPU operations
        self.thread_pool = ThreadPoolExecutor(max_workers=2)

    async def consolidate(self) -> Dict[str, Any]:
        """Run comprehensive memory consolidation process.

        Returns:
            Consolidation report
        """
        total_start = time.perf_counter()
        logger.info("Starting memory consolidation")

        report = {
            'timestamp': datetime.now().isoformat(),
            'steps': []
        }

        # FIXED: Add timing logs for each step
        try:
            # Step 1: Reorganize memory tiers
            logger.info("Step 1/6: Reorganizing memory tiers...")
            step1_start = time.perf_counter()
            await self.storage.reorganize_tiers()
            step1_duration = time.perf_counter() - step1_start
            logger.info(f"Step 1 complete in {step1_duration:.3f}s")
            report['steps'].append('tier_reorganization')

            # Step 2: Merge similar patterns
            logger.info("Step 2/6: Merging similar patterns...")
            step2_start = time.perf_counter()
            merged_count = await self.merge_similar_patterns()
            step2_duration = time.perf_counter() - step2_start
            logger.info(f"Step 2 complete: {merged_count} patterns merged in {step2_duration:.3f}s")
            report['patterns_merged'] = merged_count
            report['steps'].append('pattern_merging')

            # Step 3: Remove false positives
            logger.info("Step 3/6: Removing false positives...")
            step3_start = time.perf_counter()
            removed_count = await self.remove_false_positives()
            step3_duration = time.perf_counter() - step3_start
            logger.info(f"Step 3 complete: {removed_count} false positives removed in {step3_duration:.3f}s")
            report['false_positives_removed'] = removed_count
            report['steps'].append('false_positive_removal')

            # Step 4: Decay pattern weights
            logger.info("Step 4/6: Decaying pattern weights...")
            step4_start = time.perf_counter()
            await self.decay_pattern_weights()
            step4_duration = time.perf_counter() - step4_start
            logger.info(f"Step 4 complete in {step4_duration:.3f}s")
            report['steps'].append('weight_decay')

            # Step 5: Prune old memories
            logger.info("Step 5/6: Pruning old memories...")
            step5_start = time.perf_counter()
            await self.storage.prune_old_memories(self.config['max_age_days'])
            step5_duration = time.perf_counter() - step5_start
            logger.info(f"Step 5 complete in {step5_duration:.3f}s")
            report['steps'].append('memory_pruning')

            # Step 6: Extract new patterns
            logger.info("Step 6/6: Extracting new patterns...")
            step6_start = time.perf_counter()
            new_patterns = await self.extract_patterns()
            step6_duration = time.perf_counter() - step6_start
            logger.info(f"Step 6 complete: {len(new_patterns)} new patterns extracted in {step6_duration:.3f}s")
            report['new_patterns_extracted'] = len(new_patterns)
            report['steps'].append('pattern_extraction')

            # Update metrics
            self.metrics.consolidations_performed += 1
            self.metrics.patterns_merged += merged_count
            self.metrics.false_positives_removed += removed_count
            self.metrics.last_consolidation = datetime.now()

            # Save metrics
            self._save_metrics()

            # Generate report
            report['metrics'] = self.metrics.to_dict()
            report['storage_stats'] = self.storage.get_statistics()

            total_duration = time.perf_counter() - total_start
            logger.info(f"Consolidation complete in {total_duration:.3f}s")
            return report

        except Exception as e:
            total_duration = time.perf_counter() - total_start
            logger.error(f"Consolidation failed after {total_duration:.3f}s: {e}", exc_info=True)
            raise

    async def merge_similar_patterns(self) -> int:
        """Merge similar pattern memories using clustering.

        Returns:
            Number of patterns merged
        """
        # FIXED: Apply batch size limit to prevent timeout
        pattern_memories = [
            m for m in self.storage.memories.values()
            if m.memory_type == MemoryType.PATTERN
        ]

        # FIXED: Limit processing to prevent timeout on large datasets
        pattern_memories = pattern_memories[:CONSOLIDATION_BATCH_SIZE]
        logger.info(f"Processing {len(pattern_memories)} pattern memories for merging (batch size: {CONSOLIDATION_BATCH_SIZE})")

        if len(pattern_memories) < 2:
            return 0

        # Extract embeddings
        embeddings = []
        memory_ids = []

        for memory in pattern_memories:
            if memory.embedding:
                embeddings.append(memory.embedding)
                memory_ids.append(memory.memory_id)

        if len(embeddings) < 2:
            return 0

        # FIXED: Move blocking DBSCAN clustering to thread pool
        try:
            loop = asyncio.get_event_loop()
            embeddings_array = np.array(embeddings)
            clustering = await loop.run_in_executor(
                self.thread_pool,
                lambda: DBSCAN(
                    eps=1.0 - self.config['similarity_threshold'],
                    min_samples=self.config['min_cluster_size'],
                    metric='cosine'
                ).fit(embeddings_array)
            )
        except Exception as e:
            logger.error(f"DBSCAN clustering failed: {e}")
            return 0

        # Group memories by cluster
        clusters = defaultdict(list)
        for idx, label in enumerate(clustering.labels_):
            if label != -1:  # Ignore noise points
                clusters[label].append(memory_ids[idx])

        # Merge clusters
        merged_count = 0
        for cluster_id, cluster_memory_ids in clusters.items():
            if len(cluster_memory_ids) >= self.config['min_cluster_size']:
                cluster_memories = [self.storage.memories[mid] for mid in cluster_memory_ids]
                merged_memory = await self._merge_memories(cluster_memories)

                # Store merged memory
                await self.storage.store(merged_memory)

                # Delete original memories
                for memory_id in cluster_memory_ids:
                    await self.storage.delete(memory_id)

                merged_count += len(cluster_memory_ids) - 1

        return merged_count

    async def _merge_memories(self, memories: List[Memory]) -> Memory:
        """Merge multiple memories into a consolidated memory.

        Args:
            memories: List of memories to merge

        Returns:
            Merged memory
        """
        # Combine content
        merged_content = {
            'pattern_type': memories[0].content.get('pattern_type', 'unknown'),
            'occurrences': sum(m.content.get('occurrences', 1) for m in memories),
            'confidence': np.mean([m.metadata.confidence for m in memories]),
            'sources': [m.memory_id for m in memories],
            'merged_at': datetime.now().isoformat()
        }

        # Merge specific pattern data
        if 'wallet_addresses' in memories[0].content:
            all_wallets = set()
            for m in memories:
                all_wallets.update(m.content.get('wallet_addresses', []))
            merged_content['wallet_addresses'] = list(all_wallets)

        # FIXED: Move numpy operations to thread pool
        try:
            loop = asyncio.get_event_loop()
            embeddings = [np.array(m.embedding) for m in memories if m.embedding]
            if embeddings:
                merged_embedding = await loop.run_in_executor(
                    self.thread_pool,
                    lambda: np.mean(embeddings, axis=0).tolist()
                )
            else:
                merged_embedding = None
        except Exception as e:
            logger.error(f"Embedding merge failed: {e}")
            merged_embedding = None

        # Create merged memory
        merged_memory = Memory.create(
            memory_type=MemoryType.PATTERN,
            content=merged_content,
            importance=max(m.metadata.importance for m in memories),
            tags=list(set(tag for m in memories for tag in m.metadata.tags))
        )
        merged_memory.embedding = merged_embedding
        merged_memory.metadata.confidence = merged_content['confidence']

        return merged_memory

    async def remove_false_positives(self) -> int:
        """Remove pattern memories with low confidence (false positives).

        Returns:
            Number of false positives removed
        """
        removed_count = 0

        # FIXED: Limit to batch size to prevent timeout
        memories_to_check = list(self.storage.memories.items())[:CONSOLIDATION_BATCH_SIZE]
        logger.info(f"Checking {len(memories_to_check)} memories for false positives")

        for memory_id, memory in memories_to_check:
            if memory.memory_type == MemoryType.PATTERN:
                # Check confidence threshold
                if memory.metadata.confidence < self.config['false_positive_threshold']:
                    await self.storage.delete(memory_id)
                    removed_count += 1

        return removed_count

    async def decay_pattern_weights(self):
        """Decay confidence weights of pattern memories over time."""
        # FIXED: Limit to batch size
        memories_to_decay = list(self.storage.memories.values())[:CONSOLIDATION_BATCH_SIZE]
        logger.info(f"Decaying weights for {len(memories_to_decay)} memories")

        for memory in memories_to_decay:
            if memory.memory_type == MemoryType.PATTERN:
                # Calculate age-based decay
                age_days = (datetime.now() - memory.metadata.created_at).days
                decay_factor = self.config['pattern_weight_decay'] ** age_days

                # Apply decay to confidence
                memory.metadata.confidence *= decay_factor

                # Update importance based on confidence
                if memory.metadata.confidence < 0.3:
                    memory.metadata.importance = MemoryImportance.LOW
                elif memory.metadata.confidence < 0.6:
                    memory.metadata.importance = MemoryImportance.MEDIUM
                elif memory.metadata.confidence < 0.8:
                    memory.metadata.importance = MemoryImportance.HIGH
                else:
                    memory.metadata.importance = MemoryImportance.CRITICAL

    async def extract_patterns(self) -> List[Memory]:
        """Extract new patterns from episodic memories.

        Returns:
            List of newly extracted pattern memories
        """
        pattern_memories = []

        # FIXED: Limit episodic memories to batch size
        episodic_memories = [
            m for m in self.storage.memories.values()
            if m.memory_type == MemoryType.EPISODIC
            and (datetime.now() - m.metadata.created_at).days <= 7
        ][:CONSOLIDATION_BATCH_SIZE]

        logger.info(f"Extracting patterns from {len(episodic_memories)} episodic memories")

        if len(episodic_memories) < 3:
            return pattern_memories

        # Group by tags to find recurring patterns
        tag_groups = defaultdict(list)
        for memory in episodic_memories:
            for tag in memory.metadata.tags:
                tag_groups[tag].append(memory)

        # Extract patterns from groups with multiple occurrences
        for tag, memories in tag_groups.items():
            if len(memories) >= 3:  # Minimum occurrences for pattern
                # Create pattern memory
                pattern_content = {
                    'pattern_type': tag,
                    'occurrences': len(memories),
                    'confidence': min(1.0, len(memories) / 10.0),  # Scale with occurrences
                    'source_memories': [m.memory_id for m in memories],
                    'extracted_at': datetime.now().isoformat()
                }

                pattern_memory = Memory.create(
                    memory_type=MemoryType.PATTERN,
                    content=pattern_content,
                    importance=MemoryImportance.MEDIUM,
                    tags=[tag, 'extracted_pattern']
                )
                pattern_memory.metadata.confidence = pattern_content['confidence']

                # Store pattern
                await self.storage.store(pattern_memory)
                pattern_memories.append(pattern_memory)

        return pattern_memories

    async def update_pattern_accuracy(self, pattern_id: str, was_correct: bool):
        """Update pattern accuracy based on detection results.

        Args:
            pattern_id: Pattern memory ID
            was_correct: Whether the pattern detection was correct
        """
        memory = self.storage.memories.get(pattern_id)
        if not memory or memory.memory_type != MemoryType.PATTERN:
            return

        # Update confidence based on accuracy
        if was_correct:
            memory.metadata.confidence = min(1.0, memory.metadata.confidence * 1.1)
            self.metrics.accuracy_improvements.append(0.1)
        else:
            memory.metadata.confidence = max(0.0, memory.metadata.confidence * 0.9)
            self.metrics.accuracy_improvements.append(-0.1)

        # Update importance
        if memory.metadata.confidence > 0.8:
            memory.metadata.importance = MemoryImportance.CRITICAL
        elif memory.metadata.confidence > 0.6:
            memory.metadata.importance = MemoryImportance.HIGH
        elif memory.metadata.confidence > 0.4:
            memory.metadata.importance = MemoryImportance.MEDIUM
        else:
            memory.metadata.importance = MemoryImportance.LOW

    def _save_metrics(self):
        """Save consolidation metrics to disk."""
        self.consolidation_log_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.consolidation_log_path, 'w') as f:
            json.dump(self.metrics.to_dict(), f, indent=2)

    def _load_metrics(self):
        """Load consolidation metrics from disk."""
        if self.consolidation_log_path.exists():
            try:
                with open(self.consolidation_log_path, 'r') as f:
                    data = json.load(f)
                    self.metrics.consolidations_performed = data.get('consolidations_performed', 0)
                    self.metrics.patterns_merged = data.get('patterns_merged', 0)
                    self.metrics.false_positives_removed = data.get('false_positives_removed', 0)
                    self.metrics.memories_pruned = data.get('memories_pruned', 0)
                    self.metrics.accuracy_improvements = data.get('accuracy_improvements', [])
                    if data.get('last_consolidation'):
                        self.metrics.last_consolidation = datetime.fromisoformat(data['last_consolidation'])
            except Exception as e:
                print(f"Error loading metrics: {e}")

    async def should_consolidate(self) -> bool:
        """Check if consolidation should be triggered.

        Returns:
            True if consolidation should run
        """
        if not self.config['auto_consolidation_enabled']:
            return False

        # Check if enough time has passed
        if self.metrics.last_consolidation:
            hours_since_last = (datetime.now() - self.metrics.last_consolidation).total_seconds() / 3600
            if hours_since_last < self.config['consolidation_interval_hours']:
                return False

        # Check if there are enough memories to consolidate
        stats = self.storage.get_statistics()
        if stats['total_memories'] < 10:
            return False

        return True

    async def auto_consolidate_loop(self):
        """Run automatic consolidation loop."""
        while True:
            try:
                if await self.should_consolidate():
                    report = await self.consolidate()
                    logger.info(f"Auto-consolidation complete: {report['patterns_merged']} patterns merged")

                # Sleep for 1 hour
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error(f"Error in auto-consolidation loop: {e}", exc_info=True)
                await asyncio.sleep(3600)
