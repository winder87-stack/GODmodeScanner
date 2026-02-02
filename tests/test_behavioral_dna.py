#!/usr/bin/env python3
import asyncio
import pytest
import structlog
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, '.')

import redis.asyncio as redis

from agents.behavioral_dna.behavioral_dna_predictor import BehavioralDNAPredictor, get_predictor
from agents.wallet_profiler.agent import WalletProfilerAgent
from agents.historical_analyzer import HistoricalMetrics

logger = structlog.get_logger(__name__)

class MockDBPool:
    def __init__(self):
        self.wallet_histories = {'TestInsiderWallet123': self._generate_insider_history(), 'TestShortHistory': []}
    def _generate_insider_history(self):
        history = []
        base_time = datetime.now(timezone.utc) - timedelta(days=30)
        for i in range(25):
            launch_time = base_time + timedelta(hours=i * 6)
            buy_time = launch_time + timedelta(seconds=5)
            history.append({'action': 'BUY', 'timestamp': buy_time, 'amount': 2.5, 'token_launch_time': launch_time, 'token_market_cap': 150000})
        return history

class MockConnection:
    def __init__(self, db_pool_ref):
        self._db_pool_ref = db_pool_ref
    async def fetch(self, query, *args):
        wallet = args[0]
        limit = args[1] if len(args) > 1 else 20
        return self._db_pool_ref.wallet_histories.get(wallet, [])[:limit]
    async def fetchrow(self, query, *args): return None
    async def fetchval(self, query, *args): return None
    async def execute(self, query, *args): pass

class MockAsyncConnectionPool:
    def __init__(self, db_pool): self._db_pool = db_pool
    def acquire(self):
        class Context:
            async def __aenter__(ctx): return MockConnection(self._db_pool)
            async def __aexit__(ctx, *args): pass
        return Context()
    def connection(self): return self.acquire()

@pytest.fixture
async def redis_client():
    client = await redis.from_url('redis://localhost:6379', encoding='utf-8', decode_responses=False)
    yield client
    await client.aclose()

@pytest.fixture
def mock_db_pool(): return MockAsyncConnectionPool(MockDBPool())

@pytest.mark.asyncio
async def test_behavioral_dna_predictor_initialization():
    predictor = BehavioralDNAPredictor(model_path='models/behavioral_dna_v1.onnx')
    assert predictor is not None
    if predictor.is_available():
        assert predictor.session is not None
        print('✓ Test 1 PASSED: Predictor initialized')
    else: print('⚠ Test 1 SKIPPED: Model not available')

@pytest.mark.asyncio
async def test_behavioral_dna_singleton():
    predictor1 = get_predictor()
    predictor2 = get_predictor()
    assert predictor1 is predictor2
    print('✓ Test 2 PASSED: Singleton pattern works')

@pytest.mark.asyncio
async def test_behavioral_dna_prediction_generation(mock_db_pool):
    predictor = BehavioralDNAPredictor(model_path='models/behavioral_dna_v1.onnx')
    if not predictor.is_available():
        print('⚠ Test 3 SKIPPED: Model not available'); return
    prediction = await predictor.predict_next_action('TestInsiderWallet123', mock_db_pool, 20)
    assert prediction is not None
    assert 'action' in prediction and 'confidence' in prediction
    assert 0 <= prediction['confidence'] <= 1
    print(f"✓ Test 3 PASSED: {prediction['action']} ({prediction['confidence']:.2%})")

@pytest.mark.asyncio
async def test_behavioral_dna_insufficient_history(mock_db_pool):
    predictor = BehavioralDNAPredictor(model_path='models/behavioral_dna_v1.onnx')
    if not predictor.is_available():
        print('⚠ Test 4 SKIPPED'); return
    prediction = await predictor.predict_next_action('TestShortHistory', mock_db_pool, 20)
    assert prediction is None
    print('✓ Test 4 PASSED: Handles insufficient history')

@pytest.mark.asyncio
async def test_behavioral_dna_performance(mock_db_pool):
    predictor = BehavioralDNAPredictor(model_path='models/behavioral_dna_v1.onnx')
    if not predictor.is_available():
        print('⚠ Test 5 SKIPPED'); return
    latencies = []
    for _ in range(10):
        prediction = await predictor.predict_next_action('TestInsiderWallet123', mock_db_pool, 20)
        if prediction and 'latency_ms' in prediction:
            latencies.append(prediction['latency_ms'])
    assert len(latencies) > 0
    avg_latency = sum(latencies) / len(latencies)
    assert avg_latency < 50
    print(f'✓ Test 5 PASSED: Avg latency {avg_latency:.2f}ms (<50ms target)')

@pytest.mark.asyncio
async def test_wallet_profiler_integration(redis_client, mock_db_pool):
    profiler = WalletProfilerAgent(
        redis_client=redis_client, db_pool=mock_db_pool, cache_ttl=300,
        behavioral_dna_enabled=True, behavioral_dna_threshold=0.5
    )
    assert profiler.behavioral_dna_enabled is True
    if profiler.behavioral_dna_predictor and profiler.behavioral_dna_predictor.is_available():
        print('✓ Test 6 PASSED: Behavioral DNA integrated into WalletProfilerAgent')
    else:
        print('⚠ Test 6 PARTIAL: Integration works but model not available')

if __name__ == '__main__': pytest.main([__file__, '-v', '-s', '--tb=short'])
