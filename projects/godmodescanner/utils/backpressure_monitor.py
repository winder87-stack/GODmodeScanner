#!/usr/bin/env python3
"""Backpressure Monitor - Real-time monitoring of Redis Streams and consumer groups.

This tool monitors Redis Streams consumer groups to detect backpressure,
consumer lag, and system health issues.

Key Features:
- Real-time pending message monitoring
- Consumer lag detection
- Stream depth analysis
- Consumer group health checks
- Alerts for backpressure issues
- Historical statistics
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
import structlog
from datetime import datetime, timedelta

try:
    from redis.asyncio import Redis as AsyncRedis
    from redis.asyncio.connection import ConnectionPool
except ImportError:
    from redis.asyncio.client import Redis as AsyncRedis
    from redis.asyncio.connection import ConnectionPool

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger(__name__)

# Stream and group names
STREAM_TRANSACTIONS = "godmode:new_transactions"
STREAM_TOKEN_LAUNCHES = "godmode:token_launches"
STREAM_TRADES = "godmode:trades"
STREAM_ALERTS = "godmode:alerts"
STREAM_RISK_SCORES = "godmode:risk_scores"

# Consumer groups
WALLET_ANALYZER_GROUP = "wallet-analyzer-group"
PATTERN_RECOGNITION_GROUP = "pattern-recognition-group"
SYBIL_DETECTION_GROUP = "sybil-detection-group"
RISK_SCORING_GROUP = "risk-scoring-group"
ALERT_MANAGER_GROUP = "alert-manager-group"


@dataclass
class ConsumerInfo:
    """Information about a consumer."""
    name: str
    pending: int
    idle: int
    
    @classmethod
    def from_redis_info(cls, info: List[Any]) -> 'ConsumerInfo':
        """Create from Redis XINFO CONSUMERS output."""
        return cls(
            name=info["name"],
            pending=info["pending"],
            idle=info["idle"],
        )


@dataclass
class GroupInfo:
    """Information about a consumer group."""
    name: str
    pending: int
    last_delivered_id: str
    lag: int  # Number of messages waiting to be processed
    consumers: List[ConsumerInfo] = field(default_factory=list)
    
    @classmethod
    def def from_redis_info(cls, info: List[Any]) -> 'GroupInfo':
        """Create from Redis XINFO GROUPS output."""
        consumers = [
            ConsumerInfo.from_redis_info(c)
            for c in info.get("consumers", [])
        ]
        return cls(
            name=info["name"],
            pending=info["pending"],
            last_delivered_id=info.get("last-delivered-id", ""),
            lag=info.get("lag", 0),
            consumers=consumers,
        )


@dataclass
class StreamInfo:
    """Information about a stream."""
    name: str
    length: int
    groups: int
    first_entry_id: str
    last_entry_id: str
    
    @classmethod
    def from_redis_info(cls, info: List[Any]) -> 'StreamInfo':
        """Create from Redis XINFO STREAM output."""
        return cls(
            name=info.get("name", ""),
            length=info.get("length", 0),
            groups=info.get("groups", 0),
            first_entry_id=info.get("first-entry", {}).get("id", ""),
            last_entry_id=info.get("last-entry", {}).get("id", ""),
        )


@dataclass
class BackpressureAlert:
    """Represents a backpressure alert."""
    severity: str  # "warning", "critical"
    stream: str
    group: str
    message: str
    value: float
    threshold: float
    timestamp: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "stream": self.stream,
            "group": self.group,
            "message": self.message,
            "value": self.value,
            "threshold": self.threshold,
            "timestamp": self.timestamp,
        }


class BackpressureMonitor:
    """Real-time backpressure monitor for Redis Streams.
    
    This class monitors Redis Streams consumer groups and:
    - Tracks pending message counts
    - Detects consumer lag
    - Monitors stream depth
    - Generates alerts for backpressure issues
    - Provides historical statistics
    """

    # Thresholds
    PENDING_WARNING_THRESHOLD = 100
    PENDING_CRITICAL_THRESHOLD = 1000
    LAG_WARNING_THRESHOLD = 50
    LAG_CRITICAL_THRESHOLD = 500
    IDLE_WARNING_THRESHOLD_MS = 30000  # 30 seconds
    IDLE_CRITICAL_THRESHOLD_MS = 120000  # 2 minutes
    STREAM_DEPTH_WARNING_THRESHOLD = 10000
    STREAM_DEPTH_CRITICAL_THRESHOLD = 50000
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        check_interval: float = 5.0,  # Check every 5 seconds
    ):
        """Initialize backpressure monitor.
        
        Args:
            redis_url: Redis connection URL
            check_interval: Time between health checks (seconds)
        """
        self.redis_url = redis_url
        self.check_interval = check_interval
        
        # Connection
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[AsyncRedis] = None
        
        # State
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        
        # Monitoring targets
        self.targets = [
            (STREAM_TRANSACTIONS, [WALLET_ANALYZER_GROUP, PATTERN_RECOGNITION_GROUP, SYBIL_DETECTION_GROUP]),
            (STREAM_TOKEN_LAUNCHES, [WALLET_ANALYZER_GROUP]),
            (STREAM_TRADES, [WALLET_ANALYZER_GROUP]),
            (STREAM_ALERTS, [ALERT_MANAGER_GROUP]),
            (STREAM_RISK_SCORES, [ALERT_MANAGER_GROUP]),
        ]
        
        # Alerts history
        self.alerts: List[BackpressureAlert] = []
        self.max_alerts_history = 1000
        
        # Historical statistics
        self.history: Dict[str, List[Dict[str, Any]]] = {}
        self.max_history_per_key = 720  # 1 hour of data at 5s intervals
        
        # Current state
        self.current_state: Dict[str, Dict[str, Any]] = {}
        
        logger.info(
            "backpressure_monitor_init",
            redis_url=redis_url,
            check_interval=check_interval,
        )

    async def connect(self) -> bool:
        """Establish connection to Redis."""
        try:
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=10,
                decode_responses=False,
            )
            self._redis = AsyncRedis(connection_pool=self._pool)
            
            # Test connection
            await self._redis.ping()
            logger.info("backpressure_monitor_connected")
            return True
        except Exception as e:
            logger.error("backpressure_monitor_connect_failed", error=str(e))
            return False

    async def start(self):
        """Start monitoring in the background."""
        if self._running:
            logger.warning("backpressure_monitor_already_running")
            return
        
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("backpressure_monitor_started")

    async def stop(self):
        """Stop monitoring."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("backpressure_monitor_stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_all()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("monitor_loop_error", error=str(e))
                await asyncio.sleep(5)

    async def _check_all(self):
        """Check all streams and consumer groups."""
        now = time.time()
        timestamp = datetime.now().isoformat()
        
        for stream_name, group_names in self.targets:
            try:
                # Get stream info
                stream_info = await self._get_stream_info(stream_name)
                if not stream_info:
                    continue
                
                for group_name in group_names:
                    # Get group info
                    group_info = await self._get_group_info(stream_name, group_name)
                    if not group_info:
                        continue
                    
                    # Check for alerts
                    await self._check_for_alerts(stream_info, group_info, now)
                    
                    # Update current state
                    key = f"{stream_name}:{group_name}"
                    self.current_state[key] = {
                        "stream": stream_name,
                        "group": group_name,
                        "stream_length": stream_info.length,
                        "pending": group_info.pending,
                        "lag": group_info.lag,
                        "consumers": [
                            {
                                "name": c.name,
                                "pending": c.pending,
                                "idle_ms": c.idle,
                            }
                            for c in group_info.consumers
                        ],
                        "timestamp": timestamp,
                    }
                    
                    # Update history
                    self._update_history(key, self.current_state[key])
                
            except Exception as e:
                logger.error(
                    "check_error",
                    stream=stream_name,
                    error=str(e),
                )

    async def _get_stream_info(self, stream_name: str) -> Optional[StreamInfo]:
        """Get information about a stream."""
        try:
            info = await self._redis.xinfo_stream(stream_name)
            return StreamInfo.from_redis_info(info)
        except Exception:
            return None

    async def _get_group_info(self, stream_name: str, group_name: str) -> Optional[GroupInfo]:
        """Get information about a consumer group."""
        try:
            info = await self._redis.xinfo_groups(stream_name)
            for group in info:
                if group["name"] == group_name:
                    return GroupInfo.from_redis_info(group)
            return None
        except Exception:
            return None

    async def _check_for_alerts(self, stream_info: StreamInfo, group_info: GroupInfo, now: float):
        """Check for backpressure alerts."""
        # Check pending messages
        if group_info.pending >= self.PENDING_CRITICAL_THRESHOLD:
            self._create_alert(
                severity="critical",
                stream=stream_info.name,
                group=group_info.name,
                message=f"Critical pending message count",
                value=float(group_info.pending),
                threshold=float(self.PENDING_CRITICAL_THRESHOLD),
                timestamp=now,
            )
        elif group_info.pending >= self.PENDING_WARNING_THRESHOLD:
            self._create_alert(
                severity="warning",
                stream=stream_info.name,
                group=group_info.name,
                message=f"High pending message count",
                value=float(group_info.pending),
                threshold=float(self.PENDING_WARNING_THRESHOLD),
                timestamp=now,
            )
        
        # Check lag
        if group_info.lag >= self.LAG_CRITICAL_THRESHOLD:
            self._create_alert(
                severity="critical",
                stream=stream_info.name,
                group=group_info.name,
                message=f"Critical consumer lag",
                value=float(group_info.lag),
                threshold=float(self.LAG_CRITICAL_THRESHOLD),
                timestamp=now,
            )
        elif group_info.lag >= self.LAG_WARNING_THRESHOLD:
            self._create_alert(
                severity="warning",
                stream=stream_info.name,
                group=group_info.name,
                message=f"High consumer lag",
                value=float(group_info.lag),
                threshold=float(self.LAG_WARNING_THRESHOLD),
                timestamp=now,
            )
        
        # Check consumer idle time
        for consumer in group_info.consumers:
            if consumer.idle >= self.IDLE_CRITICAL_THRESHOLD_MS:
                self._create_alert(
                    severity="critical",
                    stream=stream_info.name,
                    group=group_info.name,
                    message=f"Consumer {consumer.name} is idle",
                    value=float(consumer.idle),
                    threshold=float(self.IDLE_CRITICAL_THRESHOLD_MS),
                    timestamp=now,
                )
            elif consumer.idle >= self.IDLE_WARNING_THRESHOLD_MS:
                self._create_alert(
                    severity="warning",
                    stream=stream_info.name,
                    group=group_info.name,
                    message=f"Consumer {consumer.name} is idle",
                    value=float(consumer.idle),
                    threshold=float(self.IDLE_WARNING_THRESHOLD_MS),
                    timestamp=now,
                )
        
        # Check stream depth
        if stream_info.length >= self.STREAM_DEPTH_CRITICAL_THRESHOLD:
            self._create_alert(
                severity="critical",
                stream=stream_info.name,
                group=group_info.name,
                message=f"Critical stream depth",
                value=float(stream_info.length),
                threshold=float(self.STREAM_DEPTH_CRITICAL_THRESHOLD),
                timestamp=now,
            )
        elif stream_info.length >= self.STREAM_DEPTH_WARNING_THRESHOLD:
            self._create_alert(
                severity="warning",
                stream=stream_info.name,
                group=group_info.name,
                message=f"High stream depth",
                value=float(stream_info.length),
                threshold=float(self.STREAM_DEPTH_WARNING_THRESHOLD),
                timestamp=now,
            )

    def _create_alert(self, severity: str, stream: str, group: str, message: str, value: float, threshold: float, timestamp: float):
        """Create a backpressure alert."""
        alert = BackpressureAlert(
            severity=severity,
            stream=stream,
            group=group,
            message=message,
            value=value,
            threshold=threshold,
            timestamp=timestamp,
        )
        
        self.alerts.append(alert)
        
        # Trim history
        if len(self.alerts) > self.max_alerts_history:
            self.alerts = self.alerts[-self.max_alerts_history:]
        
        # Log alert
        logger.warning(
            "backpressure_alert",
            severity=severity,
            stream=stream,
            group=group,
            message=message,
            value=value,
            threshold=threshold,
        )

    def _update_history(self, key: str, data: Dict[str, Any]):
        """Update historical data."""
        if key not in self.history:
            self.history[key] = []
        
        self.history[key].append(data)
        
        # Trim history
        if len(self.history[key]) > self.max_history_per_key:
            self.history[key] = self.history[key][-self.max_history_per_key:]

    async def get_current_state(self) -> Dict[str, Dict[str, Any]]:
        """Get current state of all streams and groups."""
        return self.current_state.copy()

    async def get_alerts(self, severity: Optional[str] = None, since: Optional[float] = None) -> List[BackpressureAlert]:
        """Get alerts with optional filtering."""
        alerts = self.alerts.copy()
        
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        
        if since:
            alerts = [a for a in alerts if a.timestamp >= since]
        
        return alerts

    async def get_history(self, key: str) -> List[Dict[str, Any]]:
        """Get historical data for a specific stream/group."""
        return self.history.get(key, []).copy()

    async def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the monitoring state."""
        total_pending = sum(state["pending"] for state in self.current_state.values())
        total_lag = sum(state["lag"] for state in self.current_state.values())
        
        recent_alerts = [a for a in self.alerts if time.time() - a.timestamp < 300]  # Last 5 minutes
        
        return {
            "monitoring": self._running,
            "streams_monitored": len(self.targets),
            "total_pending": total_pending,
            "total_lag": total_lag,
            "recent_alerts": len(recent_alerts),
            "critical_alerts": len([a for a in recent_alerts if a.severity == "critical"]),
            "warning_alerts": len([a for a in recent_alerts if a.severity == "warning"]),
            "last_check": self.current_state.get(list(self.current_state.keys())[0], {}).get("timestamp") if self.current_state else None,
        }

    async def close(self):
        """Clean up resources."""
        await self.stop()
        if self._redis:
            await self._redis.close()
        if self._pool:
            await self._pool.disconnect()
        logger.info("backpressure_monitor_closed")


async def main():
    """Main entry point for running the backpressure monitor."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Backpressure Monitor for Redis Streams")
    parser.add_argument("--redis-url", default="redis://localhost:6379", help="Redis URL")
    parser.add_argument("--interval", type=float, default=5.0, help="Check interval (seconds)")
    args = parser.parse_args()
    
    monitor = BackpressureMonitor(redis_url=args.redis_url, check_interval=args.interval)
    
    try:
        await monitor.connect()
        await monitor.start()
        
        # Periodically print summary
        while True:
            summary = await monitor.get_summary()
            print("\n" + "="*60)
            print(f"Backpressure Monitor Summary - {datetime.now().isoformat()}")
            print("="*60)
            print(f"Monitoring: {summary['monitoring']}")
            print(f"Streams Monitored: {summary['streams_monitored']}")
            print(f"Total Pending: {summary['total_pending']}")
            print(f"Total Lag: {summary['total_lag']}")
            print(f"Recent Alerts (5min): {summary['recent_alerts']}")
            print(f"  Critical: {summary['critical_alerts']}")
            print(f"  Warning: {summary['warning_alerts']}")
            
            await asyncio.sleep(30)
    
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
