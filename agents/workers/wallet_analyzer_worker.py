#!/usr/bin/env python3
"""Wallet Analyzer Worker - Refactored to use BaseWorker.

This worker processes transactions from Redis Streams to analyze
wallet behavior, detect suspicious patterns, and emit risk alerts.

Refactored Features (inherited from BaseWorker):
- Redis connection management
- Structlog initialization
- Message consumption loop
- Statistics tracking
- Graceful shutdown

Worker-Specific Implementation:
- process_batch(): Wallet analysis logic
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path
import sys

import structlog

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from agents.workers.base_worker import BaseWorker, BaseWorkerConfig
from utils.redis_streams_consumer import Message
from utils.redis_streams_producer import RedisStreamsProducer
from utils.validation import validate_input

logger = structlog.get_logger(__name__)


# ============================================================================
# WORKER CONFIGURATION
# ============================================================================

@dataclass
class WalletAnalyzerConfig(BaseWorkerConfig):
    """Configuration specific to wallet analyzer worker."""
    
    # Stream configuration
    stream_name: str = "godmode:new_transactions"
    group_name: str = "wallet-analyzer-group"
    
    # Analysis configuration
    behavior_window_seconds: int = 600  # 10-minute window
    max_wallets_tracked: int = 5000
    suspicious_threshold: float = 0.7
    
    # Processing
    batch_timeout_seconds: float = 2.0
    count_per_read: int = 10


# ============================================================================
# DATA MODELS
# ============================================================================

@dataclass
class WalletProfile:
    """Behavioral profile for a wallet."""
    wallet_address: str
    first_seen: float = 0.0
    last_seen: float = 0.0
    transaction_count: int = 0
    unique_tokens: Set[str] = field(default_factory=set)
    buy_times: List[float] = field(default_factory=list)
    sell_times: List[float] = field(default_factory=list)
    avg_transaction_amount: float = 0.0
    total_volume: float = 0.0
    
    def update_from_tx(self, tx_data: Dict[str, Any]):
        """Update profile from transaction data."""
        now = time.time()
        
        if self.first_seen == 0:
            self.first_seen = now
        
        self.last_seen = now
        self.transaction_count += 1
        
        # Token tracking
        token = tx_data.get("token") or tx_data.get("mint")
        if token:
            self.unique_tokens.add(token)
        
        # Buy/Sell tracking
        tx_type = tx_data.get("type", "").lower()
        amount = float(tx_data.get("amount", 0))
        
        if amount > 0:
            self.total_volume += amount
            self.avg_transaction_amount = self.total_volume / self.transaction_count
        
        if "buy" in tx_type or "swap" in tx_type:
            self.buy_times.append(now)
        elif "sell" in tx_type:
            self.sell_times.append(now)


@dataclass
class SuspiciousActivity:
    """Suspicious activity detected for a wallet."""
    wallet: str
    activity_type: str
    confidence: float
    evidence: Dict[str, Any]
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "wallet": self.wallet,
            "activity_type": self.activity_type,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "timestamp": self.timestamp,
        }


# ============================================================================
# WALLET ANALYZER WORKER
# ============================================================================

class WalletAnalyzerWorker(BaseWorker):
    """Wallet analysis worker using BaseWorker infrastructure.
    
    This worker analyzes wallet behavior patterns and detects
    suspicious activity.
    
    Inherited Features:
    - Redis connection and management
    - Message consumption loop
    - Statistics tracking
    - Graceful shutdown
    
    Worker-Specific Features:
    - Wallet behavioral profiling
    - Pattern detection
    - Risk scoring
    - Alert emission
    """
    
    AGENT_TYPE = "wallet-analyzer"
    WORKER_VERSION = "2.0.0"  # Refactored version
    
    def __init__(
        self,
        worker_id: str,
        redis_url: str = "redis://localhost:6379",
        config: Optional[WalletAnalyzerConfig] = None
    ):
        """Initialize wallet analyzer worker."""
        super().__init__(
            worker_id=worker_id,
            redis_url=redis_url,
            config=config or WalletAnalyzerConfig()
        )
        
        # Worker-specific state
        self.wallet_profiles: Dict[str, WalletProfile] = {}
        self.suspicious_activities: List[SuspiciousActivity] = []
        
        # Alert producer
        self._alert_producer: Optional[RedisStreamsProducer] = None
        
        # Statistics (extended from base)
        self.stats.update({
            "wallets_analyzed": 0,
            "suspicious_detected": 0,
            "alerts_emitted": 0,
        })
        
        logger.info(
            "wallet_analyzer_worker_init",
            worker_id=worker_id,
            redis_url=redis_url
        )
    
    async def initialize(self):
        """Initialize worker-specific resources."""
        # Create alert producer
        self._alert_producer = RedisStreamsProducer(redis_url=self.redis_url)
        await self._alert_producer.connect()
        
        logger.info(
            "wallet_analyzer_worker_initialized",
            worker_id=self.worker_id
        )
    
    async def disconnect(self):
        """Clean up worker-specific resources."""
        if self._alert_producer:
            await self._alert_producer.close()
        
        await super().disconnect()
    
    async def process_batch(self, messages: List[Message]) -> List[dict]:
        """
        Process a batch of transaction messages.
        
        This is the main worker-specific implementation.
        All common infrastructure is handled by BaseWorker.
        
        Args:
            messages: List of messages from Redis Stream
            
        Returns:
            List of analysis results
        """
        results = []
        
        for message in messages:
            try:
                result = await self._process_message(message)
                if result:
                    results.append(result)
                    self.stats["messages_acknowledged"] += 1
                else:
                    self.stats["messages_failed"] += 1
            except Exception as e:
                logger.error(
                    "batch_processing_error",
                    worker_id=self.worker_id,
                    message_id=message.message_id,
                    error=str(e)
                )
                self.stats["messages_failed"] += 1
        
        self.stats["batches_processed"] += 1
        return results
    
    async def _process_message(self, message: Message) -> Optional[dict]:
        """Process a single transaction message."""
        start_time = time.time()
        
        try:
            # Parse and validate transaction data
            tx_data = message.get_payload()
            
            if not self._is_valid_transaction(tx_data):
                return None
            
            # Extract wallet address
            wallet_address = tx_data.get("signer") or tx_data.get("wallet") or tx_data.get("from")
            
            if not wallet_address:
                return None
            
            # Validate wallet address using Pydantic
            is_valid, wallet_obj, error = validate_input('wallet', {'address': wallet_address})
            if not is_valid:
                logger.warning(
                    "invalid_wallet_address",
                    wallet=wallet_address[:16] + "..." if len(wallet_address) > 16 else wallet_address,
                    error=error
                )
                return None
            
            # Update wallet profile
            await self._update_wallet_profile(wallet_address, tx_data)
            
            # Detect suspicious patterns
            suspicious = await self._detect_suspicious_activity(wallet_address, tx_data)
            
            # Emit alert if suspicious activity detected
            if suspicious:
                await self._emit_alert(suspicious)
                self.stats["suspicious_detected"] += 1
            
            # Build result
            processing_time = (time.time() - start_time) * 1000
            result = {
                "wallet": wallet_address,
                "timestamp": int(time.time() * 1000),
                "processing_time_ms": processing_time,
                "is_suspicious": suspicious is not None,
            }
            
            if suspicious:
                result["suspicious_details"] = suspicious.to_dict()
            
            return result
            
        except Exception as e:
            logger.error(
                "message_processing_error",
                worker_id=self.worker_id,
                error=str(e)
            )
            return None
    
    def _is_valid_transaction(self, tx_data: Dict[str, Any]) -> bool:
        """Validate transaction data structure."""
        return tx_data is not None and isinstance(tx_data, dict)
    
    async def _update_wallet_profile(self, wallet_address: str, tx_data: Dict[str, Any]):
        """Update behavioral profile for a wallet."""
        config = self.config  # type: WalletAnalyzerConfig
        
        # Get or create profile
        if wallet_address not in self.wallet_profiles:
            # Evict old wallets if at capacity
            if len(self.wallet_profiles) >= config.max_wallets_tracked:
                self._evict_old_wallets(config.behavior_window_seconds)
            
            self.wallet_profiles[wallet_address] = WalletProfile(
                wallet_address=wallet_address
            )
        
        # Update profile
        profile = self.wallet_profiles[wallet_address]
        profile.update_from_tx(tx_data)
        
        self.stats["wallets_analyzed"] = len(self.wallet_profiles)
    
    async def _detect_suspicious_activity(
        self,
        wallet_address: str,
        tx_data: Dict[str, Any]
    ) -> Optional[SuspiciousActivity]:
        """Detect suspicious activity patterns."""
        profile = self.wallet_profiles.get(wallet_address)
        if not profile:
            return None
        
        now = time.time()
        
        # Pattern 1: High-frequency trading
        if profile.transaction_count > 50:
            recent_buys = sum(1 for t in profile.buy_times if now - t < 300)
            if recent_buys > 20:
                return SuspiciousActivity(
                    wallet=wallet_address,
                    activity_type="high_frequency_trading",
                    confidence=0.75,
                    evidence={
                        "tx_count": profile.transaction_count,
                        "recent_buys_5min": recent_buys,
                    },
                    timestamp=now
                )
        
        # Pattern 2: Large volume with few tokens (potential wash trading)
        if profile.transaction_count > 10 and len(profile.unique_tokens) < 3:
            if profile.avg_transaction_amount > 10:  # SOL
                return SuspiciousActivity(
                    wallet=wallet_address,
                    activity_type="wash_trading_pattern",
                    confidence=0.7,
                    evidence={
                        "tx_count": profile.transaction_count,
                        "unique_tokens": len(profile.unique_tokens),
                        "avg_amount": profile.avg_transaction_amount,
                    },
                    timestamp=now
                )
        
        # Pattern 3: Unrealistic timing
        if len(profile.buy_times) > 5:
            avg_buy_interval = (
                (profile.buy_times[-1] - profile.buy_times[0]) / len(profile.buy_times)
                if len(profile.buy_times) > 1 else 0
            )
            if avg_buy_interval < 1:  # Less than 1 second between buys
                return SuspiciousActivity(
                    wallet=wallet_address,
                    activity_type="bot_like_timing",
                    confidence=0.8,
                    evidence={
                        "avg_buy_interval_sec": avg_buy_interval,
                        "total_buys": len(profile.buy_times),
                    },
                    timestamp=now
                )
        
        return None
    
    async def _emit_alert(self, activity: SuspiciousActivity):
        """Emit alert for suspicious activity."""
        if not self._alert_producer:
            return
        
        alert = {
            "alert_type": "wallet_suspicious_activity",
            "severity": "high" if activity.confidence > 0.75 else "medium",
            "wallet": activity.wallet,
            "activity_type": activity.activity_type,
            "confidence": activity.confidence,
            "evidence": activity.evidence,
            "worker_id": self.worker_id,
            "timestamp": int(activity.timestamp * 1000),
        }
        
        await self._alert_producer.publish_alert(alert)
        self.stats["alerts_emitted"] += 1
        
        logger.warning(
            "wallet_alert_emitted",
            wallet=activity.wallet[:8] + "...",
            activity_type=activity.activity_type,
            confidence=activity.confidence
        )
    
    def _evict_old_wallets(self, window_seconds: int):
        """Evict wallets outside the behavior window."""
        now = time.time()
        expired = [
            wallet for wallet, profile in self.wallet_profiles.items()
            if now - profile.last_seen > window_seconds
        ]
        for wallet in expired:
            del self.wallet_profiles[wallet]
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get extended worker statistics."""
        stats = await super().get_stats()
        stats.update({
            "wallets_analyzed": len(self.wallet_profiles),
            "suspicious_detected": self.stats.get("suspicious_detected", 0),
            "alerts_emitted": self.stats.get("alerts_emitted", 0),
        })
        return stats


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_worker(
    worker_id: str = "wallet-analyzer-1",
    redis_url: str = "redis://localhost:6379"
) -> WalletAnalyzerWorker:
    """Factory function to create a wallet analyzer worker."""
    config = WalletAnalyzerConfig(
        redis_url=redis_url,
        stream_name="godmode:new_transactions",
        group_name="wallet-analyzer-group",
    )
    return WalletAnalyzerWorker(
        worker_id=worker_id,
        redis_url=redis_url,
        config=config
    )


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Wallet Analyzer Worker")
    parser.add_argument(
        "--worker-id",
        default="wallet-analyzer-1",
        help="Worker identifier"
    )
    parser.add_argument(
        "--redis-url",
        default="redis://localhost:6379",
        help="Redis connection URL"
    )
    
    args = parser.parse_args()
    
    worker = WalletAnalyzerWorker(
        worker_id=args.worker_id,
        redis_url=args.redis_url
    )
    
    asyncio.run(worker.run())
