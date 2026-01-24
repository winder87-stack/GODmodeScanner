"""Data models for agent memory system."""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import uuid


class MemoryType(Enum):
    """Types of memories stored by agents."""
    EPISODIC = "episodic"  # Specific events and experiences
    SEMANTIC = "semantic"  # General knowledge and facts
    PROCEDURAL = "procedural"  # How-to knowledge and procedures
    PATTERN = "pattern"  # Detected patterns and insights
    WALLET = "wallet"  # Wallet-specific information
    TOKEN = "token"  # Token-specific information


class MemoryImportance(Enum):
    """Importance levels for memory consolidation."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class MemoryMetadata:
    """Metadata for a memory entry."""
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    importance: MemoryImportance = MemoryImportance.MEDIUM
    tags: List[str] = field(default_factory=list)
    source: str = ""
    confidence: float = 1.0
    related_memories: List[str] = field(default_factory=list)

    def update_access(self):
        """Update access timestamp and count."""
        self.last_accessed = datetime.now()
        self.access_count += 1


@dataclass
class Memory:
    """A single memory entry."""
    memory_id: str
    memory_type: MemoryType
    content: Dict[str, Any]
    metadata: MemoryMetadata
    embedding: Optional[List[float]] = None

    @classmethod
    def create(cls, memory_type: MemoryType, content: Dict[str, Any], 
              importance: MemoryImportance = MemoryImportance.MEDIUM,
              tags: Optional[List[str]] = None) -> 'Memory':
        """Create a new memory entry.

        Args:
            memory_type: Type of memory
            content: Memory content
            importance: Memory importance level
            tags: Optional tags for categorization

        Returns:
            New Memory instance
        """
        now = datetime.now()
        metadata = MemoryMetadata(
            created_at=now,
            last_accessed=now,
            importance=importance,
            tags=tags or []
        )

        return cls(
            memory_id=str(uuid.uuid4()),
            memory_type=memory_type,
            content=content,
            metadata=metadata
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert memory to dictionary."""
        return {
            'memory_id': self.memory_id,
            'memory_type': self.memory_type.value,
            'content': self.content,
            'metadata': {
                'created_at': self.metadata.created_at.isoformat(),
                'last_accessed': self.metadata.last_accessed.isoformat(),
                'access_count': self.metadata.access_count,
                'importance': self.metadata.importance.value,
                'tags': self.metadata.tags,
                'source': self.metadata.source,
                'confidence': self.metadata.confidence,
                'related_memories': self.metadata.related_memories
            },
            'has_embedding': self.embedding is not None
        }


@dataclass
class MemoryQuery:
    """Query for retrieving memories."""
    query_text: Optional[str] = None
    memory_types: Optional[List[MemoryType]] = None
    tags: Optional[List[str]] = None
    min_importance: Optional[MemoryImportance] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    limit: int = 10
    similarity_threshold: float = 0.7

    def matches(self, memory: Memory) -> bool:
        """Check if a memory matches the query criteria.

        Args:
            memory: Memory to check

        Returns:
            True if memory matches query
        """
        # Check memory type
        if self.memory_types and memory.memory_type not in self.memory_types:
            return False

        # Check tags
        if self.tags:
            if not any(tag in memory.metadata.tags for tag in self.tags):
                return False

        # Check importance
        if self.min_importance:
            if memory.metadata.importance.value < self.min_importance.value:
                return False

        # Check date range
        if self.start_date and memory.metadata.created_at < self.start_date:
            return False
        if self.end_date and memory.metadata.created_at > self.end_date:
            return False

        return True
