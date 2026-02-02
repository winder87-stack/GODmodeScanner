
"""
Endpoint Health Monitor - Real-time RPC Endpoint Health Tracking
================================================================

Comprehensive health monitoring system for Solana RPC endpoints
with automatic failover and recovery detection.

Features:
- Continuous health probing
- Latency percentile tracking
- Error rate monitoring
- Automatic endpoint ranking
- Recovery detection
- Health history for trend analysis
"""

import asyncio
import time
import statistics
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import structlog

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

try:
    import orjson
    json_dumps = lambda obj: orjson.dumps(obj).decode()
    json_loads = orjson.loads
except ImportError:
    import json
    json_dumps = json.dumps
    json_loads = json.loads

logger = structlog.get_logger(__name__)


class HealthStatus(Enum):
    """Endpoint health status levels."""
    EXCELLENT = "excellent"   # <50ms, >99% success
    GOOD = "good"             # <100ms, >95% success
    FAIR = "fair"             # <200ms, >90% success
    POOR = "poor"             # <500ms, >80% success
    CRITICAL = "critical"     # >500ms or <80% success
    DEAD = "dead"             # Not responding
    UNKNOWN = "unknown"       # Not yet probed


@dataclass
class HealthProbeResult:
    """Result of a health probe."""
    timestamp: float
    endpoint: str
    success: bool
    latency_ms: float
    status_code: Optional[int] = None
    error: Optional[str] = None
    response_data: Optional[Dict] = None


