"""OVERLORD AGENT - Master Orchestrator of the Hostile Takeover

Coordinates all takeover operations:
- BattleMonitor: Performance benchmarking
- DatabaseReaper: Data migration
- SirenController: Auto-enable logic
- MirageFeatures: Advanced APIs
"""

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class TakeoverStatus:
    """Current status of the hostile takeover."""
    phase: str = "INFILTRATION"  # INFILTRATION -> DOMINANCE -> TAKEOVER -> VICTORY
    ghost_protocol_enabled: bool = False
    legacy_system_active: bool = True
    battle_score: float = 0.0  # Ghost Protocol advantage ratio
    profiles_migrated: int = 0
    profiles_remaining: int = 0
    siren_triggered: bool = False
    takeover_timestamp: Optional[datetime] = None
    uptime_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "ghost_protocol_enabled": self.ghost_protocol_enabled,
            "legacy_system_active": self.legacy_system_active,
            "battle_score": self.battle_score,
            "profiles_migrated": self.profiles_migrated,
            "profiles_remaining": self.profiles_remaining,
            "siren_triggered": self.siren_triggered,
            "takeover_timestamp": self.takeover_timestamp.isoformat() if self.takeover_timestamp else None,
            "uptime_seconds": self.uptime_seconds,
        }


class OverlordAgent:
    """Master orchestrator of the Hostile Takeover Protocol.

    Coordinates all agents to systematically replace the legacy system
    with Ghost Protocol while maintaining zero downtime.
    """

    def __init__(
        self,
        battle_mode: bool = True,
        auto_enable_threshold: float = 3.0,
        siren_stability_minutes: int = 10,
        reaper_enabled: bool = True,
        reaper_batch_size: int = 100,
    ):
        # Configuration from environment or defaults
        self.battle_mode = os.getenv("BATTLE_MODE", str(battle_mode)).lower() == "true"
        self.auto_enable_threshold = float(os.getenv(
            "GHOST_PROTOCOL_AUTO_ENABLE_THRESHOLD", 
            str(auto_enable_threshold)
        ))
        self.siren_stability_minutes = int(os.getenv(
            "SIREN_STABILITY_MINUTES",
            str(siren_stability_minutes)
        ))
        self.reaper_enabled = os.getenv("REAPER_ENABLED", str(reaper_enabled)).lower() == "true"
        self.reaper_batch_size = int(os.getenv("REAPER_BATCH_SIZE", str(reaper_batch_size)))

        # Status tracking
        self.status = TakeoverStatus()
        self._start_time = time.time()
        self._running = False

        # Sub-agents (lazy loaded)
        self._battle_monitor = None
        self._database_reaper = None
        self._siren_controller = None
        self._mirage_features = None

        # Tasks
        self._orchestration_task: Optional[asyncio.Task] = None

        logger.info(
            "OverlordAgent initialized",
            battle_mode=self.battle_mode,
            auto_enable_threshold=self.auto_enable_threshold,
            siren_stability_minutes=self.siren_stability_minutes,
            reaper_enabled=self.reaper_enabled,
            reaper_batch_size=self.reaper_batch_size,
        )

    @property
    def battle_monitor(self):
        """Lazy load BattleMonitorAgent."""
        if self._battle_monitor is None:
            from .battle_monitor_agent import BattleMonitorAgent
            self._battle_monitor = BattleMonitorAgent()
        return self._battle_monitor

    @property
    def database_reaper(self):
        """Lazy load DatabaseReaperAgent."""
        if self._database_reaper is None:
            from .database_reaper_agent import DatabaseReaperAgent
            self._database_reaper = DatabaseReaperAgent(
                batch_size=self.reaper_batch_size
            )
        return self._database_reaper

    @property
    def siren_controller(self):
        """Lazy load SirenController."""
        if self._siren_controller is None:
            from .siren_controller import SirenController
            self._siren_controller = SirenController(
                threshold=self.auto_enable_threshold,
                stability_minutes=self.siren_stability_minutes,
            )
        return self._siren_controller

    @property
    def mirage_features(self):
        """Lazy load MirageFeatures."""
        if self._mirage_features is None:
            from .mirage_features import MirageFeatures
            self._mirage_features = MirageFeatures()
        return self._mirage_features

    async def start(self):
        """Start the hostile takeover."""
        if self._running:
            logger.warning("OverlordAgent already running")
            return

        self._running = True
        self._start_time = time.time()
        self.status.phase = "INFILTRATION"

        logger.info("🔥 HOSTILE TAKEOVER PROTOCOL INITIATED 🔥")

        # Start all sub-agents
        tasks = []

        if self.battle_mode:
            tasks.append(asyncio.create_task(self.battle_monitor.start()))
            logger.info("⚔️ BattleMonitor engaged - Performance war begins")

        if self.reaper_enabled:
            tasks.append(asyncio.create_task(self.database_reaper.start()))
            logger.info("💀 DatabaseReaper deployed - Legacy system death march begins")

        tasks.append(asyncio.create_task(self.siren_controller.start()))
        logger.info("🚨 SirenController armed - Auto-takeover ready")

        tasks.append(asyncio.create_task(self.mirage_features.start()))
        logger.info("✨ MirageFeatures online - Feature envy activated")

        # Start orchestration loop
        self._orchestration_task = asyncio.create_task(self._orchestration_loop())

        logger.info(
            "HOSTILE TAKEOVER PROTOCOL FULLY OPERATIONAL",
            components_active=len(tasks) + 1,
        )

    async def stop(self):
        """Stop the hostile takeover (graceful shutdown)."""
        if not self._running:
            return

        self._running = False

        # Stop orchestration
        if self._orchestration_task:
            self._orchestration_task.cancel()
            try:
                await self._orchestration_task
            except asyncio.CancelledError:
                pass

        # Stop sub-agents
        if self._battle_monitor:
            await self._battle_monitor.stop()
        if self._database_reaper:
            await self._database_reaper.stop()
        if self._siren_controller:
            await self._siren_controller.stop()
        if self._mirage_features:
            await self._mirage_features.stop()

        logger.info("OverlordAgent stopped")

    async def _orchestration_loop(self):
        """Main orchestration loop - coordinates all takeover operations."""
        while self._running:
            try:
                # Update uptime
                self.status.uptime_seconds = time.time() - self._start_time

                # Collect metrics from sub-agents
                if self.battle_mode and self._battle_monitor:
                    battle_stats = self._battle_monitor.get_stats()
                    self.status.battle_score = battle_stats.get("advantage_ratio", 0.0)

                if self.reaper_enabled and self._database_reaper:
                    reaper_stats = self._database_reaper.get_stats()
                    self.status.profiles_migrated = reaper_stats.get("profiles_migrated", 0)
                    self.status.profiles_remaining = reaper_stats.get("profiles_remaining", 0)

                # Check Siren status
                if self._siren_controller:
                    siren_status = self._siren_controller.get_status()
                    self.status.siren_triggered = siren_status.get("triggered", False)

                    if self.status.siren_triggered and not self.status.ghost_protocol_enabled:
                        await self._execute_takeover()

                # Update phase based on progress
                self._update_phase()

                # Log status periodically
                logger.debug(
                    "Takeover status update",
                    phase=self.status.phase,
                    battle_score=f"{self.status.battle_score:.2f}x",
                    migrated=self.status.profiles_migrated,
                    remaining=self.status.profiles_remaining,
                )

                await asyncio.sleep(5)  # Update every 5 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Orchestration error: {e}")
                await asyncio.sleep(1)

    def _update_phase(self):
        """Update takeover phase based on current status."""
        if self.status.ghost_protocol_enabled:
            if self.status.profiles_remaining == 0:
                self.status.phase = "VICTORY"
                self.status.legacy_system_active = False
            else:
                self.status.phase = "TAKEOVER"
        elif self.status.battle_score >= self.auto_enable_threshold:
            self.status.phase = "DOMINANCE"
        else:
            self.status.phase = "INFILTRATION"

    async def _execute_takeover(self):
        """Execute the actual system takeover."""
        logger.warning("🚨🚨🚨 SIREN TRIGGERED - EXECUTING TAKEOVER 🚨🚨🚨")

        self.status.ghost_protocol_enabled = True
        self.status.takeover_timestamp = datetime.now(timezone.utc)
        self.status.phase = "TAKEOVER"

        # Notify all systems
        logger.info(
            "GHOST PROTOCOL NOW PRIMARY SYSTEM",
            takeover_time=self.status.takeover_timestamp.isoformat(),
            battle_score=f"{self.status.battle_score:.2f}x advantage",
        )

        # Accelerate reaper to finish migration
        if self._database_reaper:
            await self._database_reaper.accelerate()

    def get_status(self) -> dict:
        """Get current takeover status."""
        self.status.uptime_seconds = time.time() - self._start_time
        return self.status.to_dict()

    def get_stats(self) -> dict:
        """Get comprehensive statistics from all sub-agents."""
        stats = {
            "overlord": self.get_status(),
            "battle_monitor": self._battle_monitor.get_stats() if self._battle_monitor else {},
            "database_reaper": self._database_reaper.get_stats() if self._database_reaper else {},
            "siren_controller": self._siren_controller.get_status() if self._siren_controller else {},
            "mirage_features": self._mirage_features.get_stats() if self._mirage_features else {},
        }
        return stats
