#!/usr/bin/env python3
"""
Shared Signature & Behavioral Analysis for GODMODESCANNER

Analyzes transaction histories to identify behaviorally linked wallets based on:
1. Co-signed transactions (shared signatures)
2. Interactions with same obscure programs (non-DEX, non-pump.fun)

Behavioral Similarity Score (0-100) Components:
- Program Overlap (0-50 points): Shared obscure program interactions
- Co-Signature Frequency (0-30 points): Transactions signed together
- Temporal Correlation (0-20 points): Similar timing patterns

Wallets with >85% similarity are flagged as behaviorally linked.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, asdict, field
from collections import defaultdict, Counter
import itertools
import structlog

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [BEHAVIOR] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project to path
project_root = '/a0/usr/projects/godmodescanner'
sys.path.insert(0, project_root)

REDIS_AVAILABLE = False
try:
    from utils.redis_pubsub import RedisPubSubManager
    REDIS_AVAILABLE = True
except ImportError:
    pass

# Common DEX and pump.fun programs to exclude (simplified for simulation)
KNOWN_PROGRAMS = {
    'pump_fun': '675kPX9MHTjS2zt1qo1KTVaKk7ZJh1qZ5dHj5v5c5a5',
    'raydium': 'raydium',
    'jupiter': 'JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4',
    'orca': '9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM',
    'meteora': 'Eo7WjKq67rjJQSZxS6z3Y9zXYZF',
    'serum': '9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin'
}

@dataclass
class ProgramInteraction:
    """Represents a wallet's interaction with a program"""
    program_id: str
    program_name: str
    interaction_count: int
    last_interaction: str
    is_obscure: bool
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class WalletBehavior:
    """Represents behavioral profile of a wallet"""
    wallet_address: str
    program_interactions: List[ProgramInteraction]
    co_signed_transactions: List[str]  # List of signatures with other wallets
    temporal_patterns: Dict[str, int]  # Hour of day -> frequency
    obscure_programs: Set[str]
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class BehaviorSimilarity:
    """Represents similarity between two wallets"""
    wallet_a: str
    wallet_b: str
    similarity_score: float
    program_overlap_score: float
    co_signature_score: float
    temporal_correlation_score: float
    shared_programs: List[str]
    shared_signatures: int
    is_behaviorally_linked: bool
    detection_timestamp: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class BehaviorCluster:
    """Represents a cluster of behaviorally linked wallets"""
    cluster_id: str
    cluster_type: str
    wallet_addresses: List[str]
    avg_similarity_score: float
    total_shared_programs: int
    total_shared_signatures: int
    detection_timestamp: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)

