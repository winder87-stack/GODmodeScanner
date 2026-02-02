# SENTINEL RPC THROTTLING ENGINE
# Intelligent, self-regulating RPC request engine with closed-loop feedback
# Dynamically adjusts request rate to avoid rate limits and bans

import asyncio
import collections
import time
import logging
import orjson

try:
    import uvloop
except ImportError:
    uvloop = None

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('SentinelRPCClient')


class SentinelRPCClient:
    """
    Intelligent, self-regulating RPC request engine that dynamically adjusts
    its request rate based on real-time feedback from the RPC provider.
    
    Uses a closed-loop feedback system to find the maximum sustainable speed
    without triggering rate limits or bans.
    
    Features:
    - Adaptive rate limiting based on 429 responses
    - Conservative growth after sustained success
    - Automatic recovery from rate limits
    - HTTP/2 support for multiplexing
    - uvloop for maximum performance
    
    Example:
        client = SentinelRPCClient(
            rpc_url="https://api.mainnet-beta.solana.com",
            initial_rps=5.0,
            max_rps=100.0
        )
        
        result = await client.request(
            "getAccountInfo",
            [wallet, {"encoding": "base64"}]
        )
    """
    
    def __init__(
        self,
        rpc_url: str = "https://api.mainnet-beta.solana.com",
        initial_rps: float = 5.0,
        min_rps: float = 1.0,
        max_rps: float = 100.0,
        growth_threshold: int = 50,
        throttle_factor: float = 0.5,
        growth_factor: float = 1.1
    ):
        """
        Initialize the Sentinel RPC Client.
        
        Args:
            rpc_url: The RPC endpoint URL
            initial_rps: Starting requests per second (conservative)
            min_rps: Absolute minimum speed
            max_rps: Optimistic upper bound
            growth_threshold: Consecutive successes before increasing speed
            throttle_factor: Speed multiplier when rate limited (0.5 = cut in half)
            growth_factor: Speed multiplier on successful growth (1.1 = 10% increase)
        """
        # Set uvloop for maximum performance
        if uvloop:
            asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        
        self.rpc_url = rpc_url
        
        # Rate limiting state variables (THE BRAIN)
        self.current_rps = initial_rps
        self.max_rps = max_rps
        self.min_rps = min_rps
        self.growth_threshold = growth_threshold
        self.throttle_factor = throttle_factor
        self.growth_factor = growth_factor
        
        # Request tracking
        self.request_timestamps = collections.deque(maxlen=100)
        self.last_429_time = 0
        self.consecutive_successes = 0
        self.total_requests = 0
        self.total_429s = 0
        
        # HTTP client with HTTP/2 support
        self.client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=100, max_connections=100)
        )
        
        logger.info(f"🛡️  SentinelRPCClient initialized")
        logger.info(f"   Starting RPS: {self.current_rps}")
        logger.info(f"   Range: [{self.min_rps}, {self.max_rps}]")
        logger.info(f"   Growth after: {self.growth_threshold} consecutive successes")
    
    async def request(self, method: str, params: list = None, request_id: int = None) -> dict:
        """
        Execute an RPC request with automatic rate limiting and adaptive speed control.
        
        Args:
            method: RPC method name (e.g., 'getAccountInfo')
            params: RPC parameters
            request_id: Optional request identifier
            
        Returns:
            Parsed JSON response dict
        """
        if params is None:
            params = []
        
        self.total_requests += 1
        
        # ===== PRE-REQUEST THROTTLE =====
        # Calculate required delay based on current RPS
        if self.request_timestamps:
            time_since_last = time.time() - self.request_timestamps[-1]
            required_delay = 1.0 / self.current_rps
            
            if time_since_last < required_delay:
                sleep_time = required_delay - time_since_last
                await asyncio.sleep(sleep_time)
        
        # ===== MAKE THE REQUEST =====
        start_time = time.time()
        
        payload = {
            "jsonrpc": "2.0",
            "id": request_id or self.total_requests,
            "method": method,
            "params": params
        }
        
        try:
            response = await self.client.post(
                self.rpc_url,
                content=orjson.dumps(payload),
                headers={"Content-Type": "application/json"}
            )
        except Exception as e:
            logger.error(f"Network error: {e}")
            raise
        
        end_time = time.time()
        self.request_timestamps.append(end_time)
        
        # ===== POST-REQUEST FEEDBACK (THE BRAIN) =====
        
        # RATE LIMIT HIT - AGGRESSIVE THROTTLING
        if response.status_code == 429:
            self.total_429s += 1
            old_rps = self.current_rps
            self.current_rps = max(self.min_rps, self.current_rps * self.throttle_factor)
            self.consecutive_successes = 0
            self.last_429_time = time.time()
            
            logger.warning(f"""🚨 ALERT: 429 HIT! 🚨
   Old RPS: {old_rps:.2f}
   New RPS: {self.current_rps:.2f} ({self.throttle_factor*100:.0f}% reduction)
   Total 429s: {self.total_429s}""")
        
        # SUCCESS - TRACK FOR ADAPTIVE GROWTH
        elif response.status_code == 200:
            self.consecutive_successes += 1
            
            # Only grow speed after sustained success
            if self.consecutive_successes >= self.growth_threshold:
                old_rps = self.current_rps
                self.current_rps = min(self.max_rps, self.current_rps * self.growth_factor)
                self.consecutive_successes = 0  # Reset counter
                
                logger.info(f"✅ SUCCESS: Increasing speed to {self.current_rps:.2f} RPS (was {old_rps:.2f})")
            
            # Log progress every 25 requests
            elif self.consecutive_successes % 25 == 0:
                logger.info(f"📈 Progress: {self.consecutive_successes}/{self.growth_threshold} successes @ {self.current_rps:.2f} RPS")
        
        # OTHER ERRORS
        else:
            logger.warning(f"⚠️  Status {response.status_code}: {response.text[:100]}")
            # Minor penalty for non-429 errors
            self.consecutive_successes = max(0, self.consecutive_successes - 5)
        
        # Parse and return response
        try:
            result = orjson.loads(response.content)
            return result
        except orjson.JSONDecodeError:
            logger.error(f"Failed to decode response: {response.content[:200]}")
            raise
    
    def get_stats(self) -> dict:
        """Get current performance statistics."""
        return {
            "current_rps": self.current_rps,
            "total_requests": self.total_requests,
            "total_429s": self.total_429s,
            "consecutive_successes": self.consecutive_successes,
            "success_rate": (self.total_requests - self.total_429s) / max(1, self.total_requests) * 100,
            "last_429_time": self.last_429_time
        }
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
        logger.info("SentinelRPCClient closed")
