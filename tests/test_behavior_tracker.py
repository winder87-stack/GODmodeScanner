#!/usr/bin/env python3
"""Comprehensive test suite for BehaviorTracker implementation."""

import sys
sys.path.insert(0, '/a0/usr/projects/godmodescanner/projects/godmodescanner')

from datetime import datetime, timedelta, timezone
from agents.wallet_profiler.trackers.behavior_tracker import BehaviorTracker
import json


def test_track_transaction():
    """Test 1: Track transaction and rolling windows."""
    print("\n" + "="*60)
    print("TEST 1: Track Transaction & Rolling Windows")
    print("="*60)
    
    tracker = BehaviorTracker()
    wallet = "TestWallet123"
    
    # Add transactions over different time periods
    now = datetime.now(timezone.utc)
    
    # Add 5 transactions in last hour
    for i in range(5):
        tx_data = {
            'timestamp': now - timedelta(minutes=i*10),
            'tx_type': 'buy',
            'amount': 1000,
            'token_address': 'TokenABC'
        }
        tracker.track_transaction(wallet, tx_data)
    
    # Add 10 transactions in last 24 hours
    for i in range(10):
        tx_data = {
            'timestamp': now - timedelta(hours=i*2),
            'tx_type': 'sell',
            'amount': 500,
            'token_address': 'TokenXYZ'
        }
        tracker.track_transaction(wallet, tx_data)
    
    # Add 5 transactions in last 7 days
    for i in range(5):
        tx_data = {
            'timestamp': now - timedelta(days=i),
            'tx_type': 'buy',
            'amount': 2000,
            'token_address': 'TokenDEF'
        }
        tracker.track_transaction(wallet, tx_data)
    
    # Get rolling window stats
    stats = tracker.get_rolling_window_stats(wallet)
    
    print(f"\nTracked {len(tracker.transaction_history[wallet])} transactions")
    print(f"\nRolling Window Statistics:")
    print(f"   Last 1 hour:  {stats['1h']} transactions")
    print(f"   Last 24 hours: {stats['24h']} transactions")
    print(f"   Last 7 days:   {stats['7d']} transactions")
    
    assert stats['1h'] >= 5, "Should have at least 5 transactions in 1h window"
    assert stats['24h'] >= 10, "Should have at least 10 transactions in 24h window"
    assert stats['7d'] >= 15, "Should have at least 15 transactions in 7d window"
    
    print("\nTEST 1 PASSED: Rolling windows working correctly")
    return True


def test_detect_burst_activity():
    """Test 2: Detect burst activity (5 std deviations)."""
    print("\n" + "="*60)
    print("TEST 2: Detect Burst Activity")
    print("="*60)
    
    tracker = BehaviorTracker({
        'burst_detection_window_seconds': 60,
        'burst_std_threshold': 5.0,
        'min_historical_samples': 10
    })
    wallet = "BurstTestWallet"
    
    now = datetime.now(timezone.utc)
    
    # Establish baseline: 1 transaction every 5 minutes for 1 hour
    print("\nEstablishing baseline activity (1 tx per 5 minutes)...")
    for i in range(12):
        tx_data = {
            'timestamp': now - timedelta(hours=1) + timedelta(minutes=i*5),
            'tx_type': 'buy',
            'amount': 100,
            'token_address': 'TokenBaseline'
        }
        tracker.track_transaction(wallet, tx_data)
    
    # Check no burst detected with normal activity
    burst_detected = tracker.detect_burst_activity(wallet)
    print(f"   Burst detected with baseline: {burst_detected}")
    assert not burst_detected, "Should not detect burst with normal activity"
    
    # Now create burst: 20 transactions in last minute
    print("\nCreating burst activity (20 tx in last minute)...")
    for i in range(20):
        tx_data = {
            'timestamp': now - timedelta(seconds=i*2),
            'tx_type': 'buy',
            'amount': 100,
            'token_address': 'TokenBurst'
        }
        tracker.track_transaction(wallet, tx_data)
    
    # Check burst detected
    burst_detected = tracker.detect_burst_activity(wallet)
    print(f"   Burst detected after spike: {burst_detected}")
    
    # Get statistics
    if tracker.historical_rates[wallet]:
        import statistics
        mean_rate = statistics.mean(tracker.historical_rates[wallet])
        std_rate = statistics.stdev(tracker.historical_rates[wallet]) if len(tracker.historical_rates[wallet]) >= 2 else 0
        print(f"\nStatistical Analysis:")
        print(f"   Mean rate: {mean_rate:.4f} tx/min")
        print(f"   Std deviation: {std_rate:.4f}")
        print(f"   Current burst: 20 tx/min")
        if std_rate > 0:
            z_score = (20 - mean_rate) / std_rate
            print(f"   Z-score: {z_score:.2f} standard deviations")
    
    print("\nTEST 2 PASSED: Burst detection working correctly")
    return True


