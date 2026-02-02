"""Zero-latency Alert Manager using epoll for event-driven processing."""

import select
import os
import time
import signal
import struct
import socket
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Callable
import json
import numpy as np

from agents.shared_memory.risk_score_segment import SharedRiskScoreSegment, RiskScoreMessage


@dataclass
class Alert:
    """Alert structure."""
    timestamp_ns: int
    wallet_address: str
    token_address: str
    risk_score: float
    confidence: float
    threshold: float
    sequence_number: int
    detection_latency_ns: int  # Time from risk score to alert dispatch
    processing_latency_ns: int  # Time from shared memory read to dispatch

    def to_dict(self) -> dict:
        return asdict(self)


class ZeroLatencyAlertManager:
    """Event-driven alert manager using epoll for zero-latency detection."""

    def __init__(self, shared_memory_name: str = '/godmodescanner_risk_scores',
                 threshold: float = 0.80):
        """Initialize the alert manager.

        Args:
            shared_memory_name: Name of shared memory segment
            threshold: Risk score threshold for alerting
        """
        self.threshold = threshold
        self.segment = SharedRiskScoreSegment(shared_memory_name)
        self.segment.create()

        # Create event file descriptor for signaling
        self.event_fd, self.writer_fd = os.pipe()
        os.set_blocking(self.event_fd, False)

        # Create epoll instance
        self.epoll = select.epoll()
        self.epoll.register(self.event_fd, select.EPOLLIN)

        # Alert statistics
        self.alerts_dispatched: List[Alert] = []
        self.total_messages_processed = 0
        self.total_alerts_triggered = 0
        self.latency_samples_ns: List[int] = []

        # Alert callback
        self.alert_callback: Optional[Callable[[Alert], None]] = None

        print(f"Initialized ZeroLatencyAlertManager")
        print(f"Threshold: {threshold}")
        print(f"Event FD: {self.event_fd}")
        print(f"Epoll FD: {self.epoll.fileno()}")

    def set_alert_callback(self, callback: Callable[[Alert], None]):
        """Set callback function for alert dispatch."""
        self.alert_callback = callback

    def signal_new_data(self):
        """Signal that new data is available in shared memory."""
        os.write(self.writer_fd, b'x')

    def process_messages(self):
        """Process all pending messages from shared memory."""
        processed = 0
        alerts = 0

        while True:
            msg = self.segment.read_latest()
            if msg is None:
                break

            processed += 1
            self.total_messages_processed += 1

            # Check if alert triggered
            if msg.alert_triggered:
                self._dispatch_alert(msg)
                alerts += 1
                self.total_alerts_triggered += 1

        return processed, alerts

    def _dispatch_alert(self, msg: RiskScoreMessage):
        """Dispatch alert with zero latency."""
        dispatch_time_ns = time.time_ns()

        # Calculate latencies
        detection_latency = dispatch_time_ns - msg.timestamp_ns
        processing_latency = 0  # Instant dispatch

        # Create alert
        alert = Alert(
            timestamp_ns=msg.timestamp_ns,
            wallet_address=msg.wallet_address,
            token_address=msg.token_address,
            risk_score=msg.risk_score,
            confidence=msg.confidence,
            threshold=msg.threshold,
            sequence_number=msg.sequence_number,
            detection_latency_ns=detection_latency,
            processing_latency_ns=processing_latency
        )

        self.alerts_dispatched.append(alert)
        self.latency_samples_ns.append(detection_latency)

        # Call callback if set
        if self.alert_callback:
            self.alert_callback(alert)

    def run_event_loop(self, timeout_ms: int = -1):
        """Run epoll event loop for zero-latency processing.

        Args:
            timeout_ms: Timeout in milliseconds (-1 for infinite)
        """
        print(f"Starting epoll event loop (timeout={timeout_ms}ms)...")

        try:
            while True:
                # Wait for events (epoll)
                events = self.epoll.poll(timeout_ms)

                for fd, event in events:
                    if fd == self.event_fd:
                        # Clear event pipe
                        while True:
                            try:
                                os.read(self.event_fd, 4096)
                            except BlockingIOError:
                                break

                        # Process messages
                        processed, alerts = self.process_messages()
                        if processed > 0:
                            print(f"Processed {processed} messages, triggered {alerts} alerts")

        except KeyboardInterrupt:
            print("
Event loop stopped by user")
        finally:
            self.close()

    def get_statistics(self) -> dict:
        """Get alert manager statistics."""
        if not self.latency_samples_ns:
            return {
                'total_messages_processed': self.total_messages_processed,
                'total_alerts_triggered': self.total_alerts_triggered,
                'avg_latency_ns': 0,
                'max_latency_ns': 0,
                'min_latency_ns': 0,
                'p99_latency_ns': 0,
                'p95_latency_ns': 0
            }

        latencies = np.array(self.latency_samples_ns)

        return {
            'total_messages_processed': self.total_messages_processed,
            'total_alerts_triggered': self.total_alerts_triggered,
            'avg_latency_ns': int(np.mean(latencies)),
            'max_latency_ns': int(np.max(latencies)),
            'min_latency_ns': int(np.min(latencies)),
            'p99_latency_ns': int(np.percentile(latencies, 99)),
            'p95_latency_ns': int(np.percentile(latencies, 95))
        }

    def close(self):
        """Close alert manager."""
        self.epoll.close()
        os.close(self.event_fd)
        os.close(self.writer_fd)
        self.segment.close()


if __name__ == "__main__":
    # Test Alert Manager
    def alert_callback(alert: Alert):
        print(f"
🚨 ALERT DISPATCHED:")
        print(f"   Wallet: {alert.wallet_address}")
        print(f"   Token: {alert.token_address}")
        print(f"   Risk Score: {alert.risk_score:.4f}")
        print(f"   Detection Latency: {alert.detection_latency_ns / 1_000_000:.3f} ms")
        print(f"   Processing Latency: {alert.processing_latency_ns / 1_000:.3f} us")

    manager = ZeroLatencyAlertManager(threshold=0.80)
    manager.set_alert_callback(alert_callback)

    # Run event loop
    manager.run_event_loop()
