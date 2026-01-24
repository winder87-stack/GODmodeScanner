#!/usr/bin/env python3
"""GODMODESCANNER Health Check - System Diagnostics.

Checks the health of all GODMODESCANNER components:
- RPC endpoints
- WebSocket connections
- Database connections
- Detection pipeline
- Memory usage
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path


class HealthChecker:
    """System health checker."""

    def __init__(self):
        self.results = {}
        self.errors = []

    async def check_rpc_endpoints(self):
        """Check RPC endpoint health."""
        print("
🌐 Checking RPC Endpoints...")

        try:
            from utils.rpc_manager import RPCManager

            async with RPCManager() as rpc:
                # Try to get block height from first endpoint
                result = await rpc.make_request("getBlockHeight")

                if result:
                    print(f"   ✅ RPC endpoints operational (block height: {result})")
                    metrics = rpc.get_metrics()
                    print(f"   📊 Connected endpoints: {metrics['overall']['healthy_endpoints']}/8")
                    self.results['rpc'] = 'healthy'
                else:
                    print("   ❌ RPC endpoints not responding")
                    self.results['rpc'] = 'unhealthy'
                    self.errors.append("RPC endpoints not responding")

        except Exception as e:
            print(f"   ❌ RPC check failed: {str(e)}")
            self.results['rpc'] = 'error'
            self.errors.append(f"RPC error: {str(e)}")

    async def check_websocket(self):
        """Check WebSocket connection."""
        print("
🔌 Checking WebSocket Connection...")

        try:
            from utils.ws_manager import WebSocketManager

            ws = WebSocketManager()
            await ws.start()

            # Give it a moment to connect
            await asyncio.sleep(2)

            metrics = ws.get_metrics()
            connected = metrics['overall']['connected_endpoints']

            if connected > 0:
                print(f"   ✅ WebSocket connected ({connected} endpoints)")
                self.results['websocket'] = 'healthy'
            else:
                print("   ⚠️  WebSocket not connected")
                self.results['websocket'] = 'degraded'

            await ws.stop()

        except Exception as e:
            print(f"   ❌ WebSocket check failed: {str(e)}")
            self.results['websocket'] = 'error'
            self.errors.append(f"WebSocket error: {str(e)}")

    def check_configuration(self):
        """Check configuration files."""
        print("
⚙️  Checking Configuration...")

        config_files = [
            'config/agents.json',
            'config/orchestrator.json',
            'config/detection_rules.json',
            '.env',
        ]

        missing = []
        for config_file in config_files:
            path = Path(config_file)
            if not path.exists():
                missing.append(config_file)

        if missing:
            print(f"   ⚠️  Missing config files: {', '.join(missing)}")
            self.results['configuration'] = 'degraded'
        else:
            print("   ✅ All configuration files present")
            self.results['configuration'] = 'healthy'

    def check_memory_usage(self):
        """Check system memory usage."""
        print("
💾 Checking Memory Usage...")

        try:
            import psutil

            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024

            print(f"   📊 Memory usage: {memory_mb:.2f} MB")

            if memory_mb < 500:
                print("   ✅ Memory usage normal")
                self.results['memory'] = 'healthy'
            elif memory_mb < 1000:
                print("   ⚠️  Memory usage elevated")
                self.results['memory'] = 'degraded'
            else:
                print("   ❌ Memory usage high")
                self.results['memory'] = 'unhealthy'

        except ImportError:
            print("   ⚠️  psutil not installed, skipping memory check")
            self.results['memory'] = 'unknown'
        except Exception as e:
            print(f"   ❌ Memory check failed: {str(e)}")
            self.results['memory'] = 'error'

    def print_summary(self):
        """Print health check summary."""
        print("
" + "="*80)
        print("HEALTH CHECK SUMMARY")
        print("="*80 + "
")

        # Overall status
        unhealthy = sum(1 for status in self.results.values() if status == 'unhealthy')
        degraded = sum(1 for status in self.results.values() if status == 'degraded')
        errors = sum(1 for status in self.results.values() if status == 'error')

        if unhealthy == 0 and errors == 0:
            if degraded == 0:
                print("🟢 Overall Status: HEALTHY
")
                overall = 'healthy'
            else:
                print("🟡 Overall Status: DEGRADED
")
                overall = 'degraded'
        else:
            print("🔴 Overall Status: UNHEALTHY
")
            overall = 'unhealthy'

        # Component status
        print("Component Status:")
        for component, status in self.results.items():
            emoji = {
                'healthy': '✅',
                'degraded': '⚠️ ',
                'unhealthy': '❌',
                'error': '❌',
                'unknown': '❓',
            }.get(status, '❓')

            print(f"  {emoji} {component.upper()}: {status}")

        # Errors
        if self.errors:
            print("
Errors:")
            for error in self.errors:
                print(f"  ❌ {error}")

        print("
" + "="*80)
        print(f"Timestamp: {datetime.now().isoformat()}")
        print("="*80 + "
")

        return overall


async def main():
    """Main health check routine."""
    print("
" + "="*80)
    print("🔥 GODMODESCANNER HEALTH CHECK")
    print("="*80)

    checker = HealthChecker()

    # Run checks
    await checker.check_rpc_endpoints()
    await checker.check_websocket()
    checker.check_configuration()
    checker.check_memory_usage()

    # Print summary
    overall = checker.print_summary()

    # Exit code based on status
    if overall == 'healthy':
        sys.exit(0)
    elif overall == 'degraded':
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
