#!/usr/bin/env python3
"""Autonomous Sybil Detection Agent for GODMODESCANNER.

Subscribes to wallet profiles, coordinated trades, and transactions.
Runs advanced graph-based sybil detection every 30 seconds.
Publishes detected clusters, scores, and funding networks.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import logging

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from wallet_profiler.profilers.sybil_detector import SybilDetector

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logging.warning("Redis not available, using in-memory mode")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - SYBIL_DETECTION - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SybilDetectionAgent:
    """Autonomous agent for detecting sybil wallet clusters."""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        """Initialize sybil detection agent.

        Args:
            redis_url: Redis connection URL
        """
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.pubsub = None
        self.redis_connected = False

        # Initialize detector
        self.detector = SybilDetector()

        # In-memory storage (fallback when Redis unavailable)
        self.wallet_profiles_buffer: Dict[str, Dict[str, Any]] = {}
        self.coordinated_trades_buffer: List[Dict[str, Any]] = []
        self.transactions_buffer: List[Dict[str, Any]] = []

        # Agent state
        self.running = False
        self.last_analysis_time = None
        self.analysis_interval = 30  # seconds

        # Metrics
        self.metrics = {
            'agent': 'SYBIL_DETECTION',
            'status': 'INITIALIZING',
            'clusters_detected': 0,
            'total_wallets_analyzed': 0,
            'graph_nodes': 0,
            'graph_edges': 0,
            'avg_cluster_size': 0.0,
            'highest_sybil_score': 0.0,
            'detection_methods_active': 6,
            'redis_connected': False,
            'analysis_cycles': 0,
            'subscribed_channels': [],
            'messages_processed': 0,
            'last_heartbeat': None
        }

        # Subscribe channels
        self.subscribe_channels = [
            'godmode:wallet_profiles',
            'godmode:coordinated_trades',
            'godmode:transactions',
            'godmode:control'
        ]

        # Publish channels
        self.publish_channels = {
            'clusters': 'godmode:sybil_clusters',
            'scores': 'godmode:sybil_scores',
            'funding': 'godmode:funding_networks',
            'heartbeat': 'godmode:heartbeat:sybil_detection'
        }

    async def connect_redis(self) -> bool:
        """Establish Redis connection.

        Returns:
            True if connected, False otherwise
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis library not available, using in-memory mode")
            return False

        try:
            self.redis_client = redis.from_url(
                self.redis_url,
                encoding='utf-8',
                decode_responses=True
            )

            # Test connection
            await self.redis_client.ping()

            # Create pub/sub
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe(*self.subscribe_channels)

            self.redis_connected = True
            self.metrics['redis_connected'] = True
            self.metrics['subscribed_channels'] = self.subscribe_channels

            logger.info(f"✅ Connected to Redis at {self.redis_url}")
            logger.info(f"📡 Subscribed to channels: {self.subscribe_channels}")
            return True

        except Exception as e:
            logger.warning(f"⚠️  Redis connection failed: {e}")
            logger.info("📦 Using in-memory mode as fallback")
            self.redis_connected = False
            self.metrics['redis_connected'] = False
            return False

    async def publish_message(self, channel_key: str, message: Dict[str, Any]):
        """Publish message to Redis channel.

        Args:
            channel_key: Key from publish_channels dict
            message: Message to publish
        """
        if not self.redis_connected or not self.redis_client:
            logger.debug(f"Cannot publish to {channel_key} - Redis not connected")
            return

        try:
            channel = self.publish_channels.get(channel_key)
            if channel:
                await self.redis_client.publish(channel, json.dumps(message))
                logger.debug(f"📤 Published to {channel}")
        except Exception as e:
            logger.error(f"Failed to publish to {channel_key}: {e}")

    async def process_wallet_profile(self, data: Dict[str, Any]):
        """Process incoming wallet profile."""
        try:
            wallet_addr = data.get('wallet_address')
            if wallet_addr:
                self.wallet_profiles_buffer[wallet_addr] = data
                logger.debug(f"📊 Buffered wallet profile: {wallet_addr}")
        except Exception as e:
            logger.error(f"Error processing wallet profile: {e}")

    async def process_coordinated_trade(self, data: Dict[str, Any]):
        """Process coordinated trading pattern."""
        try:
            self.coordinated_trades_buffer.append(data)
            logger.debug(f"🔗 Buffered coordinated trade pattern")
        except Exception as e:
            logger.error(f"Error processing coordinated trade: {e}")

    async def process_transaction(self, data: Dict[str, Any]):
        """Process transaction data."""
        try:
            self.transactions_buffer.append(data)
            logger.debug(f"💰 Buffered transaction")
        except Exception as e:
            logger.error(f"Error processing transaction: {e}")

    async def listen_to_channels(self):
        """Listen to subscribed Redis channels."""
        if not self.redis_connected or not self.pubsub:
            logger.info("🔇 Redis not connected - skipping channel listener")
            return

        logger.info("👂 Starting Redis channel listener...")

        try:
            async for message in self.pubsub.listen():
                if message['type'] == 'message':
                    self.metrics['messages_processed'] += 1

                    try:
                        data = json.loads(message['data'])
                        channel = message['channel']

                        if channel == 'godmode:wallet_profiles':
                            await self.process_wallet_profile(data)
                        elif channel == 'godmode:coordinated_trades':
                            await self.process_coordinated_trade(data)
                        elif channel == 'godmode:transactions':
                            await self.process_transaction(data)
                        elif channel == 'godmode:control':
                            await self.handle_control_message(data)

                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON from {message['channel']}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")

        except Exception as e:
            logger.error(f"Channel listener error: {e}")

    async def handle_control_message(self, data: Dict[str, Any]):
        """Handle orchestrator control messages."""
        command = data.get('command')

        if command == 'stop':
            logger.info("🛑 Received stop command")
            self.running = False
        elif command == 'status':
            await self.publish_heartbeat()
        elif command == 'reset':
            logger.info("🔄 Resetting detector state")
            self.detector = SybilDetector()
            self.wallet_profiles_buffer.clear()

    async def run_sybil_detection(self):
        """Run sybil detection analysis cycle."""
        if not self.wallet_profiles_buffer:
            logger.debug("No wallet profiles to analyze")
            return

        try:
            logger.info(f"🔍 Starting sybil detection analysis on {len(self.wallet_profiles_buffer)} wallets")
            start_time = time.time()

            # Enrich wallet data with coordinated trade info
            enriched_wallet_data = self._enrich_wallet_data()

            # Run comprehensive detection
            clusters = self.detector.analyze_wallets(enriched_wallet_data)

            # Get detector stats
            stats = self.detector.get_stats()

            # Update metrics
            self.metrics.update(stats)
            self.metrics['analysis_cycles'] += 1

            elapsed = time.time() - start_time
            logger.info(f"✅ Analysis complete in {elapsed:.2f}s: {len(clusters)} clusters detected")

            # Publish results
            if clusters:
                await self.publish_clusters(clusters)
                await self.publish_wallet_scores(enriched_wallet_data)
                await self.publish_funding_networks(clusters)

            self.last_analysis_time = datetime.utcnow()

        except Exception as e:
            logger.error(f"Error in sybil detection: {e}", exc_info=True)

    def _enrich_wallet_data(self) -> Dict[str, Dict[str, Any]]:
        """Enrich wallet profiles with transaction and pattern data."""
        enriched = dict(self.wallet_profiles_buffer)

        # Add transactions to wallet data
        for tx in self.transactions_buffer:
            wallet = tx.get('wallet_address')
            if wallet and wallet in enriched:
                if 'transactions' not in enriched[wallet]:
                    enriched[wallet]['transactions'] = []
                enriched[wallet]['transactions'].append(tx)

        # Add coordinated trade patterns
        for pattern in self.coordinated_trades_buffer:
            wallets = pattern.get('wallets', [])
            for wallet in wallets:
                if wallet in enriched:
                    if 'coordinated_patterns' not in enriched[wallet]:
                        enriched[wallet]['coordinated_patterns'] = []
                    enriched[wallet]['coordinated_patterns'].append(pattern)

        return enriched

    async def publish_clusters(self, clusters: List[Dict[str, Any]]):
        """Publish detected sybil clusters."""
        for cluster in clusters:
            await self.publish_message('clusters', cluster)
            logger.info(f"🕸️  Published cluster: {cluster['cluster_id']} "
                       f"({cluster['cluster_size']} wallets, "
                       f"{cluster['sybil_confidence']:.2%} confidence, "
                       f"method: {cluster['detection_method']})")

    async def publish_wallet_scores(self, wallet_data: Dict[str, Dict[str, Any]]):
        """Publish individual wallet sybil scores."""
        for wallet_addr in wallet_data.keys():
            score = self.detector.get_wallet_sybil_score(wallet_addr)
            if score > 0.0:
                await self.publish_message('scores', {
                    'wallet_address': wallet_addr,
                    'sybil_score': score,
                    'timestamp': datetime.utcnow().isoformat()
                })

    async def publish_funding_networks(self, clusters: List[Dict[str, Any]]):
        """Publish common funding source alerts."""
        for cluster in clusters:
            if 'common_funding_source' in cluster.get('evidence', {}):
                await self.publish_message('funding', {
                    'funding_source': cluster['evidence']['common_funding_source'],
                    'funded_wallets': cluster['wallets'],
                    'cluster_id': cluster['cluster_id'],
                    'confidence': cluster['sybil_confidence'],
                    'timestamp': datetime.utcnow().isoformat()
                })
                logger.info(f"💸 Funding network alert: {cluster['evidence']['common_funding_source']} "
                           f"-> {len(cluster['wallets'])} wallets")

    async def publish_heartbeat(self):
        """Publish agent heartbeat with status."""
        self.metrics['status'] = 'OPERATIONAL' if self.running else 'STOPPED'
        self.metrics['last_heartbeat'] = datetime.utcnow().isoformat()

        await self.publish_message('heartbeat', self.metrics)
        logger.debug(f"💓 Heartbeat published")

    async def heartbeat_loop(self):
        """Send heartbeat every 10 seconds."""
        while self.running:
            await self.publish_heartbeat()
            await asyncio.sleep(10)

    async def analysis_loop(self):
        """Run sybil detection every 30 seconds."""
        while self.running:
            await self.run_sybil_detection()
            await asyncio.sleep(self.analysis_interval)

    async def start(self):
        """Start the sybil detection agent."""
        logger.info("🚀 Starting SYBIL_DETECTION Agent...")

        # Try to connect to Redis
        await self.connect_redis()

        # Set running state
        self.running = True
        self.metrics['status'] = 'OPERATIONAL'

        # Create tasks
        tasks = [
            asyncio.create_task(self.heartbeat_loop()),
            asyncio.create_task(self.analysis_loop())
        ]

        # Add Redis listener if connected
        if self.redis_connected:
            tasks.append(asyncio.create_task(self.listen_to_channels()))

        logger.info("✅ SYBIL_DETECTION Agent OPERATIONAL")
        logger.info(f"   - Detection methods: 6 (funding, similarity, temporal, pattern, community, PageRank)")
        logger.info(f"   - Analysis interval: {self.analysis_interval}s")
        logger.info(f"   - Redis mode: {'CONNECTED' if self.redis_connected else 'IN-MEMORY FALLBACK'}")

        # Print initial status
        print(json.dumps(self.metrics, indent=2))

        try:
            # Wait for all tasks
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("⚠️  Keyboard interrupt received")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("🛑 Shutting down SYBIL_DETECTION Agent...")
        self.running = False

        if self.redis_connected:
            try:
                if self.pubsub:
                    await self.pubsub.unsubscribe(*self.subscribe_channels)
                    await self.pubsub.close()
                if self.redis_client:
                    await self.redis_client.close()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")

        logger.info("✅ Shutdown complete")


async def main():
    """Main entry point."""
    import os

    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
    agent = SybilDetectionAgent(redis_url=redis_url)

    try:
        await agent.start()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
