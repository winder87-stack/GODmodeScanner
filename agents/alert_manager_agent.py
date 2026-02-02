#!/usr/bin/env python3
"""
ALERT_MANAGER Agent - Multi-Channel Alert Delivery System
Agent 6/6 in GODMODESCANNER Multi-Agent System

Responsibilities:
- Multi-channel alerting (Telegram, webhook, logs)
- Priority-based routing (CRITICAL/HIGH/MEDIUM/LOW)
- Rate limiting (10 alerts/min per channel)
- Alert deduplication (5-minute window)
- Retry with exponential backoff (3 attempts max)
- Alert history (7-day Redis retention)
- Delivery confirmation tracking
"""

import asyncio
import json
import os
import time
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from collections import deque
from dataclasses import dataclass, asdict
import aiohttp
import structlog

# Try importing Redis, fallback to in-memory if unavailable
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("Redis not available - using in-memory alert storage")

# Initialize structured logger
logger = structlog.get_logger("alert_manager")


@dataclass
class AlertChannel:
    """Alert delivery channel configuration."""
    channel: str
    status: str
    delivery_time: Optional[str] = None
    attempts: int = 0
    error: Optional[str] = None


@dataclass
class Alert:
    """Alert data structure."""
    alert_id: str
    timestamp: str
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    alert_type: str  # token_risk, wallet_risk, coordinated, etc.
    data: Dict
    channels: List[AlertChannel]


class RateLimiter:
    """Rate limiter with sliding window (max alerts per minute)."""

    def __init__(self, max_alerts_per_minute: int = 10):
        self.max_alerts = max_alerts_per_minute
        self.alert_times = deque(maxlen=max_alerts_per_minute)

    def can_send_alert(self) -> bool:
        """Check if alert can be sent within rate limit."""
        now = time.time()

        # Remove alerts older than 1 minute
        while self.alert_times and now - self.alert_times[0] > 60:
            self.alert_times.popleft()

        # Check if under limit
        if len(self.alert_times) < self.max_alerts:
            self.alert_times.append(now)
            return True

        return False

    def get_wait_time(self) -> float:
        """Get time to wait before next alert can be sent."""
        if not self.alert_times:
            return 0.0

        oldest = self.alert_times[0]
        elapsed = time.time() - oldest

        if elapsed >= 60:
            return 0.0

        return 60 - elapsed


class AlertDeduplicator:
    """Alert deduplicator with time-based window."""

    def __init__(self, window_seconds: int = 300):
        self.window = window_seconds
        self.recent_alerts: Dict[str, float] = {}  # signature -> timestamp

    def create_signature(self, alert_data: Dict) -> str:
        """Create hash signature from alert data."""
        key_fields = (
            f"{alert_data.get('token_address', '')}"
            f":{alert_data.get('wallet_address', '')}"
            f":{alert_data.get('pattern_type', '')}"
            f":{alert_data.get('alert_type', '')}"
        )
        return hashlib.sha256(key_fields.encode()).hexdigest()

    def is_duplicate(self, alert_data: Dict) -> bool:
        """Check if alert is duplicate within time window."""
        now = time.time()
        signature = self.create_signature(alert_data)

        # Clean old signatures
        self.recent_alerts = {
            k: v for k, v in self.recent_alerts.items()
            if now - v < self.window
        }

        # Check if duplicate
        if signature in self.recent_alerts:
            return True

        self.recent_alerts[signature] = now
        return False


