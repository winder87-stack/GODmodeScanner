import asyncio
import uvloop
import httpx
import orjson
import time
import collections
import base58
import structlog
from typing import Dict, List, Optional, Set
from solders.pubkey import Pubkey  # Use solders, not solana.keypair
from construct import Bytes, Int64ul, Int8ul, Struct, Adapter

# Import existing GODMODESCANNER infrastructure
from utils.rpc_manager import RPCManager  # Use existing RPC manager
from utils.redis_streams_producer import RedisStreamsProducer  # Existing producer
from utils.pumpfun_parser import PumpFunParser  # Existing parser
from agents.shared_memory.risk_score_segment import RiskScoreSegment  # Zero-latency pipeline

asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
logger = structlog.get_logger()

class AggressivePumpFunClient:
    def __init__(self):
        # Use EXISTING infrastructure instead of duplicating
        self.rpc_manager = RPCManager()  # Your existing RPC endpoint manager
        self.redis_producer = RedisStreamsProducer()  # Your existing Redis producer
        self.parser = PumpFunParser()  # Your existing pump.fun parser
        self.shared_mem = RiskScoreSegment()  # Your zero-latency alert pipeline
        
        # HTTP client with optimized settings
        self.client = httpx.AsyncClient(
            http2=True, 
            limits=httpx.Limits(max_connections=500, max_keepalive_connections=100),
            timeout=httpx.Timeout(10.0)
        )
        
        # Adaptive rate limiting (integrated with your existing system)
        self.current_rps = 15.0
        self.max_rps = 40.0
        self.min_rps = 5.0
        self.request_timestamps = collections.deque(maxlen=100)
        self.consecutive_successes = 0
        self.retry_count = 0
        self.max_retries = 5
        
        # Pump.fun constants
        self.PUMP_FUN_PROGRAM_ID = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
        
        # State tracking
        self.known_bonding_curves: Set[str] = set()
        self.processed_signatures: Set[str] = set()  # Deduplication
        
        logger.info("AggressivePumpFunClient initialized", 
                    rpc_endpoints=len(self.rpc_manager.endpoints))

    async def adaptive_throttle(self):
        """Self-regulating throttle integrated with GODMODESCANNER metrics."""
        if not self.request_timestamps:
            return
        time_since_last = time.time() - self.request_timestamps[-1]
        required_delay = 1.0 / self.current_rps
        if time_since_last < required_delay:
            await asyncio.sleep(required_delay - time_since_last)

    async def handle_response_feedback(self, status_code: int):
        """Adjusts RPS based on RPC response - logs to your monitoring system."""
        if status_code == 429:
            self.current_rps = max(self.min_rps, self.current_rps * 0.5)
            self.consecutive_successes = 0
            logger.warning("rate_limit_hit", 
                          new_rps=self.current_rps,
                          alert_type="THROTTLE")
        elif status_code == 200:
            self.consecutive_successes += 1
            if self.consecutive_successes >= 50:
                self.current_rps = min(self.max_rps, self.current_rps * 1.1)
                self.consecutive_successes = 0
                logger.info("rps_increased", 
                           new_rps=self.current_rps)

    async def make_rpc_request(self, method: str, params: list) -> Optional[Dict]:
        """Makes RPC call using your existing RPCManager with load balancing."""
        await self.adaptive_throttle()
        
        # Use your existing RPC manager's load-balanced endpoint selection
        url = await self.rpc_manager.get_healthy_endpoint()
        
        payload = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),  # Unique ID
            "method": method,
            "params": params
        }
        
        try:
            response = await self.client.post(url, json=payload)
            self.request_timestamps.append(time.time())
            await self.handle_response_feedback(response.status_code)
            response.raise_for_status()
            return orjson.loads(response.content)
        except httpx.HTTPStatusError as e:
            logger.error("rpc_http_error", 
                        status=e.response.status_code,
                        method=method,
                        url=url)
            if e.response.status_code == 429:
                await asyncio.sleep(2 ** self.retry_count)
                self.retry_count = min(self.retry_count + 1, self.max_retries)
                return await self.make_rpc_request(method, params)
            return None
        except Exception as e:
            logger.error("rpc_request_failed", 
                        error=str(e),
                        method=method,
                        retry_count=self.retry_count)
            await asyncio.sleep(2 ** self.retry_count)
            self.retry_count = min(self.retry_count + 1, self.max_retries)
            if self.retry_count <= self.max_retries:
                return await self.make_rpc_request(method, params)
            self.retry_count = 0
            return None

    async def get_program_accounts(self, program_id: Pubkey) -> Optional[Dict]:
        """Polls for program accounts with optimized data slice."""
        params = [
            str(program_id), 
            {
                "encoding": "base64",
                "dataSlice": {"offset": 0, "length": 200},  # Increased for metadata
                "filters": [
                    {"dataSize": 8200}  # Filter by bonding curve account size
                ]
            }
        ]
        return await self.make_rpc_request("getProgramAccounts", params)

    async def get_signatures_for_address(self, address: Pubkey, limit: int = 100) -> Optional[Dict]:
        """Gets recent signatures with commitment level."""
        params = [
            str(address),
            {
                "limit": limit,
                "commitment": "confirmed"  # Balance between speed and finality
            }
        ]
        return await self.make_rpc_request("getSignaturesForAddress", params)

    async def get_transaction(self, signature: str) -> Optional[Dict]:
        """Fetches full transaction with max commitment."""
        params = [
            signature,
            {
                "encoding": "json",
                "commitment": "confirmed",
                "maxSupportedTransactionVersion": 0  # Support versioned transactions
            }
        ]
        return await self.make_rpc_request("getTransaction", params)

    async def publish_to_redis_stream(self, stream_key: str, data: Dict):
        """Publishes to your existing Redis Streams infrastructure."""
        try:
            await self.redis_producer.publish(
                stream=stream_key,
                data=data
            )
            logger.debug("published_to_stream", 
                        stream=stream_key,
                        msg_id=data.get('signature'))
        except Exception as e:
            logger.error("redis_publish_failed", 
                        error=str(e),
                        stream=stream_key)
