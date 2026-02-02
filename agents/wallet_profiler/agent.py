#!/usr/bin/env python3
"""
Wallet Profiler Agent - Insider Hunter Orchestrator

This module orchestrates the complete wallet profiling pipeline for
identifying "Smart Money" and "Insider" wallets on pump.fun.

Pipeline:
1. Check ProfileCache for cached profiles (1-hour TTL)
2. If cache miss, trigger parallel analysis:
   - HistoricalAnalyzer: Pump.fun trading history analysis
   - BehaviorTracker: Real-time behavior tracking
3. Aggregate risk using pump.fun specific metrics
4. PREDICT NEXT ACTION (NEW: Behavioral DNA)
5. Save to cache and TimescaleDB

Key Metrics:
- Win Rate (>70%): Percentage of profitable trades
- Graduation Rate (>60%): Percentage of picks that migrate to Pumpswap
- Curve Entry (<5%): How early they enter the bonding curve
- Consistency (>10 trades): Sample size validation
- Profit Total: Total SOL profit

Author: GODMODESCANNER Team
Date: 2026-01-25
Updated: 2026-01-27 - Added Behavioral DNA prediction
"""

import asyncio
import structlog
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
import redis.asyncio as redis
from psycopg_pool import AsyncConnectionPool

# Import components
from agents.historical_analyzer import HistoricalAnalyzer, HistoricalMetrics
from agents.wallet_profiler.trackers.behavior_tracker import BehaviorTracker
from agents.risk_aggregator import RiskAggregator, RiskScore
from agents.wallet_profiler.profilers.profile_cache import ProfileCache
from agents.behavioral_dna.behavioral_dna_predictor import BehavioralDNAPredictor

logger = structlog.get_logger(__name__)


@dataclass
class WalletProfile:
    """
    Complete wallet profile with all analysis results.

    Attributes:
        wallet: Wallet address
        win_rate: Percentage of profitable trades (0.0 - 1.0)
        graduation_rate: Percentage of picks that hit Pumpswap (0.0 - 1.0)
        curve_entry: Average position on bonding curve at entry (0.0 - 1.0)
        total_trades: Total number of trades (consistency metric)
        total_profit: Total SOL profit
        avg_hold_time: Average hold time in seconds
        risk_score: Final risk score from RiskAggregator
        severity: Risk severity level
        is_king_maker: Whether wallet qualifies as "King Maker"
        confidence_interval: Tuple of (lower, upper) confidence bounds
        historical_metrics: Full HistoricalMetrics object
        behavior_metrics: Behavior tracking metrics
        next_action_prediction: NEW - Predicted next action from Behavioral DNA
        timestamp: Profile generation timestamp
        cache_hit: Whether profile was retrieved from cache
    """
    wallet: str
    win_rate: float
    graduation_rate: float
    curve_entry: float
    total_trades: int
    total_profit: float
    avg_hold_time: float
    risk_score: float
    severity: str
    is_king_maker: bool
    confidence_interval: tuple[float, float]
    historical_metrics: Optional[Dict[str, Any]] = None
    behavior_metrics: Optional[Dict[str, Any]] = None
    next_action_prediction: Optional[Dict[str, Any]] = None  # NEW: Behavioral DNA
    timestamp: Optional[datetime] = None
    cache_hit: bool = False


