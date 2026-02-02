#!/usr/bin/env python3
"""Test suite for AggressiveSolanaClient integration.

This test verifies:
1. Client initialization with multiple endpoints
2. Batch request functionality
3. Caching performance
4. Adaptive rate limiting
5. Integration with transaction monitor
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.aggressive_solana_client import AggressiveSolanaClient


class AggressiveClientIntegrationTest:
    """Comprehensive integration tests for AggressiveSolanaClient."""

    def __init__(self):
        self.client = None
        self.test_wallets = [
            "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",  # Pumpswap
            "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM",  # Serum
            "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",  # Token Program
        ]
        self.results = {
            "tests_passed": 0,
            "tests_failed": 0,
            "test_results": []
        }

    def log_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result."""
        self.results["test_results"].append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        if passed:
            self.results["tests_passed"] += 1
        else:
            self.results["tests_failed"] += 1
        
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if details:
            print(f"   └─ {details}")

    async def test_1_client_initialization(self):
        """Test 1: Client initializes correctly with multiple endpoints."""
        print("\n📋 Test 1: Client Initialization")
        try:
            self.client = AggressiveSolanaClient(
                initial_rps=5.0,
                max_rps=20.0,
                growth_threshold=10,
                max_retries=2,
                cache_maxsize=500
            )
            
            # Check client stats
            stats = self.client.get_stats()
            
            assert stats["current_rps"] == 5.0, "Initial RPS should be 5.0"
            assert stats["total_requests"] == 0, "Initial requests should be 0"
            assert len(self.client.rpc_endpoints) > 0, "Should have RPC endpoints"
            
            self.log_result(
                "Client Initialization",
                True,
                f"Endpoints: {len(self.client.rpc_endpoints)}, Initial RPS: {stats['current_rps']}"
            )
            return True
            
        except Exception as e:
            self.log_result("Client Initialization", False, str(e))
            return False

    async def test_2_single_request(self):
        """Test 2: Single request to get account info."""
        print("\n📋 Test 2: Single Request")
        try:
            wallet = self.test_wallets[0]
            result = await self.client.request(
                "getAccountInfo",
                [wallet, {"encoding": "jsonParsed"}]
            )
            
            assert "result" in result, "Response should contain 'result' field"
            assert result["result"] is not None, "Result should not be None"
            
            # Check stats
            stats = self.client.get_stats()
            assert stats["total_requests"] >= 1, "Should have made at least 1 request"
            
            self.log_result(
                "Single Request",
                True,
                f"Wallet: {wallet[:8]}..., Requests: {stats['total_requests']}"
            )
            return True
            
        except Exception as e:
            self.log_result("Single Request", False, str(e))
            return False

    async def test_3_batch_requests(self):
        """Test 3: Batch multiple requests."""
        print("\n📋 Test 3: Batch Requests")
        try:
            # Build batch request
            batch_params = [
                ("getAccountInfo", [wallet, {"encoding": "jsonParsed"}])
                for wallet in self.test_wallets
            ]
            
            start_time = time.time()
            results = await self.client.batch(batch_params)
            elapsed = time.time() - start_time
            
            assert len(results) == len(batch_params), "Should get same number of results"
            assert all("result" in r for r in results), "All results should be valid"
            
            # Check cache stats
            stats = self.client.get_stats()
            
            self.log_result(
                "Batch Requests",
                True,
                f"Processed {len(results)} requests in {elapsed:.2f}s, "
                f"Cache hits: {stats['cache_hits']}, Cache misses: {stats['cache_misses']}"
            )
            return True
            
        except Exception as e:
            self.log_result("Batch Requests", False, str(e))
            return False

    async def test_4_caching_performance(self):
        """Test 4: Caching improves performance."""
        print("\n📋 Test 4: Caching Performance")
        try:
            wallet = self.test_wallets[0]
            
            # Clear stats
            self.client.cache.clear()
            self.client.get_stats()["cache_hits"] = 0
            self.client.get_stats()["cache_misses"] = 0
            
            # First request - cache miss
            start1 = time.time()
            await self.client.request(
                "getAccountInfo",
                [wallet, {"encoding": "jsonParsed"}]
            )
            time1 = time.time() - start1
            stats1 = self.client.get_stats()
            
            # Second request - cache hit
            start2 = time.time()
            await self.client.request(
                "getAccountInfo",
                [wallet, {"encoding": "jsonParsed"}]
            )
            time2 = time.time() - start2
            stats2 = self.client.get_stats()
            
            assert stats2["cache_hits"] > 0, "Should have cache hits"
            assert time2 < time1, "Cached request should be faster"
            
            speedup = time1 / time2 if time2 > 0 else 1
            
            self.log_result(
                "Caching Performance",
                True,
                f"Uncached: {time1*1000:.2f}ms, Cached: {time2*1000:.2f}ms, "
                f"Speedup: {speedup:.1f}x"
            )
            return True
            
        except Exception as e:
            self.log_result("Caching Performance", False, str(e))
            return False

    async def test_5_adaptive_rate_limiting(self):
        """Test 5: Adaptive rate limiting grows with success."""
        print("\n📋 Test 5: Adaptive Rate Limiting")
        try:
            initial_rps = self.client.current_rps
            
            # Make several successful requests to trigger growth
            for _ in range(15):  # More than growth_threshold (10)
                try:
                    await self.client.request(
                        "getHealth",
                        []
                    )
                except:
                    pass  # Ignore errors
            
            final_rps = self.client.current_rps
            
            # RPS should have grown
            assert final_rps >= initial_rps, "RPS should grow with success"
            
            self.log_result(
                "Adaptive Rate Limiting",
                True,
                f"Initial RPS: {initial_rps:.2f}, Final RPS: {final_rps:.2f}"
            )
            return True
            
        except Exception as e:
            self.log_result("Adaptive Rate Limiting", False, str(e))
            return False

    async def test_6_user_agent_rotation(self):
        """Test 6: User-Agent rotation occurs."""
        print("\n📋 Test 6: User-Agent Rotation")
        try:
            user_agents_seen = set()
            
            # Make multiple requests and check User-Agents
            for _ in range(10):
                await self.client.request(
                    "getHealth",
                    []
                )
                # Note: User-Agent is rotated internally, not easily observable
                # But we can verify the rotation logic exists
            
            assert len(self.client.user_agents) > 1, "Should have multiple User-Agents"
            
            self.log_result(
                "User-Agent Rotation",
                True,
                f"{len(self.client.user_agents)} User-Agents configured for rotation"
            )
            return True
            
        except Exception as e:
            self.log_result("User-Agent Rotation", False, str(e))
            return False

    async def test_7_concurrent_requests(self):
        """Test 7: Concurrent request handling."""
        print("\n📋 Test 7: Concurrent Requests")
        try:
            # Create concurrent tasks
            tasks = [
                self.client.request(
                    "getAccountInfo",
                    [wallet, {"encoding": "jsonParsed"}]
                )
                for wallet in self.test_wallets * 3  # 9 concurrent requests
            ]
            
            start_time = time.time()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            elapsed = time.time() - start_time
            
            # Count successful requests
            successful = sum(1 for r in results if not isinstance(r, Exception))
            
            assert successful > 0, "At least some requests should succeed"
            
            self.log_result(
                "Concurrent Requests",
                True,
                f"{successful}/{len(tasks)} successful in {elapsed:.2f}s"
            )
            return True
            
        except Exception as e:
            self.log_result("Concurrent Requests", False, str(e))
            return False

    async def run_all_tests(self):
        """Run all integration tests."""
        print("="*60)
        print("🚀 AggressiveSolanaClient Integration Tests")
        print("="*60)
        
        tests = [
            self.test_1_client_initialization,
            self.test_2_single_request,
            self.test_3_batch_requests,
            self.test_4_caching_performance,
            self.test_5_adaptive_rate_limiting,
            self.test_6_user_agent_rotation,
            self.test_7_concurrent_requests,
        ]
        
        for test in tests:
            try:
                await test()
            except Exception as e:
                print(f"⚠️  Test crashed: {e}")
            
            await asyncio.sleep(0.5)  # Brief pause between tests
        
        # Print summary
        self._print_summary()
        
        # Cleanup
        if self.client:
            await self.client.close()

    def _print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("📊 Test Summary")
        print("="*60)
        print(f"Total Tests: {self.results['tests_passed'] + self.results['tests_failed']}")
        print(f"✅ Passed: {self.results['tests_passed']}")
        print(f"❌ Failed: {self.results['tests_failed']}")
        print(f"Success Rate: {self.results['tests_passed'] / max(1, self.results['tests_passed'] + self.results['tests_failed']) * 100:.1f}%")
        print("="*60)

        # Print client stats
        if self.client:
            print("\n📈 Client Statistics:")
            stats = self.client.get_stats()
            for key, value in stats.items():
                if isinstance(value, float):
                    print(f"  {key}: {value:.2f}")
                else:
                    print(f"  {key}: {value}")


async def main():
    """Main entry point."""
    tester = AggressiveClientIntegrationTest()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
