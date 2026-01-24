#!/usr/bin/env python3
"""TRANSACTION_MONITOR Agent - Real-time pump.fun Transaction Streaming.

This is the CRITICAL first-line defense agent in GODMODESCANNER.

Responsibilities:
- WebSocket monitoring of Solana for pump.fun transactions
- Real-time transaction parsing and event detection
- Token launch detection (<1 second latency)
- Event broadcasting via Redis pub/sub
- Performance tracking and health monitoring

Target Performance:
- Detection latency: <500ms
- Throughput: 100+ events/second
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
from utils.redis_pubsub import RedisPubSubManager

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger(__name__)


class TransactionMonitor:
    """TRANSACTION_MONITOR Agent - Primary transaction streaming and detection.

    This agent is the first line of defense in GODMODESCANNER, responsible for:
    - Maintaining WebSocket connections to multiple Solana RPC endpoints
    - Streaming ALL pump.fun program transactions in real-time
    - Parsing and detecting token launch events instantly
    - Broadcasting events to other agents via Redis pub/sub
    - Tracking performance metrics and system health
    """

    # Redis pub/sub channels
    CHANNEL_TRANSACTIONS = "godmode:transactions"
    CHANNEL_TOKEN_LAUNCHES = "godmode:token_launches"
    CHANNEL_TRADES = "godmode:trades"
    CHANNEL_CONTROL = "godmode:control"
    CHANNEL_HEARTBEAT = "godmode:heartbeat:transaction_monitor"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize transaction monitor.

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
        self.redis: Optional[RedisPubSubManager] = None

        # Performance tracking
        self.stats = {
            "agent": "TRANSACTION_MONITOR",
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
        }

        # Shutdown flag
        self._shutdown = False

        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._stats_task: Optional[asyncio.Task] = None

        logger.info(
            "transaction_monitor_initialized",
            ws_endpoints=len(self.ws_endpoints),
            redis_url=self.redis_url,
            program_id=self.pumpfun_program_id,
        )

    def _parse_endpoints(self, endpoints_str: str) -> List[str]:
        """Parse comma-separated endpoints."""
        endpoints = [e.strip() for e in endpoints_str.split(",") if e.strip()]

        # Expand to 8 endpoints by repeating if needed
        while len(endpoints) < 8:
            endpoints.extend(endpoints[:min(8 - len(endpoints), len(endpoints))])

        return endpoints[:8]

    async def start(self):
        """Start the transaction monitor."""
        logger.info("transaction_monitor_starting")

        try:
            # Initialize Redis pub/sub
            self.redis = RedisPubSubManager(self.redis_url)
            redis_connected = await self.redis.connect()
            self.stats["redis_connected"] = redis_connected

            if redis_connected:
                logger.info("redis_connected", mode="redis")
                # Subscribe to control channel
                await self.redis.subscribe(
                    self.CHANNEL_CONTROL,
                    self._handle_control_message
                )
            else:
                logger.warning("redis_unavailable_using_fallback", mode="fallback")

            # Initialize WebSocket manager
            self.ws_manager = WebSocketManager(
                endpoints=self.ws_endpoints,
                reconnect_interval=1.0,
                max_reconnect_delay=60.0,
            )

            # Start WebSocket manager
            await self.ws_manager.start()

            # Subscribe to pump.fun token events
            await self.ws_manager.subscribe_pumpfun_tokens(
                callback=self._handle_transaction
            )

            # Update stats
            ws_metrics = self.ws_manager.get_metrics()
            self.stats["connections"] = ws_metrics["overall"]["connected_endpoints"]
            self.stats["status"] = "OPERATIONAL"

            # Start background tasks
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._stats_task = asyncio.create_task(self._stats_loop())

            logger.info(
                "transaction_monitor_started",
                status="OPERATIONAL",
                connections=self.stats["connections"],
                redis_connected=self.stats["redis_connected"],
            )

            # Publish startup status
            await self._publish_status()

        except Exception as e:
            logger.error("transaction_monitor_start_failed", error=str(e))
            self.stats["status"] = "ERROR"
            self.stats["total_errors"] += 1
            raise

    async def stop(self):
        """Stop the transaction monitor."""
        logger.info("transaction_monitor_stopping")
        self._shutdown = True

        # Cancel background tasks
        for task in [self._heartbeat_task, self._stats_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Stop WebSocket manager
        if self.ws_manager:
            await self.ws_manager.stop()

        # Disconnect Redis
        if self.redis:
            await self.redis.disconnect()

        self.stats["status"] = "STOPPED"
        logger.info("transaction_monitor_stopped")

    async def _handle_transaction(self, tx_data: Dict[str, Any]):
        """Handle incoming transaction from WebSocket.

        Args:
            tx_data: Transaction data from Solana WebSocket
        """
        try:
            start_time = datetime.now()

            # Parse transaction for events
            events = self.parser.parse_transaction(tx_data)

            # Calculate detection latency
            latency_ms = (datetime.now() - start_time).total_seconds() * 1000

            # Update stats
            self.stats["total_transactions"] += 1
            self.stats["avg_detection_latency_ms"] = (
                (self.stats["avg_detection_latency_ms"] * 0.9) + (latency_ms * 0.1)
            )

            # Process and broadcast events
            for event in events:
                await self._process_event(event)

            # Publish raw transaction to Redis
            if self.redis:
                await self.redis.publish(
                    self.CHANNEL_TRANSACTIONS,
                    {
                        "transaction": tx_data,
                        "detected_at": datetime.now().isoformat(),
                        "latency_ms": latency_ms,
                    }
                )

        except Exception as e:
            logger.error(
                "transaction_handling_error",
                error=str(e),
            )
            self.stats["total_errors"] += 1

    async def _process_event(self, event: Any):
        """Process and broadcast detected event.

        Args:
            event: Parsed event object
        """
        try:
            event_dict = event.to_dict()
            event_type = event_dict.get("event_type")

            # Route to appropriate channel
            if event_type == EventType.TOKEN_CREATE:
                self.stats["total_token_launches"] += 1

                logger.info(
                    "token_launch_detected",
                    token_mint=event_dict.get("token_mint"),
                    creator=event_dict.get("creator"),
                    symbol=event_dict.get("symbol"),
                    name=event_dict.get("name"),
                )

                if self.redis:
                    await self.redis.publish(
                        self.CHANNEL_TOKEN_LAUNCHES,
                        event_dict
                    )

            elif event_type in (EventType.BUY, EventType.SELL):
                self.stats["total_trades"] += 1

                logger.debug(
                    "trade_detected",
                    event_type=event_type,
                    token_mint=event_dict.get("token_mint"),
                    trader=event_dict.get("trader"),
                    sol_amount=event_dict.get("sol_amount"),
                )

                if self.redis:
                    await self.redis.publish(
                        self.CHANNEL_TRADES,
                        event_dict
                    )

        except Exception as e:
            logger.error(
                "event_processing_error",
                error=str(e),
            )
            self.stats["total_errors"] += 1

    async def _handle_control_message(self, channel: str, message: Dict[str, Any]):
        """Handle control messages from orchestrator.

        Args:
            channel: Channel name
            message: Control message
        """
        try:
            command = message.get("command")

            if command == "status":
                await self._publish_status()
            elif command == "stop":
                await self.stop()
            elif command == "restart":
                await self.stop()
                await self.start()

            logger.info(
                "control_message_received",
                command=command,
            )

        except Exception as e:
            logger.error(
                "control_message_error",
                error=str(e),
            )

    async def _heartbeat_loop(self):
        """Send periodic heartbeat signals."""
        try:
            while not self._shutdown:
                await asyncio.sleep(10)  # Every 10 seconds

                if self.redis:
                    await self.redis.publish(
                        self.CHANNEL_HEARTBEAT,
                        {
                            "agent": "TRANSACTION_MONITOR",
                            "timestamp": datetime.now().isoformat(),
                            "status": self.stats["status"],
                            "uptime_seconds": (
                                datetime.now() - 
                                datetime.fromisoformat(self.stats["start_time"])
                            ).total_seconds(),
                        }
                    )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("heartbeat_error", error=str(e))

    async def _stats_loop(self):
        """Calculate and log performance statistics."""
        try:
            last_tx_count = 0
            last_check = datetime.now()

            while not self._shutdown:
                await asyncio.sleep(5)  # Every 5 seconds

                # Calculate events per second
                now = datetime.now()
                elapsed = (now - last_check).total_seconds()
                tx_count = self.stats["total_transactions"]

                if elapsed > 0:
                    events_per_second = (tx_count - last_tx_count) / elapsed
                    self.stats["events_per_second"] = round(events_per_second, 2)

                last_tx_count = tx_count
                last_check = now

                # Update WebSocket connection stats
                if self.ws_manager:
                    ws_metrics = self.ws_manager.get_metrics()
                    self.stats["connections"] = ws_metrics["overall"]["connected_endpoints"]

                # Log stats
                logger.info(
                    "transaction_monitor_stats",
                    **self.stats
                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("stats_loop_error", error=str(e))

    async def _publish_status(self):
        """Publish current status to Redis."""
        if self.redis:
            await self.redis.publish(
                "godmode:status:transaction_monitor",
                self.stats
            )

    def get_status(self) -> Dict[str, Any]:
        """Get current status.

        Returns:
            Status dictionary
        """
        return self.stats.copy()


async def main():
    """Main entry point for transaction monitor."""
    monitor = TransactionMonitor()

    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("shutdown_signal_received", signal=sig)
        asyncio.create_task(monitor.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start monitor
        await monitor.start()

        # Print status
        status = monitor.get_status()
        print(json.dumps(status, indent=2))

        # Keep running until shutdown
        while not monitor._shutdown:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("keyboard_interrupt")
    except Exception as e:
        logger.error("main_error", error=str(e))
    finally:
        await monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())
