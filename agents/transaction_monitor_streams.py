#!/usr/bin/env python3
"""TRANSACTION_MONITOR Agent - Redis Streams-based transaction streaming.

This is the modified Transaction Monitor that uses Redis Streams (XADD)
instead of Pub/Sub (PUBLISH) for high-throughput, fault-tolerant messaging
with backpressure support.

Key Changes from Original:
- Uses XADD to publish to Redis Streams instead of PUBLISH
- Durable messaging (messages persist until consumed)
- Built-in backpressure via consumer groups
- Better fault tolerance (messages not lost on consumer failure)

Responsibilities:
- WebSocket monitoring of Solana for pump.fun transactions
- Real-time transaction parsing and event detection
- Token launch detection (<1 second latency)
- Event streaming via Redis Streams (XADD)
- Performance tracking and health monitoring

Target Performance:
- Detection latency: <500ms
- Throughput: 1000+ events/second (with parallel consumers)
- Connection uptime: 99.9%
"""

import asyncio
import json
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.ws_manager import WebSocketManager
from utils.pumpfun_parser import PumpFunParser, EventType
from utils.redis_streams_producer import (
    RedisStreamsProducer,
    STREAM_TRANSACTIONS,
    STREAM_TOKEN_LAUNCHES,
    STREAM_TRADES,
)

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger(__name__)


