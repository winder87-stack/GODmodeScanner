"""Comprehensive benchmark for zero-latency alert pipeline."""

import asyncio
import signal
import time
import json
import sys
from pathlib import Path
import numpy as np
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.alert_manager import ZeroLatencyAlertManager, Alert
from tests.websocket_simulator import WebSocketSimulator, PumpFunTransaction
from tests.gpu_emulator import GPURiskScoringEmulator


@dataclass
class LatencyBreakdown:
    """Complete latency breakdown for end-to-end pipeline."""
    transaction_receive_ns: int     # Time from tx gen to WebSocket receive
    gpu_compute_ns: int              # Time for GPU risk scoring
    shared_memory_write_ns: int      # Time to write to shared memory
    epoll_detection_ns: int           # Time from write to epoll wake
    alert_dispatch_ns: int            # Time from detection to dispatch
    total_e2e_ns: int                 # End-to-end total latency

    def to_dict(self) -> dict:
        return asdict(self)


class Benchmark:
    """Complete end-to-end benchmark."""

    def __init__(self, duration_seconds: int = 10,
                 transactions_per_second: int = 1000,
                 alert_rate: float = 0.15):
        """Initialize benchmark.

        Args:
            duration_seconds: Benchmark duration
            transactions_per_second: Transaction rate
            alert_rate: Rate of high-risk transactions
        """
        self.duration = duration_seconds
        self.tps = transactions_per_second
        self.alert_rate = alert_rate

        # Components
        self.websocket_sim = WebSocketSimulator(transactions_per_second)
        self.gpu_emulator = GPURiskScoringEmulator(alert_rate=alert_rate)
        self.alert_manager = ZeroLatencyAlertManager(threshold=0.80)

        # Results
        self.latencies: List[LatencyBreakdown] = []
        self.transaction_times: Dict[int, int] = {}  # seq -> tx_gen_time
        self.gpu_times: Dict[int, int] = {}  # seq -> gpu_start_time
        self.write_times: Dict[int, int] = {}  # seq -> write_time

        # Statistics
        self.transactions_processed = 0
        self.alerts_dispatched = 0

    def setup(self):
        """Setup benchmark components."""
        print("
" + "="*60)
        print("ZERO-LATENCY ALERT PIPELINE BENCHMARK")
        print("="*60)
        print(f"Duration: {self.duration}s")
        print(f"Transaction Rate: {self.tps} TX/s")
        print(f"Alert Rate: {self.alert_rate*100}%")
        print(f"Target Latency: <0.8 ms")
        print("="*60)

        # Setup WebSocket callback
        self.websocket_sim.set_callback(self._on_transaction)

        # Setup alert callback
        self.alert_manager.set_alert_callback(self._on_alert)

    def _on_transaction(self, tx: PumpFunTransaction, receive_time: int):
        """Handle new transaction from WebSocket."""
        seq = hash(tx.signature) % 1_000_000

        # Track transaction generation time (simulate)
        tx_gen_time = receive_time - random.randint(10, 100)
        self.transaction_times[seq] = tx_gen_time
        self.gpu_times[seq] = receive_time

        # Process through GPU
        write_time = self.gpu_emulator.process_transaction(tx)
        self.write_times[seq] = write_time

        # Signal alert manager
        self.alert_manager.signal_new_data()

        self.transactions_processed += 1

    def _on_alert(self, alert: Alert):
        """Handle dispatched alert."""
        # Lookup timing data
        tx_gen_time = self.transaction_times.get(alert.sequence_number, 0)
        gpu_start_time = self.gpu_times.get(alert.sequence_number, 0)
        write_time = self.write_times.get(alert.sequence_number, 0)

        # Calculate breakdown
        tx_receive_latency = gpu_start_time - tx_gen_time
        gpu_compute_latency = write_time - gpu_start_time
        memory_write_latency = 0  # Already factored into write_time
        epoll_detection_latency = alert.detection_latency_ns - memory_write_latency
        alert_dispatch_latency = alert.processing_latency_ns

        total_e2e = tx_receive_latency + gpu_compute_latency + epoll_detection_latency + alert_dispatch_latency

        # Record latency breakdown
        breakdown = LatencyBreakdown(
            transaction_receive_ns=tx_receive_latency,
            gpu_compute_ns=gpu_compute_latency,
            shared_memory_write_ns=memory_write_latency,
            epoll_detection_ns=epoll_detection_latency,
            alert_dispatch_ns=alert_dispatch_latency,
            total_e2e_ns=total_e2e
        )

        self.latencies.append(breakdown)
        self.alerts_dispatched += 1

    async def run(self):
        """Run the benchmark."""
        print("
🚀 Starting benchmark...")
        print("
Stages:")
        print("  1. Transaction Receive (WebSocket)")
        print("  2. GPU Risk Scoring")
        print("  3. Shared Memory Write")
        print("  4. epoll Detection")
        print("  5. Alert Dispatch")
        print("
Collecting latency samples...")

        # Start alert manager in background
        import threading
        alert_thread = threading.Thread(
            target=self.alert_manager.run_event_loop,
            kwargs={'timeout_ms': 1},
            daemon=True
        )
        alert_thread.start()

        # Run WebSocket simulator
        await self.websocket_sim.start(duration_seconds=self.duration)

        # Wait for final alerts to process
        await asyncio.sleep(0.1)

        # Stop alert manager
        self.alert_manager.close()

        print(f"
✅ Benchmark complete!")
        print(f"   Transactions processed: {self.transactions_processed}")
        print(f"   Alerts dispatched: {self.alerts_dispatched}")

        self._print_results()

    def _print_results(self):
        """Print benchmark results."""
        if not self.latencies:
            print("
⚠️  No alerts captured during benchmark")
            return

        # Convert to arrays
        lat_data = {
            'Transaction Receive (WebSocket)': np.array([l.transaction_receive_ns for l in self.latencies]),
            'GPU Compute': np.array([l.gpu_compute_ns for l in self.latencies]),
            'Shared Memory Write': np.array([l.shared_memory_write_ns for l in self.latencies]),
            'epoll Detection': np.array([l.epoll_detection_ns for l in self.latencies]),
            'Alert Dispatch': np.array([l.alert_dispatch_ns for l in self.latencies]),
            'End-to-End Total': np.array([l.total_e2e_ns for l in self.latencies])
        }

        print("
" + "="*60)
        print("LATENCY BREAKDOWN (microseconds)")
        print("="*60)

        for stage, data in lat_data.items():
            avg = np.mean(data) / 1000
            min_val = np.min(data) / 1000
            max_val = np.max(data) / 1000
            p95 = np.percentile(data, 95) / 1000
            p99 = np.percentile(data, 99) / 1000

            print(f"
{stage}:")
            print(f"  Average: {avg:8.2f} μs")
            print(f"  Minimum: {min_val:8.2f} μs")
            print(f"  Maximum: {max_val:8.2f} μs")
            print(f"  P95:     {p95:8.2f} μs")
            print(f"  P99:     {p99:8.2f} μs")

        # Summary
        e2e_ms = lat_data['End-to-End Total'] / 1_000_000

        print("
" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"
Target Latency:      < 800 μs")
        print(f"Achieved Average:    {np.mean(e2e_ms)*1000:8.2f} μs")
        print(f"Achieved P95:        {np.percentile(e2e_ms*1000, 95):8.2f} μs")
        print(f"Achieved P99:        {np.percentile(e2e_ms*1000, 99):8.2f} μs")
        print(f"Min Latency:         {np.min(e2e_ms)*1000:8.2f} μs")
        print(f"Max Latency:         {np.max(e2e_ms)*1000:8.2f} μs")

        # Check target
        avg_us = np.mean(e2e_ms) * 1000
        if avg_us < 800:
            print(f"
✅ TARGET ACHIEVED: Average latency {avg_us:.2f} μs < 800 μs")
        else:
            print(f"
⚠️  TARGET NOT MET: Average latency {avg_us:.2f} μs >= 800 μs")

        # GPU statistics
        gpu_stats = self.gpu_emulator.get_statistics()
        print("
GPU Emulator Statistics:")
        print(f"  Compute Average: {gpu_stats['score_compute_avg_ns']/1000:.2f} μs")
        print(f"  Compute Maximum: {gpu_stats['score_compute_max_ns']/1000:.2f} μs")
        print(f"  Memory Write Avg: {gpu_stats['memory_write_avg_ns']/1000:.2f} μs")

        # Alert manager statistics
        alert_stats = self.alert_manager.get_statistics()
        print("
Alert Manager Statistics:")
        print(f"  Messages Processed: {alert_stats['total_messages_processed']}")
        print(f"  Alerts Dispatched:   {alert_stats['total_alerts_triggered']}")
        print(f"  Detection Average:   {alert_stats['avg_latency_ns']/1000:.2f} μs")
        print(f"  Detection P99:       {alert_stats['p99_latency_ns']/1000:.2f} μs")

        # Save results
        self._save_results(e2e_ms, gpu_stats, alert_stats)

    def _save_results(self, e2e_ms, gpu_stats, alert_stats):
        """Save benchmark results to file."""
        results = {
            'timestamp': time.time(),
            'duration_seconds': self.duration,
            'transactions_per_second': self.tps,
            'alert_rate': self.alert_rate,
            'transactions_processed': self.transactions_processed,
            'alerts_dispatched': self.alerts_dispatched,
            'target_latency_us': 800,
            'e2e_latency_stats': {
                'avg_us': float(np.mean(e2e_ms) * 1000),
                'min_us': float(np.min(e2e_ms) * 1000),
                'max_us': float(np.max(e2e_ms) * 1000),
                'p95_us': float(np.percentile(e2e_ms * 1000, 95)),
                'p99_us': float(np.percentile(e2e_ms * 1000, 99))
            },
            'gpu_stats': gpu_stats,
            'alert_stats': alert_stats,
            'stage_breakdown_us': {
                'transaction_receive_avg': float(np.mean([l.transaction_receive_ns for l in self.latencies]) / 1000),
                'gpu_compute_avg': float(np.mean([l.gpu_compute_ns for l in self.latencies]) / 1000),
                'epoll_detection_avg': float(np.mean([l.epoll_detection_ns for l in self.latencies]) / 1000),
                'alert_dispatch_avg': float(np.mean([l.alert_dispatch_ns for l in self.latencies]) / 1000)
            }
        }

        results_path = Path('data/benchmark_results.json')
        results_path.parent.mkdir(exist_ok=True)

        with open(results_path, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"
💾 Results saved to: {results_path}")


if __name__ == "__main__":
    # Run benchmark
    benchmark = Benchmark(
        duration_seconds=10,
        transactions_per_second=1000,
        alert_rate=0.15
    )

    benchmark.setup()
    asyncio.run(benchmark.run())
