"""HOSTILE TAKEOVER PROTOCOL - Overlord Agents

Systematic, aggressive migration strategy to make legacy systems irrelevant.

Components:
- OverlordAgent: Master orchestrator coordinating all takeover operations
- BattleMonitorAgent: Performance war - parallel benchmarking
- DatabaseReaperAgent: Continuous data migration from TimescaleDB to Redis
- SirenController: Auto-enable logic for autonomous system takeover
- MirageFeatures: Advanced APIs impossible with legacy system
"""

from .overlord_agent import OverlordAgent
from .battle_monitor_agent import BattleMonitorAgent
from .database_reaper_agent import DatabaseReaperAgent
from .siren_controller import SirenController
from .mirage_features import MirageFeatures

__all__ = [
    "OverlordAgent",
    "BattleMonitorAgent", 
    "DatabaseReaperAgent",
    "SirenController",
    "MirageFeatures",
]

__version__ = "1.0.0"
__codename__ = "HOSTILE_TAKEOVER"
