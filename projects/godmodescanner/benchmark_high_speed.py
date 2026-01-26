#!/usr/bin/env python3
"""
High-Performance Benchmark for AggressiveSolanaClient

This benchmark tests the performance of the high-speed RPC client
with 1000 concurrent requests to demonstrate the speed improvements.
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any

from utils.high_speed_client import AggressiveSolanaClient
import orjson


class PerformanceBenchmark:
    """
    Performance benchmarking utility for AggressiveSolanaClient.
    """
    
    def __init__(self, concurrency: int = 100, total_requests: int = 1000):
        self.concurrency = concurrency
        self.total_requests = total_requests
        self.test_wallet = "SystemProgram11111111111111111111111111111111"
        self.results: List[float] = []
        self.errors: List[str] = []
    
    async def single_request(self, client: AggressiveSolanaClient) -> float:
        """
        Execute a single RPC request and measure latency.
        
        Args:
            client: AggressiveSolanaClient instance
        
        Returns:
            Latency in milliseconds
        """
        start = time.perf_counter()
        try:
            result = await client.request("getBalance", [self.test_wallet])
            end = time.perf_counter()
            latency_ms = (end - start) * 1000
            if result and 'result' in result:
                return latency_ms
            else:
                self.errors.append(str(result.get('error', 'Unknown error')))
                return latency_ms
        except Exception as e:
            end = time.perf_counter()
            self.errors.append(str(e))
            return (end - start) * 1000
    
    async def concurrent_burst(self, client: AggressiveSolanaClient, num_requests: int) -> List[float]:
        """
        Execute a burst of concurrent requests.
        
        Args:
            client: AggressiveSolanaClient instance
            num_requests: Number of requests to execute
        
        Returns:
            List of latencies in milliseconds
        """
        tasks = [self.single_request(client) for _ in range(num_requests)]
        return await asyncio.gather(*tasks)
    
    async def run_benchmark(self) -> Dict[str, Any]:
        """
        Run the complete benchmark test.
        
        Returns:
            Benchmark results dictionary
        """
        print("\n" + "="*70)
        print("🚀 AGGRESSIVE SOLANA CLIENT - HIGH PERFORMANCE BENCHMARK")
        print("="*70)
        print(f"Configuration:")
        print(f"  - Concurrency Level: {self.concurrency}")
        print(f"  - Total Requests: {self.total_requests}")
        print(f"  - Test Wallet: {self.test_wallet}")
        print(f"  - Technology Stack: uvloop + httpx + orjson")
        print("="*70)
        
        # Warm-up phase
        print("\n📝 Phase 1: Warm-up (10 requests)...")
        async with AggressiveSolanaClient() as client:
            warmup_times = await self.concurrent_burst(client, 10)
            avg_warmup = statistics.mean(warmup_times)
            print(f"✅ Warm-up complete. Avg latency: {avg_warmup:.2f}ms")
        
        # Main benchmark
        print(f"\n🔥 Phase 2: Full Benchmark ({self.total_requests} requests)...")
        
        start_time = time.time()
        
        async with AggressiveSolanaClient() as client:
            # Execute requests in batches of concurrency level
            remaining = self.total_requests
            batch_num = 0
            
            while remaining > 0:
                batch_size = min(self.concurrency, remaining)
                batch_num += 1
                
                batch_times = await self.concurrent_burst(client, batch_size)
                self.results.extend(batch_times)
                
                remaining -= batch_size
                
                # Progress indicator
                progress = ((self.total_requests - remaining) / self.total_requests) * 100
                print(f"  Progress: {progress:.1f}% ({self.total_requests - remaining}/{self.total_requests} requests)", end='\r')
            
            # Get client metrics
            metrics = client.get_metrics()
        
        end_time = time.time()
        total_elapsed = end_time - start_time
        
        # Calculate statistics
        successful_requests = len(self.results)
        latencies = self.results
        
        if latencies:
            min_latency = min(latencies)
            max_latency = max(latencies)
            avg_latency = statistics.mean(latencies)
            median_latency = statistics.median(latencies)
            p90_latency = statistics.quantiles(latencies, n=10)[8] if len(latencies) >= 10 else avg_latency
            p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else avg_latency
            p99_latency = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else avg_latency
            std_dev = statistics.stdev(latencies) if len(latencies) > 1 else 0
        else:
            min_latency = max_latency = avg_latency = median_latency = 0
            p90_latency = p95_latency = p99_latency = std_dev = 0
        
        # Print results
        print("\n\n" + "="*70)
        print("📊 BENCHMARK RESULTS")
        print("="*70)
        
        print(f"\n📈 THROUGHPUT METRICS:")
        print(f"  Total Time: {total_elapsed:.2f} seconds")
        print(f"  Total Requests: {metrics['total_requests']}")
        print(f"  Successful Requests: {metrics['successful_requests']}")
        print(f"  Failed Requests: {metrics['failed_requests']}")
        print(f"  Rate Limited Requests: {metrics['rate_limited_requests']}")
        print(f"  Requests/Second: {self.total_requests / total_elapsed:.2f}")
        print(f"  Success Rate: {metrics['success_rate']:.2f}%")
        
        print(f"\n⚡ LATENCY METRICS (milliseconds):")
        print(f"  Minimum: {min_latency:.2f}ms")
        print(f"  Maximum: {max_latency:.2f}ms")
        print(f"  Average: {avg_latency:.2f}ms")
        print(f"  Median: {median_latency:.2f}ms")
        print(f"  P90: {p90_latency:.2f}ms")
        print(f"  P95: {p95_latency:.2f}ms")
        print(f"  P99: {p99_latency:.2f}ms")
        print(f"  Std Dev: {std_dev:.2f}ms")
        
        print(f"\n🎯 PERFORMANCE GRADE:")
        rps = self.total_requests / total_elapsed
        if rps > 500:
            grade = "A+ (EXCELLENT)"
            emoji = "🏆"
        elif rps > 300:
            grade = "A (VERY GOOD)"
            emoji = "⭐"
        elif rps > 200:
            grade = "B (GOOD)"
            emoji = "👍"
        elif rps > 100:
            grade = "C (ACCEPTABLE)"
            emoji = "✅"
        else:
            grade = "D (NEEDS IMPROVEMENT)"
            emoji = "⚠️"
        
        print(f"  {emoji} Grade: {grade}")
        
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            unique_errors = list(set(self.errors))
            for error in unique_errors[:5]:
                print(f"  - {error}")
        
        print("="*70)
        
        # Return results
        return {
            "concurrency": self.concurrency,
            "total_requests": self.total_requests,
            "successful_requests": successful_requests,
            "failed_requests": metrics['failed_requests'],
            "rate_limited": metrics['rate_limited_requests'],
            "total_time_seconds": total_elapsed,
            "requests_per_second": self.total_requests / total_elapsed,
            "success_rate": metrics['success_rate'],
            "latency_ms": {
                "min": min_latency,
                "max": max_latency,
                "avg": avg_latency,
                "median": median_latency,
                "p90": p90_latency,
                "p95": p95_latency,
                "p99": p99_latency,
                "std_dev": std_dev
            },
            "grade": grade
        }


async def main():
    """Main entry point."""
    benchmark = PerformanceBenchmark(
        concurrency=100,
        total_requests=1000
    )
    
    results = await benchmark.run_benchmark()
    
    # Save results to file
    results_file = "benchmark_high_speed_results.json"
    with open(results_file, 'wb') as f:
        f.write(orjson.dumps(results, option=orjson.OPT_INDENT_2))
    
    print(f"\n💾 Results saved to: {results_file}")
    
    return results


if __name__ == "__main__":
    results = asyncio.run(main())