class WalletProfilerAgent:
    """
    Orchestrator for wallet profiling pipeline.

    This agent coordinates multiple analysis components to build
    comprehensive wallet profiles for insider detection.

    Components:
    - ProfileCache: Redis-backed cache (1-hour TTL)
    - HistoricalAnalyzer: Pump.fun trading history analysis
    - BehaviorTracker: Real-time behavior tracking
    - RiskAggregator: Bayesian risk scoring
    - BehavioralDNAPredictor: ML-based behavior prediction (NEW)
    - TimescaleDB: Persistent storage
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        db_pool: AsyncConnectionPool,
        cache_ttl: int = 3600,
        behavioral_dna_enabled: bool = True,
        behavioral_dna_threshold: float = 0.7
    ):
        """
        Initialize the wallet profiler agent.

        Args:
            redis_client: Async Redis client for caching
            db_pool: Async PostgreSQL connection pool
            cache_ttl: Cache TTL in seconds (default: 3600 = 1 hour)
            behavioral_dna_enabled: Enable Behavioral DNA predictions
            behavioral_dna_threshold: Min risk score to trigger prediction (default: 0.7)
        """
        self.redis = redis_client
        self.db_pool = db_pool
        self.behavioral_dna_enabled = behavioral_dna_enabled
        self.behavioral_dna_threshold = behavioral_dna_threshold
        self.logger = logger.bind(component="WalletProfilerAgent")

        # Initialize components
        self.cache = ProfileCache(redis_client, ttl=cache_ttl)
        self.historical_analyzer = HistoricalAnalyzer(db_pool, redis_client)
        self.behavior_tracker = BehaviorTracker()
        self.risk_aggregator = RiskAggregator()
        
        # NEW: Initialize Behavioral DNA predictor
        self.behavioral_dna_predictor = None
        if behavioral_dna_enabled:
            self.behavioral_dna_predictor = BehavioralDNAPredictor()
            if self.behavioral_dna_predictor.is_available():
                self.logger.info(
                    "behavioral_dna_predictor_initialized",
                    model_path=self.behavioral_dna_predictor.model_path
                )
            else:
                self.logger.warning(
                    "behavioral_dna_predictor_unavailable",
                    reason="Model not loaded or ONNX Runtime not installed"
                )

        self.logger.info(
            "wallet_profiler_initialized",
            cache_ttl=cache_ttl,
            behavioral_dna_enabled=behavioral_dna_enabled,
            behavioral_dna_threshold=behavioral_dna_threshold
        )

    async def profile_wallet(
        self,
        wallet: str,
        force_refresh: bool = False
    ) -> WalletProfile:
        """
        Generate comprehensive wallet profile for insider detection.

        This method implements the 5-step profiling pipeline:
        1. Check ProfileCache for cached profile
        2. If cache miss, trigger parallel analysis
        3. Map pump.fun metrics to RiskAggregator
        4. Generate Behavioral DNA prediction (NEW)
        5. Save to cache and TimescaleDB

        Args:
            wallet: Wallet address to profile
            force_refresh: Force cache bypass and fresh analysis

        Returns:
            WalletProfile object with complete analysis
        """
        self.logger.info(
            "profile_wallet_start",
            wallet=wallet,
            force_refresh=force_refresh
        )

        # STEP 1: Check ProfileCache
        if not force_refresh:
            cached_profile = await self._get_cached_profile(wallet)
            if cached_profile:
                self.logger.info(
                    "profile_cache_hit",
                    wallet=wallet
                )
                return cached_profile

        # STEP 2: Cache miss - Trigger parallel analysis
        self.logger.info(
            "profile_cache_miss",
            wallet=wallet,
            action="triggering_parallel_analysis"
        )

        try:
            # Run historical and behavior analysis in parallel
            historical_metrics, behavior_metrics = await asyncio.gather(
                self._analyze_history(wallet),
                self._analyze_behavior(wallet),
                return_exceptions=True
            )

            # Handle exceptions
            if isinstance(historical_metrics, Exception):
                self.logger.error(
                    "historical_analysis_failed",
                    wallet=wallet,
                    error=str(historical_metrics)
                )
                raise historical_metrics

            if isinstance(behavior_metrics, Exception):
                self.logger.error(
                    "behavior_analysis_failed",
                    wallet=wallet,
                    error=str(behavior_metrics)
                )
                raise behavior_metrics

            # STEP 3: Map pump.fun metrics to RiskAggregator
            risk_score = await self._calculate_risk(
                wallet=wallet,
                historical=historical_metrics,
                behavior=behavior_metrics
            )

            # STEP 4: NEW - Generate Behavioral DNA prediction
            prediction = None
            if (self.behavioral_dna_enabled and 
                self.behavioral_dna_predictor and 
                self.behavioral_dna_predictor.is_available() and
                risk_score.score >= self.behavioral_dna_threshold):
                
                self.logger.info(
                    "generating_behavioral_dna_prediction",
                    wallet=wallet,
                    risk_score=risk_score.score,
                    threshold=self.behavioral_dna_threshold
                )
                
                prediction = await self.behavioral_dna_predictor.predict_next_action(
                    wallet_address=wallet,
                    db_pool=self.db_pool
                )
                
                if prediction:
                    self.logger.info(
                        "behavioral_dna_prediction_generated",
                        wallet=wallet,
                        action=prediction['action'],
                        timing=prediction['timing'],
                        amount=prediction['amount'],
                        confidence=prediction['confidence'],
                        latency_ms=prediction.get('latency_ms', 'N/A')
                    )
                else:
                    self.logger.debug(
                        "behavioral_dna_prediction_failed_or_insufficient_data",
                        wallet=wallet
                    )
            
            # Build complete profile
            profile = self._build_profile(
                wallet=wallet,
                historical=historical_metrics,
                behavior=behavior_metrics,
                risk=risk_score,
                prediction=prediction  # NEW: Add prediction
            )

            # STEP 5: Save to cache and Postgres
            await self._save_profile(profile)

            self.logger.info(
                "profile_wallet_complete",
                wallet=wallet,
                risk_score=profile.risk_score,
                severity=profile.severity,
                is_king_maker=profile.is_king_maker,
                has_prediction=profile.next_action_prediction is not None
            )

            return profile

        except Exception as e:
            self.logger.error(
                "profile_wallet_failed",
                wallet=wallet,
                error=str(e)
            )
            raise

    async def _get_cached_profile(self, wallet: str) -> Optional[WalletProfile]:
        """
        Retrieve wallet profile from cache.

        Args:
            wallet: Wallet address

        Returns:
            WalletProfile if cached, None otherwise
        """
        try:
            cached_data = await self.cache.get(wallet)

            if not cached_data:
                return None

            # Reconstruct WalletProfile from cached data
            profile = WalletProfile(
                wallet=cached_data['wallet'],
                win_rate=float(cached_data['win_rate']),
                graduation_rate=float(cached_data['graduation_rate']),
                curve_entry=float(cached_data['curve_entry']),
                total_trades=int(cached_data['total_trades']),
                total_profit=float(cached_data['total_profit']),
                avg_hold_time=float(cached_data['avg_hold_time']),
                risk_score=float(cached_data['risk_score']),
                severity=cached_data['severity'],
                is_king_maker=cached_data['is_king_maker'] == 'True',
                confidence_interval=(
                    float(cached_data['confidence_lower']),
                    float(cached_data['confidence_upper'])
                ),
                historical_metrics=cached_data.get('historical_metrics'),
                behavior_metrics=cached_data.get('behavior_metrics'),
                next_action_prediction=cached_data.get('next_action_prediction'),  # NEW
                timestamp=cached_data.get('timestamp'),
                cache_hit=True
            )

            return profile

        except Exception as e:
            self.logger.error(
                "cache_retrieval_failed",
                wallet=wallet,
                error=str(e)
            )
            return None

    async def _analyze_history(self, wallet: str) -> HistoricalMetrics:
        """
        Analyze wallet's pump.fun trading history.

        Args:
            wallet: Wallet address

        Returns:
            HistoricalMetrics object
        """
        self.logger.debug(
            "analyzing_history",
            wallet=wallet
        )

        # Use HistoricalAnalyzer to get pump.fun specific metrics
        metrics = await self.historical_analyzer.analyze_wallet_history(wallet)

        return metrics

    async def _analyze_behavior(self, wallet: str) -> Dict[str, Any]:
        """
        Analyze wallet's real-time behavior.

        Args:
            wallet: Wallet address

        Returns:
            Behavior metrics dictionary
        """
        self.logger.debug(
            "analyzing_behavior",
            wallet=wallet
        )

        # Get behavior analysis
        # Note: BehaviorTracker.analyze() returns behavior summary
        behavior = await self.behavior_tracker.analyze(wallet)

        return behavior

    async def _calculate_risk(
        self,
        wallet: str,
        historical: HistoricalMetrics,
        behavior: Dict[str, Any]
    ) -> RiskScore:
        """
        Calculate risk score using pump.fun specific metrics.

        This method maps the analysis results to the RiskAggregator's
        expected pump.fun metrics.

        Args:
            wallet: Wallet address
            historical: Historical analysis results
            behavior: Behavior analysis results

        Returns:
            RiskScore object
        """
        self.logger.debug(
            "calculating_risk",
            wallet=wallet
        )

        # Map pump.fun metrics to RiskAggregator
        risk_score = self.risk_aggregator.aggregate_risk(
            win_rate=historical.win_rate,
            graduation_rate=historical.graduation_rate,  # NEW: Pump.fun specific
            curve_entry=behavior.get('avg_curve_position', 0.5),  # NEW: Early entry metric
            consistency=historical.total_trades,
            profit_total=historical.total_pnl_sol,
            avg_hold_time=historical.avg_hold_time_seconds,
            wallet_address=wallet
        )

        return risk_score

    def _build_profile(
        self,
        wallet: str,
        historical: HistoricalMetrics,
        behavior: Dict[str, Any],
        risk: RiskScore,
        prediction: Optional[Dict[str, Any]] = None  # NEW
    ) -> WalletProfile:
        """
        Build complete WalletProfile from analysis results.

        Args:
            wallet: Wallet address
            historical: Historical metrics
            behavior: Behavior metrics
            risk: Risk score
            prediction: Behavioral DNA prediction (NEW)

        Returns:
            WalletProfile object
        """
        profile = WalletProfile(
            wallet=wallet,
            win_rate=historical.win_rate,
            graduation_rate=historical.graduation_rate,
            curve_entry=behavior.get('avg_curve_position', 0.5),
            total_trades=historical.total_trades,
            total_profit=historical.total_pnl_sol,
            avg_hold_time=historical.avg_hold_time_seconds,
            risk_score=risk.score,
            severity=risk.severity,
            is_king_maker=risk.is_king_maker,
            confidence_interval=(risk.confidence_lower, risk.confidence_upper),
            historical_metrics=asdict(historical),
            behavior_metrics=behavior,
            next_action_prediction=prediction,  # NEW
            timestamp=datetime.now(timezone.utc),
            cache_hit=False
        )

        return profile

    async def _save_profile(self, profile: WalletProfile) -> None:
        """
        Save profile to cache and TimescaleDB.

        Args:
            profile: WalletProfile to save
        """
        self.logger.debug(
            "saving_profile",
            wallet=profile.wallet
        )

        # Prepare cache data
        cache_data = {
            'wallet': profile.wallet,
            'win_rate': profile.win_rate,
            'graduation_rate': profile.graduation_rate,
            'curve_entry': profile.curve_entry,
            'total_trades': profile.total_trades,
            'total_profit': profile.total_profit,
            'avg_hold_time': profile.avg_hold_time,
            'risk_score': profile.risk_score,
            'severity': profile.severity,
            'is_king_maker': profile.is_king_maker,
            'confidence_lower': profile.confidence_interval[0],
            'confidence_upper': profile.confidence_interval[1],
            'historical_metrics': profile.historical_metrics,
            'behavior_metrics': profile.behavior_metrics,
            'next_action_prediction': profile.next_action_prediction,  # NEW
            'timestamp': profile.timestamp
        }

        # Save to cache and database in parallel
        await asyncio.gather(
            self._save_to_cache(profile.wallet, cache_data),
            self._save_to_database(profile),
            return_exceptions=True
        )

    async def _save_to_cache(
        self,
        wallet: str,
        cache_data: Dict[str, Any]
    ) -> None:
        """
        Save profile to Redis cache.

        Args:
            wallet: Wallet address
            cache_data: Profile data to cache
        """
        try:
            await self.cache.set(wallet, cache_data)

            self.logger.debug(
                "profile_cached",
                wallet=wallet
            )

        except Exception as e:
            self.logger.error(
                "cache_save_failed",
                wallet=wallet,
                error=str(e)
            )

    async def _save_to_database(self, profile: WalletProfile) -> None:
        """
        Save profile to TimescaleDB.

        Args:
            profile: WalletProfile to save
        """
        try:
            async with self.db_pool.connection() as conn:
                async with conn.cursor() as cur:
                    # Insert or update wallet profile
                    # Note: JSONB column for next_action_prediction
                    query = """
                    INSERT INTO wallet_profiles (
                        wallet_address,
                        win_rate,
                        graduation_rate,
                        curve_entry,
                        total_trades,
                        total_profit,
                        avg_hold_time,
                        risk_score,
                        severity,
                        is_king_maker,
                        confidence_lower,
                        confidence_upper,
                        next_action_prediction,
                        timestamp
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (wallet_address)
                    DO UPDATE SET
                        win_rate = EXCLUDED.win_rate,
                        graduation_rate = EXCLUDED.graduation_rate,
                        curve_entry = EXCLUDED.curve_entry,
                        total_trades = EXCLUDED.total_trades,
                        total_profit = EXCLUDED.total_profit,
                        avg_hold_time = EXCLUDED.avg_hold_time,
                        risk_score = EXCLUDED.risk_score,
                        severity = EXCLUDED.severity,
                        is_king_maker = EXCLUDED.is_king_maker,
                        confidence_lower = EXCLUDED.confidence_lower,
                        confidence_upper = EXCLUDED.confidence_upper,
                        next_action_prediction = EXCLUDED.next_action_prediction,
                        timestamp = EXCLUDED.timestamp
                    """

                    await cur.execute(
                        query,
                        (
                            profile.wallet,
                            profile.win_rate,
                            profile.graduation_rate,
                            profile.curve_entry,
                            profile.total_trades,
                            profile.total_profit,
                            profile.avg_hold_time,
                            profile.risk_score,
                            profile.severity,
                            profile.is_king_maker,
                            profile.confidence_interval[0],
                            profile.confidence_interval[1],
                            profile.next_action_prediction,  # NEW: JSONB
                            profile.timestamp
                        )
                    )

                    await conn.commit()

            self.logger.debug(
                "profile_saved_to_db",
                wallet=profile.wallet
            )

        except Exception as e:
            self.logger.error(
                "database_save_failed",
                wallet=profile.wallet,
                error=str(e)
            )

    async def batch_profile(
        self,
        wallets: List[str],
        force_refresh: bool = False
    ) -> Dict[str, WalletProfile]:
        """
        Profile multiple wallets in parallel.

        Args:
            wallets: List of wallet addresses
            force_refresh: Force cache bypass for all wallets

        Returns:
            Dictionary mapping wallet addresses to profiles
        """
        self.logger.info(
            "batch_profile_start",
            wallet_count=len(wallets)
        )

        # Profile all wallets in parallel
        tasks = [
            self.profile_wallet(wallet, force_refresh=force_refresh)
            for wallet in wallets
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Build results dictionary
        profiles = {}
        success_count = 0
        error_count = 0

        for wallet, result in zip(wallets, results):
            if isinstance(result, Exception):
                self.logger.error(
                    "batch_profile_error",
                    wallet=wallet,
                    error=str(result)
                )
                error_count += 1
            else:
                profiles[wallet] = result
                success_count += 1

        self.logger.info(
            "batch_profile_complete",
            wallet_count=len(wallets),
            success_count=success_count,
            error_count=error_count
        )

        return profiles


if __name__ == "__main__":
    import os

    async def test_wallet_profiler():
        """Test wallet profiler agent with Behavioral DNA."""

        # Initialize Redis client
        redis_client = await redis.from_url(
            "redis://localhost:6379",
            encoding="utf-8",
            decode_responses=False
        )

        # Initialize database pool
        db_pool = await AsyncConnectionPool.create(
            conninfo=f"postgresql://{os.getenv('TIMESCALEDB_USER', 'godmodescanner')}:"
                    f"{os.getenv('TIMESCALEDB_PASSWORD', 'password')}@"
                    f"{os.getenv('TIMESCALEDB_HOST', 'localhost')}:"
                    f"{os.getenv('TIMESCALEDB_PORT', '5432')}/"
                    f"{os.getenv('TIMESCALEDB_DATABASE', 'godmodescanner')}",
            min_size=2,
            max_size=10
        )

        # Initialize profiler with Behavioral DNA enabled
        profiler = WalletProfilerAgent(
            redis_client=redis_client,
            db_pool=db_pool,
            cache_ttl=300,  # 5 minutes for testing
            behavioral_dna_enabled=True,
            behavioral_dna_threshold=0.7
        )

        print("\n=== Test 1: Profile Single Wallet ===")
        test_wallet = "TestInsiderWallet123"

        try:
            profile = await profiler.profile_wallet(test_wallet)
            print(f"Wallet: {profile.wallet}")
            print(f"Win Rate: {profile.win_rate:.2%}")
            print(f"Graduation Rate: {profile.graduation_rate:.2%}")
            print(f"Risk Score: {profile.risk_score:.3f}")
            print(f"Severity: {profile.severity}")
            print(f"King Maker: {profile.is_king_maker}")
            print(f"Cache Hit: {profile.cache_hit}")
            
            # NEW: Show Behavioral DNA prediction
            if profile.next_action_prediction:
                pred = profile.next_action_prediction
                print(f"\n--- Behavioral DNA Prediction ---")
                print(f"Next Action: {pred['action']}")
                print(f"Timing: {pred['timing']:.1f}s after launch")
                print(f"Amount: {pred['amount']:.2f} SOL")
                print(f"Confidence: {pred['confidence']:.1%}")
                print(f"Inference Latency: {pred.get('latency_ms', 'N/A'):.1f}ms")
            else:
                print(f"\n--- Behavioral DNA ---")
                print("No prediction (risk score below threshold or insufficient data)")
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

        print("\n=== Test 2: Batch Profile ===")
        test_wallets = ["Wallet1", "Wallet2", "Wallet3"]

        try:
            profiles = await profiler.batch_profile(test_wallets)
            print(f"Profiled {len(profiles)} wallets")
            for wallet, profile in profiles.items():
                has_pred = "YES" if profile.next_action_prediction else "NO"
                print(f"  {wallet}: {profile.severity} (score: {profile.risk_score:.3f}) | Prediction: {has_pred}")
        except Exception as e:
            print(f"Error: {e}")

        # Cleanup
        await redis_client.close()
        await db_pool.close()

    # Run tests
    asyncio.run(test_wallet_profiler())
