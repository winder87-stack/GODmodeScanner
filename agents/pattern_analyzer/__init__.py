"""Pattern analyzer agent for detecting insider trading patterns.

This module analyzes transaction patterns, token launches, and trading behaviors
to identify potential insider trading activity on pump.fun.
"""

from .agent import PatternAnalyzerAgent
from . import detectors, models

__all__ = ['PatternAnalyzerAgent', 'detectors', 'models']
