"""Storage backend for agent memories."""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
from pathlib import Path
import asyncio
from .memory_models import Memory, MemoryType, MemoryQuery, MemoryImportance


class MemoryStorage:
    """Manages storage and retrieval of agent memories."""

    def __init__(self, storage_path: Optional[str] = None):
        """Initialize memory storage.

        Args:
            storage_path: Path to storage directory
        """
        self.storage_path = Path(storage_path or "/a0/usr/projects/godmodescanner/data/memory")
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.memories: Dict[str, Memory] = {}
        self.embeddings_cache: Dict[str, List[float]] = {}
        self._load_memories()

    def _load_memories(self):
        """Load memories from storage."""
        # TODO: Implement memory loading from disk
        pass

    def _save_memories(self):
        """Save memories to storage."""
        # TODO: Implement memory persistence
        pass

    async def store(self, memory: Memory) -> str:
        """Store a memory.

        Args:
            memory: Memory to store

        Returns:
            Memory ID
        """
        self.memories[memory.memory_id] = memory
        self._save_memories()
        return memory.memory_id

    async def retrieve(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a memory by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory if found, None otherwise
        """
        memory = self.memories.get(memory_id)
        if memory:
            memory.metadata.update_access()
        return memory

    async def query(self, query: MemoryQuery) -> List[Memory]:
        """Query memories based on criteria.

        Args:
            query: Memory query

        Returns:
            List of matching memories
        """
        results = []

        for memory in self.memories.values():
            if query.matches(memory):
                results.append(memory)

        # Sort by relevance and access patterns
        results.sort(
            key=lambda m: (m.metadata.importance.value, m.metadata.access_count),
            reverse=True
        )

        return results[:query.limit]

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory.

        Args:
            memory_id: Memory ID to delete

        Returns:
            True if deleted, False if not found
        """
        if memory_id in self.memories:
            del self.memories[memory_id]
            self._save_memories()
            return True
        return False

    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update a memory.

        Args:
            memory_id: Memory ID
            updates: Dictionary of updates to apply

        Returns:
            True if updated, False if not found
        """
        if memory_id not in self.memories:
            return False

        memory = self.memories[memory_id]

        # Update content
        if 'content' in updates:
            memory.content.update(updates['content'])

        # Update metadata
        if 'tags' in updates:
            memory.metadata.tags = updates['tags']
        if 'importance' in updates:
            memory.metadata.importance = updates['importance']

        self._save_memories()
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """Get storage statistics.

        Returns:
            Statistics about stored memories
        """
        stats = {
            'total_memories': len(self.memories),
            'by_type': {},
            'by_importance': {},
            'total_accesses': sum(m.metadata.access_count for m in self.memories.values())
        }

        # Count by type
        for memory in self.memories.values():
            type_name = memory.memory_type.value
            stats['by_type'][type_name] = stats['by_type'].get(type_name, 0) + 1

            importance_name = memory.metadata.importance.name
            stats['by_importance'][importance_name] = stats['by_importance'].get(importance_name, 0) + 1

        return stats
