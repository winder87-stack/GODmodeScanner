
"""
Adaptive Rate Limiter - Self-Learning Rate Limit Management
===========================================================

A sophisticated rate limiting system that learns optimal request rates
through real-time feedback and predictive modeling.

Features:
- Token bucket with dynamic refill rates
- Exponential smoothing for rate prediction
- Per-endpoint rate tracking
- Burst detection and prevention
- Predictive throttling before hitting limits
"""

import asyncio
import time
import math
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class ThrottleState(Enum):
    """Current throttling state."""
    NORMAL = "normal"           # Operating normally
    CAUTIOUS = "cautious"       # Approaching limits
    THROTTLED = "throttled"     # Actively throttling
    RECOVERING = "recovering"   # Coming out of throttle
    EMERGENCY = "emergency"     # Emergency stop


@dataclass
class RateLimitWindow:
    """Sliding window for rate tracking."""
    window_size_seconds: float = 1.0
    timestamps: deque = field(default_factory=lambda: deque(maxlen=10000))

    def add_request(self):
        """Record a request."""
        self.timestamps.append(time.time())

    def get_rate(self) -> float:
        """Get current request rate (requests per second)."""
        now = time.time()
        cutoff = now - self.window_size_seconds

        # Remove old timestamps
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()

        return len(self.timestamps) / self.window_size_seconds

    def get_burst_rate(self, window_ms: float = 100) -> float:
        """Get burst rate over short window."""
        now = time.time()
        cutoff = now - (window_ms / 1000)

        count = sum(1 for ts in self.timestamps if ts >= cutoff)
        return count / (window_ms / 1000)


@dataclass
class TokenBucket:
    """
    Token bucket rate limiter with dynamic capacity.

    Allows bursts up to bucket capacity while maintaining
    average rate at the refill rate.
    """
    capacity: float = 10.0          # Maximum tokens
    tokens: float = 10.0            # Current tokens
    refill_rate: float = 5.0        # Tokens per second
    last_refill: float = field(default_factory=time.time)

    # Dynamic adjustment
    min_refill_rate: float = 1.0
    max_refill_rate: float = 50.0

    def refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now

    def consume(self, tokens: float = 1.0) -> bool:
        """Try to consume tokens. Returns True if successful."""
        self.refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def can_consume(self, tokens: float = 1.0) -> bool:
        """Check if tokens are available without consuming."""
        self.refill()
        return self.tokens >= tokens

    def time_until_available(self, tokens: float = 1.0) -> float:
        """Calculate time until tokens will be available."""
        self.refill()
        if self.tokens >= tokens:
            return 0.0
        needed = tokens - self.tokens
        return needed / self.refill_rate

    def adjust_rate(self, factor: float):
        """Adjust refill rate by factor."""
        self.refill_rate = max(
            self.min_refill_rate,
            min(self.max_refill_rate, self.refill_rate * factor)
        )

    def set_rate(self, rate: float):
        """Set refill rate directly."""
        self.refill_rate = max(
            self.min_refill_rate,
            min(self.max_refill_rate, rate)
        )


@dataclass
class ExponentialSmoother:
    """
    Exponential smoothing for rate prediction.

    Uses double exponential smoothing (Holt's method) to predict
    future rate limit behavior.
    """
    alpha: float = 0.3  # Level smoothing
    beta: float = 0.1   # Trend smoothing

    level: float = 0.0
    trend: float = 0.0
    initialized: bool = False

    def update(self, value: float) -> float:
        """Update with new observation and return smoothed value."""
        if not self.initialized:
            self.level = value
            self.trend = 0.0
            self.initialized = True
            return value

        prev_level = self.level
        self.level = self.alpha * value + (1 - self.alpha) * (self.level + self.trend)
        self.trend = self.beta * (self.level - prev_level) + (1 - self.beta) * self.trend

        return self.level

    def predict(self, steps: int = 1) -> float:
        """Predict value n steps ahead."""
        return self.level + steps * self.trend

    def reset(self):
        """Reset smoother."""
        self.level = 0.0
        self.trend = 0.0
        self.initialized = False


