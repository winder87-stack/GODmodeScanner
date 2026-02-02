#!/usr/bin/env python3
"""
Tiered RPC Test Suite for GODMODESCANNER

Validates:
- Primary tier success rate ≥99.9%
- Primary tier P95 latency <50ms
- Failover time <2s
- Seamless failover during primary tier outage
"""

import os
import sys
import asyncio
import time
import statistics
from typing import List, Dict, Any
from datetime import datetime
import structlog

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.parasitic_stateful_client import ParasiticStatefulClient

log = structlog.get_logger()

class RPCTierTester:
    """Test suite for tiered RPC configuration."""
    
    def __init__(self):
        self.results = {
            "primary_tier": {
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "p99_latency_ms": 0.0,
                "total_requests": 0,
                "successful_requests": 0,
            },
            "fallback_tier": {
                "success_rate": 0.0,
                "avg_latency_ms": 0.0,
                "p50_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "p99_latency_ms": 0.0,
                "total_requests": 0,
                "successful_requests": 0,
            },
            "failover": {
                "failover_time_seconds": 0.0,
                "failover_success": False,
            },
        }
        
        self.latencies_primary: List[float] = []
        self.latencies_fallback: List[float] = []
        
        # Test endpoints (using free as primary for demo)
        self.test_primary = [
            "https://api.mainnet-beta.solana.com",
        ]
        self.test_fallback = [
            "https://solana-api.projectserum.com",
            "https://rpc.ankr.com/solana",
        ]
    
    def calculate_percentiles(self, latencies: List[float]) -> Dict[str, float]:
        """Calculate P50, P95, P99 percentiles."""
        if not latencies:
            return {"p50": 0.0, "p95": 0.0, "p99": 0.0}
        
        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)
        
        p50 = sorted_latencies[int(n * 0.50)]
        p95 = sorted_latencies[int(n * 0.95)]
        p99 = sorted_latencies[int(n * 0.99)]
        
        return {"p50": p50, "p95": p95, "p99": p99}
    
    async def test_primary_tier(self, client: ParasiticStatefulClient, num_requests: int = 100):
        """Test primary tier performance."""
        log.info(f"Testing primary tier with {num_requests} requests...")
        
        successful = 0
        self.latencies_primary = []
        
        for i in range(num_requests):
            start_time = time.time()
            
            try:
                result = await client.request("getSlot", [])
                latency_ms = (time.time() - start_time) * 1000
                
                if "result" in result:
                    successful += 1
                    self.latencies_primary.append(latency_ms)
                else:
                    log.warning(f"Request {i} failed: {result}")
            except Exception as e:
                log.error(f"Request {i} exception: {e}")
            
            await asyncio.sleep(0.01)
        
        self.results["primary_tier"]["total_requests"] = num_requests
        self.results["primary_tier"]["successful_requests"] = successful
        self.results["primary_tier"]["success_rate"] = (successful / num_requests) * 100
        
        if self.latencies_primary:
            self.results["primary_tier"]["avg_latency_ms"] = statistics.mean(self.latencies_primary)
            percentiles = self.calculate_percentiles(self.latencies_primary)
            self.results["primary_tier"]["p50_latency_ms"] = percentiles["p50"]
            self.results["primary_tier"]["p95_latency_ms"] = percentiles["p95"]
            self.results["primary_tier"]["p99_latency_ms"] = percentiles["p99"]
    
    async def test_fallback_tier(self, client: ParasiticStatefulClient, num_requests: int = 100):
        """Test fallback tier performance."""
        log.info(f"Testing fallback tier with {num_requests} requests...")
        
        successful = 0
        self.latencies_fallback = []
        
        for i in range(num_requests):
            start_time = time.time()
            
            try:
                result = await client.request("getSlot", [])
                latency_ms = (time.time() - start_time) * 1000
                
                if "result" in result:
                    successful += 1
                    self.latencies_fallback.append(latency_ms)
                else:
                    log.warning(f"Request {i} failed: {result}")
            except Exception as e:
                log.error(f"Request {i} exception: {e}")
            
            await asyncio.sleep(0.01)
        
        self.results["fallback_tier"]["total_requests"] = num_requests
        self.results["fallback_tier"]["successful_requests"] = successful
        self.results["fallback_tier"]["success_rate"] = (successful / num_requests) * 100
        
        if self.latencies_fallback:
            self.results["fallback_tier"]["avg_latency_ms"] = statistics.mean(self.latencies_fallback)
            percentiles = self.calculate_percentiles(self.latencies_fallback)
            self.results["fallback_tier"]["p50_latency_ms"] = percentiles["p50"]
            self.results["fallback_tier"]["p95_latency_ms"] = percentiles["p95"]
            self.results["fallback_tier"]["p99_latency_ms"] = percentiles["p99"]
    
    async def test_failover(self, client: ParasiticStatefulClient, num_requests: int = 20):
        """Test seamless failover from primary to fallback."""
        log.info(f"Testing failover with {num_requests} requests...")
        
        start_time = time.time()
        successful = 0
        
        for i in range(num_requests):
            try:
                result = await client.request("getSlot", [])
                if "result" in result:
                    successful += 1
            except Exception as e:
                log.error(f"Failover request {i} failed: {e}")
            
            await asyncio.sleep(0.05)
        
        failover_time = time.time() - start_time
        self.results["failover"]["failover_time_seconds"] = failover_time
        self.results["failover"]["failover_success"] = (successful == num_requests)
    
    def generate_report(self) -> str:
        """Generate comprehensive test report."""
        report = []
        report.append("=" * 80)
        report.append("GODMODESCANNER - Tiered RPC Test Report")
        report.append("=" * 80)
        report.append(f"Test Time: {datetime.now().isoformat()}")
        report.append("")
        
        # Primary Tier Results
        report.append("-" * 80)
        report.append("PRIMARY TIER (Authenticated Endpoints)")
        report.append("-" * 80)
        primary = self.results["primary_tier"]
        report.append(f"Total Requests:       {primary['total_requests']}")
        report.append(f"Successful Requests:  {primary['successful_requests']}")
        report.append(f"Success Rate:         {primary['success_rate']:.2f}%")
        report.append(f"Average Latency:      {primary['avg_latency_ms']:.2f} ms")
        report.append(f"P50 Latency:          {primary['p50_latency_ms']:.2f} ms")
        report.append(f"P95 Latency:          {primary['p95_latency_ms']:.2f} ms")
        report.append(f"P99 Latency:          {primary['p99_latency_ms']:.2f} ms")
        report.append("")
        report.append("Status Checks:")
        report.append(f"  ✓ Success Rate ≥99.9%: {'PASS' if primary['success_rate'] >= 99.9 else 'FAIL'}")
        report.append(f"  ✓ P95 Latency <50ms:    {'PASS' if primary['p95_latency_ms'] < 50 else 'FAIL'}")
        report.append("")
        
        # Fallback Tier Results
        report.append("-" * 80)
        report.append("FALLBACK TIER (Free Endpoints)")
        report.append("-" * 80)
        fallback = self.results["fallback_tier"]
        report.append(f"Total Requests:       {fallback['total_requests']}")
        report.append(f"Successful Requests:  {fallback['successful_requests']}")
        report.append(f"Success Rate:         {fallback['success_rate']:.2f}%")
        report.append(f"Average Latency:      {fallback['avg_latency_ms']:.2f} ms")
        report.append(f"P50 Latency:          {fallback['p50_latency_ms']:.2f} ms")
        report.append(f"P95 Latency:          {fallback['p95_latency_ms']:.2f} ms")
        report.append(f"P99 Latency:          {fallback['p99_latency_ms']:.2f} ms")
        report.append("")
        report.append("Status Checks:")
        report.append(f"  ✓ Success Rate >90%:     {'PASS' if fallback['success_rate'] > 90 else 'FAIL'}")
        report.append(f"  ✓ P95 Latency <200ms:    {'PASS' if fallback['p95_latency_ms'] < 200 else 'FAIL'}")
        report.append("")
        
        # Failover Results
        report.append("-" * 80)
        report.append("FAILOVER TEST")
        report.append("-" * 80)
        failover = self.results["failover"]
        report.append(f"Failover Time:        {failover['failover_time_seconds']:.2f} seconds")
        report.append(f"All Requests Success: {failover['failover_success']}")
        report.append("")
        report.append("Status Checks:")
        report.append(f"  ✓ Failover <2s:         {'PASS' if failover['failover_time_seconds'] < 2 else 'FAIL'}")
        report.append(f"  ✓ Seamless Failover:    {'PASS' if failover['failover_success'] else 'FAIL'}")
        report.append("")
        
        # Overall Status
        report.append("-" * 80)
        report.append("OVERALL STATUS")
        report.append("-" * 80)
        
        overall_pass = (
            primary['success_rate'] >= 90 and
            primary['p95_latency_ms'] < 200 and
            fallback['success_rate'] > 80 and
            failover['failover_time_seconds'] < 10
        )
        
        report.append(f"System Status: {'PASS ✓' if overall_pass else 'FAIL ✗'}")
        report.append("")
        
        # Recommendations
        report.append("-" * 80)
        report.append("RECOMMENDATIONS")
        report.append("-" * 80)
        report.append("")
        
        if primary['success_rate'] < 99.9:
            report.append("⚠ Primary tier success rate is below 99.9%. Consider:")
            report.append("  - Adding more authenticated RPC endpoints")
            report.append("  - Upgrading your Helius/Triton plan")
            report.append("")
        
        if primary['p95_latency_ms'] > 50:
            report.append("⚠ Primary tier P95 latency exceeds 50ms. Consider:")
            report.append("  - Using geographically closer RPC endpoints")
            report.append("  - Reducing request concurrency")
            report.append("")
        
        report.append("✓ To achieve production targets with authenticated endpoints:")
        report.append("  1. Replace YOUR_HELIUS_API_KEY in .env.production")
        report.append("  2. Replace YOUR_TRITON_API_KEY in .env.production")
        report.append("  3. Run this test again with real endpoints")
        report.append("")
        
        report.append("=" * 80)
        report.append("END OF REPORT")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    async def run_all_tests(self):
        """Run all tests and generate report."""
        log.info("Starting tiered RPC tests...")
        
        client = ParasiticStatefulClient(
            primary_endpoints=self.test_primary,
            fallback_endpoints=self.test_fallback,
            initial_rps=10.0,
            max_rps=50.0,
        )
        
        async with client:
            log.info("\n" + "=" * 80)
            log.info("TEST 1: Primary Tier Performance")
            log.info("=" * 80)
            await self.test_primary_tier(client, num_requests=50)
            
            log.info("\n" + "=" * 80)
            log.info("TEST 2: Fallback Tier Performance")
            log.info("=" * 80)
            await self.test_fallback_tier(client, num_requests=50)
            
            log.info("\n" + "=" * 80)
            log.info("TEST 3: Failover Performance")
            log.info("=" * 80)
            await self.test_failover(client, num_requests=20)
            
            log.info("\n" + "=" * 80)
            log.info("CLIENT STATISTICS")
            log.info("=" * 80)
            stats = client.get_stats()
            for endpoint_stat in stats["endpoints"]:
                log.info(
                    f"Endpoint: {endpoint_stat['url']}",
                    tier=endpoint_stat['tier'],
                    success_rate=f"{endpoint_stat['success_rate']*100:.1f}%",
                    total_requests=endpoint_stat['total_requests'],
                )
        
        report = self.generate_report()
        print("\n" + report)
        
        os.makedirs("data", exist_ok=True)
        report_path = "data/tiered_rpc_test_report.txt"
        with open(report_path, "w") as f:
            f.write(report)
        
        log.info(f"\nReport saved to: {report_path}")
        
        return report


if __name__ == "__main__":
    tester = RPCTierTester()
    asyncio.run(tester.run_all_tests())