class AlertManager:
    """Unified alert delivery system with multi-channel support."""

    def __init__(self):
        self.logger = logger.bind(agent="ALERT_MANAGER")

        # Configuration
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.webhook_url = os.getenv('WEBHOOK_URL', '')
        self.webhook_secret = os.getenv('WEBHOOK_SECRET', '')
        self.max_alerts_per_minute = int(os.getenv('MAX_ALERTS_PER_MINUTE', '10'))
        self.dedup_window = int(os.getenv('DEDUPLICATION_WINDOW_SECONDS', '300'))

        # Rate limiters per channel
        self.rate_limiters = {
            'telegram': RateLimiter(self.max_alerts_per_minute),
            'webhook': RateLimiter(self.max_alerts_per_minute),
            'log': RateLimiter(100)  # Higher limit for logs
        }

        # Deduplicator
        self.deduplicator = AlertDeduplicator(self.dedup_window)

        # Statistics
        self.stats = {
            'alerts_processed': 0,
            'alerts_sent': 0,
            'alerts_failed': 0,
            'alerts_deduplicated': 0,
            'alerts_rate_limited': 0,
            'delivery_times': deque(maxlen=100)
        }

        # Redis connection
        self.redis_client = None
        self.pubsub = None

        # Running flag
        self.running = False

        self.logger.info("AlertManager initialized",
                        telegram_configured=bool(self.telegram_token and self.telegram_chat_id),
                        webhook_configured=bool(self.webhook_url),
                        rate_limit=self.max_alerts_per_minute,
                        dedup_window=self.dedup_window)

    async def connect_redis(self) -> bool:
        """Connect to Redis pub/sub."""
        if not REDIS_AVAILABLE:
            self.logger.warning("Redis not available - using in-memory mode")
            return False

        try:
            self.redis_client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', '6379')),
                decode_responses=True
            )

            # Test connection
            await self.redis_client.ping()

            # Initialize pub/sub
            self.pubsub = self.redis_client.pubsub()

            # Subscribe to upstream alert channels
            await self.pubsub.subscribe(
                'godmode:high_risk_alerts',
                'godmode:suspicious_wallets',
                'godmode:coordinated_trades',
                'godmode:wash_trades',
                'godmode:bundler_alerts',
                'godmode:sybil_clusters',
                'godmode:control'
            )

            self.logger.info("Connected to Redis pub/sub", channels=7)
            return True

        except Exception as e:
            self.logger.error("Failed to connect to Redis", error=str(e))
            return False

    def determine_priority(self, alert_data: Dict) -> str:
        """Determine alert priority based on data."""
        # Token risk-based priority
        if 'risk_score' in alert_data:
            score = alert_data['risk_score']
            if score >= 80:
                return 'CRITICAL'
            elif score >= 60:
                return 'HIGH'
            elif score >= 40:
                return 'MEDIUM'
            else:
                return 'LOW'

        # Wallet risk-based priority
        if 'wallet_risk_score' in alert_data:
            score = alert_data['wallet_risk_score']
            if score >= 75:
                return 'CRITICAL'
            elif score >= 55:
                return 'HIGH'
            elif score >= 35:
                return 'MEDIUM'
            else:
                return 'LOW'

        # Pattern-based priority
        if alert_data.get('pattern_type') == 'coordinated_trading':
            wallet_count = alert_data.get('wallet_count', 0)
            if wallet_count >= 5:
                return 'CRITICAL'
            elif wallet_count >= 3:
                return 'HIGH'
            else:
                return 'MEDIUM'

        # Sybil cluster priority
        if alert_data.get('pattern_type') == 'sybil_cluster':
            confidence = alert_data.get('confidence', 0)
            if confidence >= 90:
                return 'CRITICAL'
            elif confidence >= 80:
                return 'HIGH'
            else:
                return 'MEDIUM'

        # Default to MEDIUM
        return 'MEDIUM'

    def format_telegram_message(self, alert_data: Dict, priority: str) -> str:
        """Format alert message for Telegram."""
        priority_emojis = {
            'CRITICAL': '🚨🚨🚨',
            'HIGH': '⚠️⚠️',
            'MEDIUM': '⚠️',
            'LOW': 'ℹ️'
        }

        emoji = priority_emojis.get(priority, 'ℹ️')

        # Token risk alert
        if alert_data.get('alert_type') == 'token_risk':
            token = alert_data.get('token_address', 'Unknown')[:8] + '...'
            risk_score = alert_data.get('risk_score', 0)
            confidence = alert_data.get('confidence_interval', {})
            early_buyers = alert_data.get('early_buyer_count', 0)
            coordinated = alert_data.get('coordinated_wallet_count', 0)

            parts = [
                f"{emoji} **{priority} ALERT**",
                "",
                f"**Token**: `{alert_data.get('token_address', 'Unknown')}`",
                f"**Risk Score**: {risk_score}/100 ({priority})",
                f"**Confidence**: {confidence.get('lower', 0):.1f}-{confidence.get('upper', 100):.1f}%",
                "",
                "**Evidence**:",
                f"• 🎯 Early Buyers: {early_buyers} wallets (<3s)",
                f"• 🤝 Coordinated: {coordinated} wallets"
            ]

            if priority == 'CRITICAL':
                parts.extend(["", "**Action**: AVOID TOKEN - Likely insider trading"])

            parts.append(f"\n**View**: https://dexscreener.com/solana/{alert_data.get('token_address', '')}")

            return "\n".join(parts)

        # Wallet risk alert
        elif alert_data.get('alert_type') == 'wallet_risk':
            wallet = alert_data.get('wallet_address', 'Unknown')[:8] + '...'
            risk_score = alert_data.get('wallet_risk_score', 0)
            insider_score = alert_data.get('insider_score', 0)

            parts = [
                f"{emoji} **{priority} WALLET ALERT**",
                "",
                f"**Wallet**: `{alert_data.get('wallet_address', 'Unknown')}`",
                f"**Risk Score**: {risk_score}/100 ({priority})",
                f"**Insider Score**: {insider_score}/100",
                ""
            ]

            if priority == 'CRITICAL':
                parts.append("**Action**: BLACKLIST WALLET")

            parts.append(f"\n**View**: https://solscan.io/account/{alert_data.get('wallet_address', '')}")
            return "\n".join(parts)
            return "\n".join(parts)
        elif alert_data.get('pattern_type') == 'coordinated_trading':
            wallet_count = alert_data.get('wallet_count', 0)
            confidence = alert_data.get('confidence', 0)

            parts = [
                f"{emoji} **{priority} ALERT**",
                "",
                "**Pattern**: Coordinated Trading",
                f"**Token**: `{alert_data.get('token_address', 'Unknown')}`",
                f"**Wallets Involved**: {wallet_count}",
                f"**Confidence**: {confidence}%"
            ]

            return "\n".join(parts)

            return "\n".join(parts)
            cluster_size = alert_data.get('cluster_size', 0)
            confidence = alert_data.get('confidence', 0)

            parts = [
                f"{emoji} **SYBIL NETWORK DETECTED**",
                "",
                f"**Cluster Size**: {cluster_size} wallets",
                f"**Confidence**: {confidence}%"
            ]

            return "\n".join(parts)

        # Generic alert
        else:
            parts = [
                f"{emoji} **{priority} ALERT**",
                "",
                f"**Type**: {alert_data.get('alert_type', 'Unknown')}",
                f"**Data**: {json.dumps(alert_data, indent=2)}"
            ]

            return "\n".join(parts)

    async def send_telegram_alert(self, message: str, priority: str) -> bool:
        """Send alert via Telegram Bot API."""

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

        payload = {
            'chat_id': self.telegram_chat_id,
            'text': message,
            'parse_mode': 'Markdown',
            'disable_web_page_preview': True
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    return response.status == 200
        except Exception as e:
            self.logger.error("Telegram delivery failed", error=str(e))
            return False

    async def send_webhook_alert(self, alert_data: Dict) -> bool:
        """Send alert via webhook HTTP POST."""
        if not self.webhook_url:
            return False

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'GODMODESCANNER/1.0'
        }

        if self.webhook_secret:
            headers['X-Webhook-Secret'] = self.webhook_secret

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=alert_data,
                    headers=headers,
                    timeout=10
                ) as response:
                    return response.status in [200, 201, 202]
        except Exception as e:
            self.logger.error("Webhook delivery failed", error=str(e))
            return False

    def log_alert(self, alert_data: Dict, priority: str):
        """Log alert using structured logging."""
        log_method = {
            'CRITICAL': self.logger.error,
            'HIGH': self.logger.warning,
            'MEDIUM': self.logger.info,
            'LOW': self.logger.debug
        }.get(priority, self.logger.info)

        log_method("alert_triggered", **alert_data)

    async def send_alert_with_retry(
        self,
        alert_data: Dict,
        channel: str,
        max_retries: int = 3
    ) -> AlertChannel:
        """Send alert with exponential backoff retry."""
        channel_obj = AlertChannel(channel=channel, status='pending', attempts=0)

        for attempt in range(max_retries):
            channel_obj.attempts = attempt + 1
            start_time = time.time()

            try:
                success = False

                if channel == 'telegram':
                    priority = self.determine_priority(alert_data)
                    message = self.format_telegram_message(alert_data, priority)
                    success = await self.send_telegram_alert(message, priority)

                elif channel == 'webhook':
                    success = await self.send_webhook_alert(alert_data)

                elif channel == 'log':
                    priority = self.determine_priority(alert_data)
                    self.log_alert(alert_data, priority)
                    success = True

                delivery_time = time.time() - start_time
                channel_obj.delivery_time = datetime.utcnow().isoformat()

                if success:
                    channel_obj.status = 'sent'
                    self.stats['delivery_times'].append(delivery_time * 1000)  # ms
                    return channel_obj

                # Exponential backoff: 1s, 2s, 4s
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

            except Exception as e:
                self.logger.warning(
                    f"{channel} delivery attempt {attempt+1} failed",
                    error=str(e)
                )
                channel_obj.error = str(e)

                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        channel_obj.status = 'failed'
        return channel_obj

    async def process_alert(self, alert_data: Dict):
        """Process a single alert through the pipeline."""
        start_time = time.time()

        # Determine priority
        priority = self.determine_priority(alert_data)

        # Check deduplication
        if self.deduplicator.is_duplicate(alert_data):
            self.stats['alerts_deduplicated'] += 1
            self.logger.debug("Alert deduplicated", priority=priority)
            return

        # Create alert object
        alert = Alert(
            alert_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow().isoformat(),
            priority=priority,
            alert_type=alert_data.get('alert_type', 'unknown'),
            data=alert_data,
            channels=[]
        )

        # Determine channels to use
        channels_to_send = ['log']  # Always log

        if self.telegram_token and self.telegram_chat_id:
            channels_to_send.append('telegram')

        if self.webhook_url:
            channels_to_send.append('webhook')

        # Send to each channel
        for channel in channels_to_send:
            # Check rate limit
            if not self.rate_limiters[channel].can_send_alert():
                self.stats['alerts_rate_limited'] += 1
                wait_time = self.rate_limiters[channel].get_wait_time()

                self.logger.warning(
                    f"{channel} rate limit exceeded",
                    wait_time=wait_time,
                    priority=priority
                )

                # For CRITICAL alerts, wait and retry
                if priority == 'CRITICAL':
                    await asyncio.sleep(wait_time)
                    if self.rate_limiters[channel].can_send_alert():
                        channel_result = await self.send_alert_with_retry(
                            alert_data, channel
                        )
                        alert.channels.append(channel_result)
                else:
                    alert.channels.append(
                        AlertChannel(
                            channel=channel,
                            status='rate_limited',
                            attempts=0
                        )
                    )
                continue

            # Send alert
            channel_result = await self.send_alert_with_retry(alert_data, channel)
            alert.channels.append(channel_result)

            if channel_result.status == 'sent':
                self.stats['alerts_sent'] += 1
            else:
                self.stats['alerts_failed'] += 1

        # Store in Redis (if available)
        if self.redis_client:
            try:
                alert_key = f"alert:{alert.alert_id}"
                await self.redis_client.setex(
                    alert_key,
                    60 * 60 * 24 * 7,  # 7 days
                    json.dumps(asdict(alert))
                )

                # Publish delivery status
                await self.redis_client.publish(
                    'godmode:alert_delivery_status',
                    json.dumps({
                        'alert_id': alert.alert_id,
                        'priority': priority,
                        'status': 'delivered' if any(
                            c.status == 'sent' for c in alert.channels
                        ) else 'failed',
                        'channels': [asdict(c) for c in alert.channels],
                        'processing_time_ms': (time.time() - start_time) * 1000
                    })
                )
            except Exception as e:
                self.logger.error("Failed to store alert in Redis", error=str(e))

        self.stats['alerts_processed'] += 1

        self.logger.info(
            "Alert processed",
            alert_id=alert.alert_id,
            priority=priority,
            channels_sent=sum(1 for c in alert.channels if c.status == 'sent'),
            processing_time_ms=(time.time() - start_time) * 1000
        )

    async def listen_redis(self):
        """Listen for alerts from Redis pub/sub."""
        if not self.pubsub:
            return

        self.logger.info("Starting Redis pub/sub listener")

        try:
            async for message in self.pubsub.listen():
                if message['type'] == 'message':
                    channel = message['channel']

                    # Handle control messages
                    if channel == 'godmode:control':
                        try:
                            cmd = json.loads(message['data'])
                            if cmd.get('command') == 'shutdown':
                                self.logger.info("Shutdown command received")
                                self.running = False
                                break
                        except Exception as e:
                            self.logger.error("Control message error", error=str(e))
                        continue

                    # Process alert
                    try:
                        alert_data = json.loads(message['data'])
                        await self.process_alert(alert_data)
                    except Exception as e:
                        self.logger.error(
                            "Failed to process alert",
                            channel=channel,
                            error=str(e)
                        )

        except Exception as e:
            self.logger.error("Redis listener error", error=str(e))

    async def publish_heartbeat(self):
        """Publish heartbeat every 10 seconds."""
        while self.running:
            try:
                heartbeat = {
                    'agent': 'ALERT_MANAGER',
                    'timestamp': datetime.utcnow().isoformat(),
                    'status': 'OPERATIONAL',
                    'stats': self.stats.copy()
                }

                if self.redis_client:
                    await self.redis_client.publish(
                        'godmode:heartbeat:alert_manager',
                        json.dumps(heartbeat)
                    )

                await asyncio.sleep(10)

            except Exception as e:
                self.logger.error("Heartbeat error", error=str(e))
                await asyncio.sleep(10)

    async def start(self):
        """Start the alert manager."""
        self.running = True
        self.logger.info("Starting ALERT_MANAGER agent")

        # Connect to Redis
        redis_connected = await self.connect_redis()

        # Start tasks
        tasks = []

        if redis_connected:
            tasks.append(asyncio.create_task(self.listen_redis()))
            tasks.append(asyncio.create_task(self.publish_heartbeat()))

        # Report status
        status = {
            'agent': 'ALERT_MANAGER',
            'status': 'OPERATIONAL',
            'alerts_processed': self.stats['alerts_processed'],
            'alerts_sent': self.stats['alerts_sent'],
            'alerts_failed': self.stats['alerts_failed'],
            'alerts_deduplicated': self.stats['alerts_deduplicated'],
            'alerts_rate_limited': self.stats['alerts_rate_limited'],
            'telegram_configured': bool(self.telegram_token and self.telegram_chat_id),
            'webhook_configured': bool(self.webhook_url),
            'redis_connected': redis_connected,
            'subscribed_channels': 7 if redis_connected else 0,
            'avg_delivery_time_ms': (
                sum(self.stats['delivery_times']) / len(self.stats['delivery_times'])
                if self.stats['delivery_times'] else 0.0
            )
        }

        print(json.dumps(status, indent=2))
        self.logger.info("ALERT_MANAGER operational", **status)

        # Wait for tasks
        if tasks:
            try:
                await asyncio.gather(*tasks)
            except Exception as e:
                self.logger.error("Task error", error=str(e))
        else:
            # If no Redis, just run in polling mode
            while self.running:
                await asyncio.sleep(1)

    async def shutdown(self):
        """Shutdown the alert manager."""
        self.logger.info("Shutting down ALERT_MANAGER")
        self.running = False

        if self.pubsub:
            await self.pubsub.close()

        if self.redis_client:
            await self.redis_client.close()


async def main():
    """Main entry point."""
    manager = AlertManager()

    try:
        await manager.start()
    except KeyboardInterrupt:
        print("\nShutdown requested...")
    finally:
        await manager.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
