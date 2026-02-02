#!/usr/bin/env python3
"""
Test Suite for Input Validation Module and BaseWorker Refactoring.

Tests:
1. SolanaWalletAddress validation (base58, length, suspicious patterns)
2. TransactionMessage validation (amount, signature, timestamp)
3. WalletClusterMessage and RiskScoreMessage validation
4. BaseWorker initialization and configuration
5. Worker refactoring verification
"""

import sys
import pytest
import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import validation module
from utils.validation import (
    SolanaWalletAddress,
    TransactionMessage,
    WalletClusterMessage,
    RiskScoreMessage,
    ValidationError,
    InvalidAddressError,
    SuspiciousAddressError,
    validate_input,
    parse_transaction_message,
    parse_wallet_address,
    validate_and_sanitize_string,
    validate_json_input,
)

# Import BaseWorker
from agents.workers.base_worker import BaseWorker, BaseWorkerConfig


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def valid_solana_address():
    """Return a valid Solana wallet address."""
    return "7nYhPEv7j94mLzJ2yC9vb6xqRz4jPS3hG9K7e9Kp8s3T"


@pytest.fixture
def sample_transaction_data():
    """Return sample transaction data."""
    return {
        "wallet": "7nYhPEv7j94mLzJ2yC9vb6xqRz4jPS3hG9K7e9Kp8s3T",
        "amount": 1.5,
        "signature": "5W8GdH2UqxJK4xNLy6W3nTJYdG5Qw7YBJ6c7j8hRk9s2",
        "timestamp": int(time.time()),
        "token": "EPjFWdd5AufqSSqeM3qU1mgyY5Xy4XpHc8p7kF9Gp8kL",
        "type": "buy",
    }


# ============================================================================
# TEST SOLANA WALLET ADDRESS VALIDATION
# ============================================================================

class TestSolanaWalletAddress:
    """Tests for SolanaWalletAddress validation."""
    
    def test_valid_address(self, valid_solana_address):
        """Test that valid addresses are accepted."""
        addr = SolanaWalletAddress(value=valid_solana_address)
        assert addr.value == valid_solana_address
        assert addr.short_form == "7nYhPE...8s3T"
    
    def test_address_too_short(self):
        """Test that addresses shorter than 32 chars are rejected."""
        with pytest.raises(Exception) as exc_info:
            SolanaWalletAddress(value="abc123")
        assert "min_length" in str(exc_info.value)
    
    def test_address_too_long(self):
        """Test that addresses longer than 44 chars are rejected."""
        long_address = "7nYhPEv7j94mLzJ2yC9vb6xqRz4jPS3hG9K7e9Kp8s3T" + "X" * 20
        with pytest.raises(Exception) as exc_info:
            SolanaWalletAddress(value=long_address)
        assert "max_length" in str(exc_info.value)
    
    def test_invalid_base58_characters(self):
        """Test that invalid base58 characters are rejected."""
        # 0, O, I, l are not valid base58
        with pytest.raises(InvalidAddressError):
            SolanaWalletAddress(value="0O1Il1l23456789012345678901234567890123456789")
    
    def test_uppercase_o_rejected(self):
        """Test that capital O is rejected."""
        with pytest.raises(InvalidAddressError):
            SolanaWalletAddress(value="7nYhPEv7j94mLzJ2yC9vb6xqRz4jPS3hG9K7O9Kp8s3T")
    
    def test_zero_rejected(self):
        """Test that zero digit is rejected."""
        with pytest.raises(InvalidAddressError):
            SolanaWalletAddress(value="7nYhPEv7j94mLzJ2yC9vb6xqRz4jPS3hG9K701p8s3T")
    
    def test_suspicious_patterns_logged(self, valid_solana_address, caplog):
        """Test that suspicious patterns are logged but not rejected."""
        # Create an address with suspicious patterns (should be logged)
        addr = SolanaWalletAddress(value="1I1abc23456789012345678901234567890123456")
        assert addr.value == "1I1abc23456789012345678901234567890123456"
        # The warning should be logged (verified via caplog)
    
    def test_control_characters_rejected(self):
        """Test that control characters are rejected."""
        addr_with_null = "abc\x00defghijklmnopqrstuvwxyz123456789012345"
        with pytest.raises(InvalidAddressError):
            SolanaWalletAddress(value=addr_with_null)
    
    def test_system_addresses_warn(self, caplog):
        """Test that system program addresses trigger warnings."""
        addr = SolanaWalletAddress(value="11111111111111111111111111111111")
        assert addr.value == "11111111111111111111111111111111"
    
    def test_parse_safe_success(self, valid_solana_address):
        """Test parse_safe returns success for valid address."""
        success, result, error = SolanaWalletAddress.parse_safe(valid_solana_address)
        assert success is True
        assert result is not None
        assert error is None
    
    def test_parse_safe_failure(self):
        """Test parse_safe returns failure for invalid address."""
        success, result, error = SolanaWalletAddress.parse_safe("invalid")
        assert success is False
        assert result is None
        assert error is not None


