"""Enhanced memory storage with FAISS vector store and hierarchical organization."""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json
import pickle
from pathlib import Path
import asyncio
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from ..memory.memory_models import Memory, MemoryType, MemoryQuery, MemoryImportance


class HierarchicalMemoryTier:
    """Memory tier for hierarchical organization."""
    RECENT = "recent"  # Last 7 days
    MEDIUM = "medium"  # 7-30 days
    HISTORICAL = "historical"  # 30+ days


class EnhancedMemoryStorage:
    """Enhanced memory storage with FAISS vector store and hierarchical organization."""

    def __init__(self, storage_path: Optional[str] = None, embedding_model: str = "all-MiniLM-L6-v2"):
        """Initialize enhanced memory storage.

        Args:
            storage_path: Path to storage directory
            embedding_model: Sentence transformer model name
        """
        self.storage_path = Path(storage_path or "/a0/usr/projects/godmodescanner/data/memory")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Initialize embedding model
        self.embedding_model = SentenceTransformer(embedding_model)
        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()

        # Initialize FAISS indices for each tier
        self.indices = {
            HierarchicalMemoryTier.RECENT: faiss.IndexFlatL2(self.embedding_dim),
            HierarchicalMemoryTier.MEDIUM: faiss.IndexFlatL2(self.embedding_dim),
            HierarchicalMemoryTier.HISTORICAL: faiss.IndexFlatL2(self.embedding_dim)
        }

        # Memory storage
        self.memories: Dict[str, Memory] = {}
        self.memory_to_tier: Dict[str, str] = {}
        self.tier_to_ids: Dict[str, List[str]] = {
            tier: [] for tier in [HierarchicalMemoryTier.RECENT, 
                                 HierarchicalMemoryTier.MEDIUM, 
                                 HierarchicalMemoryTier.HISTORICAL]
        }

        # Load existing memories
        self._load_memories()

    def _get_memory_tier(self, memory: Memory) -> str:
        """Determine memory tier based on age.

        Args:
            memory: Memory to classify

        Returns:
            Memory tier
        """
        age_days = (datetime.now() - memory.metadata.created_at).days

        if age_days <= 7:
            return HierarchicalMemoryTier.RECENT
        elif age_days <= 30:
            return HierarchicalMemoryTier.MEDIUM
        else:
            return HierarchicalMemoryTier.HISTORICAL

    def _generate_embedding(self, memory: Memory) -> np.ndarray:
        """Generate embedding for memory content.

        Args:
            memory: Memory to embed

        Returns:
            Embedding vector
        """
        # Create text representation of memory
        text_parts = []

        # Add memory type
        text_parts.append(f"Type: {memory.memory_type.value}")

        # Add content
        for key, value in memory.content.items():
            text_parts.append(f"{key}: {str(value)}")

        # Add tags
        if memory.metadata.tags:
            text_parts.append(f"Tags: {', '.join(memory.metadata.tags)}")

        text = " ".join(text_parts)

        # Generate embedding
        embedding = self.embedding_model.encode(text, convert_to_numpy=True)
        return embedding.astype('float32')

    async def store(self, memory: Memory) -> str:
        """Store a memory with automatic tier assignment.

        Args:
            memory: Memory to store

        Returns:
            Memory ID
        """
        # Generate embedding if not present
        if memory.embedding is None:
            embedding = self._generate_embedding(memory)
            memory.embedding = embedding.tolist()
        else:
            embedding = np.array(memory.embedding, dtype='float32')

        # Determine tier
        tier = self._get_memory_tier(memory)

        # Add to FAISS index
        self.indices[tier].add(embedding.reshape(1, -1))

        # Store memory
        self.memories[memory.memory_id] = memory
        self.memory_to_tier[memory.memory_id] = tier
        self.tier_to_ids[tier].append(memory.memory_id)

        # Save to disk
        await self._save_memories()

        return memory.memory_id

    async def similarity_search(self, query_text: str, k: int = 10, 
                               tier: Optional[str] = None,
                               similarity_threshold: float = 0.7) -> List[Tuple[Memory, float]]:
        """Search for similar memories using vector similarity.

        Args:
            query_text: Query text
            k: Number of results to return
            tier: Optional tier to search in
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of (Memory, similarity_score) tuples
        """
        # Generate query embedding
        query_embedding = self.embedding_model.encode(query_text, convert_to_numpy=True)
        query_embedding = query_embedding.astype('float32').reshape(1, -1)

        results = []

        # Search in specified tier or all tiers
        tiers_to_search = [tier] if tier else list(self.indices.keys())

        for search_tier in tiers_to_search:
            if self.indices[search_tier].ntotal == 0:
                continue

            # Search FAISS index
            distances, indices = self.indices[search_tier].search(query_embedding, min(k, self.indices[search_tier].ntotal))

            # Convert distances to similarity scores (L2 distance to cosine similarity approximation)
            # Lower distance = higher similarity
            for dist, idx in zip(distances[0], indices[0]):
                if idx < len(self.tier_to_ids[search_tier]):
                    memory_id = self.tier_to_ids[search_tier][idx]
                    memory = self.memories.get(memory_id)

                    if memory:
                        # Convert L2 distance to similarity score (0-1)
                        similarity = 1.0 / (1.0 + dist)

                        if similarity >= similarity_threshold:
                            results.append((memory, similarity))
                            memory.metadata.update_access()

        # Sort by similarity score
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:k]

    async def query(self, query: MemoryQuery) -> List[Memory]:
        """Query memories with enhanced filtering and similarity search.

        Args:
            query: Memory query

        Returns:
            List of matching memories
        """
        results = []

        # If query text is provided, use similarity search
        if query.query_text:
            similarity_results = await self.similarity_search(
                query.query_text,
                k=query.limit * 2,  # Get more results for filtering
                similarity_threshold=query.similarity_threshold
            )

            # Filter by other criteria
            for memory, score in similarity_results:
                if query.matches(memory):
                    results.append(memory)
        else:
            # Traditional filtering
            for memory in self.memories.values():
                if query.matches(memory):
                    results.append(memory)

        # Sort by importance and access count
        results.sort(
            key=lambda m: (m.metadata.importance.value, m.metadata.access_count),
            reverse=True
        )

        return results[:query.limit]

    async def reorganize_tiers(self):
        """Reorganize memories into appropriate tiers based on age."""
        # Clear indices
        for tier in self.indices:
            self.indices[tier] = faiss.IndexFlatL2(self.embedding_dim)

        # Clear tier mappings
        self.memory_to_tier.clear()
        for tier in self.tier_to_ids:
            self.tier_to_ids[tier].clear()

        # Reassign memories to tiers
        for memory_id, memory in self.memories.items():
            tier = self._get_memory_tier(memory)

            if memory.embedding:
                embedding = np.array(memory.embedding, dtype='float32')
                self.indices[tier].add(embedding.reshape(1, -1))

            self.memory_to_tier[memory_id] = tier
            self.tier_to_ids[tier].append(memory_id)

        await self._save_memories()

    async def prune_old_memories(self, max_age_days: int = 30):
        """Remove memories older than specified age.

        Args:
            max_age_days: Maximum age in days
        """
        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        memories_to_delete = []

        for memory_id, memory in self.memories.items():
            if memory.metadata.created_at < cutoff_date:
                # Keep high importance memories
                if memory.metadata.importance.value < MemoryImportance.HIGH.value:
                    memories_to_delete.append(memory_id)

        # Delete old memories
        for memory_id in memories_to_delete:
            await self.delete(memory_id)

        print(f"Pruned {len(memories_to_delete)} old memories")

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory.

        Args:
            memory_id: Memory ID to delete

        Returns:
            True if deleted, False if not found
        """
        if memory_id not in self.memories:
            return False

        # Remove from tier tracking
        tier = self.memory_to_tier.get(memory_id)
        if tier and memory_id in self.tier_to_ids[tier]:
            self.tier_to_ids[tier].remove(memory_id)

        # Remove from memory storage
        del self.memories[memory_id]
        if memory_id in self.memory_to_tier:
            del self.memory_to_tier[memory_id]

        # Rebuild FAISS index for the tier
        if tier:
            await self.reorganize_tiers()

        await self._save_memories()
        return True

    async def _save_memories(self):
        """Save memories to disk."""
        # Save memory metadata
        metadata_file = self.storage_path / "memories.json"
        metadata = {
            memory_id: memory.to_dict()
            for memory_id, memory in self.memories.items()
        }

        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Save FAISS indices
        for tier, index in self.indices.items():
            index_file = self.storage_path / f"faiss_index_{tier}.bin"
            faiss.write_index(index, str(index_file))

        # Save tier mappings
        mappings_file = self.storage_path / "tier_mappings.pkl"
        with open(mappings_file, 'wb') as f:
            pickle.dump({
                'memory_to_tier': self.memory_to_tier,
                'tier_to_ids': self.tier_to_ids
            }, f)

    def _load_memories(self):
        """Load memories from disk."""
        try:
            # Load memory metadata
            metadata_file = self.storage_path / "memories.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                # Reconstruct Memory objects
                for memory_id, mem_dict in metadata.items():
                    # Reconstruct memory (simplified - would need full deserialization)
                    pass

            # Load FAISS indices
            for tier in self.indices:
                index_file = self.storage_path / f"faiss_index_{tier}.bin"
                if index_file.exists():
                    self.indices[tier] = faiss.read_index(str(index_file))

            # Load tier mappings
            mappings_file = self.storage_path / "tier_mappings.pkl"
            if mappings_file.exists():
                with open(mappings_file, 'rb') as f:
                    mappings = pickle.load(f)
                    self.memory_to_tier = mappings['memory_to_tier']
                    self.tier_to_ids = mappings['tier_to_ids']

        except Exception as e:
            print(f"Error loading memories: {e}")

    def get_statistics(self) -> Dict[str, Any]:
        """Get enhanced storage statistics.

        Returns:
            Statistics about stored memories
        """
        stats = {
            'total_memories': len(self.memories),
            'by_tier': {},
            'by_type': {},
            'by_importance': {},
            'total_accesses': sum(m.metadata.access_count for m in self.memories.values()),
            'embedding_dimension': self.embedding_dim
        }

        # Count by tier
        for tier, ids in self.tier_to_ids.items():
            stats['by_tier'][tier] = len(ids)

        # Count by type and importance
        for memory in self.memories.values():
            type_name = memory.memory_type.value
            stats['by_type'][type_name] = stats['by_type'].get(type_name, 0) + 1

            importance_name = memory.metadata.importance.name
            stats['by_importance'][importance_name] = stats['by_importance'].get(importance_name, 0) + 1

        return stats