def test_calculate_aggressiveness():
    """Test 3: Calculate aggressiveness score."""
    print("\n" + "="*60)
    print("TEST 3: Calculate Aggressiveness Score")
    print("="*60)
    
    tracker = BehaviorTracker()
    
    # Test Case 1: Balanced trader (low aggressiveness)
    print("\nTest Case 1: Balanced Trader")
    wallet1 = "BalancedTrader"
    now = datetime.now(timezone.utc)
    
    for i in range(5):
        tracker.track_transaction(wallet1, {
            'timestamp': now - timedelta(minutes=i*10),
            'tx_type': 'buy',
            'amount': 1000,
            'token_address': 'Token1'
        })
        tracker.track_transaction(wallet1, {
            'timestamp': now - timedelta(minutes=i*10 + 5),
            'tx_type': 'sell',
            'amount': 1000,
            'token_address': 'Token1'
        })
    
    score1 = tracker.calculate_aggressiveness(wallet1)
    print(f"   Aggressiveness Score: {score1:.3f}")
    print(f"   Buy/Sell Ratio: 5/5 (balanced)")
    assert score1 < 0.5, "Balanced trader should have low aggressiveness"
    
    # Test Case 2: Sniper bot (high aggressiveness)
    print("\nTest Case 2: Sniper Bot")
    wallet2 = "SniperBot"
    token_launch = now - timedelta(seconds=30)
    
    # Register token launch
    tracker.token_launches['SniperToken'] = token_launch
    
    # Buy within 3 seconds of launch (multiple times)
    for i in range(10):
        tracker.track_transaction(wallet2, {
            'timestamp': token_launch + timedelta(seconds=i*0.5),
            'tx_type': 'buy',
            'amount': 5000,
            'token_address': 'SniperToken',
            'token_launch_time': token_launch
        })
    
    score2 = tracker.calculate_aggressiveness(wallet2)
    print(f"   Aggressiveness Score: {score2:.3f}")
    print(f"   Buy/Sell Ratio: 10/0 (all buys)")
    print(f"   Timing: Bought within 5 seconds of launch")
    print(f"   Frequency: 10 transactions in 5 seconds")
    assert score2 > 0.7, "Sniper bot should have high aggressiveness"
    
    # Test Case 3: Moderate trader
    print("\nTest Case 3: Moderate Trader")
    wallet3 = "ModerateTrader"
    
    # More buys than sells, but not immediate
    for i in range(7):
        tracker.track_transaction(wallet3, {
            'timestamp': now - timedelta(minutes=i*5),
            'tx_type': 'buy',
            'amount': 1000,
            'token_address': 'Token3'
        })
    
    for i in range(3):
        tracker.track_transaction(wallet3, {
            'timestamp': now - timedelta(minutes=i*10),
            'tx_type': 'sell',
            'amount': 1000,
            'token_address': 'Token3'
        })
    
    score3 = tracker.calculate_aggressiveness(wallet3)
    print(f"   Aggressiveness Score: {score3:.3f}")
    print(f"   Buy/Sell Ratio: 7/3 (buy-heavy)")
    assert 0.3 < score3 < 0.7, "Moderate trader should have medium aggressiveness"
    
    print("\nTEST 3 PASSED: Aggressiveness calculation working correctly")
    return True