@dataclass
class EndpointRateLimiter:
    """Rate limiter for a single endpoint."""
    endpoint: str

    # Token bucket
    bucket: TokenBucket = field(default_factory=TokenBucket)

    # Rate tracking
    rate_window: RateLimitWindow = field(default_factory=RateLimitWindow)

    # Prediction
    rate_smoother: ExponentialSmoother = field(default_factory=ExponentialSmoother)

    # State
    state: ThrottleState = ThrottleState.NORMAL

    # Rate limit detection
    observed_limit: Optional[float] = None
    rate_limit_hits: int = 0
    last_rate_limit: float = 0.0

    # Backoff
    backoff_until: float = 0.0
    backoff_multiplier: float = 1.0

    # Statistics
    total_requests: int = 0
    throttled_requests: int = 0

    def record_request(self):
        """Record a request."""
        self.rate_window.add_request()
        self.total_requests += 1

        # Update rate prediction
        current_rate = self.rate_window.get_rate()
        self.rate_smoother.update(current_rate)

    def record_rate_limit(self):
        """Record a rate limit hit."""
        self.rate_limit_hits += 1
        self.last_rate_limit = time.time()

        # Estimate the rate limit
        current_rate = self.rate_window.get_rate()
        if self.observed_limit is None:
            self.observed_limit = current_rate * 0.8  # Conservative estimate
        else:
            # Exponential moving average
            self.observed_limit = 0.7 * self.observed_limit + 0.3 * current_rate * 0.8

        # Reduce bucket rate
        self.bucket.adjust_rate(0.5)  # 50% reduction

        # Calculate backoff
        self.backoff_multiplier = min(32, self.backoff_multiplier * 2)
        backoff_seconds = min(60, 1.0 * self.backoff_multiplier)
        self.backoff_until = time.time() + backoff_seconds

        self.state = ThrottleState.THROTTLED

        logger.warning(
            "Rate limit detected",
            endpoint=self.endpoint,
            observed_limit=self.observed_limit,
            backoff_seconds=backoff_seconds,
        )

    def record_success(self):
        """Record a successful request."""
        # Gradually increase rate on success
        if self.state == ThrottleState.THROTTLED:
            self.state = ThrottleState.RECOVERING
        elif self.state == ThrottleState.RECOVERING:
            # Slowly recover
            self.backoff_multiplier = max(1.0, self.backoff_multiplier * 0.9)
            if self.backoff_multiplier <= 1.1:
                self.state = ThrottleState.NORMAL
                self.bucket.adjust_rate(1.1)  # 10% increase

    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to make a request.

        Args:
            timeout: Maximum time to wait for permission

        Returns:
            True if permission granted, False if timed out
        """
        start_time = time.time()

        while True:
            # Check backoff
            if time.time() < self.backoff_until:
                wait_time = self.backoff_until - time.time()
                if timeout and (time.time() - start_time + wait_time) > timeout:
                    self.throttled_requests += 1
                    return False
                await asyncio.sleep(min(wait_time, 0.1))
                continue

            # Check predictive throttling
            predicted_rate = self.rate_smoother.predict(steps=2)
            if self.observed_limit and predicted_rate > self.observed_limit * 0.9:
                self.state = ThrottleState.CAUTIOUS
                # Brief pause to prevent hitting limit
                await asyncio.sleep(0.05)

            # Try to consume token
            if self.bucket.consume():
                self.record_request()
                return True

            # Wait for token
            wait_time = self.bucket.time_until_available()
            if timeout and (time.time() - start_time + wait_time) > timeout:
                self.throttled_requests += 1
                return False

            await asyncio.sleep(min(wait_time, 0.1))

    def get_effective_rate(self) -> float:
        """Get current effective rate limit."""
        if self.observed_limit:
            return min(self.bucket.refill_rate, self.observed_limit * 0.9)
        return self.bucket.refill_rate

    def get_statistics(self) -> Dict:
        """Get rate limiter statistics."""
        return {
            "endpoint": self.endpoint,
            "state": self.state.value,
            "current_rate": self.rate_window.get_rate(),
            "bucket_tokens": self.bucket.tokens,
            "bucket_rate": self.bucket.refill_rate,
            "observed_limit": self.observed_limit,
            "rate_limit_hits": self.rate_limit_hits,
            "total_requests": self.total_requests,
            "throttled_requests": self.throttled_requests,
            "backoff_multiplier": self.backoff_multiplier,
        }


class AdaptiveRateLimiter:
    """
    Global adaptive rate limiter managing multiple endpoints.

    Features:
    - Per-endpoint rate tracking and limiting
    - Global rate coordination
    - Predictive throttling
    - Automatic rate discovery
    - Burst prevention
    """

    def __init__(
        self,
        initial_rate: float = 5.0,
        max_rate: float = 50.0,
        global_limit: Optional[float] = None,
        burst_threshold: float = 2.0,
    ):
        """
        Initialize the adaptive rate limiter.

        Args:
            initial_rate: Initial requests per second per endpoint
            max_rate: Maximum requests per second per endpoint
            global_limit: Global rate limit across all endpoints
            burst_threshold: Multiplier for burst detection
        """
        self.initial_rate = initial_rate
        self.max_rate = max_rate
        self.global_limit = global_limit
        self.burst_threshold = burst_threshold

        # Per-endpoint limiters
        self.endpoint_limiters: Dict[str, EndpointRateLimiter] = {}

        # Global tracking
        self.global_window = RateLimitWindow()
        self.global_bucket = TokenBucket(
            capacity=global_limit or 100,
            refill_rate=global_limit or 100,
        ) if global_limit else None

        # State
        self._lock = asyncio.Lock()

        logger.info(
            "AdaptiveRateLimiter initialized",
            initial_rate=initial_rate,
            max_rate=max_rate,
            global_limit=global_limit,
        )

    def _get_or_create_limiter(self, endpoint: str) -> EndpointRateLimiter:
        """Get or create limiter for endpoint."""
        if endpoint not in self.endpoint_limiters:
            self.endpoint_limiters[endpoint] = EndpointRateLimiter(
                endpoint=endpoint,
                bucket=TokenBucket(
                    capacity=self.initial_rate * 2,
                    refill_rate=self.initial_rate,
                    max_refill_rate=self.max_rate,
                ),
            )
        return self.endpoint_limiters[endpoint]

    async def acquire(self, endpoint: str, timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to make a request to endpoint.

        Args:
            endpoint: Target endpoint URL
            timeout: Maximum time to wait

        Returns:
            True if permission granted
        """
        async with self._lock:
            limiter = self._get_or_create_limiter(endpoint)

        # Check global limit
        if self.global_bucket:
            if not self.global_bucket.consume():
                wait_time = self.global_bucket.time_until_available()
                if timeout and wait_time > timeout:
                    return False
                await asyncio.sleep(wait_time)
                if not self.global_bucket.consume():
                    return False

        # Check endpoint limit
        result = await limiter.acquire(timeout)

        if result:
            self.global_window.add_request()

        return result

    def record_rate_limit(self, endpoint: str):
        """Record a rate limit hit for endpoint."""
        limiter = self._get_or_create_limiter(endpoint)
        limiter.record_rate_limit()

    def record_success(self, endpoint: str):
        """Record a successful request for endpoint."""
        limiter = self._get_or_create_limiter(endpoint)
        limiter.record_success()

    def get_best_endpoint(self, endpoints: List[str]) -> Optional[str]:
        """
        Get the best endpoint to use based on current rate limits.

        Args:
            endpoints: List of available endpoints

        Returns:
            Best endpoint URL or None if all throttled
        """
        best_endpoint = None
        best_score = -1

        for endpoint in endpoints:
            limiter = self._get_or_create_limiter(endpoint)

            # Skip if in backoff
            if time.time() < limiter.backoff_until:
                continue

            # Score based on available tokens and state
            score = limiter.bucket.tokens
            if limiter.state == ThrottleState.NORMAL:
                score *= 2
            elif limiter.state == ThrottleState.CAUTIOUS:
                score *= 1.5
            elif limiter.state == ThrottleState.RECOVERING:
                score *= 1.2
            elif limiter.state == ThrottleState.THROTTLED:
                score *= 0.5

            if score > best_score:
                best_score = score
                best_endpoint = endpoint

        return best_endpoint

    def detect_burst(self, endpoint: str) -> bool:
        """
        Detect if endpoint is experiencing burst traffic.

        Args:
            endpoint: Endpoint to check

        Returns:
            True if burst detected
        """
        limiter = self._get_or_create_limiter(endpoint)

        current_rate = limiter.rate_window.get_rate()
        burst_rate = limiter.rate_window.get_burst_rate(window_ms=100)

        # Burst if short-term rate significantly exceeds average
        return burst_rate > current_rate * self.burst_threshold

    def get_statistics(self) -> Dict:
        """Get global statistics."""
        return {
            "global_rate": self.global_window.get_rate(),
            "endpoints": {
                endpoint: limiter.get_statistics()
                for endpoint, limiter in self.endpoint_limiters.items()
            },
        }

    def reset_endpoint(self, endpoint: str):
        """Reset rate limiter for endpoint."""
        if endpoint in self.endpoint_limiters:
            del self.endpoint_limiters[endpoint]

    def reset_all(self):
        """Reset all rate limiters."""
        self.endpoint_limiters.clear()
        self.global_window = RateLimitWindow()


