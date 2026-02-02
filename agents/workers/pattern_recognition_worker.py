#!/usr/bin/env python3
"""Pattern Recognition Worker - Insider trading pattern detection.

This worker processes transactions from Redis Streams to detect
6 types of insider trading patterns on pump.fun:

1. Pre-launch accumulation
2. Sequential front-running
3. Coordinated dumping
4. Wash trading
5. Layering/Spoofing
6. Quote stuffing

Key Features:
- Multi-pattern detection engine
- Sliding window analysis
- Pattern confidence scoring
- Real-time alert emission
- Low-latency processing
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
import structlog

# Add project root to path
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from utils.redis_streams_consumer import Message, AgentWorker
from utils.redis_streams_producer import RedisStreamsProducer

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger(__name__)


# Pattern types
PATTERN_PRE_LAUNCH_ACCUMULATION = "pre_launch_accumulation"
PATTERN_SEQUENTIAL_FRONT_RUNNING = "sequential_front_running"
PATTERN_COORDINATED_DUMPING = "coordinated_dumping"
PATTERN_WASH_TRADING = "wash_trading"
PATTERN_LAYERING = "layering"
PATTERN_QUOTE_STUFFING = "quote_stuffing"


@dataclass
class PatternMatch:
    """Represents a detected pattern match."""
    pattern_type: str
    confidence: float
    wallet_address: str
    token_address: str
    evidence: List[Dict[str, Any]]
    detected_at: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "confidence": self.confidence,
            "wallet_address": self.wallet_address,
            "token_address": self.token_address,
            "evidence": self.evidence,
            "detected_at": self.detected_at,
        }


@dataclass
class TokenWindow:
    """Sliding window for token activity."""
    token_address: str
    transactions: deque = field(default_factory=lambda: deque(maxlen=1000))
    wallet_activity: Dict[str, List[Dict]] = field(default_factory=dict)
    buy_count: int = 0
    sell_count: int = 0
    volume: float = 0.0
    first_seen: float = 0.0
    last_seen: float = 0.0


class PatternRecognitionWorker(AgentWorker):
    """Parallel pattern recognition worker.
    
    This worker processes transactions from Redis Streams and:
    - Maintains sliding windows for token activity
    - Detects 6 types of insider trading patterns
    - Calculates pattern confidence scores
    - Emits alerts for high-confidence patterns
    - Maintains pattern detection statistics
    """

    # Configuration
    WINDOW_SIZE_SECONDS = 300  # 5-minute sliding window
    MIN_TRANSACTIONS_FOR_PATTERN = 5
    
    def __init__(self, worker_id: str, redis_url: str = "redis://localhost:6379"):
        """Initialize pattern recognition worker.
        
        Args:
            worker_id: Unique identifier for this worker instance
            redis_url: Redis connection URL
        """
        super().__init__(agent_type="pattern-recognition")
        self.worker_id = worker_id
        self.redis_url = redis_url
        
        # Token windows (sliding window analysis)
        self.token_windows: Dict[str, TokenWindow] = {}
        self.max_windows = 1000
        
        # Pattern detection history (prevent duplicate alerts)
        self.detected_patterns: Dict[str, float] = {}  # key: (wallet, token, pattern) -> last_seen
        self.alert_cooldown_seconds = 60
        
        # Producer for alerts
        self.alert_producer: Optional[RedisStreamsProducer] = None
        
        # Statistics
        self.stats = {
            "worker_id": worker_id,
            "transactions_processed": 0,
            "tokens_analyzed": 0,
            "patterns_detected": 0,
            "alerts_emitted": 0,
            "processing_time_ms": 0.0,
            "pattern_breakdown": defaultdict(int),
        }
        
        logger.info(
            "pattern_recognition_worker_init",
            worker_id=worker_id,
            redis_url=redis_url,
        )

    async def initialize(self):
        """Initialize the worker."""
        self.alert_producer = RedisStreamsProducer(redis_url=self.redis_url)
        await self.alert_producer.connect()
        logger.info("pattern_recognition_worker_initialized", worker_id=self.worker_id)

    async def process_message(self, message: Message) -> bool:
        """Process a transaction message.
        
        Args:
            message: Transaction message from stream
            
        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()
        
        try:
            # Parse transaction data
            tx_data = message.get_payload()
            
            if not self._is_valid_transaction(tx_data):
                return True
            
            # Extract token and wallet
            token_address = tx_data.get("token") or tx_data.get("mint")
            wallet_address = tx_data.get("signer") or tx_data.get("wallet")
            
            if not token_address or not wallet_address:
                return True
            
            # Update token window
            await self._update_token_window(token_address, wallet_address, tx_data)
            
            # Detect patterns
            patterns = await self._detect_patterns(token_address, wallet_address)
            
            # Emit alerts for high-confidence patterns
            for pattern in patterns:
                if pattern.confidence > 0.6:
                    await self._emit_pattern_alert(pattern)
            
            # Update stats
            self.stats["transactions_processed"] += 1
            processing_time = (time.time() - start_time) * 1000
            self._update_avg_time(processing_time)
            
            return True
            
        except Exception as e:
            logger.error(
                "process_message_error",
                worker_id=self.worker_id,
                error=str(e),
            )
            return False

    def _is_valid_transaction(self, tx_data: Dict[str, Any]) -> bool:
        """Check if transaction data is valid."""
        return tx_data is not None and isinstance(tx_data, dict)

    async def _update_token_window(self, token_address: str, wallet_address: str, tx_data: Dict[str, Any]):
        """Update the sliding window for a token."""
        now = time.time()
        
        # Get or create token window
        if token_address not in self.token_windows:
            self._evict_old_windows()
            self.token_windows[token_address] = TokenWindow(
                token_address=token_address,
                first_seen=now,
            )
        
        window = self.token_windows[token_address]
        
        # Add transaction to window
        tx_record = {
            "wallet": wallet_address,
            "type": tx_data.get("type", "unknown"),
            "amount": float(tx_data.get("amount", 0)),
            "timestamp": now,
            "tx_data": tx_data,
        }
        
        window.transactions.append(tx_record)
        window.last_seen = now
        window.volume += tx_record["amount"]
        
        # Track wallet activity
        if wallet_address not in window.wallet_activity:
            window.wallet_activity[wallet_address] = []
        window.wallet_activity[wallet_address].append(tx_record)
        
        # Update counts
        tx_type = tx_data.get("type", "").lower()
        if "buy" in tx_type:
            window.buy_count += 1
        elif "sell" in tx_type:
            window.sell_count += 1
        
        # Clean old transactions from window
        cutoff_time = now - self.WINDOW_SIZE_SECONDS
        while window.transactions and window.transactions[0]["timestamp"] < cutoff_time:
            old_tx = window.transactions.popleft()
            
            # Update stats
            window.volume -= old_tx["amount"]
            if "buy" in old_tx["type"]:
                window.buy_count -= 1
            elif "sell" in old_tx["type"]:
                window.sell_count -= 1
        
        # Clean wallet activity
        for wallet in window.wallet_activity:
            window.wallet_activity[wallet] = [
                tx for tx in window.wallet_activity[wallet]
                if tx["timestamp"] >= cutoff_time
            ]

    async def _detect_patterns(self, token_address: str, wallet_address: str) -> List[PatternMatch]:
        """Detect all patterns for a given token and wallet."""
        window = self.token_windows.get(token_address)
        if not window or len(window.transactions) < self.MIN_TRANSACTIONS_FOR_PATTERN:
            return []
        
        patterns = []
        
        # Pattern 1: Pre-launch accumulation
        pattern1 = await self._detect_pre_launch_accumulation(token_address, wallet_address, window)
        if pattern1:
            patterns.append(pattern1)
        
        # Pattern 2: Sequential front-running
        pattern2 = await self._detect_sequential_front_running(token_address, wallet_address, window)
        if pattern2:
            patterns.append(pattern2)
        
        # Pattern 3: Coordinated dumping
        pattern3 = await self._detect_coordinated_dumping(token_address, wallet_address, window)
        if pattern3:
            patterns.append(pattern3)
        
        # Pattern 4: Wash trading
        pattern4 = await self._detect_wash_trading(token_address, wallet_address, window)
        if pattern4:
            patterns.append(pattern4)
        
        # Pattern 5: Layering/Spoofing
        pattern5 = await self._detect_layering(token_address, wallet_address, window)
        if pattern5:
            patterns.append(pattern5)
        
        # Pattern 6: Quote stuffing
        pattern6 = await self._detect_quote_stuffing(token_address, wallet_address, window)
        if pattern6:
            patterns.append(pattern6)
        
        return patterns

    async def _detect_pre_launch_accumulation(self, token_address: str, wallet_address: str, window: TokenWindow) -> Optional[PatternMatch]:
        """Detect Pattern 1: Pre-launch accumulation.
        
        Characterized by:
        - Multiple small buys before token launch
        - Early entry with high precision timing
        """
        wallet_txs = window.wallet_activity.get(wallet_address, [])
        
        if len(wallet_txs) < 3:
            return None
        
        # Count buys
        buys = [tx for tx in wallet_txs if "buy" in tx["type"]]
        if len(buys) < 3:
            return None
        
        # Check if buys are early (first 10% of window)
        window_duration = window.last_seen - window.first_seen
        buy_times = [tx["timestamp"] - window.first_seen for tx in buys]
        early_buys = [t for t in buy_times if t < window_duration * 0.1]
        
        if len(early_buys) < 2:
            return None
        
        confidence = min(0.9, 0.5 + (len(early_buys) / len(buys)) * 0.4)
        
        return PatternMatch(
            pattern_type=PATTERN_PRE_LAUNCH_ACCUMULATION,
            confidence=confidence,
            wallet_address=wallet_address,
            token_address=token_address,
            evidence=[{"type": "early_buys", "count": len(early_buys)}],
            detected_at=time.time(),
        )

    async def _detect_sequential_front_running(self, token_address: str, wallet_address: str, window: TokenWindow) -> Optional[PatternMatch]:
        """Detect Pattern 2: Sequential front-running.
        
        Characterized by:
        - Consistent buys immediately before price increases
        - Predictable market movement timing
        """
        wallet_txs = window.wallet_activity.get(wallet_address, [])
        
        if len(wallet_txs) < 5:
            return None
        
        # Analyze buy timing relative to other activity
        buys = [tx for tx in wallet_txs if "buy" in tx["type"]]
        if len(buys) < 3:
            return None
        
        # Check if buys precede price increases (simplified: check for clustering)
        # In production, use actual price data
        confidence = 0.5
        
        if len(buys) > 5:
            confidence += 0.2
        
        return PatternMatch(
            pattern_type=PATTERN_SEQUENTIAL_FRONT_RUNNING,
            confidence=confidence,
            wallet_address=wallet_address,
            token_address=token_address,
            evidence=[{"type": "sequential_buys", "count": len(buys)}],
            detected_at=time.time(),
        )

    async def _detect_coordinated_dumping(self, token_address: str, wallet_address: str, window: TokenWindow) -> Optional[PatternMatch]:
        """Detect Pattern 3: Coordinated dumping.
        
        Characterized by:
        - Multiple wallets selling simultaneously
        - Large sell volumes
        - Synchronized timing
        """
        # Count recent sells across all wallets
        now = time.time()
        recent_sells = [
            tx for tx in window.transactions
            if "sell" in tx["type"] and now - tx["timestamp"] < 60
        ]
        
        if len(recent_sells) < 5:
            return None
        
        # Check if sells are from multiple wallets
        unique_wallets = set(tx["wallet"] for tx in recent_sells)
        if len(unique_wallets) < 2:
            return None
        
        confidence = min(0.95, 0.6 + (len(unique_wallets) / len(recent_sells)) * 0.35)
        
        return PatternMatch(
            pattern_type=PATTERN_COORDINATED_DUMPING,
            confidence=confidence,
            wallet_address=wallet_address,
            token_address=token_address,
            evidence=[
                {"type": "recent_sells", "count": len(recent_sells)},
                {"type": "unique_wallets", "count": len(unique_wallets)},
            ],
            detected_at=time.time(),
        )

    async def _detect_wash_trading(self, token_address: str, wallet_address: str, window: TokenWindow) -> Optional[PatternMatch]:
        """Detect Pattern 4: Wash trading.
        
        Characterized by:
        - Multiple buys and sells by same wallet
        - Similar amounts
        - No net position change
        """
        wallet_txs = window.wallet_activity.get(wallet_address, [])
        
        buys = [tx for tx in wallet_txs if "buy" in tx["type"]]
        sells = [tx for tx in wallet_txs if "sell" in tx["type"]]
        
        if len(buys) < 3 or len(sells) < 3:
            return None
        
        # Check for similar amounts
        buy_amounts = [tx["amount"] for tx in buys]
        sell_amounts = [tx["amount"] for tx in sells]
        
        avg_buy = sum(buy_amounts) / len(buy_amounts)
        avg_sell = sum(sell_amounts) / len(sell_amounts)
        
        ratio = min(avg_buy, avg_sell) / max(avg_buy, avg_sell)
        
        if ratio < 0.7:  # Not similar enough
            return None
        
        confidence = min(0.9, 0.5 + ratio * 0.4)
        
        return PatternMatch(
            pattern_type=PATTERN_WASH_TRADING,
            confidence=confidence,
            wallet_address=wallet_address,
            token_address=token_address,
            evidence=[
                {"type": "buys", "count": len(buys)},
                {"type": "sells", "count": len(sells)},
                {"type": "amount_ratio", "value": ratio},
            ],
            detected_at=time.time(),
        )

    async def _detect_layering(self, token_address: str, wallet_address: str, window: TokenWindow) -> Optional[PatternMatch]:
        """Detect Pattern 5: Layering/Spoofing.
        
        Characterized by:
        - Large number of small orders
        - Rapid order placement and cancellation
        - Market manipulation intent
        """
        wallet_txs = window.wallet_activity.get(wallet_address, [])
        
        if len(wallet_txs) < 10:
            return None
        
        # Check transaction density
        now = time.time()
        recent_txs = [tx for tx in wallet_txs if now - tx["timestamp"] < 30]
        
        if len(recent_txs) < 10:
            return None
        
        confidence = min(0.85, 0.5 + (len(recent_txs) / 20) * 0.35)
        
        return PatternMatch(
            pattern_type=PATTERN_LAYERING,
            confidence=confidence,
            wallet_address=wallet_address,
            token_address=token_address,
            evidence=[{"type": "high_frequency_txs", "count": len(recent_txs)}],
            detected_at=time.time(),
        )

    async def _detect_quote_stuffing(self, token_address: str, wallet_address: str, window: TokenWindow) -> Optional[PatternMatch]:
        """Detect Pattern 6: Quote stuffing.
        
        Characterized by:
        - Extremely high transaction frequency
        - Multiple similar transactions
        - Market flooding
        """
        wallet_txs = window.wallet_activity.get(wallet_address, [])
        
        if len(wallet_txs) < 20:
            return None
        
        # Check transaction rate
        time_span = max(1, window.last_seen - window.first_seen)
        tx_rate = len(wallet_txs) / time_span
        
        if tx_rate < 5.0:  # Less than 5 tx/second
            return None
        
        confidence = min(0.95, 0.6 + (tx_rate / 10) * 0.35)
        
        return PatternMatch(
            pattern_type=PATTERN_QUOTE_STUFFING,
            confidence=confidence,
            wallet_address=wallet_address,
            token_address=token_address,
            evidence=[{"type": "tx_rate", "value": tx_rate}],
            detected_at=time.time(),
        )

    async def _emit_pattern_alert(self, pattern: PatternMatch):
        """Emit an alert for a detected pattern."""
        if not self.alert_producer:
            return
        
        # Check cooldown
        key = f"{pattern.wallet_address}:{pattern.token_address}:{pattern.pattern_type}"
        last_seen = self.detected_patterns.get(key, 0)
        
        if time.time() - last_seen < self.alert_cooldown_seconds:
            return
        
        self.detected_patterns[key] = time.time()
        
        alert = {
            "alert_type": "pattern_detected",
            "pattern_type": pattern.pattern_type,
            "severity": "critical" if pattern.confidence > 0.8 else "high",
            "wallet_address": pattern.wallet_address,
            "token_address": pattern.token_address,
            "confidence": pattern.confidence,
            "evidence": pattern.evidence,
            "worker_id": self.worker_id,
            "timestamp": int(time.time() * 1000),
        }
        
        await self.alert_producer.publish_alert(alert)
        self.stats["alerts_emitted"] += 1
        self.stats["patterns_detected"] += 1
        self.stats["pattern_breakdown"][pattern.pattern_type] += 1
        
        logger.warning(
            "pattern_alert_emitted",
            pattern=pattern.pattern_type,
            wallet=pattern.wallet_address,
            confidence=pattern.confidence,
            worker=self.worker_id,
        )

    def _evict_old_windows(self):
        """Evict old token windows if at capacity."""
        if len(self.token_windows) >= self.max_windows:
            now = time.time()
            expired = [
                token for token, window in self.token_windows.items()
                if now - window.last_seen > self.WINDOW_SIZE_SECONDS
            ]
            for token in expired:
                del self.token_windows[token]

    def _update_avg_time(self, value_ms: float):
        """Update moving average of processing time."""
        count = self.stats["transactions_processed"]
        if count > 0:
            self.stats["processing_time_ms"] = (
                (self.stats["processing_time_ms"] * (count - 1) + value_ms) / count
            )
        else:
            self.stats["processing_time_ms"] = value_ms

    async def get_stats(self) -> Dict[str, Any]:
        """Get worker statistics."""
        base_stats = await super().get_stats()
        base_stats.update(self.stats)
        base_stats["pattern_breakdown"] = dict(self.stats["pattern_breakdown"])
        return base_stats

    async def close(self):
        """Clean up resources."""
        if self.alert_producer:
            await self.alert_producer.close()
        logger.info("pattern_recognition_worker_closed", worker_id=self.worker_id)


def create_worker(worker_id: str, redis_url: str = "redis://localhost:6379") -> PatternRecognitionWorker:
    """Factory function to create a pattern recognition worker."""
    return PatternRecognitionWorker(worker_id=worker_id, redis_url=redis_url)
