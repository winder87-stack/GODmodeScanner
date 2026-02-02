
"""
BattleMonitorAgent - The Canary Performance War

Runs every request through both backends, benchmarks everything,
and maintains a live leaderboard proving Ghost Protocol dominance.
"""

import asyncio
import time
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger()


@dataclass
class BattleResult:
    """Result of a single battle (request to both systems)."""
    operation: str
    ghost_latency_ms: float
    legacy_latency_ms: float
    ghost_success: bool
    legacy_success: bool
    ghost_error: Optional[str] = None
    legacy_error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def ghost_won(self) -> bool:
        """Ghost wins if faster AND successful."""
        if not self.ghost_success:
            return False
        if not self.legacy_success:
            return True  # Ghost wins by default
        return self.ghost_latency_ms < self.legacy_latency_ms

    @property
    def speedup_ratio(self) -> float:
        """How many times faster is Ghost Protocol."""
        if self.ghost_latency_ms == 0:
            return float('inf')
        return self.legacy_latency_ms / self.ghost_latency_ms


@dataclass
class BattleStats:
    """Aggregated battle statistics."""
    total_battles: int = 0
    ghost_wins: int = 0
    legacy_wins: int = 0
    ghost_errors: int = 0
    legacy_errors: int = 0
    ghost_avg_latency_ms: float = 0.0
    legacy_avg_latency_ms: float = 0.0
    ghost_p95_latency_ms: float = 0.0
    legacy_p95_latency_ms: float = 0.0
    ghost_cost_estimate: float = 0.0  # Always $0
    legacy_cost_estimate: float = 0.0
    current_speedup_ratio: float = 0.0

    def to_leaderboard(self) -> Dict[str, Any]:
        """Format for public leaderboard display."""
        ghost_win_rate = (self.ghost_wins / self.total_battles * 100) if self.total_battles > 0 else 0

        return {
            "🏆 LEADERBOARD": {
                "Ghost Protocol": {
                    "status": "🟢 DOMINANT" if ghost_win_rate > 90 else "🟡 COMPETING",
                    "avg_latency_ms": round(self.ghost_avg_latency_ms, 2),
                    "p95_latency_ms": round(self.ghost_p95_latency_ms, 2),
                    "errors": self.ghost_errors,
                    "cost_per_day": f"${self.ghost_cost_estimate:.2f}",
                    "wins": self.ghost_wins
                },
                "Legacy System": {
                    "status": "🔴 LOSING" if ghost_win_rate > 90 else "🟡 STRUGGLING",
                    "avg_latency_ms": round(self.legacy_avg_latency_ms, 2),
                    "p95_latency_ms": round(self.legacy_p95_latency_ms, 2),
                    "errors": self.legacy_errors,
                    "cost_per_day": f"${self.legacy_cost_estimate:.2f}",
                    "wins": self.legacy_wins
                }
            },
            "📊 SUMMARY": {
                "total_battles": self.total_battles,
                "ghost_win_rate": f"{ghost_win_rate:.1f}%",
                "speedup_ratio": f"{self.current_speedup_ratio:.1f}x faster",
                "cost_savings": f"${self.legacy_cost_estimate - self.ghost_cost_estimate:.2f}/day"
            }
        }


