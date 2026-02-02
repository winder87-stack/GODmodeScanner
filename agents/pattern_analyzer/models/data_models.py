"""Data models for pattern analysis."""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum


class PatternType(Enum):
    """Types of detected patterns."""
    EARLY_BUY = "early_buy"
    COORDINATED_TRADING = "coordinated_trading"
    LIQUIDITY_MANIPULATION = "liquidity_manipulation"
    WASH_TRADING = "wash_trading"
    PUMP_DUMP = "pump_dump"
    SYBIL_NETWORK = "sybil_network"


@dataclass
class TransactionPattern:
    """Model for a detected transaction pattern."""
    pattern_id: str
    pattern_type: PatternType
    confidence: float
    timestamp: datetime
    involved_wallets: List[str]
    evidence: Dict[str, Any]
    risk_score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TokenLaunchData:
    """Model for token launch data."""
    token_address: str
    launch_time: datetime
    creator_wallet: str
    initial_liquidity: float
    launch_platform: str
    metadata: Dict[str, Any]
    transactions: List[Dict[str, Any]] = field(default_factory=list)

    def get_early_transactions(self, window_seconds: int = 60) -> List[Dict[str, Any]]:
        """Get transactions within the early window.

        Args:
            window_seconds: Time window after launch in seconds

        Returns:
            List of early transactions
        """
        early_txs = []
        for tx in self.transactions:
            tx_time = datetime.fromisoformat(tx.get('timestamp', ''))
            if (tx_time - self.launch_time).total_seconds() <= window_seconds:
                early_txs.append(tx)
        return early_txs


@dataclass
class TradingSignal:
    """Model for a trading signal or alert."""
    signal_id: str
    signal_type: str
    severity: str  # 'low', 'medium', 'high', 'critical'
    token_address: str
    timestamp: datetime
    description: str
    detected_patterns: List[TransactionPattern]
    recommended_action: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert signal to dictionary."""
        return {
            'signal_id': self.signal_id,
            'signal_type': self.signal_type,
            'severity': self.severity,
            'token_address': self.token_address,
            'timestamp': self.timestamp.isoformat(),
            'description': self.description,
            'pattern_count': len(self.detected_patterns),
            'recommended_action': self.recommended_action,
            'metadata': self.metadata
        }
