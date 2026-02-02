#!/usr/bin/env python3
"""
WALLET_ANALYZER Agent - Real-time Wallet Profiling and Behavioral Analysis

Agent 2/6 in GODMODESCANNER multi-agent system

Responsibilities:
- Real-time wallet profiling for all pump.fun traders
- Behavioral pattern analysis and insider detection
- Reputation scoring and risk assessment
- Early buyer detection (<10s from launch)
- Funding source analysis
- Wallet network clustering
"""

import sys
import os
import asyncio
import json
import time
import logging
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, List, Set, Optional
from dataclasses import dataclass, asdict

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [WALLET_ANALYZER] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add project to path
project_root = '/a0/usr/projects/godmodescanner'
sys.path.insert(0, project_root)

try:
    from utils.redis_pubsub import RedisPubSubManager
    from utils.event_emitter import EventEmitter
    REDIS_AVAILABLE = True
except ImportError:
    logger.warning("Redis modules not available, running in standalone mode")
    REDIS_AVAILABLE = False


@dataclass
class WalletProfile:
    """Comprehensive wallet profile with behavioral metrics"""
    address: str
    first_seen: str
    last_seen: str
    total_trades: int = 0
    early_buys: int = 0  # <10 seconds
    ultra_early_buys: int = 0  # <3 seconds
    tokens_traded: List[str] = None
    win_rate: float = 0.0
    avg_hold_time: int = 0
    reputation_score: float = 50.0
    insider_score: float = 0.0
    funding_sources: List[str] = None
    linked_wallets: List[str] = None
    risk_level: str = 'low'
    transaction_history: List[dict] = None

    def __post_init__(self):
        if self.tokens_traded is None:
            self.tokens_traded = []
        if self.funding_sources is None:
            self.funding_sources = []
        if self.linked_wallets is None:
            self.linked_wallets = []
        if self.transaction_history is None:
            self.transaction_history = []

    def to_dict(self) -> dict:
        return asdict(self)


