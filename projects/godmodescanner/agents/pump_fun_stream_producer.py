"""
GODMODESCANNER - Pump.fun WebSocket Stream Producer
Connects to bloXroute Pump.fun streams and publishes to Redis Streams
"""

import asyncio
import json
import time
import random
import logging
import os
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from redis.asyncio import Redis

logger = logging.getLogger("godmode.pumpfun.producer")

# Configuration
BLOXROUTE_WS_URL = os.getenv("BLOXROUTE_WS_URL", "wss://pump-ny.solana.dex.blxrbdn.com/ws")
BLOXROUTE_AUTH_TOKEN = os.getenv("BLOXROUTE_AUTH_TOKEN", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Redis Streams
STREAM_NEW_TRANSACTIONS = "godmode:new_transactions"
STREAM_NEW_TOKENS = "godmode:new_tokens"
STREAM_HEARTBEAT = "godmode:heartbeat:pumpfun_stream"

# Stream settings
MAX_STREAM_LEN = 100000
HEARTBEAT_INTERVAL = 5
RECONNECT_MAX_DELAY = 60


class StreamType(Enum):
    NEW_TOKENS = "GetPumpFunNewTokensStream"
    SWAPS = "GetPumpFunSwapsStream"
    AMM_SWAPS = "GetPumpFunAMMSwapsStream"


@dataclass
class StreamStats:
    """Statistics tracking for the stream"""
    messages_received: int = 0
    new_tokens: int = 0
    swaps: int = 0
    amm_swaps: int = 0
    errors: int = 0
    reconnects: int = 0
    last_message_time: float = 0
    start_time: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'messages_received': self.messages_received,
            'new_tokens': self.new_tokens,
            'swaps': self.swaps,
            'amm_swaps': self.amm_swaps,
            'errors': self.errors,
            'reconnects': self.reconnects,
            'uptime': time.time() - self.start_time,
            'messages_per_second': self.messages_received / max(1, time.time() - self.start_time),
            'last_message_ago': time.time() - self.last_message_time if self.last_message_time else None
        }