class BattleMonitorAgent:
    """
    The Canary - Runs parallel benchmarks between Ghost Protocol and Legacy.

    Every request goes through both systems. Results are compared.
    A live leaderboard exposes the truth: Ghost Protocol dominance.
    """

    # Cost estimates (per 1000 requests)
    LEGACY_COST_PER_1K = 0.05  # RPC costs + DB costs
    GHOST_COST_PER_1K = 0.0    # Zero cost

    # History for percentile calculations
    MAX_HISTORY = 10000

    def __init__(self, ghost_backend, legacy_backend):
        self.ghost = ghost_backend
        self.legacy = legacy_backend

        self.results: deque[BattleResult] = deque(maxlen=self.MAX_HISTORY)
        self._running = False
        self._stats_task: Optional[asyncio.Task] = None

        # Real-time stats
        self._current_stats = BattleStats()
        self._stats_lock = asyncio.Lock()

    async def start(self):
        """Start the battle monitor."""
        self._running = True
        self._stats_task = asyncio.create_task(self._stats_aggregation_loop())
        logger.info("⚔️ BattleMonitorAgent ACTIVATED - Performance war begins!")

    async def stop(self):
        """Stop the battle monitor."""
        self._running = False
        if self._stats_task:
            self._stats_task.cancel()
            try:
                await self._stats_task
            except asyncio.CancelledError:
                pass
        logger.info("BattleMonitorAgent stopped")

    async def battle(
        self,
        operation: str,
        ghost_func: Callable,
        legacy_func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute operation on BOTH backends, benchmark, return Ghost result.

        Args:
            operation: Name of the operation (e.g., "get_wallet_profile")
            ghost_func: Ghost Protocol function to call
            legacy_func: Legacy system function to call
            *args, **kwargs: Arguments for both functions

        Returns:
            Result from Ghost Protocol (the winner's result)
        """
        # Run both in parallel
        ghost_result, legacy_result = await asyncio.gather(
            self._timed_call(ghost_func, *args, **kwargs),
            self._timed_call(legacy_func, *args, **kwargs),
            return_exceptions=True
        )

        # Unpack results
        ghost_latency, ghost_data, ghost_error = ghost_result
        legacy_latency, legacy_data, legacy_error = legacy_result

        # Record battle result
        result = BattleResult(
            operation=operation,
            ghost_latency_ms=ghost_latency,
            legacy_latency_ms=legacy_latency,
            ghost_success=ghost_error is None,
            legacy_success=legacy_error is None,
            ghost_error=str(ghost_error) if ghost_error else None,
            legacy_error=str(legacy_error) if legacy_error else None
        )

        self.results.append(result)

        # Log significant events
        if result.ghost_won:
            if result.speedup_ratio > 10:
                logger.info(
                    "crushing_victory",
                    operation=operation,
                    speedup_ratio=f"{result.speedup_ratio:.0f}x"
                )
        else:
            logger.warning(
                "legacy_won",
                operation=operation,
                ghost_ms=round(result.ghost_latency_ms, 2),
                legacy_ms=round(result.legacy_latency_ms, 2)
            )

        if legacy_error and not ghost_error:
            logger.info(
                "legacy_failed_ghost_succeeded",
                operation=operation,
                error=str(legacy_error)[:100]
            )

        # Return Ghost result (the system we're promoting)
        if ghost_error:
            raise ghost_error
        return ghost_data

    async def _timed_call(self, func: Callable, *args, **kwargs) -> tuple:
        """Execute function and measure time."""
        start = time.perf_counter()
        error = None
        data = None

        try:
            data = await func(*args, **kwargs)
        except Exception as e:
            error = e

        latency_ms = (time.perf_counter() - start) * 1000
        return latency_ms, data, error

    async def _stats_aggregation_loop(self):
        """Background task to aggregate stats every second."""
        while self._running:
            try:
                await asyncio.sleep(1.0)
                await self._calculate_stats()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("stats_aggregation_error", error=str(e))

    async def _calculate_stats(self):
        """Calculate current battle statistics."""
        if not self.results:
            return

        async with self._stats_lock:
            results = list(self.results)

            # Basic counts
            total = len(results)
            ghost_wins = sum(1 for r in results if r.ghost_won)
            ghost_errors = sum(1 for r in results if not r.ghost_success)
            legacy_errors = sum(1 for r in results if not r.legacy_success)

            # Latencies (excluding errors)
            ghost_latencies = [r.ghost_latency_ms for r in results if r.ghost_success]
            legacy_latencies = [r.legacy_latency_ms for r in results if r.legacy_success]

            ghost_avg = sum(ghost_latencies) / len(ghost_latencies) if ghost_latencies else 0
            legacy_avg = sum(legacy_latencies) / len(legacy_latencies) if legacy_latencies else 0

            # P95 latencies
            ghost_p95 = sorted(ghost_latencies)[int(len(ghost_latencies) * 0.95)] if ghost_latencies else 0
            legacy_p95 = sorted(legacy_latencies)[int(len(legacy_latencies) * 0.95)] if legacy_latencies else 0

            # Cost estimates (per day, assuming 100k requests/day)
            daily_requests = 100000
            legacy_cost = (daily_requests / 1000) * self.LEGACY_COST_PER_1K
            ghost_cost = 0.0

            # Speedup ratio
            speedup = legacy_avg / ghost_avg if ghost_avg > 0 else float('inf')

            self._current_stats = BattleStats(
                total_battles=total,
                ghost_wins=ghost_wins,
                legacy_wins=total - ghost_wins,
                ghost_errors=ghost_errors,
                legacy_errors=legacy_errors,
                ghost_avg_latency_ms=ghost_avg,
                legacy_avg_latency_ms=legacy_avg,
                ghost_p95_latency_ms=ghost_p95,
                legacy_p95_latency_ms=legacy_p95,
                ghost_cost_estimate=ghost_cost,
                legacy_cost_estimate=legacy_cost,
                current_speedup_ratio=speedup
            )

    def get_stats(self) -> BattleStats:
        """Get current battle statistics."""
        return self._current_stats

    def get_leaderboard(self) -> Dict[str, Any]:
        """Get formatted leaderboard for display."""
        return self._current_stats.to_leaderboard()

    def is_ghost_dominant(self, threshold: float = 3.0, min_battles: int = 100) -> bool:
        """
        Check if Ghost Protocol has achieved dominance.

        Args:
            threshold: Minimum speedup ratio required
            min_battles: Minimum battles before declaring dominance

        Returns:
            True if Ghost Protocol is dominant
        """
        stats = self._current_stats

        if stats.total_battles < min_battles:
            return False

        # Dominance criteria:
        # 1. Speedup ratio meets threshold
        # 2. Ghost win rate > 95%
        # 3. Zero Ghost errors (or fewer than Legacy)

        win_rate = stats.ghost_wins / stats.total_battles if stats.total_battles > 0 else 0

        return (
            stats.current_speedup_ratio >= threshold and
            win_rate > 0.95 and
            stats.ghost_errors <= stats.legacy_errors
        )

    def get_recent_battles(self, n: int = 10) -> List[Dict[str, Any]]:
        """Get N most recent battle results."""
        recent = list(self.results)[-n:]
        return [
            {
                "operation": r.operation,
                "ghost_ms": round(r.ghost_latency_ms, 2),
                "legacy_ms": round(r.legacy_latency_ms, 2),
                "winner": "Ghost" if r.ghost_won else "Legacy",
                "speedup": f"{r.speedup_ratio:.1f}x",
                "timestamp": datetime.fromtimestamp(r.timestamp).isoformat()
            }
            for r in recent
        ]