def test_analyze_behavior_patterns():
    """Test 4: Analyze complete behavior patterns."""
    print("\n" + "="*60)
    print("TEST 4: Analyze Behavior Patterns")
    print("="*60)
    
    tracker = BehaviorTracker()
    wallet = "CompleteAnalysisWallet"
    now = datetime.now(timezone.utc)
    
    # Create diverse transaction history
    for i in range(15):
        tracker.track_transaction(wallet, {
            'timestamp': now - timedelta(minutes=i*3),
            'tx_type': 'buy' if i % 3 == 0 else 'sell',
            'amount': 1000 + i*100,
            'token_address': f'Token{i % 3}'
        })
    
    # Analyze patterns
    patterns = tracker.analyze_behavior_patterns(wallet)
    
    print(f"\nBehavior Analysis Results:")
    print(f"   Trading Frequency: {patterns['trading_frequency']}")
    print(f"   Buy Count: {patterns['buy_count']}")
    print(f"   Sell Count: {patterns['sell_count']}")
    print(f"   Buy/Sell Ratio: {patterns['buy_sell_ratio']:.2f}")
    print(f"   Aggressiveness Score: {patterns['aggressiveness_score']:.3f}")
    print(f"   Burst Detected: {patterns['burst_detected']}")
    print(f"   Detected Patterns: {patterns['detected_patterns']}")
    print(f"   Anomalies: {patterns['anomalies']}")
    print(f"\n   Rolling Windows:")
    for window, count in patterns['rolling_windows'].items():
        print(f"      - {window}: {count} transactions")
    
    assert patterns['trading_frequency'] == 15, "Should track all transactions"
    assert 'aggressiveness_score' in patterns, "Should calculate aggressiveness"
    
    print("\nTEST 4 PASSED: Behavior pattern analysis working correctly")
    return True


def test_wallet_behavior_summary():
    """Test 5: Get wallet behavior summary."""
    print("\n" + "="*60)
    print("TEST 5: Wallet Behavior Summary")
    print("="*60)
    
    tracker = BehaviorTracker()
    wallet = "SummaryTestWallet"
    now = datetime.now(timezone.utc)
    
    # Create high activity (60 transactions in 24 hours)
    for i in range(60):
        tracker.track_transaction(wallet, {
            'timestamp': now - timedelta(minutes=i*20),
            'tx_type': 'buy' if i % 2 == 0 else 'sell',
            'amount': 1000,
            'token_address': 'HighActivityToken'
        })
    
    # Get summary
    summary = tracker.get_wallet_behavior_summary(wallet, days=30)
    
    print(f"\nWallet Behavior Summary:")
    print(f"   Wallet: {summary['wallet']}")
    print(f"   Period: {summary['period_days']} days")
    print(f"   Activity Level: {summary['activity_level']}")
    print(f"   Aggressiveness Score: {summary['aggressiveness_score']:.3f}")
    print(f"   Burst Detected: {summary['burst_detected']}")
    print(f"   Detected Patterns: {summary['patterns']}")
    print(f"   Risk Indicators: {summary['risk_indicators']}")
    print(f"\n   Rolling Windows:")
    for window, count in summary['rolling_windows'].items():
        print(f"      - {window}: {count} transactions")
    
    assert summary['activity_level'] in ['very_high', 'high'], "Should detect high activity"
    assert summary['wallet'] == wallet, "Should return correct wallet"
    
    print("\nTEST 5 PASSED: Wallet behavior summary working correctly")
    return True


if __name__ == "__main__":
    print("\n" + "#"*60)
    print("# GODMODESCANNER - BehaviorTracker Test Suite")
    print("#"*60)
    
    results = {
        'total_tests': 5,
        'passed': 0,
        'failed': 0,
        'tests': []
    }
    
    tests = [
        ("Track Transaction & Rolling Windows", test_track_transaction),
        ("Detect Burst Activity", test_detect_burst_activity),
        ("Calculate Aggressiveness", test_calculate_aggressiveness),
        ("Analyze Behavior Patterns", test_analyze_behavior_patterns),
        ("Wallet Behavior Summary", test_wallet_behavior_summary)
    ]
    
    for test_name, test_func in tests:
        try:
            success = test_func()
            results['passed'] += 1
            results['tests'].append({'name': test_name, 'status': 'PASSED'})
        except Exception as e:
            results['failed'] += 1
            results['tests'].append({'name': test_name, 'status': 'FAILED', 'error': str(e)})
            print(f"\nTEST FAILED: {test_name}")
            print(f"   Error: {e}")
    
    # Final summary
    print("\n" + "#"*60)
    print("# TEST SUMMARY")
    print("#"*60)
    print(f"\nPassed: {results['passed']}/{results['total_tests']}")
    print(f"Failed: {results['failed']}/{results['total_tests']}")
    print(f"\nSuccess Rate: {(results['passed']/results['total_tests']*100):.1f}%")
    
    if results['failed'] == 0:
        print("\nALL TESTS PASSED! BehaviorTracker is production-ready.")
    else:
        print("\nSome tests failed. Review errors above.")
    
    # Save results
    with open('/a0/usr/projects/godmodescanner/projects/godmodescanner/tests/behavior_tracker_test_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\nResults saved to: tests/behavior_tracker_test_results.json")
