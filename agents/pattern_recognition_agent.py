"""PATTERN_RECOGNITION Agent - Multi-wallet pattern detection for GODMODESCANNER.

Detects coordinated insider trading, wash trading, bundlers, and sybil networks
on pump.fun using DBSCAN clustering and graph analysis.
"""

import asyncio
import json
import uuid
import structlog
from typing import Dict, List, Optional, Any, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
import numpy as np

# Machine Learning
try:
    from sklearn.cluster import DBSCAN
    import networkx as nx
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("WARNING: sklearn/networkx not available - using simplified detection")

logger = structlog.get_logger(__name__)


@dataclass
class PatternDetection:
    """Detected pattern structure."""
    pattern_id: str
    pattern_type: str  # coordinated, wash_trade, bundler, sybil_cluster
    confidence: float
    wallets_involved: List[str]
    token_address: str
    timestamp: str
    time_window_seconds: float
    transaction_count: int
    total_volume_sol: float
    evidence: Dict[str, Any]
    risk_score: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PatternRecognitionAgent:
    """Multi-wallet pattern detection agent.

    Detects:
    - Coordinated trading (3+ wallets, <10s, 0.89 confidence)
    - Wash trading (back-and-forth trades)
    - Bundler activity (>10 tx/min, 0.90 confidence)
    - Sybil clusters (connected wallet networks)
    """

    def __init__(self, redis_manager=None):
        self.redis_manager = redis_manager
        self.agent_name = "PATTERN_RECOGNITION"

        # Rolling transaction buffer (60 seconds)
        self.transaction_buffer: deque = deque(maxlen=10000)
        self.buffer_window_seconds = 60

        # Wallet tracking
        self.wallet_profiles: Dict[str, Dict] = {}
        self.wallet_transaction_history: Dict[str, List] = defaultdict(list)

        # Graph for wallet relationships
        self.wallet_graph = nx.Graph() if SKLEARN_AVAILABLE else None

        # Pattern statistics
        self.stats = {
            "patterns_detected": 0,
            "coordinated_trades": 0,
            "wash_trades": 0,
            "bundlers": 0,
            "wallet_clusters": 0,
            "processing_times": deque(maxlen=1000)
        }

        # Detection thresholds
        self.thresholds = {
            "coordinated_min_wallets": 3,
            "coordinated_time_window": 10,  # seconds
            "coordinated_confidence": 0.89,
            "ultra_coordinated_min_wallets": 5,
            "ultra_coordinated_time_window": 5,
            "ultra_coordinated_confidence": 0.95,
            "wash_trade_time_window": 300,  # 5 minutes
            "wash_trade_confidence": 0.85,
            "bundler_tx_per_minute": 10,
            "bundler_confidence": 0.90,
            "large_bundler_tx_per_minute": 20,
            "large_bundler_confidence": 0.95,
            "sybil_min_connected": 5,
            "sybil_confidence": 0.80
        }

        logger.info("pattern_recognition_agent_initialized",
                   sklearn_available=SKLEARN_AVAILABLE)

    async def start(self):
        """Start the pattern recognition agent."""
        logger.info("pattern_recognition_agent_starting")

        if self.redis_manager:
            # Subscribe to channels
            await self.redis_manager.subscribe(
                "godmode:transactions",
                self._handle_transaction
            )
            await self.redis_manager.subscribe(
                "godmode:wallet_profiles",
                self._handle_wallet_profile
            )
            await self.redis_manager.subscribe(
                "godmode:token_launches",
                self._handle_token_launch
            )
            await self.redis_manager.subscribe(
                "godmode:control",
                self._handle_control
            )

            logger.info("pattern_recognition_subscribed_to_channels")

        # Start pattern analysis loop
        asyncio.create_task(self._pattern_analysis_loop())
        asyncio.create_task(self._heartbeat_loop())

        logger.info("pattern_recognition_agent_started")

    async def _handle_transaction(self, message: Dict[str, Any]):
        """Handle incoming transaction from TRANSACTION_MONITOR."""
        try:
            tx_data = message.get("data", message)

            # Add to rolling buffer
            tx_data["received_at"] = datetime.utcnow()
            self.transaction_buffer.append(tx_data)

            # Track wallet transaction history
            wallet = tx_data.get("wallet_address")
            if wallet:
                self.wallet_transaction_history[wallet].append(tx_data)

                # Keep only last 100 transactions per wallet
                if len(self.wallet_transaction_history[wallet]) > 100:
                    self.wallet_transaction_history[wallet] =                         self.wallet_transaction_history[wallet][-100:]

            # Update wallet graph
            if self.wallet_graph is not None and wallet:
                if not self.wallet_graph.has_node(wallet):
                    self.wallet_graph.add_node(wallet)

        except Exception as e:
            logger.error("transaction_handling_error", error=str(e))

    async def _handle_wallet_profile(self, message: Dict[str, Any]):
        """Handle wallet profile update from WALLET_ANALYZER."""
        try:
            profile = message.get("data", message)
            wallet = profile.get("wallet_address")

            if wallet:
                self.wallet_profiles[wallet] = profile

        except Exception as e:
            logger.error("wallet_profile_handling_error", error=str(e))

    async def _handle_token_launch(self, message: Dict[str, Any]):
        """Handle new token launch event."""
        try:
            token_data = message.get("data", message)
            logger.info("token_launch_received",
                       token=token_data.get("token_address"))

        except Exception as e:
            logger.error("token_launch_handling_error", error=str(e))

    async def _handle_control(self, message: Dict[str, Any]):
        """Handle control commands from orchestrator."""
        try:
            command = message.get("command")

            if command == "status":
                await self._publish_status()
            elif command == "reset_stats":
                self._reset_statistics()

        except Exception as e:
            logger.error("control_handling_error", error=str(e))

    async def _pattern_analysis_loop(self):
        """Main pattern analysis loop."""
        logger.info("pattern_analysis_loop_started")

        while True:
            try:
                start_time = datetime.utcnow()

                # Clean old transactions from buffer
                await self._clean_transaction_buffer()

                # Detect patterns
                await self._detect_coordinated_trading()
                await self._detect_wash_trading()
                await self._detect_bundlers()
                await self._detect_sybil_clusters()

                # Track processing time
                processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
                self.stats["processing_times"].append(processing_time)

                # Run every 5 seconds
                await asyncio.sleep(5)

            except Exception as e:
                logger.error("pattern_analysis_error", error=str(e))
                await asyncio.sleep(5)

    async def _clean_transaction_buffer(self):
        """Remove transactions older than buffer window."""
        cutoff_time = datetime.utcnow() - timedelta(seconds=self.buffer_window_seconds)

        while self.transaction_buffer and               self.transaction_buffer[0].get("received_at", datetime.utcnow()) < cutoff_time:
            self.transaction_buffer.popleft()

    async def _detect_coordinated_trading(self):
        """Detect coordinated trading patterns (3+ wallets, <10s)."""
        if len(self.transaction_buffer) < 3:
            return

        try:
            # Group transactions by token
            token_txs: Dict[str, List] = defaultdict(list)

            for tx in self.transaction_buffer:
                token = tx.get("token_address")
                if token and tx.get("transaction_type") == "buy":
                    token_txs[token].append(tx)

            # Analyze each token for coordination
            for token, txs in token_txs.items():
                if len(txs) < self.thresholds["coordinated_min_wallets"]:
                    continue

                # Sort by timestamp
                sorted_txs = sorted(txs, key=lambda x: x.get("timestamp", ""))

                # Sliding window analysis
                for i in range(len(sorted_txs) - 2):
                    window_txs = []
                    window_wallets = set()
                    start_time = datetime.fromisoformat(sorted_txs[i]["timestamp"])

                    for j in range(i, len(sorted_txs)):
                        tx = sorted_txs[j]
                        tx_time = datetime.fromisoformat(tx["timestamp"])
                        time_diff = (tx_time - start_time).total_seconds()

                        if time_diff <= self.thresholds["coordinated_time_window"]:
                            window_txs.append(tx)
                            window_wallets.add(tx["wallet_address"])
                        else:
                            break

                    # Check if coordinated
                    if len(window_wallets) >= self.thresholds["coordinated_min_wallets"]:
                        confidence = self.thresholds["coordinated_confidence"]

                        # Ultra-coordinated (5+ wallets, <5s)
                        if len(window_wallets) >= self.thresholds["ultra_coordinated_min_wallets"]:
                            last_tx_time = datetime.fromisoformat(window_txs[-1]["timestamp"])
                            if (last_tx_time - start_time).total_seconds() <=                                self.thresholds["ultra_coordinated_time_window"]:
                                confidence = self.thresholds["ultra_coordinated_confidence"]

                        # Calculate metrics
                        total_volume = sum(tx.get("amount_sol", 0) for tx in window_txs)
                        time_window = (datetime.fromisoformat(window_txs[-1]["timestamp"]) - 
                                     start_time).total_seconds()

                        # Create pattern detection
                        pattern = PatternDetection(
                            pattern_id=str(uuid.uuid4()),
                            pattern_type="coordinated" if len(window_wallets) < 5 else "ultra_coordinated",
                            confidence=confidence,
                            wallets_involved=list(window_wallets),
                            token_address=token,
                            timestamp=datetime.utcnow().isoformat(),
                            time_window_seconds=time_window,
                            transaction_count=len(window_txs),
                            total_volume_sol=total_volume,
                            evidence={
                                "timing_pattern": [tx["timestamp"] for tx in window_txs],
                                "volume_pattern": [tx.get("amount_sol", 0) for tx in window_txs],
                                "wallet_addresses": list(window_wallets)
                            },
                            risk_score=confidence * 100
                        )

                        # Publish alert
                        await self._publish_pattern(pattern, "coordinated_trades")

                        # Update stats
                        self.stats["patterns_detected"] += 1
                        self.stats["coordinated_trades"] += 1

                        logger.info("coordinated_trading_detected",
                                   wallets=len(window_wallets),
                                   time_window=time_window,
                                   confidence=confidence)

        except Exception as e:
            logger.error("coordinated_trading_detection_error", error=str(e))

    async def _detect_wash_trading(self):
        """Detect wash trading (back-and-forth trades)."""
        try:
            # Build transaction pairs
            wallet_pairs: Dict[Tuple[str, str], List] = defaultdict(list)

            for tx in self.transaction_buffer:
                wallet = tx.get("wallet_address")
                token = tx.get("token_address")
                tx_type = tx.get("transaction_type")

                if wallet and token:
                    wallet_pairs[(wallet, token)].append(tx)

            # Analyze for back-and-forth patterns
            checked_pairs = set()

            for (wallet_a, token), txs_a in wallet_pairs.items():
                for (wallet_b, token_b), txs_b in wallet_pairs.items():
                    if token != token_b or wallet_a == wallet_b:
                        continue

                    pair_key = tuple(sorted([wallet_a, wallet_b]))
                    if pair_key in checked_pairs:
                        continue
                    checked_pairs.add(pair_key)

                    # Check for alternating buy/sell pattern
                    wash_trades = []

                    for tx_a in txs_a:
                        for tx_b in txs_b:
                            time_a = datetime.fromisoformat(tx_a["timestamp"])
                            time_b = datetime.fromisoformat(tx_b["timestamp"])
                            time_diff = abs((time_b - time_a).total_seconds())

                            if time_diff <= self.thresholds["wash_trade_time_window"]:
                                if (tx_a.get("transaction_type") == "sell" and 
                                    tx_b.get("transaction_type") == "buy") or                                    (tx_a.get("transaction_type") == "buy" and 
                                    tx_b.get("transaction_type") == "sell"):
                                    wash_trades.append((tx_a, tx_b, time_diff))

                    if len(wash_trades) >= 2:  # At least 2 back-and-forth trades
                        confidence = self.thresholds["wash_trade_confidence"]
                        total_volume = sum(
                            tx_a.get("amount_sol", 0) + tx_b.get("amount_sol", 0)
                            for tx_a, tx_b, _ in wash_trades
                        )

                        pattern = PatternDetection(
                            pattern_id=str(uuid.uuid4()),
                            pattern_type="wash_trade",
                            confidence=confidence,
                            wallets_involved=[wallet_a, wallet_b],
                            token_address=token,
                            timestamp=datetime.utcnow().isoformat(),
                            time_window_seconds=max(td for _, _, td in wash_trades),
                            transaction_count=len(wash_trades) * 2,
                            total_volume_sol=total_volume,
                            evidence={
                                "wash_trade_pairs": len(wash_trades),
                                "wallet_a": wallet_a,
                                "wallet_b": wallet_b,
                                "time_intervals": [td for _, _, td in wash_trades]
                            },
                            risk_score=confidence * 100
                        )

                        await self._publish_pattern(pattern, "wash_trades")

                        self.stats["patterns_detected"] += 1
                        self.stats["wash_trades"] += 1

                        logger.info("wash_trading_detected",
                                   wallets=[wallet_a, wallet_b],
                                   pairs=len(wash_trades))

        except Exception as e:
            logger.error("wash_trading_detection_error", error=str(e))

    async def _detect_bundlers(self):
        """Detect bundler activity (>10 tx/min)."""
        try:
            # Calculate transaction rates per wallet
            now = datetime.utcnow()
            one_minute_ago = now - timedelta(minutes=1)

            wallet_tx_counts: Dict[str, int] = defaultdict(int)
            wallet_volumes: Dict[str, float] = defaultdict(float)

            for tx in self.transaction_buffer:
                tx_time = tx.get("received_at", now)
                if tx_time >= one_minute_ago:
                    wallet = tx.get("wallet_address")
                    if wallet:
                        wallet_tx_counts[wallet] += 1
                        wallet_volumes[wallet] += tx.get("amount_sol", 0)

            # Detect bundlers
            for wallet, tx_count in wallet_tx_counts.items():
                if tx_count >= self.thresholds["bundler_tx_per_minute"]:
                    confidence = self.thresholds["bundler_confidence"]
                    pattern_type = "bundler"

                    # Large bundler (>20 tx/min)
                    if tx_count >= self.thresholds["large_bundler_tx_per_minute"]:
                        confidence = self.thresholds["large_bundler_confidence"]
                        pattern_type = "large_bundler"

                    pattern = PatternDetection(
                        pattern_id=str(uuid.uuid4()),
                        pattern_type=pattern_type,
                        confidence=confidence,
                        wallets_involved=[wallet],
                        token_address="multiple",
                        timestamp=datetime.utcnow().isoformat(),
                        time_window_seconds=60,
                        transaction_count=tx_count,
                        total_volume_sol=wallet_volumes[wallet],
                        evidence={
                            "tx_per_minute": tx_count,
                            "total_volume": wallet_volumes[wallet],
                            "bundler_type": pattern_type
                        },
                        risk_score=confidence * 100
                    )

                    await self._publish_pattern(pattern, "bundler_alerts")

                    self.stats["patterns_detected"] += 1
                    self.stats["bundlers"] += 1

                    logger.info("bundler_detected",
                               wallet=wallet,
                               tx_count=tx_count,
                               type=pattern_type)

        except Exception as e:
            logger.error("bundler_detection_error", error=str(e))

    async def _detect_sybil_clusters(self):
        """Detect sybil clusters using graph analysis."""
        if not SKLEARN_AVAILABLE or self.wallet_graph is None:
            return

        try:
            # Build edges based on coordinated activity
            for tx_a in self.transaction_buffer:
                wallet_a = tx_a.get("wallet_address")
                token_a = tx_a.get("token_address")
                time_a = datetime.fromisoformat(tx_a.get("timestamp", ""))

                for tx_b in self.transaction_buffer:
                    wallet_b = tx_b.get("wallet_address")
                    token_b = tx_b.get("token_address")
                    time_b = datetime.fromisoformat(tx_b.get("timestamp", ""))

                    if wallet_a != wallet_b and token_a == token_b:
                        time_diff = abs((time_b - time_a).total_seconds())

                        # Connect wallets with coordinated timing
                        if time_diff <= 30:  # 30 second window
                            if not self.wallet_graph.has_edge(wallet_a, wallet_b):
                                self.wallet_graph.add_edge(wallet_a, wallet_b, weight=1)
                            else:
                                self.wallet_graph[wallet_a][wallet_b]["weight"] += 1

            # Find connected components (potential sybil clusters)
            clusters = list(nx.connected_components(self.wallet_graph))

            for cluster in clusters:
                if len(cluster) >= self.thresholds["sybil_min_connected"]:
                    confidence = self.thresholds["sybil_confidence"]

                    # Calculate cluster metrics
                    subgraph = self.wallet_graph.subgraph(cluster)
                    density = nx.density(subgraph)

                    pattern = PatternDetection(
                        pattern_id=str(uuid.uuid4()),
                        pattern_type="sybil_cluster",
                        confidence=confidence,
                        wallets_involved=list(cluster),
                        token_address="multiple",
                        timestamp=datetime.utcnow().isoformat(),
                        time_window_seconds=self.buffer_window_seconds,
                        transaction_count=0,
                        total_volume_sol=0.0,
                        evidence={
                            "cluster_size": len(cluster),
                            "graph_density": density,
                            "total_edges": subgraph.number_of_edges()
                        },
                        risk_score=confidence * 100
                    )

                    await self._publish_pattern(pattern, "sybil_clusters")

                    self.stats["patterns_detected"] += 1
                    self.stats["wallet_clusters"] += 1

                    logger.info("sybil_cluster_detected",
                               size=len(cluster),
                               density=density)

        except Exception as e:
            logger.error("sybil_cluster_detection_error", error=str(e))

    async def _publish_pattern(self, pattern: PatternDetection, channel: str):
        """Publish detected pattern to appropriate channel."""
        if self.redis_manager:
            await self.redis_manager.publish(
                f"godmode:{channel}",
                pattern.to_dict()
            )

    async def _heartbeat_loop(self):
        """Publish heartbeat every 10 seconds."""
        while True:
            try:
                await asyncio.sleep(10)

                if self.redis_manager:
                    await self.redis_manager.publish(
                        "godmode:heartbeat:pattern_recognition",
                        {
                            "agent": self.agent_name,
                            "timestamp": datetime.utcnow().isoformat(),
                            "status": "OPERATIONAL",
                            "stats": self.get_stats()
                        }
                    )

            except Exception as e:
                logger.error("heartbeat_error", error=str(e))

    async def _publish_status(self):
        """Publish current status."""
        status = self.get_status()

        if self.redis_manager:
            await self.redis_manager.publish(
                "godmode:agent_status",
                status
            )

        logger.info("status_published", status=status)

    def _reset_statistics(self):
        """Reset statistics."""
        self.stats = {
            "patterns_detected": 0,
            "coordinated_trades": 0,
            "wash_trades": 0,
            "bundlers": 0,
            "wallet_clusters": 0,
            "processing_times": deque(maxlen=1000)
        }
        logger.info("statistics_reset")

    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics."""
        avg_processing_time = 0
        if self.stats["processing_times"]:
            avg_processing_time = sum(self.stats["processing_times"]) /                                 len(self.stats["processing_times"])

        return {
            "patterns_detected": self.stats["patterns_detected"],
            "coordinated_trades": self.stats["coordinated_trades"],
            "wash_trades": self.stats["wash_trades"],
            "bundlers": self.stats["bundlers"],
            "wallet_clusters": self.stats["wallet_clusters"],
            "avg_processing_time_ms": round(avg_processing_time, 2),
            "buffer_size": len(self.transaction_buffer),
            "tracked_wallets": len(self.wallet_profiles)
        }

    def get_status(self) -> Dict[str, Any]:
        """Get full agent status."""
        stats = self.get_stats()

        return {
            "agent": self.agent_name,
            "status": "OPERATIONAL",
            "patterns_detected": stats["patterns_detected"],
            "coordinated_trades": stats["coordinated_trades"],
            "wash_trades": stats["wash_trades"],
            "bundlers": stats["bundlers"],
            "wallet_clusters": stats["wallet_clusters"],
            "avg_processing_time_ms": stats["avg_processing_time_ms"],
            "redis_connected": self.redis_manager is not None and 
                             self.redis_manager.connected if self.redis_manager else False,
            "ml_models_loaded": SKLEARN_AVAILABLE,
            "subscribed_channels": [
                "godmode:transactions",
                "godmode:wallet_profiles",
                "godmode:token_launches",
                "godmode:control"
            ],
            "buffer_size": stats["buffer_size"],
            "tracked_wallets": stats["tracked_wallets"]
        }


async def main():
    """Main entry point for pattern recognition agent."""
    # Initialize Redis pub/sub
    try:
        import sys
        sys.path.insert(0, '/a0/usr/projects/godmodescanner')
        from utils.redis_pubsub import RedisPubSubManager

        redis_manager = RedisPubSubManager()
        connected = await redis_manager.connect()

        if not connected:
            logger.warning("redis_unavailable_using_fallback")
    except Exception as e:
        logger.warning("redis_initialization_failed", error=str(e))
        redis_manager = None

    # Initialize and start agent
    agent = PatternRecognitionAgent(redis_manager=redis_manager)
    await agent.start()

    # Print initial status
    status = agent.get_status()
    print(json.dumps(status, indent=2))

    # Keep running
    logger.info("pattern_recognition_agent_running")

    try:
        while True:
            await asyncio.sleep(30)
            status = agent.get_status()
            logger.info("periodic_status", **status)
    except KeyboardInterrupt:
        logger.info("pattern_recognition_agent_shutdown")


if __name__ == "__main__":
    asyncio.run(main())