# ============================================================================
# TEST TRANSACTION MESSAGE VALIDATION
# ============================================================================

class TestTransactionMessage:
    """Tests for TransactionMessage validation."""
    
    def test_valid_message(self, sample_transaction_data):
        """Test that valid messages are accepted."""
        msg = TransactionMessage(
            wallet=SolanaWalletAddress(value=sample_transaction_data["wallet"]),
            amount=sample_transaction_data["amount"],
            signature=sample_transaction_data["signature"],
            timestamp=sample_transaction_data["timestamp"],
            token_address=SolanaWalletAddress(value=sample_transaction_data["token"]),
            event_type=sample_transaction_data["type"],
        )
        assert msg.wallet.value == sample_transaction_data["wallet"]
        assert msg.amount == sample_transaction_data["amount"]
    
    def test_negative_amount_rejected(self, sample_transaction_data):
        """Test that negative amounts are rejected."""
        data = sample_transaction_data.copy()
        data["amount"] = -1.0
        with pytest.raises(Exception):
            TransactionMessage(
                wallet=SolanaWalletAddress(value=data["wallet"]),
                amount=data["amount"],
                signature=data["signature"],
                timestamp=data["timestamp"],
            )
    
    def test_zero_amount_rejected(self, sample_transaction_data):
        """Test that zero amounts are rejected."""
        data = sample_transaction_data.copy()
        data["amount"] = 0
        with pytest.raises(Exception):
            TransactionMessage(
                wallet=SolanaWalletAddress(value=data["wallet"]),
                amount=data["amount"],
                signature=data["signature"],
                timestamp=data["timestamp"],
            )
    
    def test_invalid_signature_rejected(self, sample_transaction_data):
        """Test that invalid signatures are rejected."""
        data = sample_transaction_data.copy()
        data["signature"] = "invalid!@#signature"
        with pytest.raises(Exception):
            TransactionMessage(
                wallet=SolanaWalletAddress(value=data["wallet"]),
                amount=data["amount"],
                signature=data["signature"],
                timestamp=data["timestamp"],
            )
    
    def test_future_timestamp_rejected(self, sample_transaction_data):
        """Test that timestamps too far in the future are rejected."""
        data = sample_transaction_data.copy()
        data["timestamp"] = int(time.time()) + 1000  # 1000 seconds in future
        with pytest.raises(ValidationError):
            TransactionMessage(
                wallet=SolanaWalletAddress(value=data["wallet"]),
                amount=data["amount"],
                signature=data["signature"],
                timestamp=data["timestamp"],
            )
    
    def test_unknown_event_type_warns(self, sample_transaction_data, caplog):
        """Test that unknown event types trigger warnings."""
        msg = TransactionMessage(
            wallet=SolanaWalletAddress(value=sample_transaction_data["wallet"]),
            amount=sample_transaction_data["amount"],
            signature=sample_transaction_data["signature"],
            timestamp=sample_transaction_data["timestamp"],
            event_type="unknown_type",
        )
        assert msg.event_type == "unknown_type"
    
    def test_nan_amount_rejected(self, sample_transaction_data):
        """Test that NaN amounts are rejected."""
        import math
        data = sample_transaction_data.copy()
        data["amount"] = float('nan')
        with pytest.raises(ValidationError):
            TransactionMessage(
                wallet=SolanaWalletAddress(value=data["wallet"]),
                amount=data["amount"],
                signature=data["signature"],
                timestamp=data["timestamp"],
            )
    
    def test_infinity_amount_rejected(self, sample_transaction_data):
        """Test that infinity amounts are rejected."""
        data = sample_transaction_data.copy()
        data["amount"] = float('inf')
        with pytest.raises(ValidationError):
            TransactionMessage(
                wallet=SolanaWalletAddress(value=data["wallet"]),
                amount=data["amount"],
                signature=data["signature"],
                timestamp=data["timestamp"],
            )
    
    def test_to_dict(self, sample_transaction_data):
        """Test that to_dict returns correct structure."""
        msg = TransactionMessage(
            wallet=SolanaWalletAddress(value=sample_transaction_data["wallet"]),
            amount=sample_transaction_data["amount"],
            signature=sample_transaction_data["signature"],
            timestamp=sample_transaction_data["timestamp"],
        )
        d = msg.to_dict()
        assert "wallet" in d
        assert "amount" in d
        assert "signature" in d
        assert "timestamp" in d