class WalletAnalyzerAgent:
    """WALLET_ANALYZER - Real-time wallet profiling and behavioral analysis"""

    # Detection thresholds (based on research)
    THRESHOLDS = {
        'ultra_early_buy_seconds': 3,      # 99% insider probability
        'early_buy_seconds': 10,           # 95% insider probability
        'funding_window_seconds': 60,      # 95% insider if funded <60s pre-launch
        'insider_score_threshold': 0.7,    # Flag as suspicious
        'elite_win_rate': 0.7,             # Elite insider tier
        'bundler_tx_per_minute': 10,       # Bundler detection
        'high_volume_sol': 5.0             # Large buy threshold
    }

    def __init__(self):
        self.name = "WALLET_ANALYZER"
        self.status = "INITIALIZING"

        # In-memory wallet profile cache
        self.wallet_profiles: Dict[str, WalletProfile] = {}
        self.suspicious_wallets: Set[str] = set()

        # Performance metrics
        self.total_transactions_processed = 0
        self.total_profiles_created = 0
        self.processing_times = []
        self.start_time = time.time()

        # Redis pub/sub
        self.redis_connected = False
        self.redis_client = None
        self.pubsub = None

        # Event handlers
        self.event_handlers = {
            'transaction': [],
            'profile_updated': [],
            'suspicious_wallet': []
        }

        logger.info(f"Agent instance created")

    def initialize_redis(self) -> bool:
        """Initialize Redis pub/sub connection with fallback"""
        try:
            import redis
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=0,
                decode_responses=True,
                socket_timeout=2
            )
            self.redis_client.ping()
            self.redis_connected = True
            logger.info("✓ Redis connected successfully")

            # Initialize pub/sub
            self.pubsub = self.redis_client.pubsub()
            return True
        except Exception as e:
            logger.warning(f"Redis unavailable: {e}")
            logger.warning(f"Running in standalone mode with in-memory storage")
            self.redis_connected = False
            return False

    def subscribe_to_channels(self) -> bool:
        """Subscribe to required Redis pub/sub channels"""
        if not self.redis_connected or not self.pubsub:
            logger.warning("Cannot subscribe: Redis not connected")
            return False

        try:
            channels = [
                'godmode:transactions',
                'godmode:token_launches',
                'godmode:control'
            ]

            for channel in channels:
                self.pubsub.subscribe(channel)
                logger.info(f"✓ Subscribed to {channel}")

            return True
        except Exception as e:
            logger.error(f"Subscription failed: {e}")
            return False

    def create_wallet_profile(self, address: str) -> WalletProfile:
        """Create new wallet profile with default values"""
        profile = WalletProfile(
            address=address,
            first_seen=datetime.now(timezone.utc).isoformat(),
            last_seen=datetime.now(timezone.utc).isoformat()
        )

        self.wallet_profiles[address] = profile
        self.total_profiles_created += 1
        logger.debug(f"Created profile for {address}")
        return profile

    def calculate_insider_score(self, profile: WalletProfile) -> float:
        """
        Calculate insider score based on behavioral patterns

        Scoring algorithm:
        - Ultra-early buy frequency (70%+) = +0.4 points (99% insider)
        - Early buy frequency (70%+) = +0.3 points (95% insider)
        - Win rate (70%+) = +0.3 points (elite insider)

        Max score: 1.0 (100% insider probability)
        """
        score = 0.0

        if profile.total_trades == 0:
            return 0.0

        # Ultra-early buy frequency (99% insider if >70% of trades)
        ultra_early_rate = profile.ultra_early_buys / profile.total_trades
        if ultra_early_rate > 0.7:
            score += 0.4
        elif ultra_early_rate > 0.5:
            score += 0.3
        elif ultra_early_rate > 0.3:
            score += 0.2

        # Early buy frequency (95% insider if >70% of trades)
        early_rate = profile.early_buys / profile.total_trades
        if early_rate > 0.7:
            score += 0.3
        elif early_rate > 0.5:
            score += 0.2
        elif early_rate > 0.3:
            score += 0.1

        # Win rate (elite insider if >70%)
        if profile.win_rate > 0.7:
            score += 0.3
        elif profile.win_rate > 0.5:
            score += 0.15

        return min(score, 1.0)

    def calculate_risk_level(self, insider_score: float) -> str:
        """Determine risk level based on insider score"""
        if insider_score >= 0.9:
            return 'critical'
        elif insider_score >= 0.7:
            return 'high'
        elif insider_score >= 0.5:
            return 'medium'
        else:
            return 'low'

    def process_transaction(self, tx_data: dict) -> Optional[WalletProfile]:
        """
        Process transaction and update wallet profile

        Expected tx_data format:
        {
            'wallet_address': str,
            'token_address': str,
            'timing_seconds': float,  # Time since token launch
            'amount_sol': float,
            'transaction_type': str,  # 'buy' or 'sell'
            'signature': str,
            'timestamp': str
        }
        """
        start_time = time.time()

        try:
            wallet_address = tx_data.get('wallet_address')
            if not wallet_address:
                logger.warning("Transaction missing wallet_address")
                return None

            # Get or create profile
            if wallet_address not in self.wallet_profiles:
                profile = self.create_wallet_profile(wallet_address)
            else:
                profile = self.wallet_profiles[wallet_address]

            # Update profile with transaction data
            profile.last_seen = datetime.now(timezone.utc).isoformat()
            profile.total_trades += 1

            # Track timing if available
            timing = tx_data.get('timing_seconds', None)
            if timing is not None:
                if timing < self.THRESHOLDS['ultra_early_buy_seconds']:
                    profile.ultra_early_buys += 1
                    profile.early_buys += 1
                    logger.info(f"🚨 Ultra-early buy detected: {wallet_address} at {timing:.2f}s")
                elif timing < self.THRESHOLDS['early_buy_seconds']:
                    profile.early_buys += 1
                    logger.info(f"⚠️  Early buy detected: {wallet_address} at {timing:.2f}s")

            # Track token if new
            token = tx_data.get('token_address')
            if token and token not in profile.tokens_traded:
                profile.tokens_traded.append(token)

            # Add to transaction history (keep last 100)
            profile.transaction_history.append({
                'timestamp': tx_data.get('timestamp', datetime.now(timezone.utc).isoformat()),
                'token': token,
                'timing': timing,
                'amount_sol': tx_data.get('amount_sol', 0),
                'type': tx_data.get('transaction_type', 'unknown')
            })
            if len(profile.transaction_history) > 100:
                profile.transaction_history = profile.transaction_history[-100:]

            # Calculate scores
            profile.insider_score = self.calculate_insider_score(profile)
            profile.risk_level = self.calculate_risk_level(profile.insider_score)

            # Flag suspicious wallets
            if profile.insider_score >= self.THRESHOLDS['insider_score_threshold']:
                if wallet_address not in self.suspicious_wallets:
                    self.suspicious_wallets.add(wallet_address)
                    logger.warning(f"⚠️  SUSPICIOUS WALLET FLAGGED: {wallet_address} (score: {profile.insider_score:.2f})")
                    self.publish_suspicious_alert(profile)

            # Store in Redis if connected
            if self.redis_connected:
                try:
                    self.redis_client.setex(
                        f"wallet_profile:{wallet_address}",
                        7 * 24 * 3600,  # 7 day TTL
                        json.dumps(profile.to_dict())
                    )
                except Exception as e:
                    logger.debug(f"Redis cache failed: {e}")

            # Publish updated profile
            self.publish_wallet_profile(profile)

            # Track performance
            processing_time = (time.time() - start_time) * 1000
            self.processing_times.append(processing_time)
            if len(self.processing_times) > 1000:
                self.processing_times = self.processing_times[-1000:]

            self.total_transactions_processed += 1

            return profile

        except Exception as e:
            logger.error(f"Error processing transaction: {e}", exc_info=True)
            return None

    def publish_wallet_profile(self, profile: WalletProfile):
        """Publish updated wallet profile to Redis channel"""
        if not self.redis_connected:
            return

        try:
            self.redis_client.publish(
                'godmode:wallet_profiles',
                json.dumps({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'profile': profile.to_dict()
                })
            )
        except Exception as e:
            logger.debug(f"Failed to publish profile: {e}")

    def publish_suspicious_alert(self, profile: WalletProfile):
        """Publish suspicious wallet alert"""
        if not self.redis_connected:
            return

        try:
            alert = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'wallet_address': profile.address,
                'insider_score': profile.insider_score,
                'risk_level': profile.risk_level,
                'early_buys': profile.early_buys,
                'ultra_early_buys': profile.ultra_early_buys,
                'total_trades': profile.total_trades,
                'win_rate': profile.win_rate,
                'tokens_traded': len(profile.tokens_traded)
            }

            self.redis_client.publish(
                'godmode:suspicious_wallets',
                json.dumps(alert)
            )

            logger.info(f"Published suspicious wallet alert for {profile.address}")
        except Exception as e:
            logger.debug(f"Failed to publish alert: {e}")

    def publish_heartbeat(self):
        """Publish agent heartbeat"""
        if not self.redis_connected:
            return

        try:
            heartbeat = {
                'agent': self.name,
                'status': self.status,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'profiles_tracked': len(self.wallet_profiles),
                'suspicious_wallets': len(self.suspicious_wallets),
                'uptime_seconds': round(time.time() - self.start_time, 2)
            }

            self.redis_client.publish(
                'godmode:heartbeat:wallet_analyzer',
                json.dumps(heartbeat)
            )
        except Exception as e:
            logger.debug(f"Failed to publish heartbeat: {e}")

    def get_status(self) -> dict:
        """Get current agent status"""
        avg_processing_time = 0
        if self.processing_times:
            avg_processing_time = sum(self.processing_times) / len(self.processing_times)

        subscribed_channels = []
        if self.redis_connected:
            subscribed_channels = ['godmode:transactions', 'godmode:token_launches', 'godmode:control']

        return {
            'agent': self.name,
            'status': self.status,
            'profiles_tracked': len(self.wallet_profiles),
            'suspicious_wallets': len(self.suspicious_wallets),
            'total_transactions_processed': self.total_transactions_processed,
            'total_profiles_created': self.total_profiles_created,
            'avg_processing_time_ms': round(avg_processing_time, 2),
            'redis_connected': self.redis_connected,
            'subscribed_channels': subscribed_channels,
            'uptime_seconds': round(time.time() - self.start_time, 2),
            'detection_thresholds': self.THRESHOLDS
        }

    async def listen_for_transactions(self):
        """Listen for transactions from Redis pub/sub"""
        if not self.redis_connected or not self.pubsub:
            logger.error("Cannot listen: Redis not connected")
            return

        logger.info("Starting transaction listener...")

        try:
            for message in self.pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])

                        if message['channel'] == 'godmode:transactions':
                            self.process_transaction(data)
                        elif message['channel'] == 'godmode:control':
                            self.handle_control_message(data)

                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON in message: {message['data']}")
                    except Exception as e:
                        logger.error(f"Error handling message: {e}", exc_info=True)

        except KeyboardInterrupt:
            logger.info("Listener interrupted")
        except Exception as e:
            logger.error(f"Listener error: {e}", exc_info=True)

    def handle_control_message(self, data: dict):
        """Handle control messages from orchestrator"""
        command = data.get('command')

        if command == 'status':
            logger.info(f"Status request received")
            status = self.get_status()
            logger.info(json.dumps(status, indent=2))

        elif command == 'shutdown':
            logger.info("Shutdown command received")
            self.status = "SHUTDOWN"
            if self.pubsub:
                self.pubsub.close()

        elif command == 'clear_cache':
            logger.info("Clearing wallet profile cache")
            self.wallet_profiles.clear()
            self.suspicious_wallets.clear()
            logger.info("Cache cleared")

    async def run(self):
        """Main agent run loop"""
        logger.info("="*70)
        logger.info("WALLET_ANALYZER Agent Starting")
        logger.info("="*70)

        # Initialize Redis
        self.initialize_redis()

        # Subscribe to channels
        if self.redis_connected:
            self.subscribe_to_channels()

        # Set status to operational
        self.status = "OPERATIONAL"

        # Display status
        status = self.get_status()
        logger.info(f"Agent Status: {json.dumps(status, indent=2)}")

        logger.info("="*70)
        logger.info("WALLET_ANALYZER Agent Ready")
        logger.info("Awaiting transactions from TRANSACTION_MONITOR...")
        logger.info("="*70)

        # Start heartbeat task
        async def heartbeat_loop():
            while self.status == "OPERATIONAL":
                self.publish_heartbeat()
                await asyncio.sleep(10)

        heartbeat_task = asyncio.create_task(heartbeat_loop())

        # Listen for transactions
        try:
            if self.redis_connected:
                await self.listen_for_transactions()
            else:
                # Standalone mode - wait for external feed
                logger.info("Standalone mode: waiting for external transaction feed")
                while self.status == "OPERATIONAL":
                    await asyncio.sleep(1)

        finally:
            heartbeat_task.cancel()
            logger.info("WALLET_ANALYZER Agent Stopped")


if __name__ == "__main__":
    agent = WalletAnalyzerAgent()

    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        logger.info("Agent interrupted by user")
    except Exception as e:
        logger.error(f"Agent crashed: {e}", exc_info=True)
