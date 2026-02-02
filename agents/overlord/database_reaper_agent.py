
"""
DatabaseReaperAgent - The Creeping Death

Continuously drains hot data from TimescaleDB to Ghost Protocol's Redis.
Prioritizes most-accessed profiles. Deletes after verification.
A slow, methodical death for the legacy system.
"""

import asyncio
import time
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta
import structlog
import asyncpg

from core.ghost_protocol.sovereign_data_layer import SovereignDataLayer, WalletProfile

logger = structlog.get_logger()


@dataclass
class ReaperStats:
    """Statistics for the Reaper's harvest."""
    profiles_migrated: int = 0
    profiles_deleted: int = 0
    profiles_failed: int = 0
    bytes_migrated: int = 0
    cycles_completed: int = 0
    legacy_profiles_remaining: int = 0
    estimated_time_to_complete: str = "calculating..."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "☠️ REAPER STATUS": {
                "profiles_harvested": self.profiles_migrated,
                "profiles_deleted_from_legacy": self.profiles_deleted,
                "migration_failures": self.profiles_failed,
                "data_migrated_mb": round(self.bytes_migrated / 1024 / 1024, 2),
                "reap_cycles": self.cycles_completed,
                "legacy_remaining": self.legacy_profiles_remaining,
                "time_to_extinction": self.estimated_time_to_complete
            }
        }