class TransactionMonitorStreams:
    """TRANSACTION_MONITOR Agent - Redis Streams-based transaction streaming.

    This agent is the first line of defense in GODMODESCANNER, responsible for:
    - Maintaining WebSocket connections to multiple Solana RPC endpoints
    - Streaming ALL pump.fun program transactions in real-time
    - Parsing and detecting token launch events instantly
    - Publishing events to Redis Streams using XADD for durable messaging
    - Tracking performance metrics and system health
    - Supporting backpressure through Redis Streams consumer groups
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize transaction monitor with Redis Streams support.

        Args:
            config: Optional configuration dict
        """
        self.config = config or {}

        # Load environment
        load_dotenv(project_root / ".env.template")

        # Get configuration from environment
        self.ws_endpoints = self._parse_endpoints(
            os.getenv("WS_ENDPOINTS", "wss://api.mainnet-beta.solana.com")
        )
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.pumpfun_program_id = os.getenv(
            "PUMPFUN_PROGRAM_ID",
            "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
        )

        # Initialize components
        self.ws_manager: Optional[WebSocketManager] = None
        self.parser = PumpFunParser()
        self.streams_producer: Optional[RedisStreamsProducer] = None

        # Performance tracking
        self.stats = {
            "agent": "TRANSACTION_MONITOR_STREAMS",
            "status": "INITIALIZING",
            "start_time": datetime.now().isoformat(),
            "total_transactions": 0,
            "total_token_launches": 0,
            "total_trades": 0,
            "total_errors": 0,
            "avg_detection_latency_ms": 0.0,
            "events_per_second": 0.0,
            "connections": 0,
            "redis_connected": False,
            "messages_published": 0,
        }

        # Shutdown flag
        self._shutdown = False

        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._stats_task: Optional[asyncio.Task] = None

        logger.info(
            "transaction_monitor_streams_init",
            ws_endpoints=len(self.ws_endpoints),
            redis_url=self.redis_url,
            program_id=self.pumpfun_program_id,
            streaming_mode="redis_streams",
        )

    def _parse_endpoints(self, endpoints_str: str) -> List[str]:
        """Parse comma-separated endpoints."""
        endpoints = [e.strip() for e in endpoints_str.split(",") if e.strip()]

        # Expand to 8 endpoints by repeating if needed
        while len(endpoints) < 8:
            endpoints.extend(endpoints[:min(8 - len(endpoints), len(endpoints))])

        return endpoints[:8]

    async def start(self):
        """Start the transaction monitor with Redis Streams."""
        logger.info("transaction_monitor_streams_starting")

        try:
            # Initialize Redis Streams producer
            self.streams_producer = RedisStreamsProducer(
                redis_url=self.redis_url,
                max_connections=50,
                stream_maxlen=100000,  # Keep last 100k messages per stream
                batch_size=100,
            )
            
            redis_connected = await self.streams_producer.connect()
            self.stats["redis_connected"] = redis_connected

            if redis_connected:
                logger.info("redis_streams_connected", mode="streams", url=self.redis_url)
            else:
                logger.error("redis_streams_connection_failed")
                return False

            # Initialize WebSocket manager
            self.ws_manager = WebSocketManager(
                endpoints=self.ws_endpoints,
                program_id=self.pumpfun_program_id,
            )

            # Start WebSocket connections
            await self.ws_manager.connect_all()
            self.stats["connections"] = len(self.ws_manager.active_connections)
            logger.info("websocket_connections", active=self.stats["connections"])

            # Start background tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._stats_task = asyncio.create_task(self._stats_loop())

            # Start consuming WebSocket messages
            await self._consume_websocket_messages()

        except Exception as e:
            logger.error("start_error", error=str(e))
            self.stats["status"] = "ERROR"
            return False

        return True

    async def _consume_websocket_messages(self):
        """Consume messages from WebSocket connections."""
        self.stats["status"] = "RUNNING"
        logger.info("consuming_websocket_messages")

        while not self._shutdown:
            try:
                # Get message from any WebSocket connection
                message = await self.ws_manager.get_message(timeout=1.0)
                
                if message is None:
                    continue
                
                # Parse the message
                result = await self._parse_transaction(message)
                
                if result:
                    self.stats["total_transactions"] += 1
            
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.stats["total_errors"] += 1
                logger.error("consume_message_error", error=str(e))
                await asyncio.sleep(0.1)

    async def _parse_transaction(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse a transaction message and publish to Redis Streams."""
        try:
            import time
            start_time = time.time()
            
            # Parse transaction with PumpFunParser
            event_type = self.parser.parse_event_type(message)
            
            if event_type == EventType.UNKNOWN:
                return None
            
            # Extract transaction data
            tx_data = self._extract_transaction_data(message, event_type)
            
            if not tx_data:
                return None
            
            # Publish to appropriate stream
            message_id = None
            
            if event_type == EventType.TOKEN_LAUNCH:
                message_id = await self.streams_producer.publish_token_launch(tx_data)
                self.stats["total_token_launches"] += 1
            elif event_type == EventType.TRADE:
                message_id = await self.streams_producer.publish_trade(tx_data)
                self.stats["total_trades"] += 1
            else:
                message_id = await self.streams_producer.publish_transaction(tx_data)
            
            if message_id:
                self.stats["messages_published"] += 1
                
                # Update latency stats
                latency_ms = (time.time() - start_time) * 1000
                n = self.stats["total_transactions"]
                self.stats["avg_detection_latency_ms"] = (
                    (self.stats["avg_detection_latency_ms"] * (n - 1) + latency_ms) / n
                )
            
            return tx_data
            
        except Exception as e:
            logger.error("parse_transaction_error", error=str(e))
            return None

    def _extract_transaction_data(self, message: Dict[str, Any], event_type: EventType) -> Optional[Dict[str, Any]]:
        """Extract relevant transaction data."""
        # This is a simplified extraction - in production, use full parser
        tx_data = {
            "signature": message.get("signature", ""),
            "slot": message.get("slot", 0),
            "timestamp": message.get("blockTime", int(time.time())),
            "type": event_type.value,
            "signer": self._extract_signer(message),
            "token": self._extract_token(message),
            "amount": self._extract_amount(message),
            "raw": message,
        }
        
        return tx_data

    def _extract_signer(self, message: Dict[str, Any]) -> str:
        """Extract signer address from message."""
        try:
            account_keys = message.get("transaction", {}).get("message", {}).get("accountKeys", [])
            if account_keys:
                return account_keys[0].get("pubkey", "")
        except:
            pass
        return ""

    def _extract_token(self, message: Dict[str, Any]) -> str:
        """Extract token mint from message."""
        try:
            # Try to extract from postTokenBalances or preTokenBalances
            post_balances = message.get("meta", {}).get("postTokenBalances", [])
            if post_balances:
                return post_balances[0].get("mint", "")
        except:
            pass
        return ""

    def _extract_amount(self, message: Dict[str, Any]) -> float:
        """Extract transaction amount."""
        try:
            # Simplified amount extraction
            return 0.0
        except:
            return 0.0

    async def _heartbeat_loop(self):
        """Send periodic heartbeat messages."""
        while not self._shutdown:
            try:
                heartbeat = {
                    "agent": "transaction_monitor",
                    "status": self.stats["status"],
                    "timestamp": datetime.now().isoformat(),
                }
                
                # In production, publish heartbeat to control stream
                logger.debug("heartbeat", data=heartbeat)
                
                await asyncio.sleep(10)
            
            except Exception as e:
                logger.error("heartbeat_error", error=str(e))
                await asyncio.sleep(10)

    async def _stats_loop(self):
        """Periodically log statistics."""
        while not self._shutdown:
            try:
                # Calculate events per second
                uptime = (datetime.now() - datetime.fromisoformat(self.stats["start_time"])).total_seconds()
                if uptime > 0:
                    self.stats["events_per_second"] = self.stats["total_transactions"] / uptime
                
                # Log stats
                logger.info(
                    "transaction_monitor_stats",
                    transactions=self.stats["total_transactions"],
                    token_launches=self.stats["total_token_launches"],
                    trades=self.stats["total_trades"],
                    published=self.stats["messages_published"],
                    errors=self.stats["total_errors"],
                    avg_latency_ms=self.stats["avg_detection_latency_ms"],
                    events_per_sec=self.stats["events_per_second"],
                    status=self.stats["status"],
                )
                
                await asyncio.sleep(30)
            
            except Exception as e:
                logger.error("stats_loop_error", error=str(e))
                await asyncio.sleep(30)

    async def stop(self):
        """Stop the transaction monitor gracefully."""
        logger.info("transaction_monitor_stopping")
        self._shutdown = True
        self.stats["status"] = "STOPPING"
        
        # Cancel background tasks
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._stats_task:
            self._stats_task.cancel()
        
        # Close WebSocket connections
        if self.ws_manager:
            await self.ws_manager.close_all()
        
        # Close Redis Streams producer
        if self.streams_producer:
            await self.streams_producer.close()
        
        self.stats["status"] = "STOPPED"
        logger.info("transaction_monitor_stopped")

    async def get_stats(self) -> Dict[str, Any]:
        """Get current statistics."""
        return self.stats.copy()


async def main():
    """Main entry point."""
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info("shutdown_signal_received", signal=signum)
        # Will be handled in the main loop
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create and start monitor
    monitor = TransactionMonitorStreams()
    
    try:
        success = await monitor.start()
        if not success:
            logger.error("transaction_monitor_start_failed")
            sys.exit(1)
        
        # Keep running until shutdown
        while True:
            await asyncio.sleep(1)
    
    except Exception as e:
        logger.error("main_error", error=str(e))
    finally:
        await monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())
