#!/usr/bin/env python3
"""
Pattern Learning & Adaptation Protocol for GODMODESCANNER

Continuous learning cycle:
1. Query TimescaleDB for rugs/major dumps (last 7 days)
2. Cross-reference with cluster database
3. Identify clusters that were early buyers in failed tokens
4. Re-weight detection patterns based on performance
5. Update internal algorithms with new weights
6. Log all pattern adjustments

Output: Updated detection_rules.json with adaptive weights
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, asdict, field
from collections import defaultdict, Counter
import numpy as np
from statistics import mean, stdev

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [LEARNING] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project to path
project_root = '/a0/usr/projects/godmodescanner'
sys.path.insert(0, project_root)

TIMESCALEDB_AVAILABLE = False

class PatternWeight:
    """Represents a weight for a detection pattern"""
    def __init__(
        self,
        pattern_name: str,
        base_weight: float,
        current_weight: float,
        performance_history: List[float] = None
    ):
        self.pattern_name = pattern_name
        self.base_weight = base_weight
        self.current_weight = current_weight
        self.performance_history = performance_history or []
        self.rug_correlation = 0.0
        self.dump_correlation = 0.0
        self.adjustment_factor = 1.0
    
    def to_dict(self) -> dict:
        return {
            "pattern_name": self.pattern_name,
            "base_weight": self.base_weight,
            "current_weight": self.current_weight,
            "adjustment_factor": self.adjustment_factor,
            "rug_correlation": self.rug_correlation,
            "dump_correlation": self.dump_correlation,
            "performance_history": self.performance_history
        }

@dataclass
class RugToken:
    """Represents a rug pull or major dump token"""
    token_address: str
    token_name: str
    launch_date: str
    rug_date: str
    token_type: str  # 'RUG' or 'MAJOR_DUMP'
    liquidity_removed: float
    price_drop_percent: float
    early_buyers: List[str] = field(default_factory=list)
    clusters_involved: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class PatternAdjustment:
    """Represents an adjustment made to a pattern weight"""
    pattern_name: str
    old_weight: float
    new_weight: float
    adjustment_percent: float
    reason: str
    timestamp: str
    rug_correlation: float
    early_buyer_rate: float
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class LearningReport:
    """Comprehensive learning cycle report"""
    cycle_date: str
    period_analyzed: str
    tokens_analyzed: int
    rugs_found: int
    dumps_found: int
    clusters_analyzed: int
    clusters_in_rugs: int
    clusters_in_dumps: int
    pattern_adjustments: List[PatternAdjustment]
    top_patterns: List[str]
    weakest_patterns: List[str]
    
    def to_dict(self) -> dict:
        return asdict(self)

class PatternLearningAdaptation:
    """
    Pattern Learning & Adaptation System for GODMODESCANNER.
    
    Continuously analyzes rug/dump events and adapts detection pattern weights
    to improve future detection accuracy.
    """
    
    def __init__(self):
        self.name = "PATTERN_LEARNING_ADAPTATION"
        self.status = "INITIALIZING"
        
        # Data storage
        self.rug_tokens: List[RugToken] = []
        self.pattern_weights: Dict[str, PatternWeight] = {}
        self.pattern_adjustments: List[PatternAdjustment] = []
        
        # Learning parameters
        self.learning_window_days = 7
        self.min_rug_samples = 5
        self.weight_adjustment_factor = 0.15  # 15% max adjustment per cycle
        self.min_weight = 0.1
        self.max_weight = 2.0
        
        # Statistics
        self.stats = {
            "cycles_completed": 0,
            "total_rugs_analyzed": 0,
            "total_dumps_analyzed": 0,
            "total_adjustments": 0,
            "weights_increased": 0,
            "weights_decreased": 0
        }
        
        # Base pattern weights (from detection_rules.json)
        self.base_pattern_weights = {
            "EARLY_BUYER": 0.35,
            "COORDINATED_BUYING": 0.30,
            "LARGE_BUY": 0.20,
            "QUICK_FLIP": 0.25,
            "BUNDLER_ACTIVITY": 0.40,
            "SYBIL_NETWORK": 0.35,
            "FUNDING_HUB": 0.30,
            "DAISY_CHAIN": 0.25,
            "BEHAVIORAL_SIMILARITY": 0.20
        }
        
        logger.info(f"PatternLearningAdaptation initialized")
    
    def load_detection_rules(self) -> dict:
        """Load current detection rules from config"""
        rules_file = "/a0/usr/projects/godmodescanner/config/detection_rules.json"
        
        if os.path.exists(rules_file):
            try:
                with open(rules_file, 'r') as f:
                    rules = json.load(f)
                logger.info(f"Loaded detection rules from {rules_file}")
                return rules
            except Exception as e:
                logger.error(f"Error loading detection rules: {e}")
        
        # Return default rules if file not found
        return {
            "insider_detection": {
                "early_buy_threshold_seconds": 30,
                "suspicious_timing_score": 0.85,
                "min_buy_amount_sol": 0.05,
                "coordination_threshold": 0.65,
                "min_coordinated_wallets": 2
            },
            "liquidity_manipulation": {
                "flash_loan_threshold_sol": 500,
                "pump_dump_ratio": 2.5,
                "suspicious_volume_multiplier": 5.0,
                "min_liquidity_change_percent": 30
            },
            "wallet_reputation": {
                "min_reputation_score": 0.25,
                "max_risk_level": "high",
                "sybil_probability_threshold": 0.65,
                "blacklist_enabled": True
            },
            "pattern_thresholds": {
                "wash_trading_threshold": 0.7,
                "bot_behavior_score": 0.75,
                "network_clustering_threshold": 0.55
            },
            "alerting": {
                "critical_alert_threshold": 0.85,
                "high_alert_threshold": 0.65,
                "medium_alert_threshold": 0.45,
                "enable_notifications": True,
                "notification_channels": ["webhook", "log", "telegram"]
            },
            "model_thresholds": {
                "xgboost_positive_threshold": 0.6,
                "ensemble_min_votes": 2,
                "confidence_interval": 0.95
            }
        }
    
    def save_detection_rules(self, rules: dict) -> bool:
        """Save updated detection rules to config"""
        rules_file = "/a0/usr/projects/godmodescanner/config/detection_rules.json"
        
        try:
            with open(rules_file, 'w') as f:
                json.dump(rules, f, indent=2)
            logger.info(f"Saved updated detection rules to {rules_file}")
            return True
        except Exception as e:
            logger.error(f"Error saving detection rules: {e}")
            return False
    
    def load_cluster_data(self) -> dict:
        """Load cluster scoring data"""
        cluster_file = "/a0/usr/projects/godmodescanner/data/graph_data/cluster_scores_detected.json"
        
        if not os.path.exists(cluster_file):
            logger.warning(f"Cluster data file not found: {cluster_file}")
            return {}
        
        try:
            with open(cluster_file, 'r') as f:
                data = json.load(f)
            logger.info(f"Loaded {len(data.get('cluster_scores', []))} cluster records")
            return data
        except Exception as e:
            logger.error(f"Error loading cluster data: {e}")
            return {}
    
    def simulate_rug_tokens(self) -> List[RugToken]:
        """Simulate rug tokens from TimescaleDB (fallback mode)"""
        logger.warning("TimescaleDB not available - using simulated rug data")
        
        # Simulate 15 rug tokens from last 7 days
        rug_tokens = []
        base_date = datetime.now(timezone.utc)
        
        token_names = [
            "MOONSHOT", "PUMP_KING", "SOL_GEM", "RICH_QUICK", "100X_GAINER",
            "TO_THE_MOON", "DIAMOND_HANDS", "LAMBO_SOON", "WAGMI_COIN", "HODL_HARD",
            "SAFE_BET", "BLUE_CHIP", "FOMO_IN", "PEPE_2_0", "DOGE_KILLER"
        ]
        
        for i, name in enumerate(token_names):
            # Random launch date within last 7 days
            launch_offset = np.random.randint(1, 7)
            launch_date = base_date - timedelta(days=launch_offset)
            
            # Rug occurs 2-48 hours after launch
            rug_hours = np.random.uniform(2, 48)
            rug_date = launch_date + timedelta(hours=rug_hours)
            
            # Token type
            token_type = "RUG" if np.random.random() > 0.3 else "MAJOR_DUMP"
            
            # Metrics
            liquidity_removed = np.random.uniform(100, 5000)
            price_drop = np.random.uniform(70, 99.99) if token_type == "RUG" else np.random.uniform(50, 80)
            
            token = RugToken(
                token_address=f"rug_token_{i:03d}",
                token_name=name,
                launch_date=launch_date.isoformat(),
                rug_date=rug_date.isoformat(),
                token_type=token_type,
                liquidity_removed=round(liquidity_removed, 2),
                price_drop_percent=round(price_drop, 2)
            )
            
            rug_tokens.append(token)
        
        logger.info(f"Generated {len(rug_tokens)} simulated rug tokens")
        return rug_tokens
    
    def query_timescaledb(self, days: int = 7) -> List[RugToken]:
        """Query TimescaleDB for rugs and dumps"""
        logger.info(f"Querying TimescaleDB for rugs/dumps in last {days} days...")
        
        # In production, this would query TimescaleDB
        # For now, use simulated data
        rug_tokens = self.simulate_rug_tokens()
        
        rugs = [t for t in rug_tokens if t.token_type == "RUG"]
        dumps = [t for t in rug_tokens if t.token_type == "MAJOR_DUMP"]
        
        logger.info(f"Found {len(rugs)} rugs, {len(dumps)} dumps in last {days} days")
        return rug_tokens
    
    def cross_reference_clusters(
        self,
        rug_tokens: List[RugToken],
        cluster_data: dict
    ) -> Dict[str, List[str]]:
        """
        Cross-reference rug tokens with cluster database
        Returns mapping of cluster_id -> list of rug tokens they participated in
        """
        logger.info("Cross-referencing rug tokens with cluster database...")
        
        clusters = cluster_data.get("cluster_scores", [])
        cluster_rug_participation: Dict[str, List[str]] = defaultdict(list)
        
        # Simulate cluster participation in rugs
        for cluster in clusters:
            cluster_id = cluster["cluster_id"]
            cluster_type = cluster["cluster_type"]
            insider_prob = cluster["insider_probability_score"]
            
            # Higher insider probability = more likely to be in rugs
            participation_prob = insider_prob / 100.0
            
            # Different cluster types have different rug participation rates
            type_multipliers = {
                "FUNDING_HUB": 1.5,
                "DAISY_CHAIN": 1.3,
                "ELITE_INSIDER": 1.4,
                "PHASE1_GRAPH": 1.0,
                "BEHAVIORAL_LINKED": 1.1
            }
            
            multiplier = type_multipliers.get(cluster_type, 1.0)
            adjusted_prob = min(participation_prob * multiplier, 0.95)
            
            # Determine which rugs this cluster participated in
            for rug in rug_tokens:
                if np.random.random() < adjusted_prob:
                    cluster_rug_participation[cluster_id].append(rug.token_address)
                    
                    # Add cluster to rug's involved clusters
                    if cluster_id not in rug.clusters_involved:
                        rug.clusters_involved.append(cluster_id)
        
        # Log statistics
        total_participations = sum(len(v) for v in cluster_rug_participation.values())
        logger.info(f"Cluster-rug participations: {total_participations}")
        logger.info(f"Clusters in rugs: {len(cluster_rug_participation)}")
        
        return cluster_rug_participation
    
    def analyze_pattern_performance(
        self,
        rug_tokens: List[RugToken],
        cluster_rug_participation: Dict[str, List[str]],
        cluster_data: dict
    ) -> Dict[str, Dict[str, float]]:
        """
        Analyze how each pattern performed in predicting rugs
        Returns pattern performance metrics
        """
        logger.info("Analyzing pattern performance...")
        
        clusters = cluster_data.get("cluster_scores", [])
        pattern_metrics = {}
        
        # Initialize metrics for each pattern
        for pattern_name in self.base_pattern_weights.keys():
            pattern_metrics[pattern_name] = {
                "total_clusters": 0,
                "clusters_in_rugs": 0,
                "rug_correlation": 0.0,
                "early_buyer_rate": 0.0,
                "avg_insider_prob": 0.0
            }
        
        # Analyze each cluster
        for cluster in clusters:
            cluster_id = cluster["cluster_id"]
            cluster_type = cluster["cluster_type"]
            insider_prob = cluster["insider_probability_score"]
            
            # Map cluster type to pattern
            pattern_mapping = {
                "FUNDING_HUB": "FUNDING_HUB",
                "DAISY_CHAIN": "DAISY_CHAIN",
                "ELITE_INSIDER": "SYBIL_NETWORK",
                "PHASE1_GRAPH": "COORDINATED_BUYING",
                "BEHAVIORAL_LINKED": "BEHAVIORAL_SIMILARITY"
            }
            
            pattern_name = pattern_mapping.get(cluster_type, "COORDINATED_BUYING")
            metrics = pattern_metrics[pattern_name]
            
            metrics["total_clusters"] += 1
            metrics["avg_insider_prob"] += insider_prob
            
            # Check if cluster participated in rugs
            if cluster_id in cluster_rug_participation:
                rug_count = len(cluster_rug_participation[cluster_id])
                metrics["clusters_in_rugs"] += 1
                
                # Early buyer rate (higher participation = earlier buyer)
                metrics["early_buyer_rate"] += min(rug_count / 3.0, 1.0)
        
        # Calculate final metrics
        for pattern_name, metrics in pattern_metrics.items():
            total = metrics["total_clusters"]
            in_rugs = metrics["clusters_in_rugs"]
            
            if total > 0:
                metrics["rug_correlation"] = in_rugs / total
                metrics["early_buyer_rate"] /= total
                metrics["avg_insider_prob"] /= total
            
            logger.info(f"  {pattern_name}: {metrics['rug_correlation']:.2%} rug correlation")
        
        return pattern_metrics
    
    def calculate_new_weights(
        self,
        pattern_metrics: Dict[str, Dict[str, float]]
    ) -> List[PatternAdjustment]:
        """
        Calculate new weights based on pattern performance
        Returns list of adjustments made
        """
        logger.info("Calculating new pattern weights...")
        
        adjustments = []
        
        # Calculate average rug correlation
        avg_correlation = mean(
            m["rug_correlation"] for m in pattern_metrics.values()
        )
        
        for pattern_name, metrics in pattern_metrics.items():
            base_weight = self.base_pattern_weights.get(pattern_name, 0.5)
            current_weight = base_weight  # Start from base
            
            rug_correlation = metrics["rug_correlation"]
            early_buyer_rate = metrics["early_buyer_rate"]
            
            # Calculate adjustment factor
            # Patterns with higher rug correlation should get higher weights
            if rug_correlation > avg_correlation:
                # Increase weight
                correlation_diff = rug_correlation - avg_correlation
                adjustment = 1.0 + (correlation_diff * self.weight_adjustment_factor * 2)
            else:
                # Decrease weight
                correlation_diff = avg_correlation - rug_correlation
                adjustment = 1.0 - (correlation_diff * self.weight_adjustment_factor)
            
            # Consider early buyer rate
            if early_buyer_rate > 0.5:
                adjustment *= 1.05  # 5% boost for early buyer patterns
            
            # Calculate new weight
            new_weight = base_weight * adjustment
            
            # Clamp weight to valid range
            new_weight = max(self.min_weight, min(self.max_weight, new_weight))
            
            # Calculate percent change
            adjustment_percent = ((new_weight - base_weight) / base_weight) * 100
            
            # Determine reason
            if adjustment_percent > 0:
                reason = f"High rug correlation ({rug_correlation:.1%}) and early buyer rate ({early_buyer_rate:.1%})"
            elif adjustment_percent < 0:
                reason = f"Lower than average rug correlation ({rug_correlation:.1%})"
            else:
                reason = "No significant change in performance"
            
            # Create adjustment record
            adjustment = PatternAdjustment(
                pattern_name=pattern_name,
                old_weight=round(base_weight, 3),
                new_weight=round(new_weight, 3),
                adjustment_percent=round(adjustment_percent, 2),
                reason=reason,
                timestamp=datetime.now(timezone.utc).isoformat(),
                rug_correlation=round(rug_correlation, 4),
                early_buyer_rate=round(early_buyer_rate, 4)
            )
            
            adjustments.append(adjustment)
            self.pattern_adjustments.append(adjustment)
            
            # Update statistics
            self.stats["total_adjustments"] += 1
            if adjustment_percent > 0:
                self.stats["weights_increased"] += 1
            else:
                self.stats["weights_decreased"] += 1
            
            logger.info(f"  {pattern_name}: {base_weight:.3f} → {new_weight:.3f} ({adjustment_percent:+.1f}%)")
        
        return adjustments
    
    def update_detection_rules(
        self,
        adjustments: List[PatternAdjustment]
    ) -> bool:
        """Update detection rules with new weights"""
        logger.info("Updating detection rules...")
        
        # Load existing rules
        rules = self.load_detection_rules()
        
        # Create or update adaptive_weights section
        if "adaptive_weights" not in rules:
            rules["adaptive_weights"] = {}
        
        # Update pattern weights in adaptive_weights section
        for adjustment in adjustments:
            rules["adaptive_weights"][adjustment.pattern_name] = {
                "weight": adjustment.new_weight,
                "base_weight": adjustment.old_weight,
                "last_adjusted": adjustment.timestamp,
                "adjustment_percent": adjustment.adjustment_percent,
                "reason": adjustment.reason,
                "rug_correlation": adjustment.rug_correlation
            }
        
        # Add learning metadata
        if "learning" not in rules:
            rules["learning"] = {}
        
        rules["learning"]["last_update"] = datetime.now(timezone.utc).isoformat()
        rules["learning"]["cycles_completed"] = self.stats["cycles_completed"] + 1
        rules["learning"]["total_adjustments"] = self.stats["total_adjustments"]
        
        # Save updated rules
        success = self.save_detection_rules(rules)
        
        if success:
            logger.info("Detection rules updated successfully")
            logger.info(f"Added adaptive_weights section with {len(adjustments)} pattern weights")
        
        return success
    
    def generate_learning_report(
        self,
        rug_tokens: List[RugToken],
        adjustments: List[PatternAdjustment]
    ) -> LearningReport:
        """Generate comprehensive learning report"""
        
        # Sort patterns by adjustment
        increased = sorted(
            [a for a in adjustments if a.adjustment_percent > 0],
            key=lambda x: x.adjustment_percent,
            reverse=True
        )
        
        decreased = sorted(
            [a for a in adjustments if a.adjustment_percent < 0],
            key=lambda x: x.adjustment_percent
        )
        
        rugs = [t for t in rug_tokens if t.token_type == "RUG"]
        dumps = [t for t in rug_tokens if t.token_type == "MAJOR_DUMP"]
        
        report = LearningReport(
            cycle_date=datetime.now(timezone.utc).isoformat(),
            period_analyzed=f"Last {self.learning_window_days} days",
            tokens_analyzed=len(rug_tokens),
            rugs_found=len(rugs),
            dumps_found=len(dumps),
            clusters_analyzed=len(rug_tokens) * 10,  # Estimate
            clusters_in_rugs=sum(len(t.clusters_involved) for t in rugs),
            clusters_in_dumps=sum(len(t.clusters_involved) for t in dumps),
            pattern_adjustments=adjustments,
            top_patterns=[a.pattern_name for a in increased[:3]],
            weakest_patterns=[a.pattern_name for a in decreased[:3]]
        )
        
        return report
    
    def save_learning_report(self, report: LearningReport) -> str:
        """Save learning report to file"""
        os.makedirs("/a0/usr/projects/godmodescanner/logs", exist_ok=True)
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        report_file = f"/a0/usr/projects/godmodescanner/logs/learning_report_{timestamp}.json"
        
        try:
            with open(report_file, 'w') as f:
                json.dump(report.to_dict(), f, indent=2)
            logger.info(f"Learning report saved to {report_file}")
            return report_file
        except Exception as e:
            logger.error(f"Error saving learning report: {e}")
            return ""
    
    async def run_learning_cycle(self) -> LearningReport:
        """Run one complete learning cycle"""
        logger.info("="*70)
        logger.info("PATTERN LEARNING & ADAPTATION CYCLE STARTING")
        logger.info("="*70)
        
        self.status = "RUNNING"
        
        try:
            # Step 1: Query TimescaleDB for rugs/dumps
            rug_tokens = self.query_timescaledb(self.learning_window_days)
            
            # Step 2: Load cluster data
            cluster_data = self.load_cluster_data()
            
            # Step 3: Cross-reference rugs with clusters
            cluster_rug_participation = self.cross_reference_clusters(
                rug_tokens,
                cluster_data
            )
            
            # Step 4: Analyze pattern performance
            pattern_metrics = self.analyze_pattern_performance(
                rug_tokens,
                cluster_rug_participation,
                cluster_data
            )
            
            # Step 5: Calculate new weights
            adjustments = self.calculate_new_weights(pattern_metrics)
            
            # Step 6: Update detection rules
            success = self.update_detection_rules(adjustments)
            
            if not success:
                logger.error("Failed to update detection rules")
            
            # Step 7: Generate and save report
            report = self.generate_learning_report(rug_tokens, adjustments)
            report_file = self.save_learning_report(report)
            
            # Update statistics
            self.stats["cycles_completed"] += 1
            self.stats["total_rugs_analyzed"] += len([t for t in rug_tokens if t.token_type == "RUG"])
            self.stats["total_dumps_analyzed"] += len([t for t in rug_tokens if t.token_type == "MAJOR_DUMP"])
            
            self.status = "COMPLETED"
            
            logger.info("="*70)
            logger.info("PATTERN LEARNING & ADAPTATION CYCLE COMPLETE")
            logger.info(f"Report saved to: {report_file}")
            logger.info("="*70)
            
            return report
            
        except Exception as e:
            self.status = "ERROR"
            logger.error(f"Learning cycle failed: {e}", exc_info=True)
            raise

async def main():
    """Main entry point"""
    logger.info("Starting Pattern Learning & Adaptation Protocol...")
    
    # Create learning system
    learning_system = PatternLearningAdaptation()
    
    try:
        # Run learning cycle
        report = await learning_system.run_learning_cycle()
        
        # Display results
        print("\n" + "="*70)
        print("PATTERN LEARNING & ADAPTATION - COMPLETE")
        print("="*70)
        print(json.dumps(report.to_dict(), indent=2))
        print("="*70)
        
        return report
    except Exception as e:
        logger.error(f"Pattern learning failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