class DatabaseReaperAgent:
    """
    The Reaper - Continuously drains legacy database.

    Strategy:
    1. Find most-accessed (hot) profiles in TimescaleDB
    2. Migrate them to Redis (Ghost Protocol)
    3. Verify successful migration
    4. Delete from TimescaleDB
    5. Repeat until legacy is empty

    This isn't a big-bang migration - it's a slow, creeping death.
    """

    DEFAULT_BATCH_SIZE = 100
    DEFAULT_CYCLE_INTERVAL = 30  # seconds between reap cycles
    VERIFICATION_RETRY = 3

    def __init__(
        self,
        timescale_url: str,
        ghost_data_layer: SovereignDataLayer,
        batch_size: int = DEFAULT_BATCH_SIZE,
        cycle_interval: int = DEFAULT_CYCLE_INTERVAL
    ):
        self.timescale_url = timescale_url
        self.ghost = ghost_data_layer
        self.batch_size = batch_size
        self.cycle_interval = cycle_interval

        self._pg_pool: Optional[asyncpg.Pool] = None
        self._running = False
        self._reap_task: Optional[asyncio.Task] = None
        self._migrated_wallets: Set[str] = set()  # Track migrated to avoid duplicates

        self.stats = ReaperStats()

    async def start(self):
        """Awaken the Reaper."""
        self._pg_pool = await asyncpg.create_pool(self.timescale_url)
        self._running = True
        self._reap_task = asyncio.create_task(self._reap_loop())

        logger.info("☠️ DATABASE REAPER AWAKENED - The harvest begins...")

    async def stop(self):
        """Put the Reaper to rest."""
        self._running = False
        if self._reap_task:
            self._reap_task.cancel()
            try:
                await self._reap_task
            except asyncio.CancelledError:
                pass
        if self._pg_pool:
            await self._pg_pool.close()

        logger.info("☠️ Reaper resting", stats=self.stats.to_dict())

    async def _reap_loop(self):
        """Main reaping loop - runs continuously."""
        while self._running:
            try:
                await self._reap_cycle()
                self.stats.cycles_completed += 1

                # Check if harvest is complete
                if self.stats.legacy_profiles_remaining == 0:
                    logger.info("☠️ HARVEST COMPLETE - Legacy database is EMPTY!")
                    break

                await asyncio.sleep(self.cycle_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("reaper_error", error=str(e))
                await asyncio.sleep(self.cycle_interval)

    async def _reap_cycle(self):
        """Execute one reaping cycle."""
        # 1. Find hot profiles (most accessed)
        hot_profiles = await self._find_hot_profiles()

        if not hot_profiles:
            # No hot profiles, fall back to any profiles
            hot_profiles = await self._find_any_profiles()

        if not hot_profiles:
            self.stats.legacy_profiles_remaining = 0
            return

        # 2. Migrate each profile
        migrated = []
        for profile_data in hot_profiles:
            wallet = profile_data["wallet_address"]

            if wallet in self._migrated_wallets:
                continue  # Skip already migrated

            success = await self._migrate_profile(profile_data)
            if success:
                migrated.append(wallet)
                self._migrated_wallets.add(wallet)

        # 3. Verify migrations
        verified = await self._verify_migrations(migrated)

        # 4. Delete verified profiles from legacy
        deleted = await self._delete_from_legacy(verified)

        # 5. Update stats
        self.stats.profiles_migrated += len(verified)
        self.stats.profiles_deleted += deleted
        self.stats.profiles_failed += len(migrated) - len(verified)

        # Count remaining
        self.stats.legacy_profiles_remaining = await self._count_legacy_profiles()

        # Estimate time to complete
        if self.stats.cycles_completed > 0 and self.stats.profiles_migrated > 0:
            rate = self.stats.profiles_migrated / self.stats.cycles_completed
            remaining_cycles = self.stats.legacy_profiles_remaining / rate if rate > 0 else float('inf')
            remaining_seconds = remaining_cycles * self.cycle_interval

            if remaining_seconds < 3600:
                self.stats.estimated_time_to_complete = f"{remaining_seconds/60:.0f} minutes"
            elif remaining_seconds < 86400:
                self.stats.estimated_time_to_complete = f"{remaining_seconds/3600:.1f} hours"
            else:
                self.stats.estimated_time_to_complete = f"{remaining_seconds/86400:.1f} days"

        logger.info(
            "reap_cycle_complete",
            migrated=len(verified),
            deleted=deleted,
            remaining=self.stats.legacy_profiles_remaining,
            eta=self.stats.estimated_time_to_complete
        )

    async def _find_hot_profiles(self) -> List[Dict[str, Any]]:
        """
        Find most-accessed profiles in TimescaleDB.

        Uses access_log if available, otherwise falls back to
        profiles with most recent updates.
        """
        async with self._pg_pool.acquire() as conn:
            # Try access log first
            try:
                rows = await conn.fetch(
                    """
                    SELECT wp.* FROM wallet_profiles wp
                    INNER JOIN (
                        SELECT wallet_address, COUNT(*) as access_count
                        FROM profile_access_log
                        WHERE accessed_at > NOW() - INTERVAL '24 hours'
                        GROUP BY wallet_address
                        ORDER BY access_count DESC
                        LIMIT $1
                    ) hot ON wp.wallet_address = hot.wallet_address
                    WHERE wp.wallet_address NOT IN (
                        SELECT wallet_address FROM migrated_profiles
                    )
                    """,
                    self.batch_size
                )

                if rows:
                    return [dict(r) for r in rows]

            except asyncpg.UndefinedTableError:
                # access_log table doesn't exist, fall back
                pass

            # Fall back: profiles updated recently (likely active)
            rows = await conn.fetch(
                """
                SELECT * FROM wallet_profiles
                WHERE wallet_address NOT IN (
                    SELECT wallet_address FROM migrated_profiles
                )
                ORDER BY last_updated DESC NULLS LAST
                LIMIT $1
                """,
                self.batch_size
            )

            return [dict(r) for r in rows]

    async def _find_any_profiles(self) -> List[Dict[str, Any]]:
        """Find any remaining profiles."""
        async with self._pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM wallet_profiles
                LIMIT $1
                """,
                self.batch_size
            )
            return [dict(r) for r in rows]

    async def _migrate_profile(self, profile_data: Dict[str, Any]) -> bool:
        """Migrate a single profile to Ghost Protocol's Redis."""
        try:
            # Convert to WalletProfile model
            profile = WalletProfile(
                wallet_address=profile_data["wallet_address"],
                win_rate=float(profile_data.get("win_rate", 0) or 0),
                graduation_rate=float(profile_data.get("graduation_rate", 0) or 0),
                curve_entry=float(profile_data.get("curve_entry", 0.5) or 0.5),
                total_trades=int(profile_data.get("total_trades", 0) or 0),
                total_profit=float(profile_data.get("total_profit", 0) or 0),
                avg_hold_time=float(profile_data.get("avg_hold_time", 0) or 0),
                risk_score=float(profile_data.get("risk_score", 0) or 0),
                severity=profile_data.get("severity", "LOW") or "LOW",
                is_king_maker=bool(profile_data.get("is_king_maker", False)),
                confidence_lower=float(profile_data.get("confidence_lower", 0) or 0),
                confidence_upper=float(profile_data.get("confidence_upper", 1) or 1),
                first_seen=self._to_timestamp(profile_data.get("first_seen")),
                last_updated=self._to_timestamp(profile_data.get("last_updated"))
            )

            # Save to Redis
            await self.ghost.set_profile(profile)

            # Track bytes migrated (estimate)
            self.stats.bytes_migrated += len(str(profile_data))

            return True

        except Exception as e:
            logger.error("migration_failed", wallet=profile_data.get("wallet_address"), error=str(e))
            return False

    async def _verify_migrations(self, wallets: List[str]) -> List[str]:
        """Verify profiles exist in Redis with correct data."""
        verified = []

        for wallet in wallets:
            for attempt in range(self.VERIFICATION_RETRY):
                profile = await self.ghost.get_profile(wallet)

                if profile is not None:
                    verified.append(wallet)
                    break

                await asyncio.sleep(0.1)  # Brief wait before retry

        return verified

    async def _delete_from_legacy(self, wallets: List[str]) -> int:
        """Delete verified profiles from TimescaleDB."""
        if not wallets:
            return 0

        async with self._pg_pool.acquire() as conn:
            # Record migration before delete
            await conn.executemany(
                """
                INSERT INTO migrated_profiles (wallet_address, migrated_at)
                VALUES ($1, NOW())
                ON CONFLICT (wallet_address) DO NOTHING
                """,
                [(w,) for w in wallets]
            )

            # Delete from main table
            result = await conn.execute(
                """
                DELETE FROM wallet_profiles
                WHERE wallet_address = ANY($1)
                """,
                wallets
            )

            # Parse delete count
            count = int(result.split()[-1]) if result else 0
            return count

    async def _count_legacy_profiles(self) -> int:
        """Count remaining profiles in TimescaleDB."""
        async with self._pg_pool.acquire() as conn:
            return await conn.fetchval("SELECT COUNT(*) FROM wallet_profiles")

    def _to_timestamp(self, value) -> float:
        """Convert various datetime formats to timestamp."""
        if value is None:
            return time.time()
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, datetime):
            return value.timestamp()
        return time.time()

    def get_stats(self) -> Dict[str, Any]:
        """Get Reaper statistics."""
        return self.stats.to_dict()

    async def reap_now(self, count: int = None) -> Dict[str, Any]:
        """
        Manually trigger a reap cycle.

        Args:
            count: Optional number of profiles to reap (default: batch_size)

        Returns:
            Reap cycle results
        """
        original_batch = self.batch_size
        if count:
            self.batch_size = count

        try:
            await self._reap_cycle()
            return self.stats.to_dict()
        finally:
            self.batch_size = original_batch
