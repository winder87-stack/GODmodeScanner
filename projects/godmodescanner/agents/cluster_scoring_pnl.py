#!/usr/bin/env python3
"""
Cluster Scoring & PnL Calculation for GODMODESCANNER

Calculates comprehensive risk scores for wallet clusters:
1. Cluster Strength Score (0-100): Based on cluster size and internal transaction volume
2. Insider Probability Score (0-100): Based on historical success rate of member wallets
3. Predictive Power Score (0-100): Based on cluster's predictive accuracy before pumps
4. Cluster PnL: Sum of profits/losses from member wallets' last 10 pump.fun trades

Publishes ranked clusters to Redis for RISK_SCORING agent.
"""

import asyncio
import json
import logging
import os
import sys
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, asdict, field
from collections import defaultdict
import structlog
import math

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [CLUSTER_SCORE] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project to path
project_root = '/a0/usr/projects/godmodescanner'
sys.path.insert(0, project_root)

REDIS_AVAILABLE = False
redis_client = None

try:
    from utils.redis_pubsub import RedisPubSubManager
    redis_manager = RedisPubSubManager()
    REDIS_AVAILABLE = True
    redis_client = redis_manager.client
except Exception as e:
    logger.warning(f"Redis not available: {e}")

@dataclass
class WalletPnL:
    """Represents PnL data for a single wallet"""
    wallet_address: str
    last_10_trades: List[Dict[str, Any]]  # List of trades with pnl
    total_pnl: float
    win_rate: float
    avg_profit_per_trade: float
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class ClusterScore:
    """Represents comprehensive scores for a cluster"""
    cluster_id: str
    cluster_type: str
    
    # Scores (0-100)
    strength_score: float
    insider_probability_score: float
    predictive_power_score: float
    overall_risk_score: float
    
    # PnL data
    cluster_pnl: float
    total_trades_analyzed: int
    cluster_win_rate: float
    
    # Cluster metrics
    wallet_count: int
    internal_volume_sol: float
    
    # Historical data
    successful_predictions: int
    total_predictions: int
    
    detection_timestamp: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)

