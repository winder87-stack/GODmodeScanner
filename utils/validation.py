"""Input validation module for GODMODESCANNER."""

import re
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, validator, Field

# Solana wallet address validation
SOLANA_ADDRESS_PATTERN = re.compile(r'^[1-9A-HJ-NP-Za-km-z]{32,44}$')


class WalletAddress(BaseModel):
    """Validated Solana wallet address."""
    address: str = Field(..., min_length=32, max_length=44)
    
    @validator('address')
    def validate_address(cls, v):
        if not SOLANA_ADDRESS_PATTERN.match(v):
            raise ValueError(f'Invalid Solana wallet address: {v}')
        return v


class TransactionMessage(BaseModel):
    """Validated transaction message."""
    wallet: str
    amount: float = Field(..., gt=0)
    timestamp: datetime
    signature: str = Field(..., min_length=64, max_length=128)
    token_address: Optional[str] = None

    @validator('wallet')
    def validate_wallet(cls, v):
        if not SOLANA_ADDRESS_PATTERN.match(v):
            raise ValueError(f'Invalid wallet address: {v}')
        return v


class RiskScoreInput(BaseModel):
    """Validated risk score input."""
    wallet_address: str
    behavior_score: float = Field(..., ge=0.0, le=1.0)
    timing_score: float = Field(..., ge=0.0, le=1.0)
    network_score: float = Field(..., ge=0.0, le=1.0)
    volume_score: float = Field(..., ge=0.0, le=1.0)

    @validator('wallet_address')
    def validate_wallet(cls, v):
        if not SOLANA_ADDRESS_PATTERN.match(v):
            raise ValueError(f'Invalid wallet address: {v}')
        return v


def validate_sql(query: str) -> bool:
    """Basic SQL injection detection."""
    dangerous_keywords = [
        'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'UPDATE', 'INSERT', 'EXEC',
        '--', '/*', '*/', ';', 'xp_', 'sp_', '\\x00', '\\n', '\\r'
    ]
    query_upper = query.upper()
    return not any(keyword in query_upper for keyword in dangerous_keywords)


def validate_shell(command: str) -> bool:
    """Basic shell injection detection."""
    dangerous_chars = [';', '&', '|', '`', '$', '(', ')', '<', '>', '\n', '\r']
    return not any(char in command for char in dangerous_chars)
