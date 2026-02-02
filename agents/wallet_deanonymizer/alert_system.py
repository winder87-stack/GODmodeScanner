
"""
Cluster Alert System - Real-Time Alert Generation for Detected Clusters
========================================================================

Generates and distributes alerts when suspicious wallet clusters are
detected, integrating with GODMODESCANNER's zero-latency alert pipeline.

Features:
- Multi-channel alert distribution (Redis, WebSocket, Discord, Telegram)
- Alert prioritization and deduplication
- Rate limiting to prevent alert fatigue
- Alert history and analytics
- Integration with zero-latency pipeline
"""

import asyncio
import time
import hashlib
from typing import Dict, List, Optional, Set, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import structlog

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

try:
    import orjson
    json_dumps = lambda obj: orjson.dumps(obj).decode()
    json_loads = orjson.loads
except ImportError:
    import json
    json_dumps = json.dumps
    json_loads = json.loads

logger = structlog.get_logger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    CRITICAL = "critical"   # Immediate action required
    HIGH = "high"           # High priority
    MEDIUM = "medium"       # Standard priority
    LOW = "low"             # Informational
    INFO = "info"           # Debug/monitoring


class AlertChannel(Enum):
    """Alert distribution channels."""
    REDIS_STREAM = "redis_stream"
    REDIS_PUBSUB = "redis_pubsub"
    WEBSOCKET = "websocket"
    DISCORD = "discord"
    TELEGRAM = "telegram"
    SLACK = "slack"
    EMAIL = "email"
    WEBHOOK = "webhook"


class AlertType(Enum):
    """Types of cluster alerts."""
    NEW_CLUSTER = "new_cluster"
    CLUSTER_GROWTH = "cluster_growth"
    HIGH_RISK_CLUSTER = "high_risk_cluster"
    SEED_CONNECTION = "seed_connection"
    DAISY_CHAIN = "daisy_chain"
    FUNDING_HUB = "funding_hub"
    SYBIL_NETWORK = "sybil_network"
    TEMPORAL_CORRELATION = "temporal_correlation"
    CLUSTER_MERGE = "cluster_merge"


@dataclass
class ClusterAlert:
    """Represents an alert for a detected cluster."""
    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity

    # Cluster information
    cluster_id: str
    cluster_size: int
    risk_score: float

    # Alert content
    title: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)

    # Affected wallets
    wallets: List[str] = field(default_factory=list)
    seed_wallets: List[str] = field(default_factory=list)

    # Metadata
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None

    # Distribution tracking
    channels_sent: List[str] = field(default_factory=list)
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "cluster_id": self.cluster_id,
            "cluster_size": self.cluster_size,
            "risk_score": round(self.risk_score, 4),
            "title": self.title,
            "message": self.message,
            "details": self.details,
            "wallets": self.wallets[:10],  # Limit for payload size
            "seed_wallets": self.seed_wallets,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "acknowledged": self.acknowledged,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json_dumps(self.to_dict())


@dataclass
class AlertMetrics:
    """Metrics for the alert system."""
    total_alerts: int = 0
    critical_alerts: int = 0
    high_alerts: int = 0
    medium_alerts: int = 0
    low_alerts: int = 0

    alerts_sent: int = 0
    alerts_deduplicated: int = 0
    alerts_rate_limited: int = 0
    alerts_acknowledged: int = 0

    avg_delivery_time_ms: float = 0.0
    last_alert_at: float = 0.0


