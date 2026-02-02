
"""
SirenController - The Auto-Enable System

Monitors Ghost Protocol performance vs Legacy.
When Ghost Protocol achieves dominance, automatically switches backends.
No human hesitation. No bureaucracy. Pure performance-based decision.
"""

import asyncio
import time
from typing import Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import structlog

from .battle_monitor_agent import BattleMonitorAgent, BattleStats

logger = structlog.get_logger()


@dataclass
class SirenState:
    """Current state of the Siren."""
    is_armed: bool = False
    dominance_start_time: Optional[float] = None
    dominance_duration_seconds: float = 0.0
    threshold_speedup: float = 3.0
    stability_minutes: int = 10
    auto_enabled: bool = False
    auto_enabled_at: Optional[float] = None

    def to_dict(self):
        return {
            "🚨 SIREN STATUS": {
                "armed": self.is_armed,
                "auto_enabled": self.auto_enabled,
                "dominance_duration": f"{self.dominance_duration_seconds:.0f}s",
                "required_duration": f"{self.stability_minutes * 60}s",
                "threshold_speedup": f"{self.threshold_speedup}x",
                "auto_enabled_at": datetime.fromtimestamp(self.auto_enabled_at).isoformat() if self.auto_enabled_at else None
            }
        }


class SirenController:
    """
    The Siren - Auto-enables Ghost Protocol when it proves dominance.

    Logic:
    1. Monitor BattleMonitorAgent stats continuously
    2. Track consecutive time Ghost Protocol is dominant
    3. When dominance persists for stability_minutes, trigger Siren
    4. Call enable_callback to switch backends
    5. Log triumphant message
    """

    CHECK_INTERVAL = 5  # seconds between checks

    def __init__(
        self,
        battle_monitor: BattleMonitorAgent,
        enable_callback: Callable,
        threshold_speedup: float = 3.0,
        stability_minutes: int = 10,
        min_battles: int = 1000
    ):
        """
        Args:
            battle_monitor: The battle monitor providing stats
            enable_callback: Async function to call when enabling Ghost Protocol
            threshold_speedup: Minimum speedup ratio for dominance
            stability_minutes: Minutes of sustained dominance required
            min_battles: Minimum battles before considering auto-enable
        """
        self.battle = battle_monitor
        self.enable_callback = enable_callback
        self.min_battles = min_battles

        self.state = SirenState(
            threshold_speedup=threshold_speedup,
            stability_minutes=stability_minutes
        )

        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    async def start(self):
        """Arm the Siren."""
        self._running = True
        self.state.is_armed = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

        logger.info(
            "siren_armed",
            threshold=f"{self.state.threshold_speedup}x speedup",
            stability=f"{self.state.stability_minutes} minutes",
            min_battles=self.min_battles
        )

    async def stop(self):
        """Disarm the Siren."""
        self._running = False
        self.state.is_armed = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("siren_disarmed")

    async def _monitor_loop(self):
        """Continuously monitor for dominance."""
        while self._running:
            try:
                await self._check_dominance()
                await asyncio.sleep(self.CHECK_INTERVAL)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("siren_monitoring_error", error=str(e))
                await asyncio.sleep(self.CHECK_INTERVAL)

    async def _check_dominance(self):
        """Check if Ghost Protocol has achieved dominance."""
        if self.state.auto_enabled:
            return  # Already triggered

        stats = self.battle.get_stats()

        # Check minimum battles
        if stats.total_battles < self.min_battles:
            self._reset_dominance()
            return

        # Check dominance criteria
        is_dominant = self._is_dominant(stats)

        if is_dominant:
            # Track dominance duration
            if self.state.dominance_start_time is None:
                self.state.dominance_start_time = time.time()
                logger.info(
                    "dominance_detected",
                    speedup=f"{stats.current_speedup_ratio:.1f}x"
                )

            self.state.dominance_duration_seconds = time.time() - self.state.dominance_start_time
            required_seconds = self.state.stability_minutes * 60

            # Check if stability period met
            if self.state.dominance_duration_seconds >= required_seconds:
                await self._trigger_siren(stats)
        else:
            # Dominance lost, reset timer
            if self.state.dominance_start_time is not None:
                logger.info("dominance_lost_resetting")
            self._reset_dominance()

    def _is_dominant(self, stats: BattleStats) -> bool:
        """Check if Ghost Protocol meets dominance criteria."""
        # Criteria:
        # 1. Speedup ratio >= threshold
        # 2. Win rate > 95%
        # 3. Fewer errors than legacy

        win_rate = stats.ghost_wins / stats.total_battles if stats.total_battles > 0 else 0

        criteria = {
            "speedup": stats.current_speedup_ratio >= self.state.threshold_speedup,
            "win_rate": win_rate > 0.95,
            "errors": stats.ghost_errors <= stats.legacy_errors
        }

        return all(criteria.values())

    def _reset_dominance(self):
        """Reset dominance tracking."""
        self.state.dominance_start_time = None
        self.state.dominance_duration_seconds = 0.0

    async def _trigger_siren(self, stats: BattleStats):
        """
        TRIGGER THE SIREN!

        Ghost Protocol has proven dominance. Time to take over.
        """
        logger.info("=" * 70)
        logger.info("🚨🚨🚨 SIREN ACTIVATED 🚨🚨🚨")
        logger.info("=" * 70)
        logger.info("")
        logger.info("Ghost Protocol has achieved DOMINANCE.")
        logger.info("")
        logger.info(f"  Performance: {stats.current_speedup_ratio:.1f}x faster")
        logger.info(f"  Win Rate: {stats.ghost_wins}/{stats.total_battles} ({stats.ghost_wins/stats.total_battles*100:.1f}%)")
        logger.info(f"  Stability: {self.state.dominance_duration_seconds/60:.1f} minutes sustained")
        logger.info(f"  Cost Savings: ${stats.legacy_cost_estimate:.2f}/day")
        logger.info("")
        logger.info("Switching backends automatically...")
        logger.info("=" * 70)

        try:
            # Call the enable callback
            if asyncio.iscoroutinefunction(self.enable_callback):
                await self.enable_callback()
            else:
                self.enable_callback()

            self.state.auto_enabled = True
            self.state.auto_enabled_at = time.time()

            logger.info("")
            logger.info("✅ GHOST PROTOCOL IS NOW THE PRIMARY BACKEND")
            logger.info("   The legacy system has been relegated to history.")
            logger.info("")

        except Exception as e:
            logger.error("failed_to_enable_ghost_protocol", error=str(e))
            self._reset_dominance()  # Try again later

    def get_state(self) -> dict:
        """Get current Siren state."""
        return self.state.to_dict()

    def force_trigger(self):
        """Manually trigger Siren (for testing/emergency)."""
        logger.warning("manual_siren_trigger_requested")
        asyncio.create_task(self._trigger_siren(self.battle.get_stats()))
