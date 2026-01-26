"""Historical Analyzer Agent for GODMODESCANNER.

Analyzes wallet transaction history from TimescaleDB to calculate:
- Timing scores (early buyer detection)
- Network scores (cluster connections via graph analysis)
- Volume scores (whale behavior detection)
- Performance metrics (win rate, hold time, trade statistics)
- Suspicion pattern aggregation

Optimizations:
- Parallel query execution with asyncio.gather()
- Redis caching with 300s TTL
- Production-ready SQL with CTEs
- Graceful error handling

Author: GODMODESCANNER Team
Date: 2026-01-25
Updated: 2026-01-25 - Final production optimizations
"""

import asyncio
import json
import structlog
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from psycopg_pool import AsyncConnectionPool
import statistics


logger = structlog.get_logger(__name__)


@dataclass
class HistoricalMetrics:
    """Historical analysis metrics for a wallet."""
    timing_score: float  # 0-1, how early they buy (higher = more suspicious)
    network_score: float  # 0-1, cluster connections (higher = more connected to insiders)
    volume_score: float  # 0-1, whale behavior (higher = whale-like)
    win_rate: float  # Percentage of profitable trades (0-100)
    avg_hold_time: timedelta  # Average time between buy and sell
    total_trades: int  # Total completed trades
    unique_tokens: int  # Number of unique tokens traded
    first_seen: datetime  # First transaction timestamp
    suspicion_indicators: List[str] = field(default_factory=list)  # Detected patterns

    # Additional detailed metrics
    total_volume_sol: float = 0.0  # Total trading volume in SOL
    total_buy_volume: float = 0.0  # Total buy volume in SOL
    total_sell_volume: float = 0.0  # Total sell volume in SOL
    volume_stddev: float = 0.0  # Volume standard deviation
    profitable_trades: int = 0  # Number of profitable trades
    losing_trades: int = 0  # Number of losing trades
    avg_profit_pct: float = 0.0  # Average profit percentage
    max_profit_pct: float = 0.0  # Maximum profit percentage
    max_loss_pct: float = 0.0  # Maximum loss percentage