class AlertRateLimiter:
    """
    Rate limiter to prevent alert fatigue.
    """

    def __init__(
        self,
        max_alerts_per_minute: int = 10,
        max_alerts_per_cluster: int = 3,
        cooldown_seconds: float = 60.0,
    ):
        self.max_alerts_per_minute = max_alerts_per_minute
        self.max_alerts_per_cluster = max_alerts_per_cluster
        self.cooldown_seconds = cooldown_seconds

        # Tracking
        self.minute_window: List[float] = []
        self.cluster_alerts: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check_allowed(self, cluster_id: str) -> bool:
        """
        Check if an alert is allowed.

        Returns:
            True if alert should be sent, False if rate limited
        """
        async with self._lock:
            now = time.time()
            cutoff = now - 60.0

            # Clean old entries
            self.minute_window = [t for t in self.minute_window if t > cutoff]
            self.cluster_alerts[cluster_id] = [
                t for t in self.cluster_alerts[cluster_id] if t > cutoff
            ]

            # Check global rate
            if len(self.minute_window) >= self.max_alerts_per_minute:
                return False

            # Check per-cluster rate
            if len(self.cluster_alerts[cluster_id]) >= self.max_alerts_per_cluster:
                return False

            # Record this alert
            self.minute_window.append(now)
            self.cluster_alerts[cluster_id].append(now)

            return True

    async def force_cooldown(self, cluster_id: str):
        """Force cooldown for a cluster."""
        async with self._lock:
            # Fill up the cluster's quota
            now = time.time()
            self.cluster_alerts[cluster_id] = [now] * self.max_alerts_per_cluster


class AlertDeduplicator:
    """
    Deduplicates similar alerts to prevent spam.
    """

    def __init__(self, window_seconds: float = 300.0):
        self.window_seconds = window_seconds
        self.seen_hashes: Dict[str, float] = {}
        self._lock = asyncio.Lock()

    def _hash_alert(self, alert: ClusterAlert) -> str:
        """Generate hash for deduplication."""
        content = f"{alert.cluster_id}:{alert.alert_type.value}:{alert.severity.value}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def is_duplicate(self, alert: ClusterAlert) -> bool:
        """
        Check if alert is a duplicate.

        Returns:
            True if duplicate, False if new
        """
        async with self._lock:
            now = time.time()

            # Clean old entries
            cutoff = now - self.window_seconds
            self.seen_hashes = {
                h: t for h, t in self.seen_hashes.items() if t > cutoff
            }

            # Check if seen
            alert_hash = self._hash_alert(alert)
            if alert_hash in self.seen_hashes:
                return True

            # Record
            self.seen_hashes[alert_hash] = now
            return False


