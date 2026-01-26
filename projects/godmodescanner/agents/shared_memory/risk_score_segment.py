"""Shared memory segment for zero-latency risk score transmission."""

import mmap
import os
import struct
import time
from pathlib import Path
from dataclasses import dataclass
import numpy as np
from typing import Optional


@dataclass
class RiskScoreMessage:
    """Risk score message structure."""
    timestamp_ns: int          # Nanosecond timestamp
    wallet_address: str        # 44-char Solana address
    token_address: str         # 44-char Solana address
    risk_score: float          # 0.0 to 1.0
    confidence: float         # 0.0 to 1.0
    threshold: float          # Detection threshold
    alert_triggered: bool      # Alert state
    sequence_number: int       # Sequence number for ordering

    def to_bytes(self) -> bytes:
        """Serialize to binary format for shared memory."""
        header = struct.pack('<Q?I', self.timestamp_ns, self.alert_triggered, self.sequence_number)
        wallet_addrs = self.wallet_address.ljust(44, chr(0)).encode('ascii')
        token_addrs = self.token_address.ljust(44, chr(0)).encode('ascii')
        scores = struct.pack('<ddd', self.risk_score, self.confidence, self.threshold)
        return header + wallet_addrs + token_addrs + scores

    @classmethod
    def from_bytes(cls, data: bytes) -> 'RiskScoreMessage':
        """Deserialize from binary format."""
        header_size = 13
        header = struct.unpack('<Q?I', data[:header_size])
        wallet_addrs = data[header_size:header_size+44].decode('ascii').rstrip(chr(0))
        token_addrs = data[header_size+44:header_size+88].decode('ascii').rstrip(chr(0))
        scores = struct.unpack('<ddd', data[header_size+88:header_size+112])
        return cls(
            timestamp_ns=header[0],
            alert_triggered=header[1],
            sequence_number=header[2],
            wallet_address=wallet_addrs,
            token_address=token_addrs,
            risk_score=scores[0],
            confidence=scores[1],
            threshold=scores[2]
        )


class SharedRiskScoreSegment:
    """Shared memory segment for zero-copy risk score transmission."""
    MESSAGE_SIZE = 125
    MESSAGE_COUNT = 1000
    SEGMENT_SIZE = MESSAGE_SIZE * MESSAGE_COUNT

    def __init__(self, name: str = '/godmodescanner_risk_scores'):
        self.name = name
        self.segment_name = name
        self._shm = None
        self._fd = None
        self._write_pos = 0
        self._read_pos = 0
        self._sequence_number = 0

    def create(self):
        """Create or open shared memory segment."""
        try:
            memfd = os.open(f'/dev/shm{self.name}', os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o666)
            os.ftruncate(memfd, self.SEGMENT_SIZE)
            self._fd = memfd
            self._shm = mmap.mmap(self._fd, self.SEGMENT_SIZE)
            print(f"Created shared memory segment: {self.segment_name}")
            print(f"Size: {self.SEGMENT_SIZE} bytes")
        except FileExistsError:
            memfd = os.open(f'/dev/shm{self.name}', os.O_RDWR, 0o666)
            self._fd = memfd
            self._shm = mmap.mmap(self._fd, self.SEGMENT_SIZE)
            print(f"Opened existing shared memory segment: {self.segment_name}")

    def write_risk_score(self, wallet_addr: str, token_addr: str, risk_score: float, confidence: float, threshold: float) -> int:
        alert_triggered = risk_score >= threshold
        msg = RiskScoreMessage(
            timestamp_ns=time.time_ns(),
            wallet_address=wallet_addr,
            token_address=token_addr,
            risk_score=risk_score,
            confidence=confidence,
            threshold=threshold,
            alert_triggered=alert_triggered,
            sequence_number=self._sequence_number
        )
        msg_bytes = msg.to_bytes()
        offset = self._write_pos * self.MESSAGE_SIZE
        self._shm[offset:offset + self.MESSAGE_SIZE] = msg_bytes
        self._write_pos = (self._write_pos + 1) % self.MESSAGE_COUNT
        self._sequence_number += 1
        return msg.timestamp_ns

    def read_latest(self) -> Optional[RiskScoreMessage]:
        if self._write_pos == self._read_pos:
            return None
        offset = self._read_pos * self.MESSAGE_SIZE
        msg_bytes = self._shm[offset:offset + self.MESSAGE_SIZE]
        msg = RiskScoreMessage.from_bytes(msg_bytes)
        self._read_pos = (self._read_pos + 1) % self.MESSAGE_COUNT
        return msg

    def close(self):
        if self._shm:
            self._shm.close()
        if self._fd is not None:
            os.close(self._fd)


