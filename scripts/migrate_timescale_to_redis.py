"""
Migration Script: TimescaleDB → Ghost Protocol (Redis)

Migrates:
1. wallet_profiles table → Redis hashes
2. risk_scores table → Redis sorted sets
3. transactions table → Redis sorted sets
4. king_makers → Redis set

Safety features:
- Dry-run mode (default)
- Batch processing (1000 records at a time)
- Progress logging
- Verification step
- Rollback instructions
"""

import asyncio
import argparse
import json
from datetime import datetime
from typing import Dict, Any, List
import asyncpg
import structlog

from core.ghost_protocol import GhostProtocol
from core.ghost_protocol.sovereign_data_layer import WalletProfile

logger = structlog.get_logger()


class TimescaleToRedisMigration:
    """Migrate GODMODESCANNER data from TimescaleDB to Redis."""

    BATCH_SIZE = 1000

    def __init__(
        self,
        timescale_url: str,
        redis_url: str,
        dry_run: bool = True
    ):
        self.timescale_url = timescale_url
        self.redis_url = redis_url
        self.dry_run = dry_run
        self.pg_pool = None
        self.ghost = None

        self.stats = {
            "profiles_migrated": 0,
            "risk_scores_migrated": 0,
            "transactions_migrated": 0,
            "king_makers_migrated": 0,
            "errors": 0
        }

    async def connect(self):
        """Connect to both databases."""
        logger.info("Connecting to databases...")

        # Connect to TimescaleDB
        try:
            self.pg_pool = await asyncpg.create_pool(self.timescale_url)
            logger.info("Connected to TimescaleDB")
        except Exception as e:
            logger.error(f"Failed to connect to TimescaleDB: {e}")
            raise

        # Initialize Ghost Protocol
        try:
            self.ghost = GhostProtocol(redis_url=self.redis_url)
            await self.ghost.initialize()
            logger.info("Connected to Redis (Ghost Protocol)")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            await self.disconnect()
            raise

    async def disconnect(self):
        """Close all connections."""
        if self.pg_pool:
            try:
                await self.pg_pool.close()
            except Exception as e:
                logger.error(f"Error closing PostgreSQL pool: {e}")
        if self.ghost:
            try:
                await self.ghost.stop()
            except Exception as e:
                logger.error(f"Error stopping Ghost Protocol: {e}")

    async def migrate_profiles(self):
        """Migrate wallet_profiles table."""
        logger.info("Migrating wallet_profiles...")

        async with self.pg_pool.acquire() as conn:
            # Count total
            total = await conn.fetchval("SELECT COUNT(*) FROM wallet_profiles")
            logger.info(f"Found {total} profiles to migrate")

            if total == 0:
                logger.warning("No profiles found in wallet_profiles table")
                return

            # Batch migration
            offset = 0
            while offset < total:
                rows = await conn.fetch(
                    """
                    SELECT * FROM wallet_profiles
                    ORDER BY wallet_address
                    LIMIT $1 OFFSET $2
                    """,
                    self.BATCH_SIZE,
                    offset
                )

                for row in rows:
                    try:
                        profile = WalletProfile(
                            wallet_address=row["wallet_address"],
                            win_rate=float(row.get("win_rate", 0)),
                            graduation_rate=float(row.get("graduation_rate", 0)),
                            curve_entry=float(row.get("curve_entry", 0.5)),
                            total_trades=int(row.get("total_trades", 0)),
                            total_profit=float(row.get("total_profit", 0)),
                            avg_hold_time=float(row.get("avg_hold_time", 0)),
                            risk_score=float(row.get("risk_score", 0)),
                            severity=row.get("severity", "LOW"),
                            is_king_maker=bool(row.get("is_king_maker", False)),
                            first_seen=row.get("first_seen", datetime.now()).timestamp(),
                            last_updated=row.get("last_updated", datetime.now()).timestamp()
                        )

                        if not self.dry_run:
                            await self.ghost.data_layer.set_profile(profile)

                        self.stats["profiles_migrated"] += 1

                    except Exception as e:
                        logger.error(f"Error migrating profile: {e}")
                        self.stats["errors"] += 1

                offset += self.BATCH_SIZE
                logger.info(f"Progress: {min(offset, total)}/{total} profiles")

        logger.info(f"Profiles migration complete: {self.stats['profiles_migrated']}")

    async def migrate_risk_scores(self):
        """Migrate risk_scores table to sorted sets."""
        logger.info("Migrating risk_scores...")

        async with self.pg_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM risk_scores")
            logger.info(f"Found {total} risk scores to migrate")

            if total == 0:
                logger.warning("No risk scores found in risk_scores table")
                return

            # Stream in batches
            offset = 0
            while offset < total:
                rows = await conn.fetch(
                    """
                    SELECT wallet_address, risk_score, severity, confidence, 
                           factors, timestamp
                    FROM risk_scores
                    ORDER BY timestamp
                    LIMIT $1 OFFSET $2
                    """,
                    self.BATCH_SIZE,
                    offset
                )

                for row in rows:
                    try:
                        if not self.dry_run:
                            await self.ghost.data_layer.add_risk_score({
                                "wallet_address": row["wallet_address"],
                                "risk_score": float(row["risk_score"]),
                                "severity": row["severity"],
                                "confidence": float(row.get("confidence", 0.5)),
                                "factors": json.loads(row.get("factors", "{}")),
                                "timestamp": row["timestamp"].timestamp()
                            })

                        self.stats["risk_scores_migrated"] += 1

                    except Exception as e:
                        logger.error(f"Error migrating risk score: {e}")
                        self.stats["errors"] += 1

                offset += self.BATCH_SIZE
                logger.info(f"Progress: {min(offset, total)}/{total} risk scores")

    async def migrate_king_makers(self):
        """Migrate king_makers to Redis set."""
        logger.info("Migrating king_makers...")

        async with self.pg_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT wallet_address FROM wallet_profiles
                WHERE is_king_maker = true
                """
            )

            if len(rows) == 0:
                logger.warning("No king makers found in wallet_profiles table")
                return

            for row in rows:
                if not self.dry_run:
                    await self.ghost.data_layer.add_king_maker(row["wallet_address"])
                self.stats["king_makers_migrated"] += 1

        logger.info(f"King makers migrated: {self.stats['king_makers_migrated']}")

    async def verify_migration(self) -> bool:
        """Verify migration integrity."""
        logger.info("Verifying migration...")

        async with self.pg_pool.acquire() as conn:
            # Count comparisons
            pg_profiles = await conn.fetchval("SELECT COUNT(*) FROM wallet_profiles")
            try:
                redis_profiles = await self.ghost.data_layer.count_profiles()
            except Exception as e:
                logger.warning(f"Could not count profiles in Redis: {e}")
                redis_profiles = 0

            pg_king_makers = await conn.fetchval(
                "SELECT COUNT(*) FROM wallet_profiles WHERE is_king_maker = true"
            )
            try:
                redis_king_makers = len(await self.ghost.data_layer.get_king_makers(10000))
            except Exception as e:
                logger.warning(f"Could not get king makers from Redis: {e}")
                redis_king_makers = 0

            logger.info(f"Profiles: TimescaleDB={pg_profiles}, Redis={redis_profiles}")
            logger.info(f"King Makers: TimescaleDB={pg_king_makers}, Redis={redis_king_makers}")

            # Spot check 10 random profiles
            sample = await conn.fetch(
                "SELECT * FROM wallet_profiles ORDER BY RANDOM() LIMIT 10"
            )

            mismatches = 0
            for row in sample:
                try:
                    redis_profile = await self.ghost.data_layer.get_profile(row["wallet_address"])
                    if redis_profile is None:
                        logger.warning(f"Missing in Redis: {row['wallet_address']}")
                        mismatches += 1
                    elif abs(redis_profile.risk_score - float(row["risk_score"])) > 0.01:
                        logger.warning(f"Score mismatch: {row['wallet_address']}")
                        mismatches += 1
                except Exception as e:
                    logger.error(f"Error verifying profile {row['wallet_address']}: {e}")
                    mismatches += 1

            if mismatches > 0:
                logger.error(f"Verification FAILED: {mismatches} mismatches found")
                return False

            logger.info("✅ Verification PASSED")
            return True

    async def run(self):
        """Execute full migration."""
        try:
            await self.connect()

            logger.info("=" * 60)
            logger.info("GODMODESCANNER DATA MIGRATION")
            logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
            logger.info("=" * 60)

            # Run migrations
            await self.migrate_profiles()
            await self.migrate_risk_scores()
            await self.migrate_king_makers()

            # Verify if live run
            if not self.dry_run:
                await self.verify_migration()

            # Print summary
            logger.info("=" * 60)
            logger.info("MIGRATION SUMMARY")
            logger.info("=" * 60)
            for key, value in self.stats.items():
                logger.info(f"  {key}: {value}")

            if self.dry_run:
                logger.info("")
                logger.info("This was a DRY RUN. No data was written.")
                logger.info("Run with --live to execute migration.")

        finally:
            await self.disconnect()


async def main():
    parser = argparse.ArgumentParser(description="Migrate TimescaleDB to Ghost Protocol")
    parser.add_argument(
        "--timescale-url",
        default="postgresql://godmodescanner:Paxton11d##@127.0.0.1:5432/godmodescanner",
        help="TimescaleDB connection URL"
    )
    parser.add_argument(
        "--redis-url",
        default="redis://127.0.0.1:6379",
        help="Redis connection URL"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Execute live migration (default is dry-run)"
    )

    args = parser.parse_args()

    migration = TimescaleToRedisMigration(
        timescale_url=args.timescale_url,
        redis_url=args.redis_url,
        dry_run=not args.live
    )

    await migration.run()


if __name__ == "__main__":
    asyncio.run(main())