class ClusterAlertSystem:
    """
    Generates and distributes alerts for detected wallet clusters.

    Features:
    - Multi-channel distribution
    - Rate limiting and deduplication
    - Alert prioritization
    - Integration with zero-latency pipeline
    - Alert history and analytics
    """

    # Redis stream for alerts
    ALERT_STREAM = "godmode:cluster_alerts"
    ALERT_CHANNEL = "godmode:alerts:clusters"

    # Severity thresholds
    SEVERITY_THRESHOLDS = {
        AlertSeverity.CRITICAL: 0.90,
        AlertSeverity.HIGH: 0.75,
        AlertSeverity.MEDIUM: 0.55,
        AlertSeverity.LOW: 0.35,
    }

    def __init__(
        self,
        redis_url: Optional[str] = None,
        enabled_channels: Optional[List[AlertChannel]] = None,
        rate_limit_per_minute: int = 10,
        dedup_window_seconds: float = 300.0,
        alert_ttl_hours: float = 24.0,
    ):
        """
        Initialize the alert system.

        Args:
            redis_url: Redis connection URL
            enabled_channels: List of enabled alert channels
            rate_limit_per_minute: Maximum alerts per minute
            dedup_window_seconds: Deduplication window
            alert_ttl_hours: Alert expiration time
        """
        self.redis_url = redis_url
        self.enabled_channels = enabled_channels or [
            AlertChannel.REDIS_STREAM,
            AlertChannel.REDIS_PUBSUB,
        ]
        self.alert_ttl_seconds = alert_ttl_hours * 3600

        # Components
        self.rate_limiter = AlertRateLimiter(
            max_alerts_per_minute=rate_limit_per_minute,
        )
        self.deduplicator = AlertDeduplicator(
            window_seconds=dedup_window_seconds,
        )

        # Redis client
        self.redis: Optional[redis.Redis] = None

        # Alert storage
        self.alerts: Dict[str, ClusterAlert] = {}
        self.alert_history: List[str] = []  # Alert IDs in order

        # Channel handlers
        self.channel_handlers: Dict[AlertChannel, Callable] = {}

        # Metrics
        self.metrics = AlertMetrics()

        # Counter for IDs
        self._alert_counter = 0

        logger.info(
            "ClusterAlertSystem initialized",
            channels=len(self.enabled_channels),
            rate_limit=rate_limit_per_minute,
        )

    async def initialize(self):
        """Initialize connections."""
        if REDIS_AVAILABLE and self.redis_url:
            try:
                self.redis = redis.from_url(self.redis_url)
                await self.redis.ping()
                logger.info("Connected to Redis for alerts")
            except Exception as e:
                logger.warning("Redis connection failed", error=str(e))
                self.redis = None

        # Register default handlers
        self._register_default_handlers()

    async def close(self):
        """Close connections."""
        if self.redis:
            await self.redis.close()

    def _register_default_handlers(self):
        """Register default channel handlers."""
        self.channel_handlers[AlertChannel.REDIS_STREAM] = self._send_redis_stream
        self.channel_handlers[AlertChannel.REDIS_PUBSUB] = self._send_redis_pubsub
        self.channel_handlers[AlertChannel.WEBSOCKET] = self._send_websocket

    def register_handler(
        self,
        channel: AlertChannel,
        handler: Callable[[ClusterAlert], Any],
    ):
        """Register a custom channel handler."""
        self.channel_handlers[channel] = handler

    async def create_alert(
        self,
        cluster: Any,  # WalletCluster
        score: Any,    # ClusterScore
        alert_type: AlertType,
        additional_details: Optional[Dict[str, Any]] = None,
    ) -> Optional[ClusterAlert]:
        """
        Create and send an alert for a cluster.

        Args:
            cluster: WalletCluster object
            score: ClusterScore object
            alert_type: Type of alert
            additional_details: Extra details to include

        Returns:
            ClusterAlert if sent, None if filtered
        """
        # Determine severity from score
        risk_score = getattr(score, 'risk_score', 0.0)
        severity = self._determine_severity(risk_score)

        # Generate alert ID
        alert_id = self._generate_alert_id()

        # Build alert
        cluster_id = getattr(cluster, 'cluster_id', 'unknown')
        members = getattr(cluster, 'members', set())

        alert = ClusterAlert(
            alert_id=alert_id,
            alert_type=alert_type,
            severity=severity,
            cluster_id=cluster_id,
            cluster_size=len(members),
            risk_score=risk_score,
            title=self._generate_title(alert_type, severity, len(members)),
            message=self._generate_message(cluster, score, alert_type),
            details={
                **(additional_details or {}),
                "detection_method": getattr(cluster, 'detection_method', 'unknown'),
                "confidence": getattr(score, 'confidence', 0.0),
                "risk_level": getattr(score, 'risk_level', 'unknown'),
            },
            wallets=list(members)[:50],  # Limit size
            seed_wallets=[
                w for w in members
                if getattr(cluster, 'seed_node_count', 0) > 0
            ][:10],
            expires_at=time.time() + self.alert_ttl_seconds,
        )

        # Check deduplication
        if await self.deduplicator.is_duplicate(alert):
            self.metrics.alerts_deduplicated += 1
            logger.debug("Alert deduplicated", cluster_id=cluster_id)
            return None

        # Check rate limiting
        if not await self.rate_limiter.check_allowed(cluster_id):
            self.metrics.alerts_rate_limited += 1
            logger.debug("Alert rate limited", cluster_id=cluster_id)
            return None

        # Send alert
        await self._distribute_alert(alert)

        # Store alert
        self.alerts[alert_id] = alert
        self.alert_history.append(alert_id)

        # Trim history
        if len(self.alert_history) > 10000:
            old_ids = self.alert_history[:5000]
            self.alert_history = self.alert_history[5000:]
            for old_id in old_ids:
                self.alerts.pop(old_id, None)

        # Update metrics
        self._update_metrics(alert)

        return alert

    async def create_daisy_chain_alert(
        self,
        chain: Any,  # DaisyChain
        seed_nodes: Set[str],
    ) -> Optional[ClusterAlert]:
        """
        Create alert for a detected daisy chain.
        """
        chain_id = getattr(chain, 'chain_id', 'unknown')
        wallets = getattr(chain, 'wallets', [])
        length = len(wallets)

        # Determine severity based on chain properties
        starts_from_seed = getattr(chain, 'starts_from_seed', False)
        volume = getattr(chain, 'total_volume', 0)

        if starts_from_seed and length >= 5:
            severity = AlertSeverity.CRITICAL
            risk_score = 0.95
        elif starts_from_seed or length >= 7:
            severity = AlertSeverity.HIGH
            risk_score = 0.80
        elif length >= 5:
            severity = AlertSeverity.MEDIUM
            risk_score = 0.60
        else:
            severity = AlertSeverity.LOW
            risk_score = 0.40

        alert_id = self._generate_alert_id()

        alert = ClusterAlert(
            alert_id=alert_id,
            alert_type=AlertType.DAISY_CHAIN,
            severity=severity,
            cluster_id=chain_id,
            cluster_size=length,
            risk_score=risk_score,
            title=f"🔗 Daisy Chain Detected ({length} hops)",
            message=self._generate_chain_message(chain),
            details={
                "chain_length": length,
                "total_volume": volume,
                "starts_from_seed": starts_from_seed,
            },
            wallets=wallets[:50],
            seed_wallets=[w for w in wallets if w in seed_nodes],
            expires_at=time.time() + self.alert_ttl_seconds,
        )

        # Check filters
        if await self.deduplicator.is_duplicate(alert):
            return None
        if not await self.rate_limiter.check_allowed(chain_id):
            return None

        await self._distribute_alert(alert)
        self.alerts[alert_id] = alert
        self._update_metrics(alert)

        return alert

    async def create_funding_hub_alert(
        self,
        hub: Any,  # FundingHub
        seed_nodes: Set[str],
    ) -> Optional[ClusterAlert]:
        """
        Create alert for a detected funding hub.
        """
        hub_address = getattr(hub, 'hub_address', 'unknown')
        funded_count = getattr(hub, 'total_funded', 0)
        volume = getattr(hub, 'total_volume', 0)
        is_insider = getattr(hub, 'is_known_insider', False)

        # Determine severity
        if is_insider and funded_count >= 20:
            severity = AlertSeverity.CRITICAL
            risk_score = 0.95
        elif is_insider or funded_count >= 30:
            severity = AlertSeverity.HIGH
            risk_score = 0.80
        elif funded_count >= 15:
            severity = AlertSeverity.MEDIUM
            risk_score = 0.60
        else:
            severity = AlertSeverity.LOW
            risk_score = 0.40

        alert_id = self._generate_alert_id()

        alert = ClusterAlert(
            alert_id=alert_id,
            alert_type=AlertType.FUNDING_HUB,
            severity=severity,
            cluster_id=f"hub_{hub_address[:16]}",
            cluster_size=funded_count,
            risk_score=risk_score,
            title=f"💰 Funding Hub Detected ({funded_count} wallets)",
            message=self._generate_hub_message(hub),
            details={
                "hub_address": hub_address,
                "funded_count": funded_count,
                "total_volume": volume,
                "is_known_insider": is_insider,
            },
            wallets=list(getattr(hub, 'funded_wallets', set()))[:50],
            seed_wallets=[hub_address] if is_insider else [],
            expires_at=time.time() + self.alert_ttl_seconds,
        )

        # Check filters
        if await self.deduplicator.is_duplicate(alert):
            return None
        if not await self.rate_limiter.check_allowed(hub_address):
            return None

        await self._distribute_alert(alert)
        self.alerts[alert_id] = alert
        self._update_metrics(alert)

        return alert

    async def _distribute_alert(self, alert: ClusterAlert):
        """
        Distribute alert to all enabled channels.
        """
        start_time = time.time()

        for channel in self.enabled_channels:
            handler = self.channel_handlers.get(channel)
            if handler:
                try:
                    await handler(alert)
                    alert.channels_sent.append(channel.value)
                except Exception as e:
                    logger.error(
                        "Failed to send alert",
                        channel=channel.value,
                        error=str(e),
                    )

        # Update delivery time
        delivery_time = (time.time() - start_time) * 1000
        self.metrics.avg_delivery_time_ms = (
            (self.metrics.avg_delivery_time_ms * self.metrics.alerts_sent + delivery_time) /
            (self.metrics.alerts_sent + 1)
        )
        self.metrics.alerts_sent += 1

        logger.info(
            "Alert distributed",
            alert_id=alert.alert_id,
            severity=alert.severity.value,
            channels=len(alert.channels_sent),
            delivery_ms=round(delivery_time, 2),
        )

    async def _send_redis_stream(self, alert: ClusterAlert):
        """Send alert to Redis Stream."""
        if not self.redis:
            return

        await self.redis.xadd(
            self.ALERT_STREAM,
            {
                "alert_id": alert.alert_id,
                "severity": alert.severity.value,
                "data": alert.to_json(),
            },
            maxlen=10000,
        )

    async def _send_redis_pubsub(self, alert: ClusterAlert):
        """Send alert via Redis Pub/Sub."""
        if not self.redis:
            return

        await self.redis.publish(
            self.ALERT_CHANNEL,
            alert.to_json(),
        )

    async def _send_websocket(self, alert: ClusterAlert):
        """Send alert via WebSocket (placeholder)."""
        # Integration point for WebSocket server
        pass

    def _determine_severity(self, risk_score: float) -> AlertSeverity:
        """Determine severity from risk score."""
        if risk_score >= self.SEVERITY_THRESHOLDS[AlertSeverity.CRITICAL]:
            return AlertSeverity.CRITICAL
        elif risk_score >= self.SEVERITY_THRESHOLDS[AlertSeverity.HIGH]:
            return AlertSeverity.HIGH
        elif risk_score >= self.SEVERITY_THRESHOLDS[AlertSeverity.MEDIUM]:
            return AlertSeverity.MEDIUM
        elif risk_score >= self.SEVERITY_THRESHOLDS[AlertSeverity.LOW]:
            return AlertSeverity.LOW
        else:
            return AlertSeverity.INFO

    def _generate_alert_id(self) -> str:
        """Generate unique alert ID."""
        self._alert_counter += 1
        return f"alert_{self._alert_counter}_{int(time.time() * 1000)}"

    def _generate_title(self, alert_type: AlertType, severity: AlertSeverity, size: int) -> str:
        """Generate alert title."""
        emoji = {
            AlertSeverity.CRITICAL: "🚨",
            AlertSeverity.HIGH: "⚠️",
            AlertSeverity.MEDIUM: "📊",
            AlertSeverity.LOW: "ℹ️",
            AlertSeverity.INFO: "📝",
        }.get(severity, "📢")

        type_names = {
            AlertType.NEW_CLUSTER: "New Cluster",
            AlertType.CLUSTER_GROWTH: "Cluster Growth",
            AlertType.HIGH_RISK_CLUSTER: "High Risk Cluster",
            AlertType.SEED_CONNECTION: "Seed Connection",
            AlertType.DAISY_CHAIN: "Daisy Chain",
            AlertType.FUNDING_HUB: "Funding Hub",
            AlertType.SYBIL_NETWORK: "Sybil Network",
            AlertType.TEMPORAL_CORRELATION: "Temporal Correlation",
        }

        type_name = type_names.get(alert_type, "Cluster Alert")
        return f"{emoji} {type_name} Detected ({size} wallets)"

    def _generate_message(self, cluster: Any, score: Any, alert_type: AlertType) -> str:
        """Generate alert message."""
        risk_score = getattr(score, 'risk_score', 0.0)
        confidence = getattr(score, 'confidence', 0.0)
        size = len(getattr(cluster, 'members', set()))
        seed_count = getattr(cluster, 'seed_node_count', 0)

        lines = [
            f"Detected {alert_type.value.replace('_', ' ')} with {size} wallets.",
            f"Risk Score: {risk_score:.2%} (Confidence: {confidence:.2%})",
        ]

        if seed_count > 0:
            lines.append(f"⚠️ Contains {seed_count} known insider wallet(s)")

        # Add explanation from score
        explanations = getattr(score, 'explanation', [])
        if explanations:
            lines.append("")
            lines.extend(explanations[:3])

        return "\n".join(lines)
        return "\n".join(lines)

    def _generate_chain_message(self, chain: Any) -> str:
        """Generate message for daisy chain alert."""
        length = len(getattr(chain, 'wallets', []))
        volume = getattr(chain, 'total_volume', 0)
        starts_from_seed = getattr(chain, 'starts_from_seed', False)

        lines = [
            f"Detected sequential wallet chain with {length} hops.",
            f"Total Volume: {volume:.2f} SOL",
        ]

        if starts_from_seed:
            lines.append("⚠️ Chain originates from known insider wallet")

        return "\n".join(lines)

    def _generate_hub_message(self, hub: Any) -> str:
        """Generate message for funding hub alert."""
        funded_count = getattr(hub, 'total_funded', 0)
        volume = getattr(hub, 'total_volume', 0)
        is_insider = getattr(hub, 'is_known_insider', False)

        lines = [
            f"Detected centralized funding source with {funded_count} funded wallets.",
            f"Total Volume: {volume:.2f} SOL",
        ]

        if is_insider:
            lines.append("⚠️ Hub is a known insider wallet")

        return "\n".join(lines)

    def _update_metrics(self, alert: ClusterAlert):
        """Update alert metrics."""
        self.metrics.total_alerts += 1
        self.metrics.last_alert_at = time.time()

        if alert.severity == AlertSeverity.CRITICAL:
            self.metrics.critical_alerts += 1
        elif alert.severity == AlertSeverity.HIGH:
            self.metrics.high_alerts += 1
        elif alert.severity == AlertSeverity.MEDIUM:
            self.metrics.medium_alerts += 1
        else:
            self.metrics.low_alerts += 1

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """
        Acknowledge an alert.

        Returns:
            True if acknowledged, False if not found
        """
        if alert_id not in self.alerts:
            return False

        alert = self.alerts[alert_id]
        alert.acknowledged = True
        alert.acknowledged_by = acknowledged_by
        alert.acknowledged_at = time.time()

        self.metrics.alerts_acknowledged += 1

        logger.info(
            "Alert acknowledged",
            alert_id=alert_id,
            by=acknowledged_by,
        )

        return True

    def get_alert(self, alert_id: str) -> Optional[ClusterAlert]:
        """Get alert by ID."""
        return self.alerts.get(alert_id)

    def get_recent_alerts(
        self,
        limit: int = 100,
        severity: Optional[AlertSeverity] = None,
        acknowledged: Optional[bool] = None,
    ) -> List[ClusterAlert]:
        """
        Get recent alerts with optional filters.
        """
        alerts = []

        for alert_id in reversed(self.alert_history[-limit * 2:]):
            alert = self.alerts.get(alert_id)
            if not alert:
                continue

            if severity and alert.severity != severity:
                continue

            if acknowledged is not None and alert.acknowledged != acknowledged:
                continue

            alerts.append(alert)

            if len(alerts) >= limit:
                break

        return alerts

    def get_metrics(self) -> Dict[str, Any]:
        """Get alert metrics."""
        return {
            "total_alerts": self.metrics.total_alerts,
            "critical_alerts": self.metrics.critical_alerts,
            "high_alerts": self.metrics.high_alerts,
            "medium_alerts": self.metrics.medium_alerts,
            "low_alerts": self.metrics.low_alerts,
            "alerts_sent": self.metrics.alerts_sent,
            "alerts_deduplicated": self.metrics.alerts_deduplicated,
            "alerts_rate_limited": self.metrics.alerts_rate_limited,
            "alerts_acknowledged": self.metrics.alerts_acknowledged,
            "avg_delivery_time_ms": round(self.metrics.avg_delivery_time_ms, 2),
        }