class PredictiveThrottler:
    """
    Predictive throttling using rate limit patterns.

    Learns rate limit patterns over time and predicts
    when throttling will be needed.
    """

    def __init__(self, history_size: int = 1000):
        self.history_size = history_size

        # Rate limit event history
        self.rate_limit_events: deque = deque(maxlen=history_size)

        # Pattern detection
        self.hourly_patterns: Dict[int, List[float]] = {i: [] for i in range(24)}
        self.minute_patterns: Dict[int, List[float]] = {i: [] for i in range(60)}

        # Prediction model
        self.smoother = ExponentialSmoother(alpha=0.2, beta=0.05)

    def record_rate_limit(self, endpoint: str, rate: float):
        """Record a rate limit event."""
        now = time.time()
        event = {
            "timestamp": now,
            "endpoint": endpoint,
            "rate": rate,
        }
        self.rate_limit_events.append(event)

        # Update patterns
        import datetime
        dt = datetime.datetime.fromtimestamp(now)
        self.hourly_patterns[dt.hour].append(rate)
        self.minute_patterns[dt.minute].append(rate)

        # Keep patterns bounded
        for patterns in [self.hourly_patterns, self.minute_patterns]:
            for key in patterns:
                if len(patterns[key]) > 100:
                    patterns[key] = patterns[key][-100:]

    def predict_safe_rate(self, endpoint: str) -> float:
        """
        Predict safe request rate for current time.

        Args:
            endpoint: Target endpoint

        Returns:
            Predicted safe rate (requests per second)
        """
        import datetime
        now = datetime.datetime.now()

        # Get historical rates for current hour/minute
        hourly_rates = self.hourly_patterns.get(now.hour, [])
        minute_rates = self.minute_patterns.get(now.minute, [])

        rates = hourly_rates + minute_rates
        if not rates:
            return 10.0  # Default safe rate

        # Use minimum observed rate as safe baseline
        min_rate = min(rates)
        avg_rate = sum(rates) / len(rates)

        # Conservative estimate: 80% of minimum
        return min(min_rate * 0.8, avg_rate * 0.7)

    def should_throttle(self, current_rate: float, endpoint: str) -> Tuple[bool, float]:
        """
        Determine if throttling is needed.

        Args:
            current_rate: Current request rate
            endpoint: Target endpoint

        Returns:
            Tuple of (should_throttle, recommended_rate)
        """
        safe_rate = self.predict_safe_rate(endpoint)

        if current_rate > safe_rate:
            return True, safe_rate * 0.9

        return False, current_rate

    def get_statistics(self) -> Dict:
        """Get predictor statistics."""
        return {
            "total_events": len(self.rate_limit_events),
            "hourly_patterns": {
                h: len(rates) for h, rates in self.hourly_patterns.items() if rates
            },
            "minute_patterns": {
                m: len(rates) for m, rates in self.minute_patterns.items() if rates
            },
        }
