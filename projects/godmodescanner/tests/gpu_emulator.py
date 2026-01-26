"""GPU risk scoring emulator that writes to shared memory."""

import time
import random
import numpy as np
from agents.shared_memory.risk_score_segment import SharedRiskScoreSegment
from tests.websocket_simulator import PumpFunTransaction


class GPURiskScoringEmulator:
    """Simulates GPU-accelerated risk scoring."""

    def __init__(self, shared_memory_name: str = '/godmodescanner_risk_scores',
                 threshold: float = 0.80,
                 alert_rate: float = 0.15):
        """Initialize GPU emulator.

        Args:
            shared_memory_name: Name of shared memory segment
            threshold: Risk score threshold
            alert_rate: Rate of transactions that exceed threshold
        """
        self.threshold = threshold
        self.alert_rate = alert_rate
        self.shared_memory = SharedRiskScoreSegment(shared_memory_name)
        self.shared_memory.create()

        # Load simulated model parameters
        self.model_weights = np.random.randn(128, 64)
        self.model_bias = np.random.randn(64)

        # Performance tracking
        self.score_latencies_ns: List[int] = []
        self.write_latencies_ns: List[int] = []

    def compute_risk_score(self, transaction: PumpFunTransaction) -> tuple:
        """Compute risk score for a transaction.

        Simulates GPU compute with microsecond latency.

        Returns:
            (risk_score, confidence, compute_time_ns)
        """
        start_time = time.time_ns()

        # Simulate GPU computation (10-100 us)
        gpu_latency = random.randint(10, 100)
        time.sleep(gpu_latency / 1_000_000)

        # Generate random features
        features = np.random.randn(128)

        # Simulate neural network inference
        hidden = np.dot(features, self.model_weights) + self.model_bias
        output = np.tanh(hidden)

        # Generate risk score
        base_score = float(np.mean(output))

        # Normalize to [0, 1]
        risk_score = (base_score + 1) / 2

        # Inject alerts at specified rate
        if random.random() < self.alert_rate:
            risk_score = self.threshold + random.uniform(0.01, 0.19)

        # Confidence inversely related to score uncertainty
        confidence = 0.8 + random.uniform(0.0, 0.2)

        compute_time = time.time_ns() - start_time
        self.score_latencies_ns.append(compute_time)

        return risk_score, confidence, compute_time

    def process_transaction(self, transaction: PumpFunTransaction) -> int:
        """Process transaction and write to shared memory.

        Returns:
            Write timestamp in nanoseconds
        """
        # Compute risk score
        risk_score, confidence, compute_time = self.compute_risk_score(transaction)

        # Write to shared memory
        write_time = self.shared_memory.write_risk_score(
            wallet_addr=transaction.wallet_address,
            token_addr=transaction.token_address,
            risk_score=risk_score,
            confidence=confidence,
            threshold=self.threshold
        )

        write_latency = time.time_ns() - write_time
        self.write_latencies_ns.append(write_latency)

        return write_time

    def get_statistics(self) -> dict:
        """Get emulator statistics."""
        score_lat = np.array(self.score_latencies_ns)
        write_lat = np.array(self.write_latencies_ns)

        return {
            'total_transactions': len(self.score_latencies_ns),
            'score_compute_avg_ns': int(np.mean(score_lat)) if len(score_lat) > 0 else 0,
            'score_compute_max_ns': int(np.max(score_lat)) if len(score_lat) > 0 else 0,
            'score_compute_min_ns': int(np.min(score_lat)) if len(score_lat) > 0 else 0,
            'memory_write_avg_ns': int(np.mean(write_lat)) if len(write_lat) > 0 else 0,
            'memory_write_max_ns': int(np.max(write_lat)) if len(write_lat) > 0 else 0,
            'memory_write_min_ns': int(np.min(write_lat)) if len(write_lat) > 0 else 0
        }