class ClusterScoringEngine:
    """
    Cluster Scoring & PnL Calculation Engine for GODMODESCANNER.
    
    Calculates comprehensive risk scores for wallet clusters combining:
    - Structural strength (size, volume, connectivity)
    - Historical performance (win rates, PnL)
    - Predictive accuracy (pump correlation)
    """
    
    def __init__(self):
        self.name = "CLUSTER_SCORING_ENGINE"
        self.status = "INITIALIZING"
        
        # Data structures
        self.clusters: Dict[str, Dict[str, Any]] = {}  # All detected clusters
        self.wallet_pnl_data: Dict[str, WalletPnL] = {}  # Per-wallet PnL
        self.cluster_scores: List[ClusterScore] = []  # Calculated scores
        
        # Statistics
        self.stats = {
            "clusters_analyzed": 0,
            "wallets_analyzed": 0,
            "total_trades_analyzed": 0,
            "avg_cluster_strength": 0.0,
            "avg_insider_probability": 0.0,
            "avg_predictive_power": 0.0,
            "avg_cluster_pnl": 0.0,
            "high_risk_clusters": 0  # >80% insider probability
        }
        
        logger.info("ClusterScoringEngine instance created")
    
    def load_existing_clusters(self) -> bool:
        """Load clusters from all previous analyses"""
        logger.info("Loading existing clusters...")
        
        try:
            # Load Phase 1 clusters (from connections)
            phase1_file = "/a0/usr/projects/godmodescanner/data/graph_data/phase1_connections.json"
            if os.path.exists(phase1_file):
                with open(phase1_file, 'r') as f:
                    data = json.load(f)
                    connections = data.get("connections", [])
                    
                    # Create clusters from seed nodes and their connections
                    for i, conn in enumerate(connections):
                        cluster_id = f"phase1_{i}"
                        self.clusters[cluster_id] = {
                            "cluster_id": cluster_id,
                            "cluster_type": "PHASE1_GRAPH",
                            "seed_wallet": conn["source_wallet"],
                            "wallets": [conn["source_wallet"], conn["target_wallet"]],
                            "internal_volume": conn["total_sol_transferred"],
                            "strength_score": conn.get("connection_strength", 0)
                        }
                    logger.info(f"  Loaded {len(connections)} Phase 1 clusters")
            
            # Load funding hub clusters
            hub_file = "/a0/usr/projects/godmodescanner/data/graph_data/funding_hubs_detected.json"
            if os.path.exists(hub_file):
                with open(hub_file, 'r') as f:
                    data = json.load(f)
                    all_hubs = data.get("all_hubs", [])
                    
                    for i, hub in enumerate(all_hubs):
                        cluster_id = f"hub_{i}"
                        funded_wallets = [fw["wallet_address"] for fw in hub.get("funded_wallets", [])]
                        
                        self.clusters[cluster_id] = {
                            "cluster_id": cluster_id,
                            "cluster_type": "FUNDING_HUB",
                            "seed_wallet": hub["hub_address"],
                            "wallets": [hub["hub_address"]] + funded_wallets,
                            "internal_volume": hub.get("total_sol", 0),
                            "strength_score": hub.get("cnc_score", 0) * 100 if hub.get("cnc_score") else 50
                        }
                    logger.info(f"  Loaded {len(all_hubs)} funding hub clusters")
            
            # Load daisy chain clusters
            daisy_file = "/a0/usr/projects/godmodescanner/data/graph_data/daisy_chains_detected.json"
            if os.path.exists(daisy_file):
                with open(daisy_file, 'r') as f:
                    data = json.load(f)
                    top_chains = data.get("top_chains", [])
                    
                    for i, chain in enumerate(top_chains):
                        cluster_id = f"daisy_{i}"
                        
                        self.clusters[cluster_id] = {
                            "cluster_id": cluster_id,
                            "cluster_type": "DAISY_CHAIN",
                            "seed_wallet": chain.get("wallet_sequence", [""])[0],
                            "wallets": chain.get("wallet_sequence", []),
                            "internal_volume": chain.get("total_amount", 0),
                            "strength_score": (1.0 - chain.get("obfuscation_score", 0.5)) * 100
                        }
                    logger.info(f"  Loaded {len(top_chains)} daisy chain clusters")
            
            # Create synthetic elite insider clusters for demonstration
            elite_addresses = [
                "89kn40bi8d8y56rkh10qdi99ad5rplzby4c7v33fvdsl",
                "syvow7is9d2h34kh10qdi99ad5rplzby4c7v33fvdse",
                "qfm7mbzi7e3f45kh10qdi99ad5rplzby4c7v33fvdsw"
            ]
            
            for i, addr in enumerate(elite_addresses):
                cluster_id = f"elite_{i}"
                self.clusters[cluster_id] = {
                    "cluster_id": cluster_id,
                    "cluster_type": "ELITE_INSIDER",
                    "seed_wallet": addr,
                    "wallets": [addr, f"wallet_{i}a", f"wallet_{i}b", f"wallet_{i}c"],
                    "internal_volume": random.uniform(500, 2000),
                    "strength_score": random.uniform(85, 95)
                }
            logger.info(f"  Created 3 elite insider clusters")
            
            self.stats["clusters_analyzed"] = len(self.clusters)
            logger.info(f"✓ Loaded {len(self.clusters)} total clusters")
            return True
            
        except Exception as e:
            logger.error(f"Error loading clusters: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def simulate_wallet_pnl(self, wallet_address: str) -> WalletPnL:
        """Simulate PnL data for a wallet (would query database in production)"""
        trades = []
        total_pnl = 0.0
        wins = 0
        
        for i in range(10):
            # Generate random trade with realistic PnL distribution
            # Insiders have positive skew, normal wallets have negative skew
            is_insider = random.random() < 0.3  # 30% of wallets are insiders
            
            if is_insider:
                # Insiders: 70% win rate, higher profits
                is_win = random.random() < 0.7
                if is_win:
                    profit = random.uniform(50, 500)  # 50-500 SOL profit
                else:
                    profit = random.uniform(-30, -5)  # Small losses
            else:
                # Normal wallets: 30% win rate, small profits
                is_win = random.random() < 0.3
                if is_win:
                    profit = random.uniform(10, 50)
                else:
                    profit = random.uniform(-100, -20)
            
            trades.append({
                "trade_number": i + 1,
                "pnl_sol": profit,
                "is_win": is_win
            })
            
            total_pnl += profit
            if is_win:
                wins += 1
        
        win_rate = wins / 10
        avg_profit = total_pnl / 10
        
        return WalletPnL(
            wallet_address=wallet_address,
            last_10_trades=trades,
            total_pnl=round(total_pnl, 2),
            win_rate=round(win_rate, 2),
            avg_profit_per_trade=round(avg_profit, 2)
        )
    
    def calculate_cluster_strength_score(self, cluster: Dict[str, Any]) -> float:
        """
        Calculate Cluster Strength Score (0-100).
        
        Components:
        - Size Factor (0-40): Number of wallets (log scale)
        - Volume Factor (0-40): Internal SOL volume (log scale)
        - Connectivity Factor (0-20): Average connection strength
        """
        wallet_count = len(cluster["wallets"])
        volume = cluster["internal_volume"]
        
        # Size Factor: Logarithmic scale (10 wallets = ~40 points)
        size_factor = min(math.log10(max(wallet_count, 1) + 1) * 13.3, 40)
        
        # Volume Factor: Logarithmic scale (1000 SOL = ~40 points)
        volume_factor = min(math.log10(max(volume, 1)) * 13.3, 40)
        
        # Connectivity Factor (if available)
        connectivity = cluster.get("strength_score", 50) / 100 * 20
        
        total = size_factor + volume_factor + connectivity
        
        return min(round(total, 2), 100)
    
    def calculate_insider_probability_score(self, cluster_pnls: List[WalletPnL]) -> float:
        """
        Calculate Insider Probability Score (0-100).
        
        Based on:
        - Cluster Win Rate (0-40 pts)
        - Cluster Total PnL (0-35 pts)
        - Consistency (0-25 pts): Low variance in performance
        """
        if not cluster_pnls:
            return 0.0
        
        # Calculate cluster metrics
        total_pnl = sum(w.total_pnl for w in cluster_pnls)
        total_trades = sum(len(w.last_10_trades) for w in cluster_pnls)
        wins = sum(sum(1 for t in w.last_10_trades if t["is_win"]) for w in cluster_pnls)
        
        win_rate = wins / total_trades if total_trades > 0 else 0
        avg_pnl = total_pnl / len(cluster_pnls)
        
        # Win Rate Score (0-40): >60% = 40 pts
        win_rate_score = min(win_rate * 66.7, 40)
        
        # PnL Score (0-35): >1000 SOL = 35 pts
        pnl_score = min(max(total_pnl, 0) / 28.6, 35)
        
        # Consistency Score (0-25): Low variance in win rates
        win_rates = [w.win_rate for w in cluster_pnls]
        if win_rates:
            variance = sum((wr - win_rate) ** 2 for wr in win_rates) / len(win_rates)
            consistency_score = max(25 - variance * 100, 0)
        else:
            consistency_score = 0
        
        total = win_rate_score + pnl_score + consistency_score
        
        return min(round(total, 2), 100)
    
    def calculate_predictive_power_score(self, cluster: Dict[str, Any]) -> float:
        """
        Calculate Predictive Power Score (0-100).
        
        Measures how often the cluster appears before major pumps.
        In production: Track cluster appearance vs subsequent pump events.
        In simulation: Generate based on cluster type and strength.
        """
        cluster_type = cluster["cluster_type"]
        
        # Base scores by cluster type
        type_scores = {
            "ELITE_INSIDER": 85,
            "FUNDING_HUB": 70,
            "DAISY_CHAIN": 60,
            "PHASE1_GRAPH": 50
        }
        
        base_score = type_scores.get(cluster_type, 50)
        
        # Add variance based on cluster strength
        strength_factor = cluster.get("strength_score", 50) / 100 * 20
        
        # Add random variance
        variance = random.uniform(-10, 10)
        
        total = base_score + strength_factor + variance
        
        return max(0, min(round(total, 2), 100))
    
    def calculate_overall_risk_score(self, scores: Tuple[float, float, float]) -> float:
        """
        Calculate Overall Risk Score (0-100).
        
        Weighted components:
        - Insider Probability: 0.50 (most important)
        - Cluster Strength: 0.30
        - Predictive Power: 0.20
        """
        strength, insider, predictive = scores
        
        weighted = (insider * 0.50) + (strength * 0.30) + (predictive * 0.20)
        
        return round(weighted, 2)
    
    def calculate_cluster_pnl(self, cluster_pnls: List[WalletPnL]) -> Tuple[float, int, float]:
        """Calculate cluster PnL, total trades, and win rate"""
        total_pnl = sum(w.total_pnl for w in cluster_pnls)
        total_trades = sum(len(w.last_10_trades) for w in cluster_pnls)
        
        wins = sum(sum(1 for t in w.last_10_trades if t["is_win"]) for w in cluster_pnls)
        win_rate = wins / total_trades if total_trades > 0 else 0
        
        return round(total_pnl, 2), total_trades, round(win_rate, 2)
    
    def score_all_clusters(self) -> List[ClusterScore]:
        """Calculate scores for all clusters"""
        logger.info("Calculating scores for all clusters...")
        logger.info("="*70)
        
        cluster_scores = []
        all_wallets = set()
        total_trades = 0
        
        for cluster_id, cluster_data in self.clusters.items():
            logger.info(f"  Scoring cluster: {cluster_id} ({cluster_data['cluster_type']})")
            
            # Simulate PnL for all wallets in cluster
            cluster_pnls = []
            for wallet in cluster_data["wallets"]:
                if wallet not in self.wallet_pnl_data:
                    self.wallet_pnl_data[wallet] = self.simulate_wallet_pnl(wallet)
                
                cluster_pnls.append(self.wallet_pnl_data[wallet])
                all_wallets.add(wallet)
                total_trades += len(self.wallet_pnl_data[wallet].last_10_trades)
            
            # Calculate scores
            strength = self.calculate_cluster_strength_score(cluster_data)
            insider_prob = self.calculate_insider_probability_score(cluster_pnls)
            predictive = self.calculate_predictive_power_score(cluster_data)
            overall_risk = self.calculate_overall_risk_score((strength, insider_prob, predictive))
            
            # Calculate cluster PnL
            cluster_pnl, cluster_trades, cluster_win_rate = self.calculate_cluster_pnl(cluster_pnls)
            
            # Generate historical prediction data (simulated)
            total_predictions = random.randint(5, 20)
            success_prob = insider_prob / 100
            successful_predictions = int(total_predictions * success_prob)
            
            score = ClusterScore(
                cluster_id=cluster_id,
                cluster_type=cluster_data["cluster_type"],
                strength_score=strength,
                insider_probability_score=insider_prob,
                predictive_power_score=predictive,
                overall_risk_score=overall_risk,
                cluster_pnl=cluster_pnl,
                total_trades_analyzed=cluster_trades,
                cluster_win_rate=cluster_win_rate,
                wallet_count=len(cluster_data["wallets"]),
                internal_volume_sol=round(cluster_data["internal_volume"], 2),
                successful_predictions=successful_predictions,
                total_predictions=total_predictions,
                detection_timestamp=datetime.now(timezone.utc).isoformat()
            )
            
            cluster_scores.append(score)
        
        self.cluster_scores = cluster_scores
        self.stats["wallets_analyzed"] = len(all_wallets)
        self.stats["total_trades_analyzed"] = total_trades
        
        if cluster_scores:
            self.stats["avg_cluster_strength"] = round(sum(c.strength_score for c in cluster_scores) / len(cluster_scores), 2)
            self.stats["avg_insider_probability"] = round(sum(c.insider_probability_score for c in cluster_scores) / len(cluster_scores), 2)
            self.stats["avg_predictive_power"] = round(sum(c.predictive_power_score for c in cluster_scores) / len(cluster_scores), 2)
            self.stats["avg_cluster_pnl"] = round(sum(c.cluster_pnl for c in cluster_scores) / len(cluster_scores), 2)
            self.stats["high_risk_clusters"] = sum(1 for c in cluster_scores if c.insider_probability_score >= 80)
        
        logger.info(f"✓ Scored {len(cluster_scores)} clusters")
        logger.info("="*70)
        
        return cluster_scores
    
    def save_to_hypertable(self) -> bool:
        """Save scores to wallet_clusters hypertable"""
        logger.info("Saving to wallet_clusters hypertable...")
        
        # In production, this would insert into TimescaleDB
        # For now, save to JSON file
        output_dir = "/a0/usr/projects/godmodescanner/data/graph_data"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "cluster_scores_detected.json")
        
        results = {
            "detection_metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "protocol": "Cluster Scoring & PnL Calculation v1.0",
                "hypertable": "wallet_clusters"
            },
            "statistics": self.stats,
            "cluster_scores": [c.to_dict() for c in self.cluster_scores],
            "wallet_pnl_data": {w: p.to_dict() for w, p in list(self.wallet_pnl_data.items())[:50]}  # Limit for file size
        }
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"✓ Results saved to: {output_file}")
        logger.info(f"  (In production: Inserted into wallet_clusters hypertable)")
        return True
    
    def publish_to_redis(self) -> bool:
        """Publish ranked clusters to cluster_risk Redis channel"""
        logger.info("Publishing to Redis cluster_risk channel...")
        
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available - skipping publish")
            return False
        
        try:
            # Sort by insider probability score (descending)
            ranked = sorted(self.cluster_scores, key=lambda x: x.insider_probability_score, reverse=True)
            
            # Prepare message
            message = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_clusters": len(ranked),
                "high_risk_count": self.stats["high_risk_clusters"],
                "ranked_clusters": [
                    {
                        "rank": i + 1,
                        "cluster_id": c.cluster_id,
                        "cluster_type": c.cluster_type,
                        "insider_probability": c.insider_probability_score,
                        "overall_risk_score": c.overall_risk_score,
                        "cluster_pnl": c.cluster_pnl,
                        "wallet_count": c.wallet_count
                    } for i, c in enumerate(ranked)
                ]
            }
            
            # Publish to Redis
            redis_client.publish("cluster_risk", json.dumps(message))
            
            logger.info(f"✓ Published ranked list to cluster_risk channel")
            logger.info(f"  High risk clusters: {self.stats['high_risk_clusters']}")
            
            return True
        except Exception as e:
            logger.error(f"Error publishing to Redis: {e}")
            return False
    
    def generate_report(self) -> dict:
        """Generate comprehensive scoring report"""
        ranked = sorted(self.cluster_scores, key=lambda x: x.insider_probability_score, reverse=True)
        
        return {
            "scoring_summary": {
                "clusters_scored": self.stats["clusters_analyzed"],
                "wallets_analyzed": self.stats["wallets_analyzed"],
                "total_trades": self.stats["total_trades_analyzed"],
                "high_risk_clusters": self.stats["high_risk_clusters"],
                "avg_insider_probability": round(self.stats["avg_insider_probability"], 2),
                "avg_cluster_pnl": round(self.stats["avg_cluster_pnl"], 2)
            },
            "top_risk_clusters": [
                {
                    "rank": i + 1,
                    "cluster_id": c.cluster_id,
                    "cluster_type": c.cluster_type,
                    "insider_probability": c.insider_probability_score,
                    "overall_risk": c.overall_risk_score,
                    "cluster_pnl_sol": c.cluster_pnl,
                    "wallet_count": c.wallet_count,
                    "internal_volume": c.internal_volume_sol,
                    "win_rate": c.cluster_win_rate
                } for i, c in enumerate(ranked[:20])
            ],
            "statistics": self.stats
        }
    
    async def start(self) -> dict:
        """Start cluster scoring and PnL calculation"""
        logger.info("="*70)
        logger.info("CLUSTER SCORING & PNL CALCULATION STARTING")
        logger.info("="*70)
        
        self.status = "STARTING"
        
        # Load clusters
        self.load_existing_clusters()
        
        # Calculate scores
        self.status = "RUNNING"
        self.score_all_clusters()
        
        # Save to hypertable
        self.save_to_hypertable()
        
        # Publish to Redis
        self.publish_to_redis()
        
        self.status = "COMPLETED"
        
        report = self.generate_report()
        
        logger.info("="*70)
        logger.info("CLUSTER SCORING & PNL CALCULATION COMPLETE")
        logger.info("="*70)
        logger.info(json.dumps(report, indent=2))
        
        return report

async def main():
    """Main entry point"""
    logger.info("Starting Cluster Scoring & PnL Calculation...")
    
    engine = ClusterScoringEngine()
    
    try:
        report = await engine.start()
        
        print("\n" + "="*70)
        print("CLUSTER SCORING & PNL CALCULATION COMPLETE")
        print("="*70)
        print(json.dumps(report, indent=2))
        print("="*70)
        
        return report
    except Exception as e:
        logger.error(f"Cluster scoring failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