@dataclass
class EndpointHealthMetrics:
    """Comprehensive health metrics for an endpoint."""
    endpoint: str
    status: HealthStatus = HealthStatus.UNKNOWN

    # Probe history
    probe_history: deque = field(default_factory=lambda: deque(maxlen=1000))

    # Latency metrics
    latencies: deque = field(default_factory=lambda: deque(maxlen=100))
    avg_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0

    # Success metrics
    total_probes: int = 0
    successful_probes: int = 0
    failed_probes: int = 0
    success_rate: float = 0.0

    # Error tracking
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_error: Optional[str] = None
    last_error_time: float = 0.0

    # Rate limit tracking
    rate_limit_count: int = 0
    last_rate_limit_time: float = 0.0

    # Recovery tracking
    last_healthy_time: float = 0.0
    last_unhealthy_time: float = 0.0
    recovery_count: int = 0

    # Trend analysis
    latency_trend: float = 0.0  # Positive = getting slower
    success_trend: float = 0.0  # Positive = improving

    def record_probe(self, result: HealthProbeResult):
        """Record a probe result."""
        self.probe_history.append(result)
        self.total_probes += 1

        if result.success:
            self.successful_probes += 1
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            self.last_healthy_time = result.timestamp

            # Update latency metrics
            self.latencies.append(result.latency_ms)
            self._update_latency_metrics()

            # Check for recovery
            if self.status in [HealthStatus.CRITICAL, HealthStatus.DEAD]:
                self.recovery_count += 1
                logger.info(
                    "Endpoint recovered",
                    endpoint=self.endpoint,
                    recovery_count=self.recovery_count,
                )
        else:
            self.failed_probes += 1
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            self.last_error = result.error
            self.last_error_time = result.timestamp
            self.last_unhealthy_time = result.timestamp

            # Track rate limits
            if result.status_code == 429:
                self.rate_limit_count += 1
                self.last_rate_limit_time = result.timestamp

        # Update success rate
        self.success_rate = self.successful_probes / self.total_probes

        # Update status
        self._update_status()

        # Update trends
        self._update_trends()

    def _update_latency_metrics(self):
        """Update latency statistics."""
        if not self.latencies:
            return

        latency_list = list(self.latencies)
        self.avg_latency_ms = statistics.mean(latency_list)
        self.min_latency_ms = min(latency_list)
        self.max_latency_ms = max(latency_list)

        sorted_latencies = sorted(latency_list)
        n = len(sorted_latencies)
        self.p50_latency_ms = sorted_latencies[int(n * 0.50)]
        self.p95_latency_ms = sorted_latencies[min(int(n * 0.95), n - 1)]
        self.p99_latency_ms = sorted_latencies[min(int(n * 0.99), n - 1)]

    def _update_status(self):
        """Update health status based on metrics."""
        # Dead if too many consecutive failures
        if self.consecutive_failures >= 5:
            self.status = HealthStatus.DEAD
            return

        # Critical if recent failures or high latency
        if self.consecutive_failures >= 3 or self.success_rate < 0.80:
            self.status = HealthStatus.CRITICAL
            return

        # Determine status based on latency and success rate
        if self.avg_latency_ms < 50 and self.success_rate >= 0.99:
            self.status = HealthStatus.EXCELLENT
        elif self.avg_latency_ms < 100 and self.success_rate >= 0.95:
            self.status = HealthStatus.GOOD
        elif self.avg_latency_ms < 200 and self.success_rate >= 0.90:
            self.status = HealthStatus.FAIR
        elif self.avg_latency_ms < 500 and self.success_rate >= 0.80:
            self.status = HealthStatus.POOR
        else:
            self.status = HealthStatus.CRITICAL

    def _update_trends(self):
        """Update trend analysis."""
        if len(self.latencies) < 10:
            return

        # Compare recent vs older latencies
        latency_list = list(self.latencies)
        recent = latency_list[-10:]
        older = latency_list[-20:-10] if len(latency_list) >= 20 else latency_list[:10]

        recent_avg = statistics.mean(recent)
        older_avg = statistics.mean(older)

        # Positive trend = getting slower
        self.latency_trend = (recent_avg - older_avg) / max(older_avg, 1)

        # Success trend from probe history
        if len(self.probe_history) >= 20:
            recent_probes = list(self.probe_history)[-10:]
            older_probes = list(self.probe_history)[-20:-10]

            recent_success = sum(1 for p in recent_probes if p.success) / 10
            older_success = sum(1 for p in older_probes if p.success) / 10

            self.success_trend = recent_success - older_success

    def get_health_score(self) -> float:
        """
        Calculate overall health score (0-100).

        Returns:
            Health score from 0 (dead) to 100 (excellent)
        """
        if self.status == HealthStatus.DEAD:
            return 0.0
        if self.status == HealthStatus.UNKNOWN:
            return 50.0

        # Success rate component (40%)
        success_score = self.success_rate * 40

        # Latency component (30%)
        if self.avg_latency_ms <= 50:
            latency_score = 30
        elif self.avg_latency_ms <= 100:
            latency_score = 25
        elif self.avg_latency_ms <= 200:
            latency_score = 20
        elif self.avg_latency_ms <= 500:
            latency_score = 10
        else:
            latency_score = 0

        # Stability component (20%)
        stability_score = 20 if self.consecutive_failures == 0 else max(0, 20 - self.consecutive_failures * 5)

        # Trend component (10%)
        trend_score = 5
        if self.latency_trend < 0:  # Getting faster
            trend_score += 5
        elif self.latency_trend > 0.2:  # Getting slower
            trend_score -= 5

        return success_score + latency_score + stability_score + trend_score

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "endpoint": self.endpoint,
            "status": self.status.value,
            "health_score": round(self.get_health_score(), 1),
            "latency": {
                "avg_ms": round(self.avg_latency_ms, 2),
                "p50_ms": round(self.p50_latency_ms, 2),
                "p95_ms": round(self.p95_latency_ms, 2),
                "p99_ms": round(self.p99_latency_ms, 2),
                "min_ms": round(self.min_latency_ms, 2) if self.min_latency_ms != float('inf') else 0,
                "max_ms": round(self.max_latency_ms, 2),
            },
            "success": {
                "rate": round(self.success_rate * 100, 1),
                "total_probes": self.total_probes,
                "successful": self.successful_probes,
                "failed": self.failed_probes,
            },
            "errors": {
                "consecutive_failures": self.consecutive_failures,
                "rate_limit_count": self.rate_limit_count,
                "last_error": self.last_error,
            },
            "trends": {
                "latency_trend": round(self.latency_trend * 100, 1),
                "success_trend": round(self.success_trend * 100, 1),
            },
            "recovery_count": self.recovery_count,
        }