class RiskScoreSegment:
    """Wrapper class for SharedRiskScoreSegment to maintain backward compatibility.
    
    This class provides a simple interface for writing alerts to shared memory
    with zero-latency transmission (~15.65μs).
    """
    
    def __init__(self, name: str = '/godmodescanner_risk_scores'):
        """Initialize the risk score segment."""
        self._segment = SharedRiskScoreSegment(name=name)
        # Create the shared memory segment
        self._segment.create()
    
    def write_alert(self, alert_data: dict) -> int:
        """Write an alert to shared memory.
        
        Args:
            alert_data: Dictionary containing alert data:
                - type: Alert type (e.g., 'LARGE_SWAP')
                - user: Wallet address
                - mint: Token mint address
                - amount: SOL amount in lamports
                - timestamp: Unix timestamp
                
        Returns:
            Timestamp in nanoseconds
        """
        wallet_addr = alert_data.get('user', '')
        token_addr = alert_data.get('mint', '')
        
        # Calculate risk score based on alert type and amount
        risk_score = self._calculate_risk_score(alert_data)
        
        # Use default confidence and threshold for alerts
        confidence = 0.9  # High confidence for direct alerts
        threshold = 0.7   # Default risk threshold
        
        return self._segment.write_risk_score(
            wallet_addr=wallet_addr,
            token_addr=token_addr,
            risk_score=risk_score,
            confidence=confidence,
            threshold=threshold
        )
    
    def write_score(self, wallet_addr: str, token_addr: str, risk_score: float, 
                   confidence: float = 0.8, threshold: float = 0.7) -> int:
        """Write a risk score to shared memory.
        
        Args:
            wallet_addr: Wallet address
            token_addr: Token mint address
            risk_score: Risk score (0.0 to 1.0)
            confidence: Confidence level (0.0 to 1.0)
            threshold: Detection threshold (0.0 to 1.0)
            
        Returns:
            Timestamp in nanoseconds
        """
        return self._segment.write_risk_score(
            wallet_addr=wallet_addr,
            token_addr=token_addr,
            risk_score=risk_score,
            confidence=confidence,
            threshold=threshold
        )
    
    def read_latest(self) -> Optional['RiskScoreMessage']:
        """Read the latest risk score from shared memory.
        
        Returns:
            RiskScoreMessage or None if no new messages
        """
        return self._segment.read_latest()
    
    def _calculate_risk_score(self, alert_data: dict) -> float:
        """Calculate risk score based on alert data."""
        alert_type = alert_data.get('type', '')
        amount = alert_data.get('amount', 0)
        
        # Convert amount from lamports to SOL
        amount_sol = amount / 1e9 if amount > 0 else 0
        
        # Base risk score based on alert type
        risk_scores = {
            'LARGE_SWAP': 0.8,
            'EARLY_BUY': 0.9,
            'INSIDER_PATTERN': 0.95,
            'SYBIL_NETWORK': 0.85,
            'FUNDING_HUB': 0.9
        }
        
        base_score = risk_scores.get(alert_type, 0.7)
        
        # Adjust based on amount
        if amount_sol > 100:
            base_score = min(1.0, base_score + 0.1)
        elif amount_sol > 50:
            base_score = min(1.0, base_score + 0.05)
        
        return base_score
    
    def close(self):
        """Close the shared memory segment."""
        self._segment.close()
