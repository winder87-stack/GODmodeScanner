#!/usr/bin/env python3
"""Sybil Detection Worker - Parallel Sybil network detection.

This worker processes transactions from Redis Streams to identify
Sybil networks - multiple wallets controlled by the same entity
used to manipulate markets and evade detection.

Key Features:
- Behavioral similarity analysis across wallets
- Coordinated action detection
- Funding hub identification
- Real-time Sybil network alerts
- Graph-based clustering
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict, deque
import structlog
import random

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


@dataclass
class WalletBehavior:
    """Behavioral profile for a wallet."""
    wallet_address: str
    first_seen: float = 0.0
    last_seen: float = 0.0
    transaction_count: int = 0
    unique_tokens: Set[str] = field(default_factory=set)
    buy_times: List[float] = field(default_factory=list)
    sell_times: List[float] = field(default_factory=list)
    funding_sources: Set[str] = field(default_factory=set)
    funding_destinations: Set[str] = field(default_factory=set)
    avg_transaction_amount: float = 0.0
    
    def get_behavioral_signature(self) -> str:
        """Generate a simple behavioral signature."""
        # Simplified: hash key metrics
        sig = f"{self.transaction_count}_{len(self.unique_tokens)}_{self.avg_transaction_amount:.2f}"
        return sig


@dataclass
class SybilCluster:
    """Represents a detected Sybil cluster."""
    cluster_id: str
    wallets: Set[str]
    confidence: float
    common_funding_source: Optional[str] = None
    coordinated_actions: int = 0
    first_detected: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "wallets": list(self.wallets),
            "wallet_count": len(self.wallets),
            "confidence": self.confidence,
            "common_funding_source": self.common_funding_source,
            "coordinated_actions": self.coordinated_actions,
            "first_detected": self.first_detected,
        }


class SybilDetectionWorker(AgentWorker):
    """Parallel Sybil detection worker.
    
    This worker processes transactions from Redis Streams and:
    - Builds behavioral profiles for wallets
    - Detects behavioral similarity (Sybil candidates)
    - Identifies common funding sources
    - Detects coordinated trading actions
    - Emits alerts for high-confidence Sybil networks
    """

    # Configuration
    BEHAVIOR_WINDOW_SECONDS = 600  # 10-minute window for behavior analysis
    MIN_CLUSTER_SIZE = 2  # Minimum wallets for a Sybil cluster
    MAX_WALLETS_TRACKED = 5000
    SIMILARITY_THRESHOLD = 0.7  # Behavioral similarity threshold
    
    def __init__(self, worker_id: str, redis_url: str = "redis://localhost:6379"):
        """Initialize Sybil detection worker.
        
        Args:
            worker_id: Unique identifier for this worker instance
            redis_url: Redis connection URL
        """
        super().__init__(agent_type="sybil-detection")
        self.worker_id = worker_id
        self.redis_url = redis_url
        
        # Wallet behavioral profiles
        self.wallet_profiles: Dict[str, WalletBehavior] = {}
        
        # Detected Sybil clusters
        self.sybil_clusters: Dict[str, SybilCluster] = {}
        
        # Funding graph (wallet -> funding sources)
        self.funding_graph: Dict[str, Set[str]] = defaultdict(set)
        
        # Recent transactions for coordination detection
        self.recent_transactions: deque = deque(maxlen=10000)
        
        # Producer for alerts
        self.alert_producer: Optional[RedisStreamsProducer] = None
        
        # Statistics
        self.stats = {
            "worker_id": worker_id,
            "transactions_processed": 0,
            "wallets_analyzed": 0,
            "sybil_clusters_detected": 0,
            "alerts_emitted": 0,
            "processing_time_ms": 0.0,
        }
        
        logger.info(
            "sybil_detection_worker_init",
            worker_id=worker_id,
            redis_url=redis_url,
        )

    async def initialize(self):
        """Initialize the worker."""
        self.alert_producer = RedisStreamsProducer(redis_url=self.redis_url)
        await self.alert_producer.connect()
        logger.info("sybil_detection_worker_initialized", worker_id=self.worker_id)

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
            
            # Extract wallet and token
            wallet_address = tx_data.get("signer") or tx_data.get("wallet")
            token_address = tx_data.get("token") or tx_data.get("mint")
            
            if not wallet_address:
                return True
            
            # Update wallet profile
            await self._update_wallet_profile(wallet_address, token_address, tx_data)
            
            # Update funding graph
            await self._update_funding_graph(wallet_address, tx_data)
            
            # Add to recent transactions
            self.recent_transactions.append({
                "wallet": wallet_address,
                "token": token_address,
                "type": tx_data.get("type", "unknown"),
                "timestamp": time.time(),
            })
            
            # Periodically analyze for Sybil clusters
            if self.stats["transactions_processed"] % 100 == 0:
                await self._analyze_sybil_clusters()
            
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

    async def _update_wallet_profile(self, wallet_address: str, token_address: str, tx_data: Dict[str, Any]):
        """Update behavioral profile for a wallet."""
        now = time.time()
        
        # Get or create wallet profile
        if wallet_address not in self.wallet_profiles:
            if len(self.wallet_profiles) >= self.MAX_WALLETS_TRACKED:
                self._evict_old_wallets()
            
            self.wallet_profiles[wallet_address] = WalletBehavior(
                wallet_address=wallet_address,
                first_seen=now,
            )
        
        profile = self.wallet_profiles[wallet_address]
        
        # Update profile
        profile.last_seen = now
        profile.transaction_count += 1
        
        if token_address:
            profile.unique_tokens.add(token_address)
        
        # Track buy/sell times
        tx_type = tx_data.get("type", "").lower()
        amount = float(tx_data.get("amount", 0))
        
        if "buy" in tx_type:
            profile.buy_times.append(now)
        elif "sell" in tx_type:
            profile.sell_times.append(now)
        
        # Update average transaction amount
        profile.avg_transaction_amount = (
            (profile.avg_transaction_amount * (profile.transaction_count - 1) + amount) /
            profile.transaction_count
        )
        
        self.stats["wallets_analyzed"] = len(self.wallet_profiles)

    async def _update_funding_graph(self, wallet_address: str, tx_data: Dict[str, Any]):
        """Update the funding graph."""
        # Extract funding information
        funding_source = tx_data.get("funding_source") or tx_data.get("from")
        funding_dest = tx_data.get("funding_destination") or tx_data.get("to")
        
        if funding_source and funding_source != wallet_address:
            self.funding_graph[wallet_address].add(funding_source)
        
        if funding_dest and funding_dest != wallet_address:
            self.funding_graph[wallet_address].add(funding_dest)

    async def _analyze_sybil_clusters(self):
        """Analyze for Sybil clusters based on behavior and funding."""
        now = time.time()
        
        # 1. Detect by common funding source
        funding_clusters = self._detect_by_funding_source()
        for cluster in funding_clusters:
            self._update_sybil_cluster(cluster)
        
        # 2. Detect by behavioral similarity
        behavior_clusters = self._detect_by_behavioral_similarity()
        for cluster in behavior_clusters:
            self._update_sybil_cluster(cluster)
        
        # 3. Detect coordinated actions
        coordinated_clusters = self._detect_coordinated_actions()
        for cluster in coordinated_clusters:
            self._update_sybil_cluster(cluster)
        
        # Emit alerts for high-confidence clusters
        for cluster_id, cluster in self.sybil_clusters.items():
            if cluster.confidence > 0.7 and len(cluster.wallets) >= self.MIN_CLUSTER_SIZE:
                await self._emit_sybil_alert(cluster)

    def _detect_by_funding_source(self) -> List[SybilCluster]:
        """Detect Sybil clusters by common funding source."""
        clusters = []
        
        # Group wallets by funding sources
        funding_to_wallets = defaultdict(set)
        for wallet, sources in self.funding_graph.items():
            for source in sources:
                funding_to_wallets[source].add(wallet)
        
        # Create clusters for wallets with common funding
        for funding_source, wallets in funding_to_wallets.items():
            if len(wallets) >= self.MIN_CLUSTER_SIZE:
                cluster = SybilCluster(
                    cluster_id=f"funding-{funding_source[:8]}",
                    wallets=wallets,
                    confidence=0.6,  # Base confidence for common funding
                    common_funding_source=funding_source,
                    first_detected=time.time(),
                )
                clusters.append(cluster)
        
        return clusters

    def _detect_by_behavioral_similarity(self) -> List[SybilCluster]:
        """Detect Sybil clusters by behavioral similarity."""
        clusters = []
        
        # Group wallets by behavioral signature
        signature_to_wallets = defaultdict(set)
        for wallet, profile in self.wallet_profiles.items():
            signature = profile.get_behavioral_signature()
            signature_to_wallets[signature].add(wallet)
        
        # Create clusters for wallets with similar behavior
        for signature, wallets in signature_to_wallets.items():
            if len(wallets) >= self.MIN_CLUSTER_SIZE:
                cluster = SybilCluster(
                    cluster_id=f"behavior-{signature[:8]}",
                    wallets=wallets,
                    confidence=0.5,  # Base confidence for behavioral similarity
                    first_detected=time.time(),
                )
                clusters.append(cluster)
        
        return clusters

    def _detect_coordinated_actions(self) -> List[SybilCluster]:
        """Detect coordinated actions across wallets."""
        clusters = []
        
        if not self.recent_transactions:
            return clusters
        
        now = time.time()
        recent_txs = [
            tx for tx in self.recent_transactions
            if now - tx["timestamp"] < 60  # Last 60 seconds
        ]
        
        if len(recent_txs) < 10:
            return clusters
        
        # Group by token
        token_to_wallets = defaultdict(set)
        for tx in recent_txs:
            token_to_wallets[tx["token"]].add(tx["wallet"])
        
        # Detect coordinated buys/sells on same token
        for token, wallets in token_to_wallets.items():
            if len(wallets) >= self.MIN_CLUSTER_SIZE:
                cluster = SybilCluster(
                    cluster_id=f"coordinated-{token[:8]}",
                    wallets=wallets,
                    confidence=0.55,  # Base confidence for coordination
                    coordinated_actions=len([tx for tx in recent_txs if tx["token"] == token]),
                    first_detected=now,
                )
                clusters.append(cluster)
        
        return clusters

    def _update_sybil_cluster(self, new_cluster: SybilCluster):
        """Update or create a Sybil cluster."""
        cluster_id = new_cluster.cluster_id
        
        if cluster_id in self.sybil_clusters:
            existing = self.sybil_clusters[cluster_id]
            
            # Merge wallets
            existing.wallets.update(new_cluster.wallets)
            
            # Update confidence (max of both)
            existing.confidence = max(existing.confidence, new_cluster.confidence)
            
            # Update coordinated actions
            existing.coordinated_actions += new_cluster.coordinated_actions
        else:
            self.sybil_clusters[cluster_id] = new_cluster
            self.stats["sybil_clusters_detected"] += 1

    async def _emit_sybil_alert(self, cluster: SybilCluster):
        """Emit an alert for a detected Sybil cluster."""
        if not self.alert_producer:
            return
        
        alert = {
            "alert_type": "sybil_cluster_detected",
            "severity": "critical" if cluster.confidence > 0.85 else "high",
            "cluster_id": cluster.cluster_id,
            "wallet_count": len(cluster.wallets),
            "wallets": list(cluster.wallets)[:10],  # Limit to first 10
            "confidence": cluster.confidence,
            "common_funding_source": cluster.common_funding_source,
            "coordinated_actions": cluster.coordinated_actions,
            "worker_id": self.worker_id,
            "timestamp": int(time.time() * 1000),
        }
        
        await self.alert_producer.publish_alert(alert)
        self.stats["alerts_emitted"] += 1
        
        logger.warning(
            "sybil_cluster_alert_emitted",
            cluster=cluster.cluster_id,
            wallet_count=len(cluster.wallets),
            confidence=cluster.confidence,
            worker=self.worker_id,
        )

    def _evict_old_wallets(self):
        """Evict old wallet profiles if at capacity."""
        now = time.time()
        expired = [
            wallet for wallet, profile in self.wallet_profiles.items()
            if now - profile.last_seen > self.BEHAVIOR_WINDOW_SECONDS
        ]
        for wallet in expired:
            del self.wallet_profiles[wallet]

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
        base_stats["active_clusters"] = len(self.sybil_clusters)
        base_stats["wallets_tracked"] = len(self.wallet_profiles)
        return base_stats

    async def close(self):
        """Clean up resources."""
        if self.alert_producer:
            await self.alert_producer.close()
        logger.info("sybil_detection_worker_closed", worker_id=self.worker_id)


def create_worker(worker_id: str, redis_url: str = "redis://localhost:6379") -> SybilDetectionWorker:
    """Factory function to create a Sybil detection worker."""
    return SybilDetectionWorker(worker_id=worker_id, redis_url=redis_url)
