import os
import asyncio
import random
from typing import List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import httpx
from collections import deque
import structlog

log = structlog.get_logger()

# User-Agent rotation for spoofing
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edg/120.0.0.0",
    "SolanaTool/1.0.0",
]

@dataclass
class EndpointConfig:
    """Configuration for a single RPC endpoint."""
    url: str
    tier: str  # 'primary' or 'fallback'
    rps_limit: float = 10.0
    provider: str = 'default'

@dataclass
class CircuitBreakerState:
    """Circuit breaker state for an endpoint."""
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    is_open: bool = False
    cooldown_until: Optional[datetime] = None

@dataclass
class RequestStats:
    """Request statistics for an endpoint."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    last_success_time: Optional[datetime] = None
    last_failure_time: Optional[datetime] = None
    p50_latency: float = 0.0
    p95_latency: float = 0.0
    latencies: deque = field(default_factory=lambda: deque(maxlen=100))


class ParasiticStatefulClient:
    """
    High-performance RPC client with tiered endpoint selection, circuit breaker, and adaptive rate limiting.
    
    Features:
    - Tiered endpoint selection (primary authenticated -> fallback free)
    - Circuit breaker pattern with auto-recovery
    - User-Agent rotation for stealth
    - Adaptive rate limiting (5-40 RPS)
    - HTTP/2 support with connection pooling
    """
    
    def __init__(
        self,
        primary_endpoints: Optional[List[str]] = None,
        fallback_endpoints: Optional[List[str]] = None,
        rps_limits: Optional[str] = None,
        initial_rps: float = 5.0,
        max_rps: float = 40.0,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_cooldown: int = 60,
        pool_size: int = 500,
    ):
        self.primary_endpoints = primary_endpoints or []
        self.fallback_endpoints = fallback_endpoints or []
        self.initial_rps = initial_rps
        self.max_rps = max_rps
        self.current_rps = initial_rps
        self.pool_size = pool_size
        
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_cooldown = circuit_breaker_cooldown
        
        self.rps_limits_map = self._parse_rps_limits(rps_limits) if rps_limits else {}
        
        self.endpoint_configs: List[EndpointConfig] = []
        self.circuit_breakers: dict[str, CircuitBreakerState] = {}
        self.request_stats: dict[str, RequestStats] = {}
        
        if not self.primary_endpoints and not self.fallback_endpoints:
            self._load_endpoints_from_env()
        else:
            self._initialize_endpoints()
        
        self.client: Optional[httpx.AsyncClient] = None
        
        self.request_times: deque = deque()
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        
        log.info(
            "ParasiticStatefulClient initialized",
            primary_endpoints=len(self.primary_endpoints),
            fallback_endpoints=len(self.fallback_endpoints),
            initial_rps=self.initial_rps,
            max_rps=self.max_rps,
        )
    
    def _parse_rps_limits(self, rps_limits: str) -> dict:
        """Parse RPS limits string like 'helius-rpc:100,triton:50,default:10'."""
        limits = {}
        for item in rps_limits.split(','):
            if ':' in item:
                provider, limit = item.strip().split(':')
                limits[provider] = float(limit)
        return limits
    
    def _load_endpoints_from_env(self):
        """Load endpoints from environment variables."""
        primary_urls = os.getenv('RPC_ENDPOINTS', '').split(',')
        self.primary_endpoints = [url.strip() for url in primary_urls if url.strip()]
        
        fallback_urls = os.getenv('RPC_FALLBACK', '').split(',')
        self.fallback_endpoints = [url.strip() for url in fallback_urls if url.strip()]
        
        rps_limits = os.getenv('RPC_RPS_LIMITS', '')
        self.rps_limits_map = self._parse_rps_limits(rps_limits)
        
        self._initialize_endpoints()
    
    def _initialize_endpoints(self):
        """Initialize endpoint configurations."""
        for url in self.primary_endpoints:
            provider = self._extract_provider(url)
            rps_limit = self.rps_limits_map.get(provider, 100.0)
            
            config = EndpointConfig(url=url, tier='primary', rps_limit=rps_limit, provider=provider)
            self.endpoint_configs.append(config)
            self.circuit_breakers[url] = CircuitBreakerState()
            self.request_stats[url] = RequestStats()
        
        for url in self.fallback_endpoints:
            provider = self._extract_provider(url)
            rps_limit = self.rps_limits_map.get(provider, 10.0)
            
            config = EndpointConfig(url=url, tier='fallback', rps_limit=rps_limit, provider=provider)
            self.endpoint_configs.append(config)
            self.circuit_breakers[url] = CircuitBreakerState()
            self.request_stats[url] = RequestStats()
        
        log.info(
            "Endpoints initialized",
            primary=len([e for e in self.endpoint_configs if e.tier == 'primary']),
            fallback=len([e for e in self.endpoint_configs if e.tier == 'fallback']),
        )
    
    def _extract_provider(self, url: str) -> str:
        """Extract provider name from URL."""
        if 'helius' in url:
            return 'helius-rpc'
        elif 'triton' in url:
            return 'triton'
        elif 'quicknode' in url:
            return 'quicknode'
        else:
            return 'default'
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
    
    async def start(self):
        if self.client is None:
            limits = httpx.Limits(max_connections=self.pool_size, max_keepalive_connections=self.pool_size)
            timeout = httpx.Timeout(30.0, connect=10.0)
            self.client = httpx.AsyncClient(limits=limits, timeout=timeout, http2=True, verify=False)
            log.info("HTTP client started", pool_size=self.pool_size)
    
    async def stop(self):
        if self.client:
            await self.client.aclose()
            self.client = None
            log.info("HTTP client stopped")
    
    def _is_rate_limited(self) -> bool:
        now = asyncio.get_event_loop().time()
        while self.request_times and now - self.request_times[0] > 1.0:
            self.request_times.popleft()
        return len(self.request_times) >= self.current_rps
    
    def _get_random_user_agent(self) -> str:
        return random.choice(USER_AGENTS)
    
    def _select_endpoint(self) -> Optional[EndpointConfig]:
        now = datetime.now()
        primary_available = []
        fallback_available = []
        
        for config in self.endpoint_configs:
            cb_state = self.circuit_breakers.get(config.url)
            
            if cb_state.is_open:
                if cb_state.cooldown_until and now < cb_state.cooldown_until:
                    continue
                else:
                    cb_state.is_open = False
                    cb_state.failure_count = 0
                    cb_state.cooldown_until = None
                    log.info(f"Endpoint recovered: {config.url[:50]}...")
            
            if config.tier == 'primary':
                primary_available.append(config)
            else:
                fallback_available.append(config)
        
        if primary_available:
            available = sorted(primary_available, key=lambda c: self._calculate_success_rate(c.url), reverse=True)
            return available[0]
        elif fallback_available:
            available = sorted(fallback_available, key=lambda c: self._calculate_success_rate(c.url), reverse=True)
            return available[0]
        else:
            log.warning("No available endpoints!")
            return None
    
    def _calculate_success_rate(self, url: str) -> float:
        stats = self.request_stats.get(url)
        if not stats or stats.total_requests == 0:
            return 0.0
        return stats.successful_requests / stats.total_requests
    
    def _record_success(self, url: str, latency: float):
        stats = self.request_stats.get(url)
        if stats:
            stats.total_requests += 1
            stats.successful_requests += 1
            stats.last_success_time = datetime.now()
            stats.latencies.append(latency)
        
        self.consecutive_failures = 0
        self.consecutive_successes += 1
        
        if self.consecutive_successes >= 100 and self.current_rps < self.max_rps:
            self.current_rps = min(self.current_rps * 1.1, self.max_rps)
            log.info(f"Rate limit increased: {self.current_rps:.1f} RPS")
    
    def _record_failure(self, url: str, error_code: int):
        stats = self.request_stats.get(url)
        if stats:
            stats.total_requests += 1
            stats.failed_requests += 1
            stats.last_failure_time = datetime.now()
        
        cb_state = self.circuit_breakers.get(url)
        if cb_state:
            cb_state.failure_count += 1
            cb_state.last_failure_time = datetime.now()
            
            if cb_state.failure_count >= self.circuit_breaker_threshold:
                cb_state.is_open = True
                cb_state.cooldown_until = datetime.now() + timedelta(seconds=self.circuit_breaker_cooldown)
                log.warning(f"Circuit breaker tripped: {url[:50]}...", failure_count=cb_state.failure_count)
        
        self.consecutive_successes = 0
        self.consecutive_failures += 1
        
        if self.consecutive_failures >= 3:
            self.current_rps = max(self.current_rps * 0.5, self.initial_rps)
            log.warning(f"Rate limit decreased: {self.current_rps:.1f} RPS")
    
    async def request(self, method: str, params: list, retry_count: int = 3) -> dict:
        if self.client is None:
            await self.start()
        
        for attempt in range(retry_count + 1):
            if self._is_rate_limited():
                wait_time = 1.0 / self.current_rps
                await asyncio.sleep(wait_time)
            
            endpoint = self._select_endpoint()
            if not endpoint:
                await asyncio.sleep(1.0)
                continue
            
            headers = {
                "Content-Type": "application/json",
                "User-Agent": self._get_random_user_agent(),
            }
            
            payload = {
                "jsonrpc": "2.0",
                "id": random.randint(1, 999999),
                "method": method,
                "params": params,
            }
            
            start_time = asyncio.get_event_loop().time()
            
            try:
                response = await self.client.post(endpoint.url, json=payload, headers=headers, timeout=30.0)
                latency = (asyncio.get_event_loop().time() - start_time) * 1000
                
                if response.status_code == 429:
                    self._record_failure(endpoint.url, 429)
                    await asyncio.sleep(2 ** attempt)
                    continue
                elif response.status_code == 403:
                    self._record_failure(endpoint.url, 403)
                    await asyncio.sleep(2 ** attempt)
                    continue
                elif response.status_code >= 500:
                    self._record_failure(endpoint.url, response.status_code)
                    await asyncio.sleep(2 ** attempt)
                    continue
                
                response_json = response.json()
                
                if "error" in response_json:
                    error_code = response_json["error"].get("code", -1)
                    self._record_failure(endpoint.url, error_code)
                    await asyncio.sleep(1.0)
                    continue
                
                self._record_success(endpoint.url, latency)
                return response_json
                
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                self._record_failure(endpoint.url, -1)
                await asyncio.sleep(2 ** attempt)
                continue
            except Exception as e:
                self._record_failure(endpoint.url, -1)
                await asyncio.sleep(2 ** attempt)
                continue
        
        log.error(f"All retries failed for method: {method}", retry_count=retry_count)
        return {"error": {"code": -32603, "message": "All retries failed"}}
    
    def get_stats(self) -> dict:
        stats = {"current_rps": self.current_rps, "endpoints": []}
        
        for config in self.endpoint_configs:
            cb_state = self.circuit_breakers.get(config.url)
            req_stats = self.request_stats.get(config.url)
            
            endpoint_stat = {
                "url": config.url[:50] + "...",
                "tier": config.tier,
                "provider": config.provider,
                "rps_limit": config.rps_limit,
                "is_open": cb_state.is_open if cb_state else False,
                "failure_count": cb_state.failure_count if cb_state else 0,
                "total_requests": req_stats.total_requests if req_stats else 0,
                "successful_requests": req_stats.successful_requests if req_stats else 0,
                "success_rate": self._calculate_success_rate(config.url),
            }
            stats["endpoints"].append(endpoint_stat)
        
        return stats