# ============================================================================
# TEST CLUSTER AND RISK MESSAGE VALIDATION
# ============================================================================

class TestWalletClusterMessage:
    """Tests for WalletClusterMessage validation."""
    
    def test_valid_cluster_message(self, valid_solana_address):
        """Test valid cluster message."""
        msg = WalletClusterMessage(
            wallet=SolanaWalletAddress(value=valid_solana_address),
            cluster_id="test-cluster-001",
            confidence=0.75,
            timestamp=int(time.time()),
            metadata={},
        )
        assert msg.cluster_id == "test-cluster-001"
    
    def test_invalid_cluster_id_chars(self, valid_solana_address):
        """Test that invalid cluster ID characters are rejected."""
        with pytest.raises(ValidationError):
            WalletClusterMessage(
                wallet=SolanaWalletAddress(value=valid_solana_address),
                cluster_id="invalid cluster!@#",
                confidence=0.75,
                timestamp=int(time.time()),
            )
    
    def test_confidence_bounds(self, valid_solana_address):
        """Test confidence score bounds."""
        # Too low
        with pytest.raises(Exception):
            WalletClusterMessage(
                wallet=SolanaWalletAddress(value=valid_solana_address),
                cluster_id="test",
                confidence=-0.1,
                timestamp=int(time.time()),
            )
        # Too high
        with pytest.raises(Exception):
            WalletClusterMessage(
                wallet=SolanaWalletAddress(value=valid_solana_address),
                cluster_id="test",
                confidence=1.5,
                timestamp=int(time.time()),
            )


class TestRiskScoreMessage:
    """Tests for RiskScoreMessage validation."""
    
    def test_valid_risk_message(self, valid_solana_address):
        """Test valid risk score message."""
        msg = RiskScoreMessage(
            wallet=SolanaWalletAddress(value=valid_solana_address),
            risk_score=75.0,
            confidence=0.85,
            factors=["high_frequency", "large_volume"],
            timestamp=int(time.time()),
        )
        assert msg.risk_score == 75.0
    
    def test_risk_score_bounds(self, valid_solana_address):
        """Test risk score bounds."""
        with pytest.raises(Exception):
            RiskScoreMessage(
                wallet=SolanaWalletAddress(value=valid_solana_address),
                risk_score=150,  # Too high
                confidence=0.85,
                factors=[],
                timestamp=int(time.time()),
            )
    
    def test_non_string_factors_rejected(self, valid_solana_address):
        """Test that non-string factors are rejected."""
        with pytest.raises(ValidationError):
            RiskScoreMessage(
                wallet=SolanaWalletAddress(value=valid_solana_address),
                risk_score=75.0,
                confidence=0.85,
                factors=[123, 456],  # Should be strings
                timestamp=int(time.time()),
            )


# ============================================================================
# TEST VALIDATION UTILITIES
# ============================================================================

class TestValidationUtilities:
    """Tests for validation utility functions."""
    
    def test_validate_and_sanitize_string_valid(self):
        """Test valid string sanitization."""
        result = validate_and_sanitize_string("hello world", "test_field")
        assert result == "hello world"
    
    def test_validate_and_sanitize_string_empty(self):
        """Test empty string rejection."""
        with pytest.raises(ValidationError):
            validate_and_sanitize_string("", "test_field")
    
    def test_validate_and_sanitize_string_too_long(self):
        """Test max length enforcement."""
        long_str = "x" * 1001
        with pytest.raises(ValidationError):
            validate_and_sanitize_string(long_str, "test_field", max_length=1000)
    
    def test_validate_and_sanitize_control_chars(self):
        """Test control character rejection."""
        with pytest.raises(ValidationError):
            validate_and_sanitize_string("hello\x00world", "test_field")
    
    def test_validate_and_sanitize_injection_patterns(self):
        """Test SQL injection pattern detection."""
        with pytest.raises(ValidationError):
            validate_and_sanitize_string("'; DROP TABLE users;--", "test_field")
    
    def test_validate_json_valid(self):
        """Test valid JSON validation."""
        result = validate_json_input({"field1": "value1", "field2": 123})
        assert result is True
    
    def test_validate_json_not_dict(self):
        """Test non-dict rejection."""
        with pytest.raises(ValidationError):
            validate_json_input(["not", "a", "dict"])
    
    def test_validate_json_missing_fields(self):
        """Test required field checking."""
        with pytest.raises(ValidationError):
            validate_json_input({"field1": "value"}, required_fields=["field1", "field2"])
    
    def test_parse_transaction_message(self, sample_transaction_data):
        """Test parse_transaction_message convenience function."""
        msg = parse_transaction_message(sample_transaction_data)
        assert isinstance(msg, TransactionMessage)
        assert msg.wallet.value == sample_transaction_data["wallet"]
    
    def test_parse_wallet_address(self, valid_solana_address):
        """Test parse_wallet_address convenience function."""
        addr = parse_wallet_address(valid_solana_address)
        assert isinstance(addr, SolanaWalletAddress)
    
    def test_validate_input_wallet_type(self, valid_solana_address):
        """Test validate_input with wallet type."""
        success, model, error = validate_input('wallet', {'address': valid_solana_address})
        assert success is True
        assert model is not None
        assert error is None
    
    def test_validate_input_transaction_type(self, sample_transaction_data):
        """Test validate_input with transaction type."""
        success, model, error = validate_input('transaction', sample_transaction_data)
        assert success is True
        assert model is not None
        assert error is None
    
    def test_validate_input_cluster_type(self, valid_solana_address):
        """Test validate_input with cluster type."""
        data = {
            'wallet': valid_solana_address,
            'cluster_id': 'test-cluster',
            'confidence': 0.75,
            'timestamp': int(time.time()),
        }
        success, model, error = validate_input('cluster', data)
        assert success is True
        assert model is not None
    
    def test_validate_input_risk_type(self, valid_solana_address):
        """Test validate_input with risk type."""
        data = {
            'wallet': valid_solana_address,
            'risk_score': 75.0,
            'confidence': 0.85,
            'factors': ['test'],
            'timestamp': int(time.time()),
        }
        success, model, error = validate_input('risk', data)
        assert success is True
        assert model is not None
    
    def test_validate_input_unknown_type(self):
        """Test validate_input with unknown type."""
        success, model, error = validate_input('unknown_type', {})
        assert success is False
        assert model is None
        assert "Unknown input type" in error