class EndpointHealthMonitor:
    """
    Real-time health monitoring for multiple RPC endpoints.

    Features:
    - Continuous background health probing
    - Automatic endpoint ranking
    - Failover recommendations
    - Health history and trends
    - Alert generation for degradation
    """

    # Health probe RPC method
    HEALTH_CHECK_METHOD = "getHealth"
    SLOT_CHECK_METHOD = "getSlot"

    def __init__(
        self,
        endpoints: List[str],
        probe_interval_seconds: float = 10.0,
        probe_timeout_seconds: float = 5.0,
        enable_continuous_monitoring: bool = True,
    ):
        """
        Initialize the health monitor.

        Args:
            endpoints: List of RPC endpoint URLs
            probe_interval_seconds: Time between health probes
            probe_timeout_seconds: Timeout for each probe
            enable_continuous_monitoring: Start background monitoring
        """
        self.endpoints = endpoints
        self.probe_interval = probe_interval_seconds
        self.probe_timeout = probe_timeout_seconds
        self.enable_continuous = enable_continuous_monitoring

        # Health metrics per endpoint
        self.metrics: Dict[str, EndpointHealthMetrics] = {
            url: EndpointHealthMetrics(endpoint=url)
            for url in endpoints
        }

        # HTTP client
        self.client: Optional[httpx.AsyncClient] = None

        # State
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._callbacks: List[callable] = []

        logger.info(
            "EndpointHealthMonitor initialized",
            endpoints=len(endpoints),
            probe_interval=probe_interval_seconds,
        )

    async def start(self):
        """Start the health monitor."""
        if self._running:
            return

        # Initialize HTTP client
        if HTTPX_AVAILABLE:
            self.client = httpx.AsyncClient(
                http2=True,
                timeout=httpx.Timeout(self.probe_timeout),
            )
        else:
            import aiohttp
            self.client = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.probe_timeout)
            )

        self._running = True

        # Initial probe
        await self.probe_all()

        # Start continuous monitoring
        if self.enable_continuous:
            self._monitor_task = asyncio.create_task(self._monitor_loop())

        logger.info("EndpointHealthMonitor started")

    async def stop(self):
        """Stop the health monitor."""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self.client:
            await self.client.aclose()

        logger.info("EndpointHealthMonitor stopped")

    async def _monitor_loop(self):
        """Background monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.probe_interval)
                await self.probe_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Monitor loop error", error=str(e))

    async def probe_endpoint(self, endpoint: str) -> HealthProbeResult:
        """
        Probe a single endpoint.

        Args:
            endpoint: RPC endpoint URL

        Returns:
            HealthProbeResult with probe outcome
        """
        start_time = time.perf_counter()
        timestamp = time.time()

        payload = {
            "jsonrpc": "2.0",
            "id": "health",
            "method": self.SLOT_CHECK_METHOD,  # getSlot is more reliable than getHealth
            "params": [],
        }

        try:
            if HTTPX_AVAILABLE:
                response = await self.client.post(
                    endpoint,
                    content=json_dumps(payload),
                    headers={"Content-Type": "application/json"},
                )
                status_code = response.status_code
                response_text = response.text
            else:
                async with self.client.post(
                    endpoint,
                    data=json_dumps(payload),
                    headers={"Content-Type": "application/json"},
                ) as response:
                    status_code = response.status
                    response_text = await response.text()

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Check for rate limiting
            if status_code == 429:
                return HealthProbeResult(
                    timestamp=timestamp,
                    endpoint=endpoint,
                    success=False,
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error="Rate limited",
                )

            # Check for other errors
            if status_code >= 400:
                return HealthProbeResult(
                    timestamp=timestamp,
                    endpoint=endpoint,
                    success=False,
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error=f"HTTP {status_code}",
                )

            # Parse response
            result = json_loads(response_text)

            if "error" in result:
                return HealthProbeResult(
                    timestamp=timestamp,
                    endpoint=endpoint,
                    success=False,
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error=str(result["error"]),
                    response_data=result,
                )

            return HealthProbeResult(
                timestamp=timestamp,
                endpoint=endpoint,
                success=True,
                latency_ms=latency_ms,
                status_code=status_code,
                response_data=result,
            )

        except asyncio.TimeoutError:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return HealthProbeResult(
                timestamp=timestamp,
                endpoint=endpoint,
                success=False,
                latency_ms=latency_ms,
                error="Timeout",
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return HealthProbeResult(
                timestamp=timestamp,
                endpoint=endpoint,
                success=False,
                latency_ms=latency_ms,
                error=str(e),
            )

    async def probe_all(self) -> Dict[str, HealthProbeResult]:
        """
        Probe all endpoints concurrently.

        Returns:
            Dictionary of endpoint -> probe result
        """
        tasks = [
            self.probe_endpoint(endpoint)
            for endpoint in self.endpoints
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        probe_results = {}
        for endpoint, result in zip(self.endpoints, results):
            if isinstance(result, Exception):
                result = HealthProbeResult(
                    timestamp=time.time(),
                    endpoint=endpoint,
                    success=False,
                    latency_ms=0,
                    error=str(result),
                )

            probe_results[endpoint] = result
            self.metrics[endpoint].record_probe(result)

            # Trigger callbacks for status changes
            await self._check_alerts(endpoint)

        return probe_results

    async def _check_alerts(self, endpoint: str):
        """Check for alert conditions."""
        metrics = self.metrics[endpoint]

        # Alert on status degradation
        if metrics.status in [HealthStatus.CRITICAL, HealthStatus.DEAD]:
            for callback in self._callbacks:
                try:
                    await callback("degradation", endpoint, metrics)
                except Exception as e:
                    logger.error("Callback error", error=str(e))

        # Alert on recovery
        if metrics.recovery_count > 0 and metrics.consecutive_successes == 1:
            for callback in self._callbacks:
                try:
                    await callback("recovery", endpoint, metrics)
                except Exception as e:
                    logger.error("Callback error", error=str(e))

    def register_callback(self, callback: callable):
        """Register a callback for health events."""
        self._callbacks.append(callback)

    def get_best_endpoint(self) -> Optional[str]:
        """
        Get the healthiest endpoint.

        Returns:
            URL of the healthiest endpoint or None
        """
        available = [
            (url, metrics) for url, metrics in self.metrics.items()
            if metrics.status not in [HealthStatus.DEAD, HealthStatus.CRITICAL]
        ]

        if not available:
            # Return least bad endpoint
            return min(
                self.metrics.items(),
                key=lambda x: x[1].consecutive_failures
            )[0]

        # Sort by health score
        return max(available, key=lambda x: x[1].get_health_score())[0]

    def get_ranked_endpoints(self) -> List[Tuple[str, float]]:
        """
        Get endpoints ranked by health score.

        Returns:
            List of (endpoint, health_score) tuples, sorted descending
        """
        ranked = [
            (url, metrics.get_health_score())
            for url, metrics in self.metrics.items()
        ]
        return sorted(ranked, key=lambda x: x[1], reverse=True)

    def get_healthy_endpoints(self) -> List[str]:
        """
        Get list of healthy endpoints.

        Returns:
            List of endpoint URLs with good health
        """
        return [
            url for url, metrics in self.metrics.items()
            if metrics.status in [HealthStatus.EXCELLENT, HealthStatus.GOOD, HealthStatus.FAIR]
        ]

    def get_endpoint_metrics(self, endpoint: str) -> Optional[EndpointHealthMetrics]:
        """Get metrics for a specific endpoint."""
        return self.metrics.get(endpoint)

    def get_all_metrics(self) -> Dict[str, Dict]:
        """Get metrics for all endpoints."""
        return {
            url: metrics.to_dict()
            for url, metrics in self.metrics.items()
        }

    def get_summary(self) -> Dict:
        """Get summary of all endpoint health."""
        statuses = {status: 0 for status in HealthStatus}
        for metrics in self.metrics.values():
            statuses[metrics.status] += 1

        healthy_count = sum(
            1 for m in self.metrics.values()
            if m.status in [HealthStatus.EXCELLENT, HealthStatus.GOOD]
        )

        avg_latency = statistics.mean(
            m.avg_latency_ms for m in self.metrics.values()
            if m.avg_latency_ms > 0
        ) if any(m.avg_latency_ms > 0 for m in self.metrics.values()) else 0

        return {
            "total_endpoints": len(self.endpoints),
            "healthy_endpoints": healthy_count,
            "status_distribution": {s.value: c for s, c in statuses.items() if c > 0},
            "avg_latency_ms": round(avg_latency, 2),
            "best_endpoint": self.get_best_endpoint(),
            "ranked_endpoints": self.get_ranked_endpoints()[:5],
        }

    def add_endpoint(self, endpoint: str):
        """Add a new endpoint to monitor."""
        if endpoint not in self.endpoints:
            self.endpoints.append(endpoint)
            self.metrics[endpoint] = EndpointHealthMetrics(endpoint=endpoint)
            logger.info("Added endpoint", endpoint=endpoint)

    def remove_endpoint(self, endpoint: str):
        """Remove an endpoint from monitoring."""
        if endpoint in self.endpoints:
            self.endpoints.remove(endpoint)
            del self.metrics[endpoint]
            logger.info("Removed endpoint", endpoint=endpoint)