class HistoricalAnalyzer:
    """Analyzes wallet transaction history for insider trading patterns."""

    def __init__(self, pool: AsyncConnectionPool, redis_client):
        """Initialize the Historical Analyzer.

        Args:
            pool: AsyncConnectionPool for TimescaleDB
            redis_client: Redis client for graph data and caching
        """
        self.pool = pool
        self.redis = redis_client
        self.logger = structlog.get_logger(__name__)

        # Scoring thresholds (updated per user requirements)
        self.EARLY_BUY_THRESHOLD_SECONDS = 60  # Within 60s of token launch
        self.WHALE_VOLUME_THRESHOLD_SOL = 100.0  # 100+ SOL = whale
        self.HIGH_WIN_RATE_THRESHOLD = 0.85  # 85%+ win rate suspicious (updated)
        self.CLUSTER_CONNECTION_THRESHOLD = 3  # 3+ connections to known clusters

        # Suspicion indicator thresholds (per user requirements)
        self.EARLY_BUYER_THRESHOLD = 0.8  # timing_score > 0.8
        self.CLUSTER_CONNECTED_THRESHOLD = 0.7  # network_score > 0.7
        self.WHALE_BEHAVIOR_THRESHOLD = 0.8  # volume_score > 0.8
        self.ABNORMAL_WIN_RATE_THRESHOLD = 0.85  # win_rate > 0.85

        # Caching configuration
        self.CACHE_TTL = 300  # 5 minutes
        self.MIN_SAMPLE_SIZE = 3  # Minimum trades for valid timing score

    async def analyze_wallet_history(
        self, 
        wallet: str, 
        lookback_days: int = 30,
        use_cache: bool = True
    ) -> HistoricalMetrics:
        """Main entry point for historical wallet analysis.

        Args:
            wallet: Wallet address to analyze
            lookback_days: Number of days to look back (default 30)
            use_cache: Whether to use Redis cache (default True)

        Returns:
            HistoricalMetrics with comprehensive analysis
        """
        self.logger.info(
            "analyzing_wallet_history",
            wallet=wallet,
            lookback_days=lookback_days,
            use_cache=use_cache
        )

        # Check cache first
        if use_cache:
            cached = await self._get_cached_metrics(wallet, lookback_days)
            if cached:
                self.logger.debug(
                    "cache_hit",
                    wallet=wallet,
                    lookback_days=lookback_days
                )
                return cached

        try:
            async with self.pool.connection() as conn:
                # Run all analyses in parallel with error handling
                results = await asyncio.gather(
                    self._analyze_timing(conn, wallet, lookback_days),
                    self._analyze_network(conn, wallet),
                    self._analyze_volume(conn, wallet, lookback_days),
                    self._analyze_performance(conn, wallet, lookback_days),
                    self._get_first_seen(conn, wallet),
                    self._get_unique_tokens(conn, wallet, lookback_days),
                    return_exceptions=True  # Don't fail entire analysis on single error
                )

                # Extract results with error handling
                timing_score = results[0] if not isinstance(results[0], Exception) else 0.5
                network_score = results[1] if not isinstance(results[1], Exception) else 0.5
                volume_data = results[2] if not isinstance(results[2], Exception) else {
                    'volume_score': 0.5,
                    'total_volume_sol': 0.0,
                    'total_buy_volume': 0.0,
                    'total_sell_volume': 0.0,
                    'volume_stddev': 0.0
                }
                performance_data = results[3] if not isinstance(results[3], Exception) else {
                    'win_rate': 0.0,
                    'avg_hold_time': timedelta(0),
                    'total_trades': 0,
                    'profitable_trades': 0,
                    'losing_trades': 0,
                    'avg_profit_pct': 0.0,
                    'max_profit_pct': 0.0,
                    'max_loss_pct': 0.0
                }
                first_seen = results[4] if not isinstance(results[4], Exception) else datetime.now(timezone.utc)
                unique_tokens = results[5] if not isinstance(results[5], Exception) else 0

                # Log any errors
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        self.logger.warning(
                            "analysis_component_failed",
                            wallet=wallet,
                            component=i,
                            error=str(result)
                        )

                # Detect suspicion patterns
                suspicion_indicators = self._detect_suspicion_patterns(
                    timing_score,
                    network_score,
                    volume_data['volume_score'],
                    performance_data
                )

                # Build metrics object
                metrics = HistoricalMetrics(
                    timing_score=timing_score,
                    network_score=network_score,
                    volume_score=volume_data['volume_score'],
                    win_rate=performance_data['win_rate'],
                    avg_hold_time=performance_data['avg_hold_time'],
                    total_trades=performance_data['total_trades'],
                    unique_tokens=unique_tokens,
                    first_seen=first_seen,
                    suspicion_indicators=suspicion_indicators,
                    total_volume_sol=volume_data['total_volume_sol'],
                    total_buy_volume=volume_data['total_buy_volume'],
                    total_sell_volume=volume_data['total_sell_volume'],
                    volume_stddev=volume_data['volume_stddev'],
                    profitable_trades=performance_data['profitable_trades'],
                    losing_trades=performance_data['losing_trades'],
                    avg_profit_pct=performance_data['avg_profit_pct'],
                    max_profit_pct=performance_data['max_profit_pct'],
                    max_loss_pct=performance_data['max_loss_pct']
                )

                # Cache the results
                if use_cache:
                    await self._cache_metrics(wallet, lookback_days, metrics)

                self.logger.info(
                    "wallet_history_analyzed",
                    wallet=wallet,
                    timing_score=timing_score,
                    network_score=network_score,
                    volume_score=volume_data['volume_score'],
                    win_rate=performance_data['win_rate'],
                    suspicion_count=len(suspicion_indicators)
                )

                return metrics

        except Exception as e:
            self.logger.error(
                "wallet_history_analysis_failed",
                wallet=wallet,
                error=str(e),
                exc_info=True
            )
            # Return default metrics on error
            return HistoricalMetrics(
                timing_score=0.5,  # Default to neutral score
                network_score=0.5,
                volume_score=0.5,
                win_rate=0.0,
                avg_hold_time=timedelta(0),
                total_trades=0,
                unique_tokens=0,
                first_seen=datetime.now(timezone.utc),
                suspicion_indicators=["analysis_error"]
            )

    async def _get_cached_metrics(
        self, 
        wallet: str, 
        lookback_days: int
    ) -> Optional[HistoricalMetrics]:
        """Retrieve cached metrics from Redis.

        Args:
            wallet: Wallet address
            lookback_days: Lookback period

        Returns:
            HistoricalMetrics if cached, None otherwise
        """
        try:
            cache_key = f"history:{wallet}:{lookback_days}"
            cached_data = await self.redis.get(cache_key)

            if cached_data:
                data = json.loads(cached_data)
                # Reconstruct timedelta from seconds
                data['avg_hold_time'] = timedelta(seconds=data.get('avg_hold_time_seconds', 0))
                data.pop('avg_hold_time_seconds', None)
                # Reconstruct datetime
                data['first_seen'] = datetime.fromisoformat(data['first_seen'])
                return HistoricalMetrics(**data)

            return None

        except Exception as e:
            self.logger.warning(
                "cache_retrieval_failed",
                wallet=wallet,
                error=str(e)
            )
            return None

    async def _cache_metrics(
        self, 
        wallet: str, 
        lookback_days: int, 
        metrics: HistoricalMetrics
    ) -> None:
        """Cache metrics in Redis with TTL.

        Args:
            wallet: Wallet address
            lookback_days: Lookback period
            metrics: Metrics to cache
        """
        try:
            cache_key = f"history:{wallet}:{lookback_days}"

            # Convert to dict and handle special types
            data = asdict(metrics)
            data['avg_hold_time_seconds'] = metrics.avg_hold_time.total_seconds()
            data.pop('avg_hold_time')
            data['first_seen'] = metrics.first_seen.isoformat()

            await self.redis.setex(
                cache_key,
                self.CACHE_TTL,
                json.dumps(data)
            )

            self.logger.debug(
                "metrics_cached",
                wallet=wallet,
                lookback_days=lookback_days,
                ttl=self.CACHE_TTL
            )

        except Exception as e:
            self.logger.warning(
                "cache_storage_failed",
                wallet=wallet,
                error=str(e)
            )

    async def _analyze_timing(
        self, 
        conn, 
        wallet: str, 
        lookback_days: int
    ) -> float:
        """Calculate early buyer score (0-1) using optimized SQL.

        Higher score = more suspicious (buys very early after token launch)

        Formula: max(0, min(1, 1 - (avg_seconds / 3600)))
        - 0-30 seconds = 1.0 (very suspicious)
        - >3600 seconds = 0.0 (normal)

        Args:
            conn: Database connection
            wallet: Wallet address
            lookback_days: Analysis window

        Returns:
            Timing score from 0.0 (normal) to 1.0 (highly suspicious)
        """
        try:
            # Optimized query with CTEs
            query = f"""
            WITH token_first_buys AS (
                SELECT token_address, MIN(block_time) as launch_time
                FROM transactions
                WHERE block_time > NOW() - INTERVAL '{lookback_days} days'
                GROUP BY token_address
            ),
            wallet_buys AS (
                SELECT 
                    t.token_address,
                    MIN(t.block_time) as wallet_first_buy,
                    tfb.launch_time,
                    EXTRACT(EPOCH FROM (MIN(t.block_time) - tfb.launch_time)) as seconds_after_launch
                FROM transactions t
                JOIN token_first_buys tfb ON t.token_address = tfb.token_address
                WHERE t.wallet_address = $1 AND t.transaction_type = 'buy'
                GROUP BY t.token_address, tfb.launch_time
            )
            SELECT 
                AVG(seconds_after_launch) as avg_seconds,
                PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY seconds_after_launch) as median_seconds,
                COUNT(*) as sample_size
            FROM wallet_buys WHERE seconds_after_launch >= 0
            """

            async with conn.cursor() as cur:
                await cur.execute(query, (wallet,))
                row = await cur.fetchone()

            if not row or row[0] is None:
                return 0.5  # Default neutral score

            avg_seconds = float(row[0])
            median_seconds = float(row[1]) if row[1] else avg_seconds
            sample_size = int(row[2])

            # Require minimum sample size for valid score
            if sample_size < self.MIN_SAMPLE_SIZE:
                self.logger.debug(
                    "insufficient_sample_size",
                    wallet=wallet,
                    sample_size=sample_size,
                    required=self.MIN_SAMPLE_SIZE
                )
                return 0.5  # Default neutral score

            # Score formula: 1 - (avg_seconds / 3600)
            # 0-30 seconds = ~1.0, >3600 seconds = 0.0
            timing_score = max(0.0, min(1.0, 1.0 - (avg_seconds / 3600.0)))

            self.logger.debug(
                "timing_analysis_complete",
                wallet=wallet,
                avg_seconds=avg_seconds,
                median_seconds=median_seconds,
                sample_size=sample_size,
                timing_score=timing_score
            )

            return timing_score

        except Exception as e:
            self.logger.error(
                "timing_analysis_failed",
                wallet=wallet,
                error=str(e)
            )
            return 0.5  # Default neutral score on error

    async def _analyze_network(self, conn, wallet: str) -> float:
        """3-hop BFS for cluster membership using optimized recursive SQL.

        Analyzes wallet's connections to known insider clusters via:
        - Direct connections (1-hop)
        - 2-hop connections (friends of friends)
        - 3-hop connections (extended network)

        Args:
            conn: Database connection
            wallet: Wallet address

        Returns:
            Network score from 0.0 (isolated) to 1.0 (highly connected)
        """
        try:
            # Optimized recursive CTE for 3-hop BFS
            query = """
            WITH RECURSIVE wallet_graph AS (
                SELECT DISTINCT counterparty_wallet as connected_wallet, 1 as hop_distance
                FROM transactions
                WHERE wallet_address = $1 AND counterparty_wallet IS NOT NULL
                UNION
                SELECT DISTINCT t.counterparty_wallet, wg.hop_distance + 1
                FROM wallet_graph wg
                JOIN transactions t ON t.wallet_address = wg.connected_wallet
                WHERE wg.hop_distance < 3 AND t.counterparty_wallet IS NOT NULL
            ),
            cluster_analysis AS (
                SELECT connected_wallet, MIN(hop_distance) as min_distance
                FROM wallet_graph GROUP BY connected_wallet
            )
            SELECT 
                COUNT(*) as total_connections,
                COUNT(*) FILTER (WHERE min_distance = 1) as direct,
                COUNT(*) FILTER (WHERE min_distance = 2) as hop_2,
                COUNT(*) FILTER (WHERE min_distance = 3) as hop_3,
                COUNT(*) FILTER (WHERE connected_wallet IN (
                    SELECT wallet_address FROM flagged_wallets WHERE flag_type = 'insider'
                )) as suspicious_connections
            FROM cluster_analysis
            """

            async with conn.cursor() as cur:
                await cur.execute(query, (wallet,))
                row = await cur.fetchone()

            if not row or row[0] is None or row[0] == 0:
                return 0.0

            total_connections = int(row[0])
            direct = int(row[1]) if row[1] else 0
            hop_2 = int(row[2]) if row[2] else 0
            hop_3 = int(row[3]) if row[3] else 0
            suspicious_connections = int(row[4]) if row[4] else 0

            # Calculate network score with weighted hops
            # 1-hop: 60% weight, 2-hop: 30% weight, 3-hop: 10% weight
            hop_1_score = min(1.0, direct / 5.0) * 0.6
            hop_2_score = min(1.0, hop_2 / 10.0) * 0.3
            hop_3_score = min(1.0, hop_3 / 15.0) * 0.1

            network_score = hop_1_score + hop_2_score + hop_3_score

            # Boost score if connected to suspicious wallets
            if suspicious_connections >= self.CLUSTER_CONNECTION_THRESHOLD:
                network_score = min(1.0, network_score * 1.3)

            self.logger.debug(
                "network_analysis_complete",
                wallet=wallet,
                total_connections=total_connections,
                direct=direct,
                hop_2=hop_2,
                hop_3=hop_3,
                suspicious_connections=suspicious_connections,
                network_score=network_score
            )

            return min(1.0, network_score)

        except Exception as e:
            self.logger.error(
                "network_analysis_failed",
                wallet=wallet,
                error=str(e)
            )
            return 0.5  # Default neutral score on error

    async def _analyze_volume(
        self, 
        conn, 
        wallet: str, 
        lookback_days: int
    ) -> Dict:
        """Whale behavior detection based on trading volume (OPTIMIZED).

        Args:
            conn: Database connection
            wallet: Wallet address
            lookback_days: Analysis window

        Returns:
            Dict with volume metrics and score
        """
        try:
            # Optimized volume analysis query
            query = f"""
            SELECT 
                COUNT(DISTINCT token_address) as unique_tokens,
                SUM(CASE WHEN transaction_type = 'buy' THEN sol_amount ELSE 0 END) as total_buy_volume,
                SUM(CASE WHEN transaction_type = 'sell' THEN sol_amount ELSE 0 END) as total_sell_volume,
                AVG(sol_amount) as avg_tx_size,
                MAX(sol_amount) as max_tx_size,
                STDDEV(sol_amount) as volume_stddev
            FROM transactions
            WHERE wallet_address = $1 AND block_time > NOW() - INTERVAL '{lookback_days} days'
            """

            async with conn.cursor() as cur:
                await cur.execute(query, (wallet,))
                row = await cur.fetchone()

            if not row or row[1] is None:
                return {
                    'volume_score': 0.5,
                    'total_volume_sol': 0.0,
                    'total_buy_volume': 0.0,
                    'total_sell_volume': 0.0,
                    'volume_stddev': 0.0
                }

            unique_tokens = int(row[0]) if row[0] else 0
            total_buy_volume = float(row[1]) if row[1] else 0.0
            total_sell_volume = float(row[2]) if row[2] else 0.0
            avg_tx_size = float(row[3]) if row[3] else 0.0
            max_tx_size = float(row[4]) if row[4] else 0.0
            volume_stddev = float(row[5]) if row[5] else 0.0

            total_volume = total_buy_volume + total_sell_volume

            # Calculate volume score based on:
            # 1. Total volume (50% weight)
            # 2. Average transaction size (30% weight)
            # 3. Max transaction size (20% weight)

            # Normalize total volume (0-500 SOL -> 0.0-1.0)
            volume_component = min(1.0, total_volume / 500.0) * 0.5

            # Normalize average tx size (0-50 SOL -> 0.0-1.0)
            avg_component = min(1.0, avg_tx_size / 50.0) * 0.3

            # Normalize max tx size (0-100 SOL -> 0.0-1.0)
            max_component = min(1.0, max_tx_size / 100.0) * 0.2

            volume_score = volume_component + avg_component + max_component

            self.logger.debug(
                "volume_analysis_complete",
                wallet=wallet,
                total_volume_sol=total_volume,
                total_buy_volume=total_buy_volume,
                total_sell_volume=total_sell_volume,
                unique_tokens=unique_tokens,
                avg_tx_size=avg_tx_size,
                max_tx_size=max_tx_size,
                volume_stddev=volume_stddev,
                volume_score=volume_score
            )

            return {
                'volume_score': min(1.0, volume_score),
                'total_volume_sol': total_volume,
                'total_buy_volume': total_buy_volume,
                'total_sell_volume': total_sell_volume,
                'volume_stddev': volume_stddev
            }

        except Exception as e:
            self.logger.error(
                "volume_analysis_failed",
                wallet=wallet,
                error=str(e)
            )
            return {
                'volume_score': 0.5,
                'total_volume_sol': 0.0,
                'total_buy_volume': 0.0,
                'total_sell_volume': 0.0,
                'volume_stddev': 0.0
            }

    async def _analyze_performance(
        self, 
        conn, 
        wallet: str, 
        lookback_days: int
    ) -> Dict:
        """Win rate calculation and performance metrics (OPTIMIZED).

        Args:
            conn: Database connection
            wallet: Wallet address
            lookback_days: Analysis window

        Returns:
            Dict with performance metrics
        """
        try:
            # Optimized performance analysis query
            query = f"""
            WITH token_trades AS (
                SELECT 
                    token_address,
                    SUM(CASE WHEN transaction_type = 'buy' THEN sol_amount ELSE 0 END) as spent,
                    SUM(CASE WHEN transaction_type = 'sell' THEN sol_amount ELSE 0 END) as received,
                    MIN(block_time) as first_trade,
                    MAX(block_time) as last_trade
                FROM transactions
                WHERE wallet_address = $1 AND block_time > NOW() - INTERVAL '{lookback_days} days'
                GROUP BY token_address
                HAVING SUM(CASE WHEN transaction_type = 'sell' THEN 1 ELSE 0 END) > 0
            )
            SELECT 
                COUNT(*) FILTER (WHERE received > spent) as wins,
                COUNT(*) as total,
                AVG(EXTRACT(EPOCH FROM (last_trade - first_trade))) as avg_hold_seconds,
                MIN(first_trade) as first_seen,
                AVG((received - spent) / NULLIF(spent, 0) * 100) as avg_profit_pct,
                MAX((received - spent) / NULLIF(spent, 0) * 100) as max_profit_pct,
                MIN((received - spent) / NULLIF(spent, 0) * 100) as max_loss_pct
            FROM token_trades
            """

            async with conn.cursor() as cur:
                await cur.execute(query, (wallet,))
                row = await cur.fetchone()

            if not row or row[1] is None or row[1] == 0:
                return {
                    'win_rate': 0.0,
                    'avg_hold_time': timedelta(0),
                    'total_trades': 0,
                    'profitable_trades': 0,
                    'losing_trades': 0,
                    'avg_profit_pct': 0.0,
                    'max_profit_pct': 0.0,
                    'max_loss_pct': 0.0
                }

            wins = int(row[0]) if row[0] else 0
            total_trades = int(row[1])
            avg_hold_seconds = float(row[2]) if row[2] else 0.0
            avg_profit_pct = float(row[4]) if row[4] else 0.0
            max_profit_pct = float(row[5]) if row[5] else 0.0
            max_loss_pct = float(row[6]) if row[6] else 0.0

            profitable_trades = wins
            losing_trades = total_trades - wins
            win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0.0
            avg_hold_time = timedelta(seconds=avg_hold_seconds)

            self.logger.debug(
                "performance_analysis_complete",
                wallet=wallet,
                total_trades=total_trades,
                profitable_trades=profitable_trades,
                losing_trades=losing_trades,
                win_rate=win_rate,
                avg_hold_time_hours=avg_hold_seconds / 3600,
                avg_profit_pct=avg_profit_pct,
                max_profit_pct=max_profit_pct,
                max_loss_pct=max_loss_pct
            )

            return {
                'win_rate': win_rate,
                'avg_hold_time': avg_hold_time,
                'total_trades': total_trades,
                'profitable_trades': profitable_trades,
                'losing_trades': losing_trades,
                'avg_profit_pct': avg_profit_pct,
                'max_profit_pct': max_profit_pct,
                'max_loss_pct': max_loss_pct
            }

        except Exception as e:
            self.logger.error(
                "performance_analysis_failed",
                wallet=wallet,
                error=str(e)
            )
            return {
                'win_rate': 0.0,
                'avg_hold_time': timedelta(0),
                'total_trades': 0,
                'profitable_trades': 0,
                'losing_trades': 0,
                'avg_profit_pct': 0.0,
                'max_profit_pct': 0.0,
                'max_loss_pct': 0.0
            }

    async def _get_first_seen(self, conn, wallet: str) -> datetime:
        """Get first transaction timestamp for wallet."""
        try:
            query = """
            SELECT MIN(timestamp) as first_seen
            FROM transactions
            WHERE wallet_address = $1
            """

            async with conn.cursor() as cur:
                await cur.execute(query, (wallet,))
                row = await cur.fetchone()

            if row and row[0]:
                return row[0]
            else:
                return datetime.now(timezone.utc)

        except Exception as e:
            self.logger.error(
                "first_seen_query_failed",
                wallet=wallet,
                error=str(e)
            )
            return datetime.now(timezone.utc)

    async def _get_unique_tokens(
        self, 
        conn, 
        wallet: str, 
        lookback_days: int
    ) -> int:
        """Count unique tokens traded by wallet."""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(days=lookback_days)

            query = """
            SELECT COUNT(DISTINCT token_address) as unique_tokens
            FROM transactions
            WHERE wallet_address = $1
              AND timestamp >= $2
            """

            async with conn.cursor() as cur:
                await cur.execute(query, (wallet, cutoff_time))
                row = await cur.fetchone()

            return int(row[0]) if row and row[0] else 0

        except Exception as e:
            self.logger.error(
                "unique_tokens_query_failed",
                wallet=wallet,
                error=str(e)
            )
            return 0

    def _detect_suspicion_patterns(
        self,
        timing: float,
        network: float,
        volume: float,
        performance: Dict
    ) -> List[str]:
        """Pattern aggregation - detect suspicion indicators (UPDATED THRESHOLDS).

        Updated thresholds per user requirements:
        - EARLY_BUYER: timing_score > 0.8
        - CLUSTER_CONNECTED: network_score > 0.7
        - WHALE_BEHAVIOR: volume_score > 0.8
        - ABNORMAL_WIN_RATE: win_rate > 0.85

        Args:
            timing: Timing score (0-1)
            network: Network score (0-1)
            volume: Volume score (0-1)
            performance: Performance metrics dict

        Returns:
            List of detected suspicion patterns
        """
        indicators = []
        win_rate = performance.get('win_rate', 0.0) / 100.0  # Convert to 0-1 range

        # Primary indicators (per user requirements)
        if timing > self.EARLY_BUYER_THRESHOLD:
            indicators.append("EARLY_BUYER")

        if network > self.CLUSTER_CONNECTED_THRESHOLD:
            indicators.append("CLUSTER_CONNECTED")

        if volume > self.WHALE_BEHAVIOR_THRESHOLD:
            indicators.append("WHALE_BEHAVIOR")

        if win_rate > self.ABNORMAL_WIN_RATE_THRESHOLD:
            indicators.append("ABNORMAL_WIN_RATE")

        # Additional granular patterns
        if timing >= 0.9:
            indicators.append("sniper_bot_suspected")

        if network >= 0.8:
            indicators.append("sybil_network_suspected")

        if volume >= 0.9:
            indicators.append("institutional_trader")

        # Hold time patterns
        avg_hold_time = performance.get('avg_hold_time', timedelta(0))
        if avg_hold_time.total_seconds() < 300:  # < 5 minutes
            indicators.append("flash_trading_pattern")
        if avg_hold_time.total_seconds() < 60:  # < 1 minute
            indicators.append("bot_trading_suspected")

        # Combined high-risk patterns
        if timing >= 0.7 and network >= 0.6:
            indicators.append("coordinated_insider_group")
        if timing >= 0.8 and volume >= 0.7:
            indicators.append("whale_sniper")
        if network >= 0.7 and win_rate >= 0.75:
            indicators.append("organized_trading_ring")

        self.logger.debug(
            "suspicion_patterns_detected",
            timing_score=timing,
            network_score=network,
            volume_score=volume,
            win_rate=win_rate,
            pattern_count=len(indicators),
            patterns=indicators
        )

        return indicators