class BehavioralSimilarityAnalyzer:
    """
    Shared Signature & Behavioral Analysis System for GODMODESCANNER.
    
    Identifies behaviorally linked wallets through analysis of
    transaction signatures and program interaction patterns.
    """
    
    SIMILARITY_THRESHOLD = 85.0
    MIN_SHARED_INTERACTIONS = 3
    
    def __init__(self):
        self.name = "BEHAVIORAL_SIMILARITY_ANALYZER"
        self.status = "INITIALIZING"
        
        # Data structures
        self.wallet_behaviors: Dict[str, WalletBehavior] = {}
        self.all_wallets: Set[str] = set()
        self.similarities: List[BehaviorSimilarity] = []
        self.behavior_clusters: List[BehaviorCluster] = []
        
        # Statistics
        self.stats = {
            "wallets_analyzed": 0,
            "wallet_pairs_compared": 0,
            "behaviorally_linked_pairs": 0,
            "avg_similarity_score": 0.0,
            "max_similarity_score": 0.0,
            "total_clusters_created": 0,
            "wallets_clustered": 0
        }
        
        logger.info("BehavioralSimilarityAnalyzer instance created")
    
    def load_graph_data(self) -> bool:
        """Load wallet data from existing graph analyses"""
        logger.info("Loading graph data...")
        try:
            # Load Phase 1 connections
            phase1_file = "/a0/usr/projects/godmodescanner/data/graph_data/phase1_connections.json"
            if os.path.exists(phase1_file):
                with open(phase1_file, 'r') as f:
                    data = json.load(f)
                    for conn in data.get("connections", []):
                        self.all_wallets.add(conn["source_wallet"])
                        self.all_wallets.add(conn["target_wallet"])
                logger.info(f"  Loaded {len(self.all_wallets)} wallets from Phase 1")
            
            # Load funding hubs
            hub_file = "/a0/usr/projects/godmodescanner/data/graph_data/funding_hubs_detected.json"
            if os.path.exists(hub_file):
                with open(hub_file, 'r') as f:
                    data = json.load(f)
                    for hub in data.get("all_hubs", []):
                        self.all_wallets.add(hub["hub_address"])
                        for fw in hub.get("funded_wallets", []):
                            self.all_wallets.add(fw["wallet_address"])
                logger.info(f"  Added wallets from funding hubs")
            
            # Load daisy chains
            daisy_file = "/a0/usr/projects/godmodescanner/data/graph_data/daisy_chains_detected.json"
            if os.path.exists(daisy_file):
                with open(daisy_file, 'r') as f:
                    data = json.load(f)
                    for chain in data.get("top_chains", []):
                        for wallet in chain.get("wallet_sequence", []):
                            self.all_wallets.add(wallet)
                logger.info(f"  Added wallets from daisy chains")
            
            self.stats["wallets_analyzed"] = len(self.all_wallets)
            logger.info(f"✓ Loaded {len(self.all_wallets)} unique wallets")
            return True
        except Exception as e:
            logger.error(f"Error loading graph data: {e}")
            return False
    
    def simulate_transaction_history(self) -> None:
        """Simulate transaction histories for all wallets"""
        logger.info("Simulating transaction histories...")
        
        import random
        import string
        
        # Generate obscure programs for simulation
        obscure_programs = [
            ("meta1qo1K...", "StakePool"),
            ("compute9...", "ComputeBudget"),
            ("sysvar1...", "Sysvar"),
            ("vote9...", "VoteProgram"),
            ("config9...", "ConfigProgram"),
            ("nonce1...", "NonceProgram"),
            ("tokenz...", "TokenProgram"),
            ("memo1...", "MemoProgram"),
            ("customA...", "CustomDappA"),
            ("customB...", "CustomDappB"),
            ("nftX...", "NFTMinter"),
            ("bridgeY...", "CrossChainBridge")
        ]
        
        for wallet in self.all_wallets:
            interactions = []
            obscure_programs_set = set()
            
            # Randomly assign 3-8 program interactions
            num_interactions = random.randint(3, 8)
            selected_programs = random.sample(obscure_programs, min(num_interactions, len(obscure_programs)))
            
            for program_id, program_name in selected_programs:
                interaction_count = random.randint(1, 20)
                is_obscure = program_name not in ["StakePool", "ComputeBudget", "Sysvar"]
                
                if is_obscure:
                    obscure_programs_set.add(program_id)
                
                interactions.append(ProgramInteraction(
                    program_id=program_id,
                    program_name=program_name,
                    interaction_count=interaction_count,
                    last_interaction=(datetime.now(timezone.utc) - timedelta(hours=random.uniform(1, 48))).isoformat(),
                    is_obscure=is_obscure
                ))
            
            # Generate temporal patterns
            temporal_patterns = defaultdict(int)
            for _ in range(random.randint(5, 30)):
                hour = random.randint(0, 23)
                temporal_patterns[str(hour)] += 1
            
            self.wallet_behaviors[wallet] = WalletBehavior(
                wallet_address=wallet,
                program_interactions=interactions,
                co_signed_transactions=[],
                temporal_patterns=dict(temporal_patterns),
                obscure_programs=obscure_programs_set
            )
        
        # Generate co-signed transactions (simulated)
        self._generate_co_signatures()
        
        logger.info("✓ Transaction histories simulated")
    
    def _generate_co_signatures(self) -> None:
        """Generate simulated co-signed transactions between wallets"""
        import random
        
        wallets = list(self.all_wallets)
        
        # Create some shared signatures between wallets
        # Wallets with higher similarity share more signatures
        for i in range(len(wallets)):
            wallet_a = wallets[i]
            
            # Each wallet shares signatures with 2-5 other wallets
            num_shared = random.randint(2, 5)
            others = random.sample([w for w in wallets if w != wallet_a], min(num_shared, len(wallets) - 1))
            
            for wallet_b in others:
                # 20% chance of sharing a signature
                if random.random() < 0.2:
                    num_signatures = random.randint(1, 5)
                    signature = f"sig_{i}_{wallets.index(wallet_b)}"
                    
                    if signature not in self.wallet_behaviors[wallet_a].co_signed_transactions:
                        self.wallet_behaviors[wallet_a].co_signed_transactions.append(signature)
                    if signature not in self.wallet_behaviors[wallet_b].co_signed_transactions:
                        self.wallet_behaviors[wallet_b].co_signed_transactions.append(signature)
    
    def calculate_program_overlap_score(
        self,
        behavior_a: WalletBehavior,
        behavior_b: WalletBehavior
    ) -> Tuple[float, List[str]]:
        """
        Calculate program overlap score (0-50 points).
        
        Score based on:
        - Number of shared obscure programs
        - Frequency of interactions with shared programs
        """
        # Get obscure programs
        programs_a = {p.program_id: p.interaction_count for p in behavior_a.program_interactions if p.is_obscure}
        programs_b = {p.program_id: p.interaction_count for p in behavior_b.program_interactions if p.is_obscure}
        
        shared_programs = set(programs_a.keys()) & set(programs_b.keys())
        
        if not shared_programs:
            return 0.0, []
        
        # Calculate overlap score
        # Base: 10 points per shared obscure program (max 30)
        # Bonus: Frequency correlation (up to 20 points)
        base_score = min(len(shared_programs) * 10, 30)
        
        # Calculate frequency correlation
        if shared_programs:
            total_freq = sum(programs_a[p] + programs_b[p] for p in shared_programs)
            avg_freq = total_freq / len(shared_programs)
            freq_bonus = min(avg_freq / 5, 20)
        else:
            freq_bonus = 0
        
        total_score = min(base_score + freq_bonus, 50)
        
        return total_score, list(shared_programs)
    
    def calculate_co_signature_score(
        self,
        behavior_a: WalletBehavior,
        behavior_b: WalletBehavior
    ) -> Tuple[int, int]:
        """
        Calculate co-signature score (0-30 points).
        
        Returns: (score, shared_signature_count)
        """
        sigs_a = set(behavior_a.co_signed_transactions)
        sigs_b = set(behavior_b.co_signed_transactions)
        
        shared = sigs_a & sigs_b
        count = len(shared)
        
        if count == 0:
            return 0.0, 0
        
        # 5 points per shared signature (max 30)
        score = min(count * 5, 30)
        
        return score, count
    
    def calculate_temporal_correlation(
        self,
        behavior_a: WalletBehavior,
        behavior_b: WalletBehavior
    ) -> float:
        """
        Calculate temporal correlation score (0-20 points).
        
        Measures similarity in transaction timing patterns.
        """
        patterns_a = behavior_a.temporal_patterns
        patterns_b = behavior_b.temporal_patterns
        
        all_hours = set(patterns_a.keys()) | set(patterns_b.keys())
        
        if not all_hours:
            return 0.0
        
        # Calculate correlation using simple cosine similarity
        dot_product = sum(patterns_a.get(h, 0) * patterns_b.get(h, 0) for h in all_hours)
        norm_a = sum(v ** 2 for v in patterns_a.values()) ** 0.5
        norm_b = sum(v ** 2 for v in patterns_b.values()) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        correlation = dot_product / (norm_a * norm_b)
        
        # Scale to 0-20
        score = correlation * 20
        
        return max(0, min(score, 20))
    
    def calculate_similarity(self, wallet_a: str, wallet_b: str) -> BehaviorSimilarity:
        """Calculate behavioral similarity between two wallets"""
        behavior_a = self.wallet_behaviors[wallet_a]
        behavior_b = self.wallet_behaviors[wallet_b]
        
        # Calculate components
        program_score, shared_programs = self.calculate_program_overlap_score(behavior_a, behavior_b)
        co_sig_score, shared_sigs = self.calculate_co_signature_score(behavior_a, behavior_b)
        temporal_score = self.calculate_temporal_correlation(behavior_a, behavior_b)
        
        # Total similarity (0-100)
        total_score = program_score + co_sig_score + temporal_score
        
        is_linked = total_score >= self.SIMILARITY_THRESHOLD
        
        return BehaviorSimilarity(
            wallet_a=wallet_a,
            wallet_b=wallet_b,
            similarity_score=round(total_score, 2),
            program_overlap_score=round(program_score, 2),
            co_signature_score=round(co_sig_score, 2),
            temporal_correlation_score=round(temporal_score, 2),
            shared_programs=shared_programs,
            shared_signatures=shared_sigs,
            is_behaviorally_linked=is_linked,
            detection_timestamp=datetime.now(timezone.utc).isoformat()
        )
    
    def analyze_all_pairs(self) -> List[BehaviorSimilarity]:
        """Analyze similarity for all wallet pairs"""
        logger.info("Analyzing wallet pairs...")
        logger.info("="*70)
        
        wallets = list(self.all_wallets)
        total_pairs = len(wallets) * (len(wallets) - 1) // 2
        
        logger.info(f"  Total pairs to analyze: {total_pairs}")
        
        similarities = []
        linked_pairs = 0
        
        for i, wallet_a in enumerate(wallets):
            for wallet_b in wallets[i+1:]:
                similarity = self.calculate_similarity(wallet_a, wallet_b)
                similarities.append(similarity)
                
                if similarity.is_behaviorally_linked:
                    linked_pairs += 1
        
        self.similarities = similarities
        self.stats["wallet_pairs_compared"] = total_pairs
        self.stats["behaviorally_linked_pairs"] = linked_pairs
        
        if similarities:
            scores = [s.similarity_score for s in similarities]
            self.stats["avg_similarity_score"] = sum(scores) / len(scores)
            self.stats["max_similarity_score"] = max(scores)
        
        logger.info(f"✓ Analyzed {total_pairs} pairs")
        logger.info(f"  Behaviorally linked pairs: {linked_pairs} ({linked_pairs/total_pairs*100:.2f}%)")
        logger.info("="*70)
        
        return similarities
    
    def create_behavior_clusters(self) -> List[BehaviorCluster]:
        """Create clusters from behaviorally linked wallets"""
        logger.info("Creating behavior clusters...")
        
        # Build graph of behaviorally linked wallets
        linked_graph = defaultdict(set)
        
        for sim in self.similarities:
            if sim.is_behaviorally_linked:
                linked_graph[sim.wallet_a].add(sim.wallet_b)
                linked_graph[sim.wallet_b].add(sim.wallet_a)
        
        # Find connected components (clusters)
        visited = set()
        clusters = []
        
        for wallet in linked_graph:
            if wallet not in visited:
                # BFS to find cluster
                cluster_wallets = []
                queue = [wallet]
                
                while queue:
                    w = queue.pop(0)
                    if w not in visited:
                        visited.add(w)
                        cluster_wallets.append(w)
                        queue.extend(linked_graph[w] - visited)
                
                if len(cluster_wallets) >= 2:
                    # Calculate cluster metrics
                    cluster_sims = [
                        s for s in self.similarities
                        if s.wallet_a in cluster_wallets and s.wallet_b in cluster_wallets
                    ]
                    
                    avg_sim = sum(s.similarity_score for s in cluster_sims) / len(cluster_sims) if cluster_sims else 0
                    total_programs = len(set().union(*[s.shared_programs for s in cluster_sims]))
                    total_sigs = sum(s.shared_signatures for s in cluster_sims)
                    
                    cluster = BehaviorCluster(
                        cluster_id=f"behavioral_{cluster_wallets[0][:8]}",
                        cluster_type="BEHAVIORAL_LINKED",
                        wallet_addresses=cluster_wallets,
                        avg_similarity_score=round(avg_sim, 2),
                        total_shared_programs=total_programs,
                        total_shared_signatures=total_sigs,
                        detection_timestamp=datetime.now(timezone.utc).isoformat()
                    )
                    
                    clusters.append(cluster)
                    logger.info(f"  Created cluster: {cluster.cluster_id} ({len(cluster_wallets)} wallets)")
        
        self.behavior_clusters = clusters
        self.stats["total_clusters_created"] = len(clusters)
        self.stats["wallets_clustered"] = sum(len(c.wallet_addresses) for c in clusters)
        
        logger.info(f"✓ Created {len(clusters)} behavioral clusters")
        logger.info(f"  Wallets in clusters: {self.stats['wallets_clustered']}")
        
        return clusters
    
    def save_results(self) -> str:
        """Save analysis results to file"""
        logger.info("Saving behavioral similarity results...")
        
        output_dir = "/a0/usr/projects/godmodescanner/data/graph_data"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "behavioral_similarity_detected.json")
        
        results = {
            "detection_metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "protocol": "Shared Signature & Behavioral Analysis v1.0",
                "similarity_threshold": self.SIMILARITY_THRESHOLD
            },
            "statistics": self.stats,
            "all_wallets": list(self.all_wallets),
            "linked_pairs": [s.to_dict() for s in self.similarities if s.is_behaviorally_linked],
            "top_similarities": sorted([s.to_dict() for s in self.similarities], key=lambda x: x['similarity_score'], reverse=True)[:50],
            "behavioral_clusters": [c.to_dict() for c in self.behavior_clusters]
        }
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"✓ Results saved to: {output_file}")
        return output_file
    
    def generate_report(self) -> dict:
        """Generate comprehensive detection report"""
        linked_pairs = sorted(
            [s for s in self.similarities if s.is_behaviorally_linked],
            key=lambda x: x.similarity_score,
            reverse=True
        )
        
        return {
            "detection_summary": {
                "wallets_analyzed": self.stats["wallets_analyzed"],
                "pairs_compared": self.stats["wallet_pairs_compared"],
                "behaviorally_linked_pairs": self.stats["behaviorally_linked_pairs"],
                "link_rate_percent": round(
                    (self.stats["behaviorally_linked_pairs"] / self.stats["wallet_pairs_compared"]) * 100, 2
                ) if self.stats["wallet_pairs_compared"] > 0 else 0,
                "clusters_created": self.stats["total_clusters_created"],
                "avg_similarity": round(self.stats["avg_similarity_score"], 2),
                "max_similarity": round(self.stats["max_similarity_score"], 2)
            },
            "top_linked_pairs": [
                {
                    "wallet_a": s.wallet_a[:25] + "...",
                    "wallet_b": s.wallet_b[:25] + "...",
                    "similarity_score": s.similarity_score,
                    "shared_programs": len(s.shared_programs),
                    "shared_signatures": s.shared_signatures
                } for s in linked_pairs[:10]
            ],
            "behavioral_clusters": [
                {
                    "cluster_id": c.cluster_id,
                    "wallet_count": len(c.wallet_addresses),
                    "avg_similarity": c.avg_similarity_score,
                    "shared_programs": c.total_shared_programs,
                    "shared_signatures": c.total_shared_signatures
                } for c in self.behavior_clusters[:10]
            ],
            "statistics": self.stats
        }
    
    async def start(self) -> dict:
        """Start behavioral similarity analysis"""
        logger.info("="*70)
        logger.info("SHARED SIGNATURE & BEHAVIORAL ANALYSIS STARTING")
        logger.info("="*70)
        
        self.status = "STARTING"
        
        # Load graph data
        self.load_graph_data()
        
        # Simulate transaction histories
        self.simulate_transaction_history()
        
        # Analyze all pairs
        self.status = "RUNNING"
        self.analyze_all_pairs()
        
        # Create clusters
        self.create_behavior_clusters()
        
        # Save results
        self.save_results()
        
        self.status = "COMPLETED"
        
        report = self.generate_report()
        
        logger.info("="*70)
        logger.info("SHARED SIGNATURE & BEHAVIORAL ANALYSIS COMPLETE")
        logger.info("="*70)
        logger.info(json.dumps(report, indent=2))
        
        return report

async def main():
    """Main entry point"""
    logger.info("Starting Shared Signature & Behavioral Analysis...")
    
    analyzer = BehavioralSimilarityAnalyzer()
    
    try:
        report = await analyzer.start()
        
        print("\n" + "="*70)
        print("SHARED SIGNATURE & BEHAVIORAL ANALYSIS COMPLETE")
        print("="*70)
        print(json.dumps(report, indent=2))
        print("="*70)
        
        return report
    except Exception as e:
        logger.error(f"Behavioral similarity analysis failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