class PumpFunStreamProducer:
    """
    Production-grade Pump.fun WebSocket stream producer.
    
    Features:
    - Multi-stream subscription (new tokens, swaps, AMM swaps)
    - Automatic reconnection with exponential backoff
    - Redis Streams publishing for parallel processing
    - Deduplication of transactions
    - Health monitoring and heartbeats
    """

    def __init__(
        self,
        ws_url: str = BLOXROUTE_WS_URL,
        auth_token: str = BLOXROUTE_AUTH_TOKEN,
        redis_url: str = REDIS_URL
    ):
        self.ws_url = ws_url
        self.auth_token = auth_token
        self.redis_url = redis_url
        
        # State
        self._redis: Optional[Redis] = None
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_attempt = 0
        
        # Deduplication (track recent transaction signatures)
        self._seen_txns: Set[str] = set()
        self._seen_txns_max = 10000
        
        # Stats
        self._stats = StreamStats()

    async def start(self) -> None:
        """Start the stream producer"""
        logger.info("🚀 Starting PumpFunStreamProducer...")
        
        # Connect to Redis
        self._redis = Redis.from_url(self.redis_url, decode_responses=False)
        await self._redis.ping()
        logger.info("✅ Redis connected")
        
        # Create consumer groups if needed
        await self._ensure_consumer_groups()
        
        self._running = True
        
        # Run main loops
        await asyncio.gather(
            self._stream_loop(),
            self._heartbeat_loop(),
            return_exceptions=True
        )

    async def stop(self) -> None:
        """Stop the stream producer"""
        logger.info("🛑 Stopping PumpFunStreamProducer...")
        self._running = False
        
        if self._websocket:
            await self._websocket.close()
        if self._redis:
            await self._redis.close()
        
        logger.info("✅ PumpFunStreamProducer stopped")

    async def _ensure_consumer_groups(self) -> None:
        """Create Redis consumer groups"""
        groups = [
            (STREAM_NEW_TRANSACTIONS, "wallet-analyzer-group"),
            (STREAM_NEW_TRANSACTIONS, "pattern-recognition-group"),
            (STREAM_NEW_TRANSACTIONS, "sybil-detection-group"),
            (STREAM_NEW_TOKENS, "token-tracker-group"),
        ]
        
        for stream, group in groups:
            try:
                await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
                logger.info(f"✅ Created consumer group: {group} on {stream}")
            except Exception as e:
                if "BUSYGROUP" in str(e):
                    logger.debug(f"Consumer group {group} already exists")
                else:
                    logger.error(f"Failed to create group {group}: {e}")

    async def _stream_loop(self) -> None:
        """Main WebSocket streaming loop with reconnection"""
        while self._running:
            try:
                await self._connect_and_stream()
            except Exception as e:
                logger.error(f"Stream error: {e}")
                self._stats.errors += 1
                
            if self._running:
                await self._reconnect_backoff()

    async def _connect_and_stream(self) -> None:
        """Connect to WebSocket and process messages"""
        headers = {}
        if self.auth_token:
            headers["Authorization"] = self.auth_token
        
        logger.info(f"🔌 Connecting to {self.ws_url}...")
        
        async with websockets.connect(
            self.ws_url,
            extra_headers=headers,
            ping_interval=20,
            ping_timeout=10,
            max_size=10 * 1024 * 1024  # 10MB max message
        ) as ws:
            self._websocket = ws
            self._reconnect_attempt = 0
            logger.info("✅ WebSocket connected")
            
            # Subscribe to all streams
            await self._subscribe_to_streams(ws)
            
            # Process messages
            async for message in ws:
                if not self._running:
                    break
                await self._process_message(message)

    async def _subscribe_to_streams(self, ws) -> None:
        """Subscribe to Pump.fun streams"""
        subscriptions = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "subscribe",
                "params": [StreamType.NEW_TOKENS.value, {}]
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "subscribe",
                "params": [StreamType.SWAPS.value, {}]
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "subscribe",
                "params": [StreamType.AMM_SWAPS.value, {}]
            }
        ]
        
        for sub in subscriptions:
            await ws.send(json.dumps(sub))
            logger.info(f"📡 Subscribed to {sub['params'][0]}")

    async def _process_message(self, raw_message: str) -> None:
        """Process incoming WebSocket message"""
        try:
            data = json.loads(raw_message)
            self._stats.messages_received += 1
            self._stats.last_message_time = time.time()
            
            # Handle subscription confirmations
            if "id" in data and "result" not in data.get("params", {}):
                logger.debug(f"Subscription confirmed: {data}")
                return
            
            # Extract result from params
            result = data.get("params", {}).get("result", {})
            if not result:
                return
            
            # Determine message type and process
            txn_hash = result.get("txnHash", "")
            
            # Deduplicate
            if txn_hash and txn_hash in self._seen_txns:
                return
            if txn_hash:
                self._seen_txns.add(txn_hash)
                # Prune seen set if too large
                if len(self._seen_txns) > self._seen_txns_max:
                    self._seen_txns = set(list(self._seen_txns)[-5000:])
            
            # Classify and publish
            if "name" in result and "symbol" in result:
                # New token launch
                await self._publish_new_token(result)
                self._stats.new_tokens += 1
            elif "isBuy" in result:
                # Swap transaction
                await self._publish_swap(result)
                self._stats.swaps += 1
            else:
                # AMM or other
                await self._publish_transaction(result)
                self._stats.amm_swaps += 1
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            self._stats.errors += 1
        except Exception as e:
            logger.error(f"Message processing error: {e}")
            self._stats.errors += 1

    async def _publish_new_token(self, data: Dict[str, Any]) -> None:
        """Publish new token launch to Redis Stream"""
        message = {
            b"type": b"new_token",
            b"txn_hash": data.get("txnHash", "").encode(),
            b"mint": data.get("mint", "").encode(),
            b"name": data.get("name", "").encode(),
            b"symbol": data.get("symbol", "").encode(),
            b"uri": data.get("uri", "").encode(),
            b"creator": data.get("creator", "").encode(),
            b"bonding_curve": data.get("bondingCurve", "").encode(),
            b"timestamp": data.get("timestamp", "").encode(),
            b"slot": str(data.get("slot", "")).encode(),
            b"received_at": str(time.time()).encode(),
        }
        
        # Publish to both streams
        await self._redis.xadd(STREAM_NEW_TOKENS, message, maxlen=MAX_STREAM_LEN)
        await self._redis.xadd(STREAM_NEW_TRANSACTIONS, message, maxlen=MAX_STREAM_LEN)
        
        logger.info(f"🆕 New Token: {data.get('symbol')} ({data.get('mint')[:8]}...)")

    async def _publish_swap(self, data: Dict[str, Any]) -> None:
        """Publish swap transaction to Redis Stream"""
        message = {
            b"type": b"swap",
            b"txn_hash": data.get("txnHash", "").encode(),
            b"mint": data.get("mintAddress", "").encode(),
            b"user": data.get("userAddress", "").encode(),
            b"user_token_account": data.get("userTokenAccountAddress", "").encode(),
            b"bonding_curve": data.get("bondingCurveAddress", "").encode(),
            b"token_vault": data.get("tokenVaultAddress", "").encode(),
            b"sol_amount": str(data.get("solAmount", 0)).encode(),
            b"token_amount": str(data.get("tokenAmount", 0)).encode(),
            b"is_buy": b"1" if data.get("isBuy") else b"0",
            b"virtual_sol_reserves": str(data.get("virtualSolReserves", 0)).encode(),
            b"virtual_token_reserves": str(data.get("virtualTokenReserves", 0)).encode(),
            b"creator": data.get("creator", "").encode(),
            b"timestamp": data.get("timestamp", "").encode(),
            b"slot": str(data.get("slot", "")).encode(),
            b"received_at": str(time.time()).encode(),
        }
        
        await self._redis.xadd(STREAM_NEW_TRANSACTIONS, message, maxlen=MAX_STREAM_LEN)
        
        action = "BUY" if data.get("isBuy") else "SELL"
        sol = int(data.get("solAmount", 0)) / 1e9
        logger.debug(f"💱 {action}: {sol:.4f} SOL - {data.get('mintAddress', '')[:8]}...")

    async def _publish_transaction(self, data: Dict[str, Any]) -> None:
        """Publish generic transaction to Redis Stream"""
        message = {
            b"type": b"transaction",
            b"txn_hash": data.get("txnHash", "").encode(),
            b"data": json.dumps(data).encode(),
            b"timestamp": data.get("timestamp", str(time.time())).encode(),
            b"received_at": str(time.time()).encode(),
        }
        
        await self._redis.xadd(STREAM_NEW_TRANSACTIONS, message, maxlen=MAX_STREAM_LEN)

    async def _reconnect_backoff(self) -> None:
        """Exponential backoff for reconnection"""
        self._reconnect_attempt += 1
        self._stats.reconnects += 1
        
        delay = min(
            RECONNECT_MAX_DELAY,
            (2 ** self._reconnect_attempt) + random.uniform(0, 1)
        )
        
        logger.warning(f"🔄 Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempt})...")
        await asyncio.sleep(delay)

    async def _heartbeat_loop(self) -> None:
        """Publish heartbeat and stats"""
        while self._running:
            try:
                stats = self._stats.to_dict()
                await self._redis.publish(
                    STREAM_HEARTBEAT,
                    json.dumps({
                        "agent": "pumpfun_stream_producer",
                        "status": "running",
                        "stats": stats,
                        "timestamp": time.time()
                    }).encode()
                )
                
                # Log periodic stats
                logger.info(
                    f"📊 Stats: {stats['messages_received']} msgs, "
                    f"{stats['new_tokens']} tokens, "
                    f"{stats['swaps']} swaps, "
                    f"{stats['messages_per_second']:.1f} msg/s"
                )
                
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return self._stats.to_dict()


# ==================== MAIN ENTRY POINT ====================

async def main():
    """Main entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    producer = PumpFunStreamProducer()
    
    try:
        await producer.start()
    except KeyboardInterrupt:
        pass
    finally:
        await producer.stop()


if __name__ == "__main__":
    asyncio.run(main())