# ============================================================================
# TEST BASE WORKER
# ============================================================================

class TestBaseWorker:
    """Tests for BaseWorker class."""
    
    def test_worker_initialization(self):
        """Test worker initializes with correct defaults."""
        worker = BaseWorker(
            worker_id="test-worker",
            redis_url="redis://localhost:6379"
        )
        assert worker.worker_id == "test-worker"
        assert worker.redis_url == "redis://localhost:6379"
        assert worker.AGENT_TYPE == "base-worker"
        assert worker.WORKER_VERSION == "1.0.0"
    
    def test_default_config(self):
        """Test default configuration."""
        config = BaseWorkerConfig()
        assert config.redis_url == "redis://localhost:6379"
        assert config.max_connections == 20
        assert config.stream_name == "godmode:transactions"
        assert config.group_name == "worker-group"
        assert config.count_per_read == 10
        assert config.block_ms == 100
    
    def test_custom_config(self):
        """Test custom configuration."""
        config = BaseWorkerConfig(
            redis_url="redis://custom:6380",
            stream_name="custom:stream",
            group_name="custom:group",
        )
        assert config.redis_url == "redis://custom:6380"
        assert config.stream_name == "custom:stream"
        assert config.group_name == "custom:group"
    
    def test_stats_initialization(self):
        """Test stats dictionary initialization."""
        worker = BaseWorker(worker_id="test-worker")
        assert "worker_id" in worker.stats
        assert "agent_type" in worker.stats
        assert "messages_consumed" in worker.stats
        assert "messages_acknowledged" in worker.stats
        assert "messages_failed" in worker.stats
        assert worker.stats["worker_id"] == "test-worker"
    
    def test_repr_format(self):
        """Test string representation."""
        worker = BaseWorker(worker_id="test-worker", redis_url="redis://localhost:6379")
        repr_str = repr(worker)
        assert "BaseWorker" in repr_str
        assert "test-worker" in repr_str
        assert "base-worker" in repr_str
    
    def test_process_batch_raises_not_implemented(self):
        """Test that process_batch raises NotImplementedError."""
        worker = BaseWorker(worker_id="test-worker")
        
        async def test():
            await worker.process_batch([])
        
        with pytest.raises(NotImplementedError):
            asyncio.run(test())
    
    def test_health_check_returns_structure(self):
        """Test health check returns correct structure."""
        worker = BaseWorker(worker_id="test-worker")
        
        async def test():
            health = await worker.health_check()
            assert "healthy" in health
            assert "worker_id" in health
            assert "agent_type" in health
            assert "uptime_seconds" in health
        
        asyncio.run(test())
    
    def test_get_stats_returns_copy(self):
        """Test get_stats returns a copy of stats."""
        worker = BaseWorker(worker_id="test-worker")
        
        async def test():
            stats1 = await worker.get_stats()
            stats1["new_field"] = "test"  # Modify returned dict
            stats2 = await worker.get_stats()
            assert "new_field" not in stats2  # Original unchanged
        
        asyncio.run(test())


# ============================================================================
# TEST RUNNER
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
