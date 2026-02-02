#!/usr/bin/env python3
"""
Autonomous Alert Triggering Protocol for GODMODESCANNER

Continuously monitors cluster database and triggers autonomous alerts:
- CRITICAL: Insider Probability > 85%
- HIGH: Insider Probability 65-84%

Alerts are published to the 'alerts' Redis channel within 500ms of threshold breach.

Alert Format:
{
  "alert_type": "CRITICAL" | "HIGH",
  "cluster_id": "...",
  "wallet_count": N,
  "insider_probability": N.N,
  "pattern_type": "Funding Hub" | "Daisy Chain" | "Phase 1 Graph" | "Elite Insider",
  "timestamp": "ISO-8601",
  "detection_source": "autonomous_alert_trigger"
}
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, asdict
import structlog
from collections import defaultdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [ALERT_TRIGGER] %(levelname)s: %(message)s',
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

# Alert thresholds
CRITICAL_THRESHOLD = 85.0
HIGH_THRESHOLD_MIN = 65.0
HIGH_THRESHOLD_MAX = 84.999

@dataclass
class ClusterState:
    """Tracks the state of a cluster for alert triggering"""
    cluster_id: str
    cluster_type: str
    wallet_count: int
    insider_probability: float
    overall_risk: float
    cluster_pnl: float
    last_alert_type: Optional[str] = None
    last_alert_time: Optional[str] = None
    
    def to_dict(self) -> dict:
        return asdict(self)

@dataclass
class Alert:
    """Represents an alert triggered for a cluster"""
    alert_type: str  # CRITICAL, HIGH
    cluster_id: str
    wallet_count: int
    insider_probability: float
    pattern_type: str
    timestamp: str
    detection_source: str
    latency_ms: float
    
    def to_dict(self) -> dict:
        return asdict(self)

class AutonomousAlertTrigger:
    """
    Autonomous Alert Triggering System for GODMODESCANNER.
    
    Continuously monitors cluster scores and triggers alerts within 500ms
    of threshold breaches.
    """
    
    def __init__(self, poll_interval: float = 1.0):
        self.name = "AUTONOMOUS_ALERT_TRIGGER"
        self.status = "INITIALIZING"
        self.poll_interval = poll_interval
        
        # Data structures
        self.cluster_states: Dict[str, ClusterState] = {}
        self.alert_history: List[Alert] = []
        self.last_file_mtime = 0
        
        # Statistics
        self.stats = {
            "alerts_triggered": 0,
            "critical_alerts": 0,
            "high_alerts": 0,
            "avg_latency_ms": 0.0,
            "max_latency_ms": 0.0,
            "clusters_monitored": 0,
            "threshold_breaches": 0
        }
        
        # Cluster type to pattern mapping
        self.pattern_mapping = {
            "FUNDING_HUB": "Funding Hub",
            "DAISY_CHAIN": "Daisy Chain",
            "PHASE1_GRAPH": "Phase 1 Graph",
            "ELITE_INSIDER": "Elite Insider",
            "BEHAVIORAL_LINKED": "Behaviorally Linked"
        }
        
        logger.info(f"AutonomousAlertTrigger instance created (poll_interval={poll_interval}s)")
    
    def load_cluster_scores(self) -> bool:
        """Load cluster scores from detection file"""
        cluster_file = "/a0/usr/projects/godmodescanner/data/graph_data/cluster_scores_detected.json"
        
        if not os.path.exists(cluster_file):
            logger.warning(f"Cluster scores file not found: {cluster_file}")
            return False
        
        # Check file modification time
        current_mtime = os.path.getmtime(cluster_file)
        if current_mtime <= self.last_file_mtime:
            return False  # No changes
        
        self.last_file_mtime = current_mtime
        
        try:
            with open(cluster_file, 'r') as f:
                data = json.load(f)
            
            cluster_scores = data.get("cluster_scores", [])
            
            for cluster_data in cluster_scores:
                cluster_id = cluster_data["cluster_id"]
                
                self.cluster_states[cluster_id] = ClusterState(
                    cluster_id=cluster_id,
                    cluster_type=cluster_data["cluster_type"],
                    wallet_count=cluster_data["wallet_count"],
                    insider_probability=cluster_data["insider_probability_score"],
                    overall_risk=cluster_data["overall_risk_score"],
                    cluster_pnl=cluster_data["cluster_pnl"]
                )
            
            self.stats["clusters_monitored"] = len(self.cluster_states)
            logger.info(f"Loaded {len(cluster_scores)} cluster states")
            return True
            
        except Exception as e:
            logger.error(f"Error loading cluster scores: {e}")
            return False
    
    def determine_alert_type(self, insider_probability: float) -> Optional[str]:
        """Determine alert type based on insider probability score"""
        if insider_probability > CRITICAL_THRESHOLD:
            return "CRITICAL"
        elif HIGH_THRESHOLD_MIN <= insider_probability <= HIGH_THRESHOLD_MAX:
            return "HIGH"
        return None
    
    def check_threshold_breaches(self) -> List[Alert]:
        """Check for threshold breaches and generate alerts"""
        alerts = []
        
        for cluster_id, state in self.cluster_states.items():
            alert_type = self.determine_alert_type(state.insider_probability)
            
            if alert_type:
                # Check if this is a new alert or an escalation
                should_alert = False
                
                if state.last_alert_type is None:
                    # First time crossing threshold
                    should_alert = True
                elif state.last_alert_type == "HIGH" and alert_type == "CRITICAL":
                    # Escalation from HIGH to CRITICAL
                    should_alert = True
                
                if should_alert:
                    start_time = time.time()
                    
                    # Map cluster type to pattern name
                    pattern_type = self.pattern_mapping.get(
                        state.cluster_type,
                        state.cluster_type
                    )
                    
                    alert = Alert(
                        alert_type=alert_type,
                        cluster_id=cluster_id,
                        wallet_count=state.wallet_count,
                        insider_probability=state.insider_probability,
                        pattern_type=pattern_type,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        detection_source="autonomous_alert_trigger",
                        latency_ms=0.0  # Will be updated after publish
                    )
                    
                    alerts.append(alert)
                    
                    # Update cluster state
                    state.last_alert_type = alert_type
                    state.last_alert_time = alert.timestamp
                    
                    self.stats["threshold_breaches"] += 1
                    if alert_type == "CRITICAL":
                        self.stats["critical_alerts"] += 1
                    else:
                        self.stats["high_alerts"] += 1
                    
                    # Calculate latency
                    latency = (time.time() - start_time) * 1000
                    alert.latency_ms = round(latency, 2)
                    
                    # Update latency statistics
                    if self.stats["alerts_triggered"] == 0:
                        self.stats["avg_latency_ms"] = latency
                    else:
                        self.stats["avg_latency_ms"] = (
                            self.stats["avg_latency_ms"] * self.stats["alerts_triggered"] + latency
                        ) / (self.stats["alerts_triggered"] + 1)
                    
                    self.stats["max_latency_ms"] = max(self.stats["max_latency_ms"], latency)
        
        self.stats["alerts_triggered"] = len(alerts)
        return alerts
    
    def publish_alert(self, alert: Alert) -> bool:
        """Publish alert to Redis alerts channel"""
        if not REDIS_AVAILABLE:
            logger.warning(f"Redis not available - would publish: {alert.alert_type} for {alert.cluster_id}")
            return False
        
        try:
            alert_dict = alert.to_dict()
            message = json.dumps(alert_dict)
            
            start_time = time.time()
            redis_client.publish("alerts", message)
            publish_time = (time.time() - start_time) * 1000
            
            # Update alert latency
            alert.latency_ms = round(alert.latency_ms + publish_time, 2)
            
            logger.info(f"Published {alert.alert_type} alert for cluster {alert.cluster_id}")
            logger.info(f"  Latency: {alert.latency_ms}ms (threshold: {alert.latency_ms})")
            
            return True
        except Exception as e:
            logger.error(f"Error publishing alert: {e}")
            return False
    
    def publish_alerts(self, alerts: List[Alert]) -> int:
        """Publish multiple alerts to Redis"""
        published_count = 0
        
        for alert in alerts:
            if self.publish_alert(alert):
                published_count += 1
                self.alert_history.append(alert)
        
        return published_count
    
    def generate_report(self) -> dict:
        """Generate alert monitoring report"""
        recent_alerts = sorted(
            self.alert_history,
            key=lambda x: x.timestamp,
            reverse=True
        )[:20]
        
        return {
            "monitoring_summary": {
                "clusters_monitored": self.stats["clusters_monitored"],
                "alerts_triggered": self.stats["alerts_triggered"],
                "critical_alerts": self.stats["critical_alerts"],
                "high_alerts": self.stats["high_alerts"],
                "avg_latency_ms": round(self.stats["avg_latency_ms"], 2),
                "max_latency_ms": round(self.stats["max_latency_ms"], 2)
            },
            "recent_alerts": [
                {
                    "alert_type": a.alert_type,
                    "cluster_id": a.cluster_id,
                    "pattern_type": a.pattern_type,
                    "insider_probability": a.insider_probability,
                    "wallet_count": a.wallet_count,
                    "latency_ms": a.latency_ms,
                    "timestamp": a.timestamp
                } for a in recent_alerts
            ],
            "statistics": self.stats
        }
    
    async def run_one_cycle(self) -> None:
        """Run one monitoring cycle"""
        # Load cluster scores
        if self.load_cluster_scores():
            # Check for threshold breaches
            alerts = self.check_threshold_breaches()
            
            if alerts:
                logger.info(f"="*70)
                logger.info(f"THRESHOLD BREACH DETECTED: {len(alerts)} alerts")
                logger.info(f"="*70)
                
                # Publish alerts
                self.publish_alerts(alerts)
    
    async def run_continuous(self, max_cycles: int = None) -> None:
        """Run continuous monitoring"""
        logger.info("="*70)
        logger.info("AUTONOMOUS ALERT TRIGGERING STARTING")
        logger.info(f"Critical Threshold: >{CRITICAL_THRESHOLD}%")
        logger.info(f"High Threshold: {HIGH_THRESHOLD_MIN}%-{HIGH_THRESHOLD_MAX}%")
        logger.info(f"Target Latency: <500ms")
        logger.info("="*70)
        
        self.status = "RUNNING"
        cycle = 0
        
        try:
            while True:
                if max_cycles and cycle >= max_cycles:
                    logger.info(f"Reached max cycles ({max_cycles})")
                    break
                
                await self.run_one_cycle()
                
                cycle += 1
                
                # Wait for next poll
                await asyncio.sleep(self.poll_interval)
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}", exc_info=True)
        finally:
            self.status = "STOPPED"
            self.generate_final_report()
    
    def generate_final_report(self) -> None:
        """Generate final monitoring report"""
        logger.info("="*70)
        logger.info("AUTONOMOUS ALERT TRIGGERING FINAL REPORT")
        logger.info("="*70)
        
        report = self.generate_report()
        logger.info(json.dumps(report, indent=2))
        
        logger.info("="*70)

async def main():
    """Main entry point"""
    logger.info("Starting Autonomous Alert Triggering Protocol...")
    
    # Create trigger with 1-second poll interval
    trigger = AutonomousAlertTrigger(poll_interval=1.0)
    
    try:
        # Run for demonstration (3 cycles)
        await trigger.run_continuous(max_cycles=3)
        
        # Generate report
        report = trigger.generate_report()
        
        print("\n" + "="*70)
        print("AUTONOMOUS ALERT TRIGGERING COMPLETE")
        print("="*70)
        print(json.dumps(report, indent=2))
        print("="*70)
        
        return report
    except Exception as e:
        logger.error(f"Autonomous alert triggering failed: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    asyncio.run(main())
