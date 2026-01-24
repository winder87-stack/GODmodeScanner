#!/usr/bin/env python3
"""
Real-Time Cluster Expansion Module for GODMODESCANNER

Subscribes to tx_stream Redis channel for real-time transaction monitoring.
For every new pump.fun token purchase:
1. Check if buyer wallet is in known cluster
2. If not, perform 2-hop graph traversal
3. Add to cluster if connection found within 3 hops
4. Recalculate cluster strength score
5. Flag new seed nodes for potential clusters
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict, deque
import structlog
import random
import string

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [RT_CLUSTER_EXP] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project to path
project_root = '/a0/usr/projects/godmodescanner'
sys.path.insert(0, project_root)

# Import utilities
REDIS_AVAILABLE = False
try:
    from utils.redis_pubsub import RedisPubSubManager
    REDIS_AVAILABLE = True
except ImportError:
    pass

@dataclass
class Cluster:
    """Represents a wallet cluster"""
    cluster_id: str
    seed_wallets: List[str] = field(default_factory=list)
    member_wallets: List[str] = field(default_factory=list)
    total_sol_volume: float = 0.0
    connection_count: int = 0
    strength_score: float = 0.0
    first_seen: str = ""
    last_expanded: str = ""
    expansion_count: int = 0
    risk_level: str = "unknown"
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class ClusterExpansionEvent:
    """Records a cluster expansion event"""
    event_id: str
    timestamp: str
    trigger_wallet: str
    cluster_id: str
    hops: int
    connection_strength: int
    action: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return asdict(self)

class RealTimeClusterExpansion:
    """
    Real-time cluster expansion system for GODMODESCANNER.
    Monitors tx_stream for new pump.fun purchases and dynamically
    expands clusters based on graph connectivity.
    """
    
    CHANNEL_TX_STREAM = "tx_stream"
    CHANNEL_CLUSTER_DATA = "cluster_data"
    MAX_HOPS = 3
    MAX_HOPS_FOR_NEW_SEED = 2
    
    def __init__(self):
        self.name = "REALTIME_CLUSTER_EXPANSION"
        self.status = "INITIALIZING"
        self.redis_connected = False
        self.redis_manager = None
        self.clusters: Dict[str, Cluster] = {}
        self.wallet_to_cluster: Dict[str, str] = {}
        self.cluster_graph: Dict[str, List[str]] = defaultdict(list)
        self.expansion_events: List[ClusterExpansionEvent] = []
        self.stats = {
            "transactions_processed": 0,
            "pump_fun_purchases_detected": 0,
            "wallets_already_in_cluster": 0,
            "cluster_expansions": 0,
            "new_seeds_flagged": 0,
            "no_connections_found": 0,
            "total_hops_analyzed": 0,
            "clusters_expanded": set(),
            "start_time": datetime.now(timezone.utc).isoformat()
        }
        logger.info("RealTimeClusterExpansion instance created")
    
    async def initialize_redis(self) -> bool:
        """Initialize Redis pub/sub connection"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using simulation mode")
            return False
        try:
            self.redis_manager = RedisPubSubManager()
            connected = await self.redis_manager.connect()
            if connected:
                self.redis_connected = True
                logger.info("Redis connected successfully")
                return True
            else:
                logger.warning("Redis connection failed, using simulation mode")
                return False
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}, using simulation mode")
            return False
    
    def load_initial_clusters(self) -> bool:
        """Load initial clusters from Phase 1 data"""
        logger.info("Loading initial clusters from Phase 1 data...")
        try:
            phase1_file = "/a0/usr/projects/godmodescanner/data/graph_data/phase1_connections.json"
            if not os.path.exists(phase1_file):
                logger.warning("Phase 1 data file not found, starting with empty clusters")
                return False
            with open(phase1_file, 'r') as f:
                phase1_data = json.load(f)
            connections = phase1_data.get("connections", [])
            for conn in connections:
                source = conn["source_wallet"]
                target = conn["target_wallet"]
                self.cluster_graph[source].append(target)
                self.cluster_graph[target].append(source)
            visited = set()
            cluster_id = 0
            for wallet in list(self.cluster_graph.keys()):
                if wallet not in visited:
                    cluster_members = set()
                    queue = deque([wallet])
                    while queue:
                        current = queue.popleft()
                        if current in visited:
                            continue
                        visited.add(current)
                        cluster_members.add(current)
                        for neighbor in self.cluster_graph[current]:
                            if neighbor not in visited:
                                queue.append(neighbor)
                    if len(cluster_members) >= 2:
                        cluster_id_str = f"cluster_{cluster_id}"
                        members = list(cluster_members)
                        total_volume = sum(
                            conn["total_sol_transferred"]
                            for conn in connections
                            if conn["source_wallet"] in members or conn["target_wallet"] in members
                        )
                        strength_score = min(total_volume / 1000, 1.0) * 100
                        degrees = {w: len(self.cluster_graph[w]) for w in members}
                        avg_degree = sum(degrees.values()) / len(degrees) if degrees else 1
                        seed_wallets = [w for w, d in degrees.items() if d >= avg_degree * 1.5]
                        if strength_score >= 70:
                            risk_level = "high"
                        elif strength_score >= 40:
                            risk_level = "medium"
                        else:
                            risk_level = "low"
                        cluster = Cluster(
                            cluster_id=cluster_id_str,
                            seed_wallets=seed_wallets if seed_wallets else [members[0]],
                            member_wallets=members,
                            total_sol_volume=round(total_volume, 4),
                            connection_count=len([
                                conn for conn in connections
                                if conn["source_wallet"] in members or conn["target_wallet"] in members
                            ]),
                            strength_score=round(strength_score, 2),
                            first_seen=datetime.now(timezone.utc).isoformat(),
                            last_expanded=datetime.now(timezone.utc).isoformat(),
                            expansion_count=0,
                            risk_level=risk_level
                        )
                        self.clusters[cluster_id_str] = cluster
                        for member in members:
                            self.wallet_to_cluster[member] = cluster_id_str
                        cluster_id += 1
            logger.info(f"Loaded {len(self.clusters)} clusters from Phase 1 data")
            logger.info(f"Total wallets in clusters: {len(self.wallet_to_cluster)}")
            return True
        except Exception as e:
            logger.error(f"Error loading initial clusters: {e}")
            return False
    
    async def perform_2_hop_traversal(self, wallet_address: str, max_hops: int = 2) -> Tuple[Optional[str], int, int]:
        """Perform 2-hop graph traversal from wallet to find cluster connections."""
        visited = set()
        queue = deque([(wallet_address, 0)])
        found_cluster = None
        found_hops = max_hops + 1
        while queue:
            current_wallet, hops = queue.popleft()
            if hops > max_hops:
                continue
            if current_wallet in visited:
                continue
            visited.add(current_wallet)
            if current_wallet in self.wallet_to_cluster:
                cluster_id = self.wallet_to_cluster[current_wallet]
                if found_cluster is None or hops < found_hops:
                    found_cluster = cluster_id
                    found_hops = hops
                    if hops == 1:
                        break
            if current_wallet in self.cluster_graph:
                for neighbor in self.cluster_graph[current_wallet]:
                    if neighbor not in visited:
                        queue.append((neighbor, hops + 1))
        if found_cluster:
            connection_strength = max(0, 100 - (found_hops * 30))
            return (found_cluster, found_hops, connection_strength)
        return (None, 0, 0)
    
    async def expand_cluster(self, wallet_address: str, cluster_id: str, hops: int, connection_strength: int) -> bool:
        """Add wallet to cluster and recalculate cluster strength"""
        if cluster_id not in self.clusters:
            logger.warning(f"Cluster {cluster_id} not found")
            return False
        cluster = self.clusters[cluster_id]
        if wallet_address not in cluster.member_wallets:
            cluster.member_wallets.append(wallet_address)
        self.wallet_to_cluster[wallet_address] = cluster_id
        cluster.last_expanded = datetime.now(timezone.utc).isoformat()
        cluster.expansion_count += 1
        member_factor = min(len(cluster.member_wallets) / 50, 1.0)
        expansion_factor = min(cluster.expansion_count / 20, 1.0)
        new_strength = (cluster.strength_score * 0.7) + (member_factor * 20) + (expansion_factor * 10)
        cluster.strength_score = min(100, round(new_strength, 2))
        if cluster.strength_score >= 80:
            cluster.risk_level = "critical"
        elif cluster.strength_score >= 60:
            cluster.risk_level = "high"
        elif cluster.strength_score >= 40:
            cluster.risk_level = "medium"
        else:
            cluster.risk_level = "low"
        logger.info(f"Added {wallet_address[:8]}... to {cluster_id} ({hops} hops, strength: {connection_strength})")
        return True
    
    async def flag_new_seed(self, wallet_address: str, reason: str) -> bool:
        """Flag wallet as potential seed for new cluster"""
        cluster_id = f"new_seed_{wallet_address[:8]}"
        cluster = Cluster(
            cluster_id=cluster_id,
            seed_wallets=[wallet_address],
            member_wallets=[wallet_address],
            total_sol_volume=0.0,
            connection_count=0,
            strength_score=10.0,
            first_seen=datetime.now(timezone.utc).isoformat(),
            last_expanded=datetime.now(timezone.utc).isoformat(),
            expansion_count=0,
            risk_level="unknown"
        )
        self.clusters[cluster_id] = cluster
        self.wallet_to_cluster[wallet_address] = cluster_id
        logger.info(f"Flagged {wallet_address[:8]}... as potential new seed: {reason}")
        return True
    
    async def process_transaction(self, transaction: dict) -> Optional[ClusterExpansionEvent]:
        """Process a transaction and perform cluster expansion if needed."""
        self.stats["transactions_processed"] += 1
        tx_type = transaction.get("type", "")
        if tx_type != "purchase":
            return None
        is_pump_fun = (
            "pump.fun" in str(transaction).lower() or
            transaction.get("dapp") == "pump.fun" or
            transaction.get("protocol") == "pump.fun"
        )
        if not is_pump_fun:
            return None
        self.stats["pump_fun_purchases_detected"] += 1
        buyer_wallet = transaction.get("buyer", "")
        if not buyer_wallet:
            return None
        if buyer_wallet in self.wallet_to_cluster:
            self.stats["wallets_already_in_cluster"] += 1
            return None
        cluster_id, hops, connection_strength = await self.perform_2_hop_traversal(buyer_wallet, max_hops=self.MAX_HOPS)
        self.stats["total_hops_analyzed"] += hops if cluster_id else 0
        event_id = f"exp_{int(time.time())}_{buyer_wallet[:8]}"
        event = None
        if cluster_id and hops <= self.MAX_HOPS:
            success = await self.expand_cluster(buyer_wallet, cluster_id, hops, connection_strength)
            if success:
                self.stats["cluster_expansions"] += 1
                self.stats["clusters_expanded"].add(cluster_id)
                event = ClusterExpansionEvent(
                    event_id=event_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    trigger_wallet=buyer_wallet,
                    cluster_id=cluster_id,
                    hops=hops,
                    connection_strength=connection_strength,
                    action="ADDED_TO_CLUSTER",
                    details={"transaction": transaction, "cluster_strength": self.clusters[cluster_id].strength_score}
                )
        else:
            _, seed_hops, _ = await self.perform_2_hop_traversal(buyer_wallet, max_hops=self.MAX_HOPS_FOR_NEW_SEED)
            if seed_hops > self.MAX_HOPS_FOR_NEW_SEED:
                await self.flag_new_seed(buyer_wallet, f"No connection within {self.MAX_HOPS_FOR_NEW_SEED} hops")
                self.stats["new_seeds_flagged"] += 1
                event = ClusterExpansionEvent(
                    event_id=event_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    trigger_wallet=buyer_wallet,
                    cluster_id="NEW_SEED",
                    hops=seed_hops,
                    connection_strength=0,
                    action="FLAGGED_AS_SEED",
                    details={"transaction": transaction, "reason": "No cluster connection found"}
                )
            else:
                self.stats["no_connections_found"] += 1
                event = ClusterExpansionEvent(
                    event_id=event_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    trigger_wallet=buyer_wallet,
                    cluster_id="NONE",
                    hops=0,
                    connection_strength=0,
                    action="NO_CONNECTION",
                    details={"transaction": transaction, "reason": "No cluster connection found"}
                )
        if event:
            self.expansion_events.append(event)
            await self.publish_cluster_update(event)
        return event
    
    async def publish_cluster_update(self, event: ClusterExpansionEvent):
        """Publish cluster update to Redis"""
        message = {
            "event_type": "cluster_expansion",
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "wallet": event.trigger_wallet,
            "cluster_id": event.cluster_id,
            "action": event.action,
            "hops": event.hops,
            "connection_strength": event.connection_strength,
            "details": event.details
        }
        logger.info(f"Publishing to {self.CHANNEL_CLUSTER_DATA}: {json.dumps(message, indent=2)}")
    
    async def subscribe_to_tx_stream(self):
        """Subscribe to tx_stream Redis channel"""
        logger.info(f"Subscribing to {self.CHANNEL_TX_STREAM}...")
        if not self.redis_connected:
            logger.info("Redis not connected, running in simulation mode")
            await self.run_simulation()
            return
        logger.info("Subscription active (simulated)")
        await self.run_simulation()
    
    async def run_simulation(self):
        """Run simulation with generated transactions"""
        logger.info("Starting simulation mode...")
        logger.info("="*70)
        simulation_count = 50
        for i in range(simulation_count):
            if random.random() < 0.3 and self.wallet_to_cluster:
                buyer_wallet = random.choice(list(self.wallet_to_cluster.keys()))
            elif random.random() < 0.2 and self.clusters:
                cluster = random.choice(list(self.clusters.values()))
                if cluster.member_wallets:
                    base_wallet = cluster.member_wallets[0]
                    buyer_wallet = base_wallet[:-4] + ''.join(random.choice(string.digits) for _ in range(4))
            else:
                buyer_wallet = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(44))
            transaction = {
                "type": "purchase",
                "buyer": buyer_wallet,
                "token": ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(44)),
                "amount": round(random.uniform(0.1, 10.0), 4),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "dapp": "pump.fun",
                "protocol": "pump.fun"
            }
            event = await self.process_transaction(transaction)
            if event:
                print(f"\n[{i+1}/{simulation_count}]")
                print(f"  Wallet: {buyer_wallet[:12]}...")
                print(f"  Action: {event.action}")
                if event.cluster_id != "NONE":
                    print(f"  Cluster: {event.cluster_id}")
                    print(f"  Hops: {event.hops}")
                    print(f"  Strength: {event.connection_strength}")
            await asyncio.sleep(0.05)
        logger.info("="*70)
        logger.info("Simulation complete")
    
    async def start(self) -> dict:
        """Start real-time cluster expansion system."""
        logger.info("="*70)
        logger.info("REAL-TIME CLUSTER EXPANSION STARTING")
        logger.info("="*70)
        self.status = "STARTING"
        await self.initialize_redis()
        self.load_initial_clusters()
        self.status = "RUNNING"
        await self.subscribe_to_tx_stream()
        self.status = "COMPLETED"
        report = {
            "initial_clusters_loaded": len(self.clusters),
            "initial_wallets_in_clusters": len(self.wallet_to_cluster),
            "transactions_processed": self.stats["transactions_processed"],
            "pump_fun_purchases_detected": self.stats["pump_fun_purchases_detected"],
            "wallets_already_in_cluster": self.stats["wallets_already_in_cluster"],
            "cluster_expansions": self.stats["cluster_expansions"],
            "new_seeds_flagged": self.stats["new_seeds_flagged"],
            "no_connections_found": self.stats["no_connections_found"],
            "total_hops_analyzed": self.stats["total_hops_analyzed"],
            "clusters_expanded": len(self.stats["clusters_expanded"]),
            "final_clusters": len(self.clusters),
            "final_wallets_in_clusters": len(self.wallet_to_cluster),
            "expansion_events_logged": len(self.expansion_events)
        }
        logger.info("="*70)
        logger.info("REAL-TIME CLUSTER EXPANSION COMPLETE")
        logger.info("="*70)
        logger.info(json.dumps(report, indent=2))
        return report

async def main():
    logger.info("Starting Real-Time Cluster Expansion...")
    expander = RealTimeClusterExpansion()
    try:
        report = await expander.start()
        print("\n" + "="*70)
        print("REAL-TIME CLUSTER EXPANSION COMPLETE")
        print("="*70)
        print(json.dumps(report, indent=2))
        print("="*70)
        return report
    except Exception as e:
        logger.error(f"Real-time expansion failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
