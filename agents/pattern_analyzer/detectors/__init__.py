"""Detection modules for identifying insider trading patterns."""

from .insider_detectors import (
    EarlyBuyDetector,
    CoordinatedTradingDetector,
    LiquidityManipulationDetector,
)

__all__ = [
    'EarlyBuyDetector',
    'CoordinatedTradingDetector',
    'LiquidityManipulationDetector',
]
