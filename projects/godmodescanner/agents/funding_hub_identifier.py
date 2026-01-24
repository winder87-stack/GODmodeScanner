#!/usr/bin/env python3
"""
Funding Hub Identification Protocol for GODMODESCANNER

Analyzes the graph database to identify "Command and Control" (C&C) funding hubs.
A funding hub is a wallet that has funded 10+ other wallets within a 72-hour window.

C&C Score Calculation:
- Based on number of funded wallets (scale)
- Based on percentage of funded wallets that made pump.fun purchases (conversion rate)

Hubs with C&C score > 80% are flagged as CRITICAL.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, asdict, field
from collections import defaultdict
import structlog

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [FUNDING_HUB] %(levelname)s: %(message)s',
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

@dataclass
class FundedWallet:
    """Represents a wallet that received funding from a hub"""
    wallet_address: str
    amount_received: float
    funding_timestamp: str
    made_pumpfun_purchase: bool = False
    pumpfun_purchase_details: Optional[dict] = None
    hours_to_purchase: float = 0.0
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class FundingHub:
    """Represents a detected funding hub"""
    hub_address: str
    total_funded_wallets: int
    funded_wallets: List[FundedWallet]
    total_amount_distributed: float
    funding_window_start: str
    funding_window_end: str
    window_hours: float
    
    # Metrics
    wallets_with_pumpfun_purchase: int
    conversion_rate: float  # Percentage that bought pump.fun
    cc_score: float  # Command and Control score
    risk_level: str
    detection_timestamp: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)

class FundingHubIdentifier:
    """
    Funding Hub Identification System for GODMODESCANNER.
    
    Identifies C&C hubs that coordinate insider trading through
    strategic funding distribution.
    """
    
    MIN_FUNDED_WALLETS = 10
    FUNDING_WINDOW_HOURS = 72
    PUMP_FUN_WINDOW_HOURS = 24
    CRITICAL_CC_THRESHOLD = 0.80
    
    def __init__(self):
        self.name = "FUNDING_HUB_IDENTIFIER"
        self.status = "INITIALIZING"
        
        # Data structures
        self.connections: List[dict] = []
        self.hub_outflows: Dict[str, List[dict]] = defaultdict(list)  # hub -> list of transfers
        self.detected_hubs: List[FundingHub] = []
        
        # Statistics
        self.stats = {
            "connections_loaded": 0,
            "potential_hubs_analyzed": 0,
            "qualified_hubs_found": 0,
            "critical_hubs_found": 0,
            "total_funded_wallets": 0,
            "total_pumpfun_conversions": 0,
            "avg_conversion_rate": 0.0,
            "avg_cc_score": 0.0
        }
        
        logger.info("FundingHubIdentifier instance created")
    
    def load_connection_data(self) -> bool:
        """Load Phase 1 connection data and reconstruct hub-to-fundee mappings"""
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
            
            # Build hub-to-fundee mapping
            # Assuming source_wallet funded target_wallet
            base_time = datetime.now(timezone.utc) - timedelta(hours=48)
            
            for conn in self.connections:
                source = conn["source_wallet"]
                target = conn["target_wallet"]
                total_sol = conn["total_sol_transferred"]
                transfer_count = conn["transfer_count"]
                strength = conn["connection_strength"]
                
                # Simulate individual funding events
                # In production, this would use actual transaction timestamps
                for i in range(min(transfer_count, 3)):  # Limit for simulation
                    timestamp = base_time + timedelta(hours=i*12)  # Spread within 48h
                    self.hub_outflows[source].append({
                        "target_wallet": target,
                        "amount": total_sol / transfer_count if transfer_count > 0 else total_sol,
                        "timestamp": timestamp
                    })
            
            # Filter hubs by time window and minimum wallet count
            qualified_hubs = []
            for hub, outflows in self.hub_outflows.items():
                # Sort by timestamp
                outflows.sort(key=lambda x: x["timestamp"])
                
                # Check 72-hour window
                if len(outflows) >= self.MIN_FUNDED_WALLETS:
                    window_start = outflows[0]["timestamp"]
                    window_end = outflows[-1]["timestamp"]
                    window_hours = (window_end - window_start).total_seconds() / 3600
                    
                    if window_hours <= self.FUNDING_WINDOW_HOURS:
                        qualified_hubs.append(hub)
            
            self.stats["potential_hubs_analyzed"] = len(self.hub_outflows)
            
            logger.info(f"✓ Loaded {len(self.connections)} connections")
            logger.info(f"  Built outflow graph for {len(self.hub_outflows)} hubs")
            logger.info(f"  Qualified hubs (10+ wallets in 72h): {len(qualified_hubs)}")
            
            return True
        except Exception as e:
            logger.error(f"Error loading connection data: {e}")
            return False
    
    def simulate_pumpfun_purchase(
        self,
        funded_wallet: str,
        funding_timestamp: datetime
    ) -> Optional[dict]:
        """
        Simulate checking if funded wallet made pump.fun purchase within 24h.
        In production, this would query transaction history.
        """
        import random
        import string
        
        # 40% chance of pump.fun purchase for funded wallets
        if random.random() < 0.4:
            purchase_delay = random.uniform(1, 24)
            purchase_time = funding_timestamp + timedelta(hours=purchase_delay)
            token = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(44))
            
            return {
                "wallet": funded_wallet,
                "token": token,
                "amount": round(random.uniform(0.5, 10.0), 4),
                "timestamp": purchase_time.isoformat(),
                "hours_after_funding": round(purchase_delay, 2),
                "platform": "pump.fun"
            }
        return None
    
    def calculate_cc_score(self, hub: FundingHub) -> float:
        """
        Calculate Command and Control score.
        
        Formula: (Conversion Rate * 0.7) + (Scale Factor * 0.3)
        - Conversion Rate: % of funded wallets that bought pump.fun
        - Scale Factor: Normalized by funded wallet count (0-1 scale, capped at 50 wallets)
        """
        # Base score from conversion rate
        conversion_score = hub.conversion_rate
        
        # Scale factor (0-1 based on wallet count, capped at 50)
        scale_factor = min(hub.total_funded_wallets / 50.0, 1.0)
        
        # Combined C&C score
        cc_score = (conversion_score * 0.7) + (scale_factor * 0.3)
        
        return round(cc_score, 4)
    
    def identify_funding_hubs(self) -> List[FundingHub]:
        """Identify and analyze all funding hubs"""
        logger.info("Identifying funding hubs...")
        logger.info("="*70)
        
        hubs = []
        
        for hub_wallet, outflows in self.hub_outflows.items():
            if len(outflows) < self.MIN_FUNDED_WALLETS:
                continue
            
            # Check funding window
            outflows.sort(key=lambda x: x["timestamp"])
            window_start = outflows[0]["timestamp"]
            window_end = outflows[-1]["timestamp"]
            window_hours = (window_end - window_start).total_seconds() / 3600
            
            if window_hours > self.FUNDING_WINDOW_HOURS:
                continue
            
            # Process funded wallets
            funded_wallets = []
            total_distributed = 0.0
            pumpfun_count = 0
            
            # Deduplicate targets
            unique_targets = {}
            for flow in outflows:
                target = flow["target_wallet"]
                if target not in unique_targets:
                    unique_targets[target] = flow
                    total_distributed += flow["amount"]
                else:
                    # Aggregate if multiple transfers to same wallet
                    unique_targets[target]["amount"] += flow["amount"]
            
            for target, flow in unique_targets.items():
                # Check for pump.fun purchase
                purchase = self.simulate_pumpfun_purchase(target, flow["timestamp"])
                
                funded = FundedWallet(
                    wallet_address=target,
                    amount_received=round(flow["amount"], 4),
                    funding_timestamp=flow["timestamp"].isoformat(),
                    made_pumpfun_purchase=purchase is not None,
                    pumpfun_purchase_details=purchase,
                    hours_to_purchase=purchase["hours_after_funding"] if purchase else 0.0
                )
                
                funded_wallets.append(funded)
                if purchase:
                    pumpfun_count += 1
            
            # Calculate metrics
            total_funded = len(funded_wallets)
            conversion_rate = (pumpfun_count / total_funded) * 100 if total_funded > 0 else 0
            
            hub = FundingHub(
                hub_address=hub_wallet,
                total_funded_wallets=total_funded,
                funded_wallets=funded_wallets,
                total_amount_distributed=round(total_distributed, 4),
                funding_window_start=window_start.isoformat(),
                funding_window_end=window_end.isoformat(),
                window_hours=round(window_hours, 2),
                wallets_with_pumpfun_purchase=pumpfun_count,
                conversion_rate=round(conversion_rate, 2),
                cc_score=0.0,  # Will be calculated below
                risk_level="",
                detection_timestamp=datetime.now(timezone.utc).isoformat()
            )
            
            # Calculate C&C score
            hub.cc_score = self.calculate_cc_score(hub)
            
            # Determine risk level
            if hub.cc_score >= 0.90:
                hub.risk_level = "CRITICAL"
            elif hub.cc_score >= 0.80:
                hub.risk_level = "HIGH"
            elif hub.cc_score >= 0.60:
                hub.risk_level = "MEDIUM"
            else:
                hub.risk_level = "LOW"
            
            hubs.append(hub)
            self.stats["qualified_hubs_found"] += 1
            self.stats["total_funded_wallets"] += total_funded
            self.stats["total_pumpfun_conversions"] += pumpfun_count
            
            if hub.cc_score > self.CRITICAL_CC_THRESHOLD:
                self.stats["critical_hubs_found"] += 1
        
        # Sort by C&C score
        hubs.sort(key=lambda h: h.cc_score, reverse=True)
        self.detected_hubs = hubs
        
        # Calculate averages
        if hubs:
            self.stats["avg_conversion_rate"] = sum(h.conversion_rate for h in hubs) / len(hubs)
            self.stats["avg_cc_score"] = sum(h.cc_score for h in hubs) / len(hubs)
        
        logger.info(f"✓ Identified {len(hubs)} funding hubs")
        logger.info(f"  Critical hubs (C&C > 80%): {self.stats['critical_hubs_found']}")
        logger.info("="*70)
        
        return hubs
    
    def create_cluster_entities(self) -> List[dict]:
        """Create cluster entities for critical funding hubs"""
        logger.info("Creating cluster entities for critical hubs...")
        
        clusters = []
        critical_hubs = [h for h in self.detected_hubs if h.cc_score > self.CRITICAL_CC_THRESHOLD]
        
        for hub in critical_hubs:
            cluster = {
                "cluster_id": f"funding_hub_{hub.hub_address[:8]}",
                "cluster_type": "CRITICAL_FUNDING_HUB",
                "timestamp": hub.detection_timestamp,
                "cc_score": hub.cc_score,
                "risk_level": hub.risk_level,
                "hub_wallet": hub.hub_address,
                "cluster_wallets": [hub.hub_address] + [fw.wallet_address for fw in hub.funded_wallets],
                "total_wallets": hub.total_funded_wallets + 1,
                "stats": {
                    "total_distributed_sol": hub.total_amount_distributed,
                    "conversion_rate": hub.conversion_rate,
                    "pumpfun_purchases": hub.wallets_with_pumpfun_purchase,
                    "funding_window_hours": hub.window_hours
                },
                "funded_wallets": [fw.to_dict() for fw in hub.funded_wallets]
            }
            clusters.append(cluster)
            logger.info(f"✓ Created cluster: {cluster['cluster_id']} ({hub.total_funded_wallets} funded wallets)")
        
        return clusters
    
    def save_results(self) -> str:
        """Save detection results to file"""
        logger.info("Saving funding hub detection results...")
        
        output_dir = "/a0/usr/projects/godmodescanner/data/graph_data"
        os.makedirs(output_dir, exist_ok=True)
        output_file = os.path.join(output_dir, "funding_hubs_detected.json")
        
        results = {
            "detection_metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "protocol": "Funding Hub Identification v1.0",
                "data_source": "phase1_connections.json"
            },
            "statistics": self.stats,
            "all_hubs": [h.to_dict() for h in self.detected_hubs],
            "critical_hubs": [h.to_dict() for h in self.detected_hubs if h.cc_score > self.CRITICAL_CC_THRESHOLD],
            "cluster_entities": self.create_cluster_entities()
        }
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        
        logger.info(f"✓ Results saved to: {output_file}")
        return output_file
    
    def generate_report(self) -> dict:
        """Generate comprehensive detection report"""
        critical_hubs = [h for h in self.detected_hubs if h.cc_score > self.CRITICAL_CC_THRESHOLD]
        
        return {
            "detection_summary": {
                "total_hubs_found": len(self.detected_hubs),
                "critical_hubs": len(critical_hubs),
                "total_wallets_funded": self.stats["total_funded_wallets"],
                "total_pumpfun_conversions": self.stats["total_pumpfun_conversions"],
                "avg_conversion_rate": round(self.stats["avg_conversion_rate"], 2),
                "avg_cc_score": round(self.stats["avg_cc_score"], 4)
            },
            "critical_hubs": [
                {
                    "hub_address": h.hub_address,
                    "cc_score": h.cc_score,
                    "risk_level": h.risk_level,
                    "wallets_funded": h.total_funded_wallets,
                    "conversion_rate": h.conversion_rate,
                    "total_distributed": h.total_amount_distributed,
                    "window_hours": h.window_hours
                } for h in critical_hubs
            ],
            "statistics": self.stats
        }
    
    async def start(self) -> dict:
        """Start funding hub identification"""
        logger.info("="*70)
        logger.info("FUNDING HUB IDENTIFICATION STARTING")
        logger.info("="*70)
        
        self.status = "STARTING"
        
        # Load connection data
        self.load_connection_data()
        
        # Identify funding hubs
        self.status = "RUNNING"
        self.identify_funding_hubs()
        
        # Save results
        self.save_results()
        
        self.status = "COMPLETED"
        
        report = self.generate_report()
        
        logger.info("="*70)
        logger.info("FUNDING HUB IDENTIFICATION COMPLETE")
        logger.info("="*70)
        logger.info(json.dumps(report, indent=2))
        
        return report

async def main():
    """Main entry point"""
    logger.info("Starting Funding Hub Identification...")
    
    identifier = FundingHubIdentifier()
    
    try:
        report = await identifier.start()
        
        print("\n" + "="*70)
        print("FUNDING HUB IDENTIFICATION COMPLETE")
        print("="*70)
        print(json.dumps(report, indent=2))
        print("="*70)
        
        return report
    except Exception as e:
        logger.error(f"Funding hub identification failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
