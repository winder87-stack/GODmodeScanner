#!/usr/bin/env python3
"""Example: Running the GODMODESCANNER Insider Detector.

This script demonstrates how to use the InsiderDetector to monitor
pump.fun for insider trading activity in real-time.
"""

import asyncio
import signal
from datetime import datetime

from detector import InsiderDetector
import structlog

# Configure logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)

logger = structlog.get_logger(__name__)


async def on_insider_detected(alert):
    """Callback function called when insider activity is detected."""
    print("
" + "="*80)
    print("🚨 INSIDER ALERT DETECTED! 🚨")
    print("="*80)
    print(f"Alert Type: {alert.alert_type}")
    print(f"Token: {alert.token_mint}")
    print(f"Trader: {alert.trader}")
    print(f"Score: {alert.score:.3f}")
    print(f"Time: {alert.timestamp}")
    print(f"
Evidence:")
    for key, value in alert.evidence.items():
        print(f"  {key}: {value}")
    print("="*80 + "
")

    # Here you could:
    # - Send Telegram notification
    # - Post to Discord webhook
    # - Store in database
    # - Trigger automated actions


async def print_stats(detector, interval=30):
    """Print statistics periodically."""
    while True:
        await asyncio.sleep(interval)
        stats = detector.get_stats()

        print("
" + "-"*80)
        print(f"📊 GODMODESCANNER Statistics - {datetime.now().strftime('%H:%M:%S')}")
        print("-"*80)

        detection = stats['detection_stats']
        print(f"Tokens Monitored: {detection['tokens_monitored']}")
        print(f"Trades Analyzed: {detection['trades_analyzed']}")
        print(f"Alerts Generated: {detection['alerts_generated']}")
        print(f"Early Buys Detected: {detection['early_buys_detected']}")
        print(f"Coordinated Patterns: {detection['coordinated_patterns']}")
        print(f"Wash Trades: {detection['wash_trades']}")
        print(f"Uptime: {detection['uptime_seconds']:.2f}s")
        print(f"Processing Rate: {detection['trades_per_second']:.2f} trades/sec")

        print(f"
Suspicious Wallets Flagged: {len(detector.get_suspicious_wallets())}")
        print("-"*80 + "
")


async def main():
    """Main entry point."""
    print("""

╔═══════════════════════════════════════════════════════════════╗
║                                                                 ║
║            🔥 GODMODESCANNER - pump.fun Insider Detector 🔥     ║
║                                                                 ║
║  The BEST insider trading detection system for pump.fun        ║
║  Zero-cost operation • <1 second latency • Real-time alerts   ║
║                                                                 ║
╚═══════════════════════════════════════════════════════════════╝

""")

    logger.info("initializing_godmodescanner")

    # Create detector with custom settings
    detector = InsiderDetector(
        early_buy_threshold=60.0,  # Flag buys within 60 seconds
        insider_score_threshold=0.7,  # Alert on score >= 0.7
        alert_callback=on_insider_detected,  # Custom alert handler
    )

    # Start detection
    await detector.start()

    logger.info(
        "godmodescanner_started",
        monitoring="ALL pump.fun tokens",
        status="ACTIVE",
    )

    print("
✅ GODMODESCANNER is now ACTIVE and monitoring pump.fun!")
    print("   Press Ctrl+C to stop
")

    # Start stats printer
    stats_task = asyncio.create_task(print_stats(detector))

    try:
        # Run forever
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("

⏹️  Stopping GODMODESCANNER...")
        stats_task.cancel()
        await detector.stop()

        # Print final statistics
        print("
" + "="*80)
        print("📊 Final Statistics")
        print("="*80)
        final_stats = detector.get_stats()
        print(final_stats['detection_stats'])
        print("
🔥 Thank you for using GODMODESCANNER!
")


if __name__ == "__main__":
    asyncio.run(main())
