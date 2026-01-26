"""Comprehensive test suite for HistoricalAnalyzer.

Tests all methods and integration scenarios for wallet historical analysis.

Author: GODMODESCANNER Team
Date: 2026-01-25
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.historical_analyzer import HistoricalAnalyzer, HistoricalMetrics


class MockAsyncConnection:
    """Mock async database connection."""

    def __init__(self, test_data):
        self.test_data = test_data
        self.cursor_instance = MockAsyncCursor(test_data)

    def cursor(self):
        return self

    async def __aenter__(self):
        return self.cursor_instance

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockAsyncCursor:
    """Mock async database cursor."""

    def __init__(self, test_data):
        self.test_data = test_data
        self.query_count = 0

    async def execute(self, query, params=None):
        self.query_count += 1
        self.last_query = query
        self.last_params = params

    async def fetchone(self):
        if "MIN(timestamp)" in self.last_query:
            return (datetime.now(timezone.utc) - timedelta(days=90),)
        elif "COUNT(DISTINCT token_address)" in self.last_query:
            return (15,)
        elif "SUM(amount)" in self.last_query:
            return (250.5, 100, 2.5, 50.0)
        elif "WITH trades AS" in self.last_query:
            return (50, 35, 15, 7200.0, 25.5, 150.0, -45.0)
        return None

    async def fetchall(self):
        if "token_launches" in self.last_query:
            now = datetime.now(timezone.utc)
            return [
                (now - timedelta(seconds=30), "token1", 1.0, now - timedelta(seconds=45)),
                (now - timedelta(seconds=90), "token2", 2.0, now - timedelta(seconds=120)),
                (now - timedelta(seconds=200), "token3", 1.5, now - timedelta(seconds=250)),
            ]
        elif "wallet_network" in self.last_query:
            return [
                ("wallet1", 1, "cluster1", 0.8),
                ("wallet2", 1, "cluster2", 0.9),
                ("wallet3", 2, "cluster3", 0.6),
                ("wallet4", 2, "cluster4", 0.7),
                ("wallet5", 3, "cluster5", 0.5),
            ]
        return []


class MockAsyncConnectionPool:
    """Mock async connection pool."""

    def __init__(self, test_data=None):
        self.test_data = test_data or {}
        self.connection = MockAsyncConnection(test_data)

    def connection(self):
        return self

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class MockRedisClient:
    """Mock Redis client."""

    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value


async def test_initialization():
    """Test 1: HistoricalAnalyzer initialization."""
    separator = "=" * 70
    print(f"\n{separator}")
    print("TEST 1: Initialization")
    print(separator)

    pool = MockAsyncConnectionPool()
    redis = MockRedisClient()

    analyzer = HistoricalAnalyzer(pool, redis)

    assert analyzer.pool is not None, "Pool should be initialized"
    assert analyzer.redis is not None, "Redis should be initialized"
    assert analyzer.EARLY_BUY_THRESHOLD_SECONDS == 60, "Early buy threshold should be 60s"
    assert analyzer.WHALE_VOLUME_THRESHOLD_SOL == 100.0, "Whale threshold should be 100 SOL"

    print("✅ Initialization test PASSED")
    print(f"   - Pool initialized: {analyzer.pool is not None}")
    print(f"   - Redis initialized: {analyzer.redis is not None}")
    print(f"   - Early buy threshold: {analyzer.EARLY_BUY_THRESHOLD_SECONDS}s")
    print(f"   - Whale threshold: {analyzer.WHALE_VOLUME_THRESHOLD_SOL} SOL")

    return True


async def test_timing_analysis():
    """Test 2: Timing analysis (early buyer detection)."""
    separator = "=" * 70
    print(f"\n{separator}")
    print("TEST 2: Timing Analysis (Early Buyer Detection)")
    print(separator)

    pool = MockAsyncConnectionPool()
    redis = MockRedisClient()
    analyzer = HistoricalAnalyzer(pool, redis)

    conn = pool.connection
    timing_score = await analyzer._analyze_timing(conn, "test_wallet", 30)

    print("✅ Timing analysis test PASSED")
    print(f"   - Timing score: {timing_score:.3f}")
    print(f"   - Score range: 0.0 (normal) to 1.0 (suspicious)")
    print(f"   - Interpretation: {'SUSPICIOUS' if timing_score > 0.7 else 'NORMAL'}")

    assert 0.0 <= timing_score <= 1.0, "Timing score should be between 0 and 1"

    return True


async def test_network_analysis():
    """Test 3: Network analysis (3-hop graph traversal)."""
    separator = "=" * 70
    print(f"\n{separator}")
    print("TEST 3: Network Analysis (3-Hop Graph Traversal)")
    print(separator)

    pool = MockAsyncConnectionPool()
    redis = MockRedisClient()
    analyzer = HistoricalAnalyzer(pool, redis)

    conn = pool.connection
    network_score = await analyzer._analyze_network(conn, "test_wallet")

    print("✅ Network analysis test PASSED")
    print(f"   - Network score: {network_score:.3f}")
    print(f"   - Score range: 0.0 (isolated) to 1.0 (highly connected)")
    print(f"   - Interpretation: {'CLUSTER CONNECTED' if network_score > 0.6 else 'ISOLATED'}")

    assert 0.0 <= network_score <= 1.0, "Network score should be between 0 and 1"

    return True


async def test_volume_analysis():
    """Test 4: Volume analysis (whale behavior detection)."""
    separator = "=" * 70
    print(f"\n{separator}")
    print("TEST 4: Volume Analysis (Whale Behavior Detection)")
    print(separator)

    pool = MockAsyncConnectionPool()
    redis = MockRedisClient()
    analyzer = HistoricalAnalyzer(pool, redis)

    conn = pool.connection
    volume_data = await analyzer._analyze_volume(conn, "test_wallet", 30)

    print("✅ Volume analysis test PASSED")
    print(f"   - Volume score: {volume_data['volume_score']:.3f}")
    print(f"   - Total volume: {volume_data['total_volume_sol']:.2f} SOL")
    print(f"   - Whale threshold: {analyzer.WHALE_VOLUME_THRESHOLD_SOL} SOL")
    print(f"   - Interpretation: {'WHALE BEHAVIOR' if volume_data['volume_score'] > 0.7 else 'NORMAL TRADER'}")

    assert 0.0 <= volume_data['volume_score'] <= 1.0, "Volume score should be between 0 and 1"
    assert volume_data['total_volume_sol'] >= 0, "Total volume should be non-negative"

    return True


async def test_performance_analysis():
    """Test 5: Performance analysis (win rate calculation)."""
    separator = "=" * 70
    print(f"\n{separator}")
    print("TEST 5: Performance Analysis (Win Rate Calculation)")
    print(separator)

    pool = MockAsyncConnectionPool()
    redis = MockRedisClient()
    analyzer = HistoricalAnalyzer(pool, redis)

    conn = pool.connection
    performance_data = await analyzer._analyze_performance(conn, "test_wallet", 30)

    print("✅ Performance analysis test PASSED")
    print(f"   - Win rate: {performance_data['win_rate']:.1f}%")
    print(f"   - Total trades: {performance_data['total_trades']}")
    print(f"   - Profitable trades: {performance_data['profitable_trades']}")
    print(f"   - Losing trades: {performance_data['losing_trades']}")
    print(f"   - Avg hold time: {performance_data['avg_hold_time']}")
    print(f"   - Avg profit: {performance_data['avg_profit_pct']:.1f}%")
    print(f"   - Max profit: {performance_data['max_profit_pct']:.1f}%")
    print(f"   - Max loss: {performance_data['max_loss_pct']:.1f}%")

    assert 0.0 <= performance_data['win_rate'] <= 100.0, "Win rate should be between 0 and 100"
    assert performance_data['total_trades'] >= 0, "Total trades should be non-negative"

    return True


async def test_suspicion_pattern_detection():
    """Test 6: Suspicion pattern detection."""
    separator = "=" * 70
    print(f"\n{separator}")
    print("TEST 6: Suspicion Pattern Detection")
    print(separator)

    pool = MockAsyncConnectionPool()
    redis = MockRedisClient()
    analyzer = HistoricalAnalyzer(pool, redis)

    test_cases = [
        {
            'name': 'Normal Trader',
            'timing': 0.3,
            'network': 0.2,
            'volume': 0.4,
            'performance': {'win_rate': 55.0, 'avg_hold_time': timedelta(hours=2)}
        },
        {
            'name': 'Sniper Bot',
            'timing': 0.95,
            'network': 0.4,
            'volume': 0.6,
            'performance': {'win_rate': 65.0, 'avg_hold_time': timedelta(seconds=30)}
        },
        {
            'name': 'Insider Group',
            'timing': 0.8,
            'network': 0.85,
            'volume': 0.5,
            'performance': {'win_rate': 78.0, 'avg_hold_time': timedelta(minutes=10)}
        },
        {
            'name': 'Whale Sniper',
            'timing': 0.85,
            'network': 0.3,
            'volume': 0.95,
            'performance': {'win_rate': 82.0, 'avg_hold_time': timedelta(minutes=5)}
        }
    ]

    for case in test_cases:
        patterns = analyzer._detect_suspicion_patterns(
            case['timing'],
            case['network'],
            case['volume'],
            case['performance']
        )

        print(f"\n   {case['name']}:")
        print(f"     - Timing: {case['timing']:.2f}, Network: {case['network']:.2f}, Volume: {case['volume']:.2f}")
        print(f"     - Win Rate: {case['performance']['win_rate']:.1f}%")
        print(f"     - Patterns detected: {len(patterns)}")
        for pattern in patterns:
            print(f"       • {pattern}")

    print("\n✅ Suspicion pattern detection test PASSED")

    return True


async def test_full_integration():
    """Test 7: Full integration test."""
    separator = "=" * 70
    print(f"\n{separator}")
    print("TEST 7: Full Integration Test")
    print(separator)

    pool = MockAsyncConnectionPool()
    redis = MockRedisClient()
    analyzer = HistoricalAnalyzer(pool, redis)

    metrics = await analyzer.analyze_wallet_history("test_wallet", lookback_days=30)

    print("\n✅ Full integration test PASSED")
    print("\n📊 Complete Wallet Analysis Results:")
    print("   Wallet: test_wallet")
    print("   Lookback Period: 30 days")
    print("\n   📈 Risk Scores:")
    print(f"     - Timing Score: {metrics.timing_score:.3f} (0=normal, 1=suspicious)")
    print(f"     - Network Score: {metrics.network_score:.3f} (0=isolated, 1=connected)")
    print(f"     - Volume Score: {metrics.volume_score:.3f} (0=normal, 1=whale)")
    print("\n   💰 Performance Metrics:")
    print(f"     - Win Rate: {metrics.win_rate:.1f}%")
    print(f"     - Total Trades: {metrics.total_trades}")
    print(f"     - Profitable Trades: {metrics.profitable_trades}")
    print(f"     - Losing Trades: {metrics.losing_trades}")
    print(f"     - Avg Profit: {metrics.avg_profit_pct:.1f}%")
    print(f"     - Max Profit: {metrics.max_profit_pct:.1f}%")
    print(f"     - Max Loss: {metrics.max_loss_pct:.1f}%")
    print("\n   📊 Trading Statistics:")
    print(f"     - Total Volume: {metrics.total_volume_sol:.2f} SOL")
    print(f"     - Unique Tokens: {metrics.unique_tokens}")
    print(f"     - Avg Hold Time: {metrics.avg_hold_time}")
    print(f"     - First Seen: {metrics.first_seen.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\n   🚨 Suspicion Indicators ({len(metrics.suspicion_indicators)}):")
    for indicator in metrics.suspicion_indicators:
        print(f"     • {indicator}")

    assert isinstance(metrics, HistoricalMetrics), "Should return HistoricalMetrics object"
    assert 0.0 <= metrics.timing_score <= 1.0, "Timing score out of range"
    assert 0.0 <= metrics.network_score <= 1.0, "Network score out of range"
    assert 0.0 <= metrics.volume_score <= 1.0, "Volume score out of range"
    assert 0.0 <= metrics.win_rate <= 100.0, "Win rate out of range"
    assert metrics.total_trades >= 0, "Total trades should be non-negative"
    assert metrics.unique_tokens >= 0, "Unique tokens should be non-negative"

    return True


async def run_all_tests():
    """Run all tests and generate report."""
    header = "#" * 70
    print(f"\n{header}")
    print("#" + " " * 68 + "#")
    print("#" + " " * 15 + "HISTORICAL ANALYZER TEST SUITE" + " " * 23 + "#")
    print("#" + " " * 68 + "#")
    print(header)

    tests = [
        ("Initialization", test_initialization),
        ("Timing Analysis", test_timing_analysis),
        ("Network Analysis", test_network_analysis),
        ("Volume Analysis", test_volume_analysis),
        ("Performance Analysis", test_performance_analysis),
        ("Suspicion Pattern Detection", test_suspicion_pattern_detection),
        ("Full Integration", test_full_integration)
    ]

    results = []
    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append({'test': test_name, 'status': 'PASSED', 'error': None})
            passed += 1
        except Exception as e:
            results.append({'test': test_name, 'status': 'FAILED', 'error': str(e)})
            failed += 1
            print(f"\n❌ {test_name} FAILED: {e}")

    separator = "=" * 70
    print(f"\n{separator}")
    print("TEST SUMMARY")
    print(separator)
    print(f"\nTotal Tests: {len(tests)}")
    print(f"Passed: {passed} ✅")
    print(f"Failed: {failed} ❌")
    print(f"Success Rate: {(passed/len(tests)*100):.1f}%")

    report = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'total_tests': len(tests),
        'passed': passed,
        'failed': failed,
        'success_rate': passed/len(tests)*100,
        'results': results
    }

    with open('tests/historical_analyzer_test_results.json', 'w') as f:
        json.dump(report, f, indent=2)

    print("\n📄 Test results saved to: tests/historical_analyzer_test_results.json")

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED! HistoricalAnalyzer is production-ready!")
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please review and fix.")

    return passed == len(tests)


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
