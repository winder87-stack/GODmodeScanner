"""Data models for wallet profiling."""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(Enum):
    """Risk level classifications for wallets."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class WalletType(Enum):
    """Types of wallet classifications."""
    RETAIL = "retail"
    WHALE = "whale"
    BOT = "bot"
    INSIDER = "insider"
    SYBIL = "sybil"
    EXCHANGE = "exchange"
    CONTRACT = "contract"
    UNKNOWN = "unknown"


@dataclass
class WalletProfile:
    """Complete profile for a wallet."""
    address: str
    wallet_type: WalletType
    risk_level: RiskLevel
    reputation_score: float
    first_seen: datetime
    last_active: datetime
    total_transactions: int
    total_volume_sol: float
    behavior_patterns: List[str] = field(default_factory=list)
    sybil_probability: float = 0.0
    connected_wallets: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_suspicious(self) -> bool:
        """Check if wallet exhibits suspicious characteristics."""
        return (
            self.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL] or
            self.sybil_probability > 0.7 or
            self.reputation_score < 0.3
        )


@dataclass
class BehaviorPattern:
    """Model for detected wallet behavior pattern."""
    pattern_id: str
    pattern_type: str
    wallet_address: str
    detected_at: datetime
    frequency: float
    confidence: float
    description: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SybilCluster:
    """Model for a cluster of potentially related wallets."""
    cluster_id: str
    wallet_addresses: List[str]
    confidence: float
    evidence_type: List[str]
    detected_at: datetime
    shared_characteristics: Dict[str, Any] = field(default_factory=dict)

    def cluster_size(self) -> int:
        """Get the number of wallets in the cluster."""
        return len(self.wallet_addresses)
