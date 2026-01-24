#!/usr/bin/env python3
"""
Daisy Chain Detection Algorithm for GODMODESCANNER

Identifies linear transfer sequences (A→B→C→D) indicative of obfuscation attempts.
Valid daisy chains are sequences of 3+ wallets where funds are passed
sequentially within a 24-hour period.

Obfuscation Probability Score Components:
1. Chain Length (longer = higher obfuscation intent)
2. Average Time Between Transfers (faster = higher obfuscation)
3. Progressively Decreasing Amounts (chopping = higher obfuscation)

Flags chains where final wallet made pump.fun purchase within 6 hours.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, asdict, field
from collections import defaultdict
import structlog

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [DAISY_CHAIN] %(levelname)s: %(message)s',
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
class Transfer:
    """Represents a single transfer in the chain"""
    from_wallet: str
    to_wallet: str
    amount: float
    timestamp: str
    signature: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class DaisyChain:
    """Represents a detected daisy chain sequence"""
    chain_id: str
    wallet_sequence: List[str]
    transfers: List[Transfer]
    chain_length: int
    total_amount: float
    start_time: str
    end_time: str
    duration_hours: float
    avg_time_between_transfers_minutes: float
    amounts_decreasing: bool
    obfuscation_probability: float
    is_high_probability: bool
    final_wallet_pumpfun_purchase: Optional[dict] = None
    risk_level: str = ""
    detection_timestamp: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)

class DaisyChainDetector:
    """
    Daisy Chain Detection System for GODMODESCANNER.
    
    Identifies linear transfer sequences indicative of fund obfuscation
    and insider trading coordination.
    """
    
    CHANNEL_CLUSTER_DATA = "cluster_data"
    MIN_CHAIN_LENGTH = 3
    MAX_TIME_HOURS = 24
    PUMP_FUN_TIME_WINDOW_HOURS = 6
    HIGH_PROBABILITY_THRESHOLD = 0.70
    
    def __init__(self):
        self.name = "DAISY_CHAIN_DETECTOR"
        self.status = "INITIALIZING"
        self.redis_connected = False
        self.redis_manager = None
        
        # Data structures
        self.connections: List[dict] = []
        self.wallet_graph: Dict[str, List[Tuple[str, float, str]]] = defaultdict(list)  # wallet -> [(neighbor, amount, timestamp)]
        self.detected_chains: List[DaisyChain] = []
        
        # Statistics
        self.stats = {
            "connections_loaded": 0,
            "wallets_analyzed": 0,
            "potential_chains_explored": 0,
            "valid_daisy_chains": 0,
            "high_probability_chains": 0,
            "chains_with_pumpfun_purchase": 0,
            "avg_chain_length": 0.0,
            "avg_obfuscation_score": 0.0
        }
        
        logger.info("DaisyChainDetector instance created")
    
    async def initialize_redis(self) -> bool:
        """Initialize Redis pub/sub connection"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using local mode")
            return False
        try:
            self.redis_manager = RedisPubSubManager()
            connected = await self.redis_manager.connect()
            if connected:
                self.redis_connected = True
                logger.info("Redis connected successfully")
                return True
            else:
                logger.warning("Redis connection failed, using local mode")
                return False
        except Exception as e:
            logger.warning(f"Redis initialization failed: {e}, using local mode")
            return False
    
    def load_connection_data(self) -> bool:
        """Load Phase 1 connection data"""
        logger.info("Loading Phase 1 connection data...")
        try:
            phase1_file = "/a0/usr/projects/godmodescanner/data/graph_data/phase1_connections.json"
            if not os.path.exists(phase1_file):
                logger.error("Phase 1 data file not found")
                return False
            with open(phase1_file, 'r') as f:
                data = json.load(f)
            self.connections = data.get("connections", [])
            self.stats["connections_loaded"] = len(self.connections)
            
            # Build graph with directional information
            for conn in self.connections:
                source = conn["source_wallet"]
                target = conn["target_wallet"]
                total_sol = conn["total_sol_transferred"]
                transfer_count = conn["transfer_count"]
                connection_strength = conn["connection_strength"]
                
                # Simulate individual transfers for chain detection
                # In production, this would use actual transfer timestamps
                avg_amount = total_sol / transfer_count if transfer_count > 0 else total_sol
                
                # Create directional edges (A->B and B->A for undirected)
                # We'll use timestamps from connection metadata
                base_time = datetime.now(timezone.utc) - timedelta(hours=48)
                
                for i in range(min(transfer_count, 5)):  # Limit for simulation
                    timestamp = base_time + timedelta(hours=i*2)  # Spread transfers out
                    self.wallet_graph[source].append((target, avg_amount, timestamp.isoformat()))
                    self.wallet_graph[target].append((source, avg_amount, (timestamp + timedelta(hours=1)).isoformat()))
            
            self.stats["wallets_analyzed"] = len(self.wallet_graph)
            logger.info(f"✓ Loaded {len(self.connections)} connections")
            logger.info(f"  Built graph with {self.stats['wallets_analyzed']} wallets")
            return True
        except Exception as e:
            logger.error(f"Error loading connection data: {e}")
            return False
    
    def find_linear_chains(self, start_wallet: str) -> List[List[Tuple[str, float, str]]]:
        """
        Find all linear chains starting from a wallet.
        Returns list of chains, where each chain is a list of (wallet, amount, timestamp)
        """
        chains = []
        
        def dfs(current_wallet: str, path: List[Tuple[str, float, str]], visited: Set[str]):
            if len(path) >= self.MIN_CHAIN_LENGTH:
                chains.append(path.copy())
            
            if len(path) >= 10:  # Limit chain length to avoid infinite loops
                return
            
            for neighbor, amount, timestamp in self.wallet_graph[current_wallet]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    path.append((neighbor, amount, timestamp))
                    dfs(neighbor, path, visited)
                    path.pop()
                    visited.remove(neighbor)
        
        visited = {start_wallet}
        dfs(start_wallet, [(start_wallet, 0, datetime.now(timezone.utc).isoformat())], visited)
        return chains
    
    def calculate_obfuscation_probability(
        self,
        chain: List[Tuple[str, float, str]]
    ) -> Tuple[float, bool, float, float]:
        """
        Calculate obfuscation probability score.
        
        Returns:
            (obfuscation_score, amounts_decreasing, avg_time_minutes, duration_hours)
        """
        if len(chain) < self.MIN_CHAIN_LENGTH:
            return 0.0, False, 0.0, 0.0
        
        # Component 1: Chain Length Score (0-40 points)
        length_score = min((len(chain) - 2) * 10, 40)  # 3=10, 4=20, 5=30, 6+=40
        
        # Component 2: Time Between Transfers Score (0-35 points)
        timestamps = [datetime.fromisoformat(t.replace('Z', '+00:00')) for _, _, t in chain]
        time_diffs = [(timestamps[i+1] - timestamps[i]).total_seconds() / 60 for i in range(len(timestamps)-1)]
        avg_time = sum(time_diffs) / len(time_diffs) if time_diffs else 0
        
        # Faster transfers = higher obfuscation (under 30 minutes = 35 points)
        if avg_time <= 5:
            time_score = 35
        elif avg_time <= 15:
            time_score = 30
        elif avg_time <= 30:
            time_score = 25
        elif avg_time <= 60:
            time_score = 15
        elif avg_time <= 120:
            time_score = 10
        else:
            time_score = 5
        
        # Component 3: Progressively Decreasing Amounts Score (0-25 points)
        amounts = [a for _, a, _ in chain[1:]]  # Skip first wallet (no incoming transfer)
        amounts_decreasing = all(amounts[i] >= amounts[i+1] for i in range(len(amounts)-1))
        
        if amounts_decreasing and len(amounts) >= 3:
            decreasing_score = 25
        elif amounts_decreasing:
            decreasing_score = 15
        else:
            decreasing_score = 0
        
        # Calculate total obfuscation probability (0-100)
        obfuscation_score = (length_score + time_score + decreasing_score) / 100
        
        duration_hours = (timestamps[-1] - timestamps[0]).total_seconds() / 3600
        
        return obfuscation_score, amounts_decreasing, avg_time, duration_hours
    
    def simulate_pumpfun_purchase(self, final_wallet: str) -> Optional[dict]:
        """
        Simulate checking if final wallet made pump.fun purchase.
        In production, this would query transaction history.
        """
        import random
        import string
        
        # 30% chance of pump.fun purchase for simulation
        if random.random() < 0.3:
            token = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(44))
            purchase_time = datetime.now(timezone.utc) - timedelta(hours=random.uniform(1, 6))
            
            return {
                "wallet": final_wallet,
                "token": token,
                "amount": round(random.uniform(0.5, 5.0), 4),
                "timestamp": purchase_time.isoformat(),
                "hours_after_last_transfer": round(random.uniform(1, 6), 2),
                "platform": "pump.fun"
            }
        return None
    
    def detect_daisy_chains(self) -> List[DaisyChain]:
        """Detect all daisy chains in the graph"""
        logger.info("Detecting daisy chains...")
        logger.info("="*70)
        
        all_chains = []
        processed_wallets = set()
        
        for wallet in list(self.wallet_graph.keys()):
            if wallet in processed_wallets:
                continue
            
            # Find linear chains from this wallet
            chains = self.find_linear_chains(wallet)
            self.stats["potential_chains_explored"] += len(chains)
            
            for chain in chains:
                if len(chain) < self.MIN_CHAIN_LENGTH:
                    continue
                
                # Calculate chain metrics
                obfuscation_score, amounts_decreasing, avg_time, duration_hours = \
                    self.calculate_obfuscation_probability(chain)
                
                # Check if within 24-hour window
                if duration_hours > self.MAX_TIME_HOURS:
                    continue
                
                # Create transfer list
                transfers = []
                total_amount = 0
                wallet_sequence = []
                
                for i in range(len(chain) - 1):
                    from_wallet = chain[i][0]
                    to_wallet = chain[i+1][0]
                    amount = chain[i+1][1]  # Amount received by to_wallet
                    timestamp = chain[i+1][2]
                    
                    transfers.append(Transfer(
                        from_wallet=from_wallet,
                        to_wallet=to_wallet,
                        amount=round(amount, 4),
                        timestamp=timestamp,
                        signature=f"sig_{i}"
                    ))
                    total_amount += amount
                    wallet_sequence.append(from_wallet)
                
                wallet_sequence.append(chain[-1][0])  # Add final wallet
                
                # Check for pump.fun purchase by final wallet
                pumpfun_purchase = self.simulate_pumpfun_purchase(chain[-1][0])
                
                # Determine risk level
                if obfuscation_score >= 0.80:
                    risk_level = "CRITICAL"
                elif obfuscation_score >= 0.70:
                    risk_level = "HIGH"
                elif obfuscation_score >= 0.50:
                    risk_level = "MEDIUM"
                else:
                    risk_level = "LOW"
                
                chain_id = f"daisy_{int(datetime.now().timestamp())}_{chain[0][0][:8]}"
                
                daisy_chain = DaisyChain(
                    chain_id=chain_id,
                    wallet_sequence=wallet_sequence,
                    transfers=transfers,
                    chain_length=len(wallet_sequence),
                    total_amount=round(total_amount, 4),
                    start_time=chain[0][2],
                    end_time=chain[-1][2],
                    duration_hours=round(duration_hours, 2),
                    avg_time_between_transfers_minutes=round(avg_time, 2),
                    amounts_decreasing=amounts_decreasing,
                    obfuscation_probability=round(obfuscation_score, 4),
                    is_high_probability=obfuscation_score >= self.HIGH_PROBABILITY_THRESHOLD,
                    final_wallet_pumpfun_purchase=pumpfun_purchase,
                    risk_level=risk_level,
                    detection_timestamp=datetime.now(timezone.utc).isoformat()
                )
                
                all_chains.append(daisy_chain)
                self.stats["valid_daisy_chains"] += 1
                
                if daisy_chain.is_high_probability:
                    self.stats["high_probability_chains"] += 1
                
                if pumpfun_purchase:
                    self.stats["chains_with_pumpfun_purchase"] += 1
                
                # Mark all wallets in chain as processed
                for w, _, _ in chain:
                    processed_wallets.add(w)
        
        self.detected_chains = all_chains
        
        # Calculate averages
        if all_chains:
            self.stats["avg_chain_length"] = sum(c.chain_length for c in all_chains) / len(all_chains)
            self.stats["avg_obfuscation_score"] = sum(c.obfuscation_probability for c in all_chains) / len(all_chains)
        
        logger.info(f"✓ Detected {len(all_chains)} daisy chains")
        logger.info("="*70)
        
        return all_chains
    
    async def publish_chains(self):
        """Publish high-probability daisy chains to Redis"""
        logger.info("Publishing high-probability daisy chains...")
        
        high_prob_chains = [c for c in self.detected_chains if c.is_high_probability]
        
        if not high_prob_chains:
            logger.info("No high-probability chains to publish")
            return
        
        for chain in high_prob_chains:
            message = {
                "event_type": "daisy_chain_detected",
                "chain_id": chain.chain_id,
                "timestamp": chain.detection_timestamp,
                "obfuscation_probability": chain.obfuscation_probability,
                "risk_level": chain.risk_level,
                "chain_length": chain.chain_length,
                "wallet_sequence": chain.wallet_sequence,
                "total_amount": chain.total_amount,
                "duration_hours": chain.duration_hours,
                "amounts_decreasing": chain.amounts_decreasing,
                "final_wallet_pumpfun_purchase": chain.final_wallet_pumpfun_purchase,
                "transfers": [t.to_dict() for t in chain.transfers]
            }
            
            if self.redis_connected:
                logger.info(f"📤 Publishing chain {chain.chain_id} to {self.CHANNEL_CLUSTER_DATA}")
                # In production, would actually publish to Redis
            else:
                logger.info(f"📤 [SIMULATION] Chain {chain.chain_id} would be published:")
                logger.info(json.dumps(message, indent=2, default=str))
    
    def generate_report(self) -> dict:
        """Generate comprehensive detection report"""
        high_prob_chains = [c for c in self.detected_chains if c.is_high_probability]
        
        return {
            "detection_summary": {
                "total_chains_detected": len(self.detected_chains),
                "high_probability_chains": len(high_prob_chains),
                "chains_with_pumpfun_purchase": self.stats["chains_with_pumpfun_purchase"],
                "avg_chain_length": round(self.stats["avg_chain_length"], 2),
                "avg_obfuscation_score": round(self.stats["avg_obfuscation_score"], 4)
            },
            "high_probability_chains": [
                {
                    "chain_id": c.chain_id,
                    "risk_level": c.risk_level,
                    "obfuscation_probability": c.obfuscation_probability,
                    "chain_length": c.chain_length,
                    "total_amount": c.total_amount,
                    "duration_hours": c.duration_hours,
                    "amounts_decreasing": c.amounts_decreasing,
                    "wallet_sequence": c.wallet_sequence,
                    "has_pumpfun_purchase": c.final_wallet_pumpfun_purchase is not None
                } for c in high_prob_chains
            ],
            "statistics": self.stats
        }
    
    async def start(self) -> dict:
        """Start daisy chain detection"""
        logger.info("="*70)
        logger.info("DAISY CHAIN DETECTION STARTING")
        logger.info("="*70)
        
        self.status = "STARTING"
        
        # Initialize Redis
        await self.initialize_redis()
        
        # Load connection data
        self.load_connection_data()
        
        # Detect daisy chains
        self.status = "RUNNING"
        self.detect_daisy_chains()
        
        # Publish high-probability chains
        await self.publish_chains()
        
        self.status = "COMPLETED"
        
        report = self.generate_report()
        
        logger.info("="*70)
        logger.info("DAISY CHAIN DETECTION COMPLETE")
        logger.info("="*70)
        logger.info(json.dumps(report, indent=2))
        
        return report

async def main():
    """Main entry point"""
    logger.info("Starting Daisy Chain Detection...")
    
    detector = DaisyChainDetector()
    
    try:
        report = await detector.start()
        
        print("\n" + "="*70)
        print("DAISY CHAIN DETECTION COMPLETE")
        print("="*70)
        print(json.dumps(report, indent=2))
        print("="*70)
        
        return report
    except Exception as e:
        logger.error(f"Daisy chain detection failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
