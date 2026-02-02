
"""
Health Monitor - Performance Tracking for Wallet De-anonymizer
==============================================================

Monitors the health and performance of the wallet cluster
de-anonymization system, providing real-time metrics and alerts.

Features:
- Component health tracking
- Performance metrics collection
- Anomaly detection
- SLA monitoring
- Automated health reports
"""

import asyncio
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import structlog

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

logger = structlog.get_logger(__name__)


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class ComponentType(Enum):
    """Types of monitored components."""
    GRAPH_BUILDER = "graph_builder"
    CLUSTER_DETECTOR = "cluster_detector"
    SCORING_ENGINE = "scoring_engine"
    ALERT_SYSTEM = "alert_system"
    REDIS = "redis"
    DATABASE = "database"


@dataclass
class ComponentHealth:
    """Health status for a component."""
    component: ComponentType
    status: HealthStatus = HealthStatus.UNKNOWN

    # Metrics
    latency_ms: float = 0.0
    error_rate: float = 0.0
    throughput: float = 0.0

    # Status details
    last_check: float = 0.0
    last_success: float = 0.0
    last_error: Optional[str] = None
    consecutive_failures: int = 0

    # SLA tracking
    uptime_percent: float = 100.0
    sla_violations: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "component": self.component.value,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "error_rate": round(self.error_rate, 4),
            "throughput": round(self.throughput, 2),
            "uptime_percent": round(self.uptime_percent, 2),
            "consecutive_failures": self.consecutive_failures,
            "last_error": self.last_error,
        }


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot."""
    timestamp: float = field(default_factory=time.time)

    # Detection metrics
    clusters_detected: int = 0
    daisy_chains_detected: int = 0
    funding_hubs_detected: int = 0

    # Timing metrics
    avg_detection_time_ms: float = 0.0
    avg_scoring_time_ms: float = 0.0
    avg_alert_time_ms: float = 0.0

    # Throughput
    transactions_processed: int = 0
    wallets_analyzed: int = 0
    alerts_generated: int = 0

    # Quality metrics
    detection_accuracy: float = 0.0
    false_positive_rate: float = 0.0

    # Resource usage
    cpu_percent: float = 0.0
    memory_mb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "detection": {
                "clusters": self.clusters_detected,
                "daisy_chains": self.daisy_chains_detected,
                "funding_hubs": self.funding_hubs_detected,
            },
            "timing": {
                "detection_ms": round(self.avg_detection_time_ms, 2),
                "scoring_ms": round(self.avg_scoring_time_ms, 2),
                "alert_ms": round(self.avg_alert_time_ms, 2),
            },
            "throughput": {
                "transactions": self.transactions_processed,
                "wallets": self.wallets_analyzed,
                "alerts": self.alerts_generated,
            },
            "quality": {
                "accuracy": round(self.detection_accuracy, 4),
                "false_positive_rate": round(self.false_positive_rate, 4),
            },
            "resources": {
                "cpu_percent": round(self.cpu_percent, 1),
                "memory_mb": round(self.memory_mb, 1),
            },
        }


@dataclass
class SLAConfig:
    """SLA configuration."""
    # Latency SLAs (milliseconds)
    max_detection_latency_ms: float = 1000.0  # 1 second
    max_scoring_latency_ms: float = 100.0     # 100ms
    max_alert_latency_ms: float = 50.0        # 50ms

    # Error rate SLAs
    max_error_rate: float = 0.01  # 1%

    # Uptime SLA
    min_uptime_percent: float = 99.9

    # Throughput SLAs
    min_throughput_tps: float = 100.0  # Transactions per second


class HealthMonitor:
    """
    Monitors health and performance of the wallet de-anonymizer.

    Features:
    - Real-time component health tracking
    - Performance metrics collection
    - SLA monitoring and violation alerts
    - Anomaly detection
    - Automated health reports
    """

    def __init__(
        self,
        sla_config: Optional[SLAConfig] = None,
        metrics_window_size: int = 1000,
        health_check_interval: float = 10.0,
    ):
        """
        Initialize the health monitor.

        Args:
            sla_config: SLA configuration
            metrics_window_size: Size of metrics history window
            health_check_interval: Interval between health checks (seconds)
        """
        self.sla_config = sla_config or SLAConfig()
        self.metrics_window_size = metrics_window_size
        self.health_check_interval = health_check_interval

        # Component health
        self.component_health: Dict[ComponentType, ComponentHealth] = {
            ct: ComponentHealth(component=ct) for ct in ComponentType
        }

        # Metrics history
        self.metrics_history: deque = deque(maxlen=metrics_window_size)
        self.latency_history: Dict[str, deque] = {
            "detection": deque(maxlen=1000),
            "scoring": deque(maxlen=1000),
            "alert": deque(maxlen=1000),
        }

        # Error tracking
        self.error_counts: Dict[str, int] = {}
        self.total_operations: int = 0

        # Health check callbacks
        self.health_checks: Dict[ComponentType, Callable] = {}

        # Monitoring state
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

        # Start time for uptime calculation
        self._start_time = time.time()
        self._downtime_seconds = 0.0

        logger.info(
            "HealthMonitor initialized",
            check_interval=health_check_interval,
            window_size=metrics_window_size,
        )

    async def start(self):
        """Start the health monitoring loop."""
        if self._running:
            return

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Health monitoring started")

    async def stop(self):
        """Stop the health monitoring loop."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitoring stopped")

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._run_health_checks()
                await self._collect_metrics()
                await self._check_sla_violations()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health check error", error=str(e))
                await asyncio.sleep(self.health_check_interval)

    def register_health_check(
        self,
        component: ComponentType,
        check_func: Callable[[], bool],
    ):
        """
        Register a health check function for a component.

        Args:
            component: Component type
            check_func: Async function returning True if healthy
        """
        self.health_checks[component] = check_func

    async def _run_health_checks(self):
        """Run all registered health checks."""
        for component, check_func in self.health_checks.items():
            health = self.component_health[component]
            health.last_check = time.time()

            try:
                start = time.time()

                if asyncio.iscoroutinefunction(check_func):
                    is_healthy = await check_func()
                else:
                    is_healthy = check_func()

                latency = (time.time() - start) * 1000
                health.latency_ms = latency

                if is_healthy:
                    health.last_success = time.time()
                    health.consecutive_failures = 0
                    health.status = HealthStatus.HEALTHY
                else:
                    health.consecutive_failures += 1
                    health.status = self._determine_status(health.consecutive_failures)

            except Exception as e:
                health.consecutive_failures += 1
                health.last_error = str(e)
                health.status = self._determine_status(health.consecutive_failures)
                logger.warning(
                    "Health check failed",
                    component=component.value,
                    error=str(e),
                )

    def _determine_status(self, consecutive_failures: int) -> HealthStatus:
        """Determine health status based on failure count."""
        if consecutive_failures == 0:
            return HealthStatus.HEALTHY
        elif consecutive_failures <= 2:
            return HealthStatus.DEGRADED
        elif consecutive_failures <= 5:
            return HealthStatus.UNHEALTHY
        else:
            return HealthStatus.CRITICAL

    async def _collect_metrics(self):
        """Collect current performance metrics."""
        metrics = PerformanceMetrics()

        # Calculate averages from history
        if self.latency_history["detection"]:
            metrics.avg_detection_time_ms = sum(self.latency_history["detection"]) / len(self.latency_history["detection"])
        if self.latency_history["scoring"]:
            metrics.avg_scoring_time_ms = sum(self.latency_history["scoring"]) / len(self.latency_history["scoring"])
        if self.latency_history["alert"]:
            metrics.avg_alert_time_ms = sum(self.latency_history["alert"]) / len(self.latency_history["alert"])

        # Resource usage
        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process()
                metrics.cpu_percent = process.cpu_percent()
                metrics.memory_mb = process.memory_info().rss / (1024 * 1024)
            except Exception:
                pass

        self.metrics_history.append(metrics)

    async def _check_sla_violations(self):
        """Check for SLA violations."""
        violations = []

        # Check latency SLAs
        if self.latency_history["detection"]:
            avg_detection = sum(self.latency_history["detection"]) / len(self.latency_history["detection"])
            if avg_detection > self.sla_config.max_detection_latency_ms:
                violations.append(f"Detection latency {avg_detection:.0f}ms > {self.sla_config.max_detection_latency_ms}ms")

        if self.latency_history["scoring"]:
            avg_scoring = sum(self.latency_history["scoring"]) / len(self.latency_history["scoring"])
            if avg_scoring > self.sla_config.max_scoring_latency_ms:
                violations.append(f"Scoring latency {avg_scoring:.0f}ms > {self.sla_config.max_scoring_latency_ms}ms")

        # Check error rate
        if self.total_operations > 0:
            error_rate = sum(self.error_counts.values()) / self.total_operations
            if error_rate > self.sla_config.max_error_rate:
                violations.append(f"Error rate {error_rate:.2%} > {self.sla_config.max_error_rate:.2%}")

        # Log violations
        for violation in violations:
            logger.warning("SLA violation", violation=violation)
            for health in self.component_health.values():
                health.sla_violations += 1

    def record_latency(self, operation: str, latency_ms: float):
        """
        Record a latency measurement.

        Args:
            operation: Operation type (detection, scoring, alert)
            latency_ms: Latency in milliseconds
        """
        if operation in self.latency_history:
            self.latency_history[operation].append(latency_ms)

    def record_operation(self, success: bool, error_type: Optional[str] = None):
        """
        Record an operation result.

        Args:
            success: Whether operation succeeded
            error_type: Type of error if failed
        """
        self.total_operations += 1
        if not success and error_type:
            self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

    def update_component_metrics(
        self,
        component: ComponentType,
        latency_ms: Optional[float] = None,
        throughput: Optional[float] = None,
        error: Optional[str] = None,
    ):
        """
        Update metrics for a specific component.

        Args:
            component: Component type
            latency_ms: Latest latency measurement
            throughput: Current throughput
            error: Error message if any
        """
        health = self.component_health[component]

        if latency_ms is not None:
            health.latency_ms = latency_ms

        if throughput is not None:
            health.throughput = throughput

        if error:
            health.last_error = error
            health.consecutive_failures += 1
            health.status = self._determine_status(health.consecutive_failures)
        else:
            health.last_success = time.time()
            health.consecutive_failures = 0
            health.status = HealthStatus.HEALTHY

    def get_overall_status(self) -> HealthStatus:
        """
        Get overall system health status.

        Returns:
            Worst status among all components
        """
        statuses = [h.status for h in self.component_health.values()]

        if HealthStatus.CRITICAL in statuses:
            return HealthStatus.CRITICAL
        elif HealthStatus.UNHEALTHY in statuses:
            return HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            return HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN

    def get_component_health(self, component: ComponentType) -> ComponentHealth:
        """Get health status for a specific component."""
        return self.component_health[component]

    def get_uptime(self) -> float:
        """Get system uptime percentage."""
        total_time = time.time() - self._start_time
        if total_time <= 0:
            return 100.0
        uptime = ((total_time - self._downtime_seconds) / total_time) * 100
        return max(0.0, min(100.0, uptime))

    def get_health_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive health report.

        Returns:
            Health report dictionary
        """
        # Calculate error rate
        error_rate = 0.0
        if self.total_operations > 0:
            error_rate = sum(self.error_counts.values()) / self.total_operations

        # Get latest metrics
        latest_metrics = self.metrics_history[-1].to_dict() if self.metrics_history else {}

        # Calculate percentiles
        detection_p95 = self._percentile(list(self.latency_history["detection"]), 95)
        scoring_p95 = self._percentile(list(self.latency_history["scoring"]), 95)
        alert_p95 = self._percentile(list(self.latency_history["alert"]), 95)

        return {
            "timestamp": time.time(),
            "overall_status": self.get_overall_status().value,
            "uptime_percent": round(self.get_uptime(), 2),
            "components": {
                ct.value: health.to_dict()
                for ct, health in self.component_health.items()
            },
            "latency_p95": {
                "detection_ms": round(detection_p95, 2) if detection_p95 else None,
                "scoring_ms": round(scoring_p95, 2) if scoring_p95 else None,
                "alert_ms": round(alert_p95, 2) if alert_p95 else None,
            },
            "error_rate": round(error_rate, 4),
            "total_operations": self.total_operations,
            "error_breakdown": dict(self.error_counts),
            "latest_metrics": latest_metrics,
            "sla_config": {
                "max_detection_latency_ms": self.sla_config.max_detection_latency_ms,
                "max_scoring_latency_ms": self.sla_config.max_scoring_latency_ms,
                "max_alert_latency_ms": self.sla_config.max_alert_latency_ms,
                "max_error_rate": self.sla_config.max_error_rate,
                "min_uptime_percent": self.sla_config.min_uptime_percent,
            },
        }

    def get_metrics_summary(self, window_minutes: int = 5) -> Dict[str, Any]:
        """
        Get metrics summary for a time window.

        Args:
            window_minutes: Time window in minutes

        Returns:
            Metrics summary dictionary
        """
        cutoff = time.time() - (window_minutes * 60)
        recent_metrics = [
            m for m in self.metrics_history
            if m.timestamp > cutoff
        ]

        if not recent_metrics:
            return {"window_minutes": window_minutes, "data_points": 0}

        return {
            "window_minutes": window_minutes,
            "data_points": len(recent_metrics),
            "avg_detection_time_ms": round(
                sum(m.avg_detection_time_ms for m in recent_metrics) / len(recent_metrics), 2
            ),
            "avg_scoring_time_ms": round(
                sum(m.avg_scoring_time_ms for m in recent_metrics) / len(recent_metrics), 2
            ),
            "total_clusters_detected": sum(m.clusters_detected for m in recent_metrics),
            "total_alerts_generated": sum(m.alerts_generated for m in recent_metrics),
        }

    def _percentile(self, data: List[float], percentile: float) -> Optional[float]:
        """Calculate percentile of data."""
        if not data:
            return None
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]

    def reset_metrics(self):
        """Reset all metrics."""
        self.metrics_history.clear()
        for key in self.latency_history:
            self.latency_history[key].clear()
        self.error_counts.clear()
        self.total_operations = 0
        logger.info("Metrics reset")
