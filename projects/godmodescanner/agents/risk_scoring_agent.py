#!/usr/bin/env python3
"""
RISK_SCORING AGENT - GODMODESCANNER Multi-Agent System

Role: Unified risk score aggregation and normalization
Priority: MEDIUM
Position: Agent 5/6

Aggregates risk signals from 4 upstream agents:
- WALLET_ANALYZER: insider scores, reputation
- PATTERN_RECOGNITION: coordinated trades, wash trades, bundlers
- SYBIL_DETECTION: sybil clusters, probability scores
- TRANSACTION_MONITOR: token launches

Produces:
- Token risk scores (0-100) with confidence intervals
- Wallet risk scores (0-100) with confidence intervals
- Risk level classifications (LOW/MEDIUM/HIGH/CRITICAL)
- CRITICAL risk alerts for immediate action
"""

import asyncio
import json
import time
import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import numpy as np
import scipy.stats as stats

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("⚠️  Redis not available - using in-memory fallback")

# psycopg v3 - async PostgreSQL driver
try:
    import psycopg
    from psycopg_pool import AsyncConnectionPool
    PSYCOPG_AVAILABLE = True
except ImportError:
    PSYCOPG_AVAILABLE = False
    print("⚠️  psycopg v3 not available - database persistence disabled")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - RISK_SCORING - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================
# DATA MODELS
# ============================================================

@dataclass
class FactorScores:
    """Individual risk factor scores (0.0-1.0 normalized)"""
    early_buyer: float = 0.0
    coordinated_trading: float = 0.0
    sybil_cluster: float = 0.0
    bundler: float = 0.0
    wash_trading: float = 0.0
    insider: float = 0.0
    sybil_probability: float = 0.0
    pattern_involvement: float = 0.0
    reputation: float = 1.0  # Higher is better (inverted for risk)


@dataclass
class ConfidenceInterval:
    """Bayesian 95% confidence interval"""
    lower_bound: float
    upper_bound: float
    confidence_width: float
    confidence_level: float = 0.95


@dataclass
class HistoricalTrend:
    """Historical risk score trend"""
    previous_score: Optional[float] = None
    change_percentage: Optional[float] = None
    trend: str = "insufficient_data"  # increasing/decreasing/stable


@dataclass
class RiskScore:
    """Complete risk score structure"""
    token_address: Optional[str] = None
    wallet_address: Optional[str] = None
    risk_score: float = 0.0
    risk_level: str = "LOW"
    confidence_interval: Optional[ConfidenceInterval] = None
    factor_scores: Optional[FactorScores] = None
    evidence_sources: List[str] = None
    evidence_count: int = 0
    timestamp: str = ""
    last_updated: str = ""
    historical_trend: Optional[HistoricalTrend] = None

    def __post_init__(self):
        if self.evidence_sources is None:
            self.evidence_sources = []
        if self.timestamp == "":
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.last_updated == "":
            self.last_updated = self.timestamp


# ============================================================
# BAYESIAN CONFIDENCE CALCULATOR
# ============================================================

class BayesianConfidence:
    """Calculate Bayesian confidence intervals using Beta distribution"""

    @staticmethod
    def calculate_interval(
        risk_score: float,
        evidence_count: int,
        confidence_level: float = 0.95
    ) -> ConfidenceInterval:
        """
        Calculate Bayesian confidence interval.

        Args:
            risk_score: Calculated risk score (0-100)
            evidence_count: Number of independent evidence sources
            confidence_level: Confidence level (default 0.95 for 95% CI)

        Returns:
            ConfidenceInterval with lower/upper bounds
        """
        if evidence_count == 0:
            # No evidence - maximum uncertainty
            return ConfidenceInterval(
                lower_bound=0.0,
                upper_bound=100.0,
                confidence_width=100.0,
                confidence_level=confidence_level
            )

        # Convert to probability (0-1)
        p = risk_score / 100.0

        # Beta distribution parameters (Bayesian posterior)
        # Using uniform prior (alpha=1, beta=1)
        alpha = evidence_count * p + 1
        beta = evidence_count * (1 - p) + 1

        # Calculate confidence interval
        alpha_level = (1 - confidence_level) / 2
        lower_bound = stats.beta.ppf(alpha_level, alpha, beta) * 100
        upper_bound = stats.beta.ppf(1 - alpha_level, alpha, beta) * 100
        confidence_width = upper_bound - lower_bound

        return ConfidenceInterval(
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            confidence_width=confidence_width,
            confidence_level=confidence_level
        )


# ============================================================
# RISK CALCULATOR
# ============================================================

class RiskCalculator:
    """Calculate risk scores using weighted algorithms"""

    # Token risk weights (total = 1.0)
    TOKEN_WEIGHTS = {
        'early_buyer': 0.30,
        'coordinated_trading': 0.25,
        'sybil_cluster': 0.20,
        'bundler': 0.15,
        'wash_trading': 0.10
    }

    # Wallet risk weights (total = 1.0)
    WALLET_WEIGHTS = {
        'insider': 0.35,
        'sybil_probability': 0.30,
        'pattern_involvement': 0.20,
        'reputation': 0.15  # Inverted (high reputation = low risk)
    }

    # Risk thresholds
    TOKEN_THRESHOLDS = {
        'CRITICAL': 80,
        'HIGH': 60,
        'MEDIUM': 40
    }

    WALLET_THRESHOLDS = {
        'CRITICAL': 75,
        'HIGH': 55,
        'MEDIUM': 35
    }

    @classmethod
    def calculate_token_risk(cls, factors: FactorScores) -> float:
        """
        Calculate token risk score using weighted algorithm.

        Returns:
            Risk score (0-100)
        """
        risk_score = (
            factors.early_buyer * cls.TOKEN_WEIGHTS['early_buyer'] +
            factors.coordinated_trading * cls.TOKEN_WEIGHTS['coordinated_trading'] +
            factors.sybil_cluster * cls.TOKEN_WEIGHTS['sybil_cluster'] +
            factors.bundler * cls.TOKEN_WEIGHTS['bundler'] +
            factors.wash_trading * cls.TOKEN_WEIGHTS['wash_trading']
        ) * 100

        return min(100.0, max(0.0, risk_score))

    @classmethod
    def calculate_wallet_risk(cls, factors: FactorScores) -> float:
        """
        Calculate wallet risk score using weighted algorithm.

        Returns:
            Risk score (0-100)
        """
        # Invert reputation (high reputation = low risk)
        reputation_risk = 1.0 - factors.reputation

        risk_score = (
            factors.insider * cls.WALLET_WEIGHTS['insider'] +
            factors.sybil_probability * cls.WALLET_WEIGHTS['sybil_probability'] +
            factors.pattern_involvement * cls.WALLET_WEIGHTS['pattern_involvement'] +
            reputation_risk * cls.WALLET_WEIGHTS['reputation']
        ) * 100

        return min(100.0, max(0.0, risk_score))

    @classmethod
    def classify_token_risk(cls, risk_score: float) -> str:
        """Classify token risk level"""
        if risk_score >= cls.TOKEN_THRESHOLDS['CRITICAL']:
            return "CRITICAL"
        elif risk_score >= cls.TOKEN_THRESHOLDS['HIGH']:
            return "HIGH"
        elif risk_score >= cls.TOKEN_THRESHOLDS['MEDIUM']:
            return "MEDIUM"
        else:
            return "LOW"

    @classmethod
    def classify_wallet_risk(cls, risk_score: float) -> str:
        """Classify wallet risk level"""
        if risk_score >= cls.WALLET_THRESHOLDS['CRITICAL']:
            return "CRITICAL"
        elif risk_score >= cls.WALLET_THRESHOLDS['HIGH']:
            return "HIGH"
        elif risk_score >= cls.WALLET_THRESHOLDS['MEDIUM']:
            return "MEDIUM"
        else:
            return "LOW"


# ============================================================
# TREND ANALYZER
# ============================================================

class TrendAnalyzer:
    """Analyze historical risk score trends"""

    @staticmethod
    def analyze_trend(
        current_score: float,
        previous_scores: List[float]
    ) -> HistoricalTrend:
        """
        Analyze risk score trend over time.

        Args:
            current_score: Current risk score
            previous_scores: List of historical scores (chronological)

        Returns:
            HistoricalTrend with trend classification
        """
        if len(previous_scores) < 1:
            return HistoricalTrend()

        previous_score = previous_scores[-1]
        change_percentage = ((current_score - previous_score) / max(previous_score, 1.0)) * 100

        if len(previous_scores) < 2:
            # Not enough data for regression
            if change_percentage > 5:
                trend = "increasing"
            elif change_percentage < -5:
                trend = "decreasing"
            else:
                trend = "stable"
        else:
            # Linear regression for trend
            x = np.arange(len(previous_scores))
            y = np.array(previous_scores)
            slope, _ = np.polyfit(x, y, 1)

            if slope > 5:  # Increasing >5 points/hour
                trend = "increasing"
            elif slope < -5:  # Decreasing >5 points/hour
                trend = "decreasing"
            else:
                trend = "stable"

        return HistoricalTrend(
            previous_score=previous_score,
            change_percentage=change_percentage,
            trend=trend
        )


# ============================================================
# CACHE MANAGER
# ============================================================

class CacheManager:
    """Manage in-memory risk score cache with LRU eviction"""

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.token_scores: Dict[str, RiskScore] = {}
        self.wallet_scores: Dict[str, RiskScore] = {}
        self.token_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=24))  # 24 hours
        self.wallet_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=24))
        self.access_order = deque(maxlen=max_size)

    def _evict_if_needed(self):
        """LRU eviction if cache is full"""
        while len(self.token_scores) + len(self.wallet_scores) > self.max_size:
            if not self.access_order:
                break
            oldest_key = self.access_order.popleft()

            # Remove from appropriate cache
            if oldest_key.startswith('token:'):
                token_addr = oldest_key.replace('token:', '')
                self.token_scores.pop(token_addr, None)
                self.token_history.pop(token_addr, None)
            elif oldest_key.startswith('wallet:'):
                wallet_addr = oldest_key.replace('wallet:', '')
                self.wallet_scores.pop(wallet_addr, None)
                self.wallet_history.pop(wallet_addr, None)

    def set_token_score(self, token_address: str, score: RiskScore):
        """Store token risk score"""
        self._evict_if_needed()
        self.token_scores[token_address] = score
        self.token_history[token_address].append(score.risk_score)

        cache_key = f'token:{token_address}'
        if cache_key in self.access_order:
            self.access_order.remove(cache_key)
        self.access_order.append(cache_key)

    def set_wallet_score(self, wallet_address: str, score: RiskScore):
        """Store wallet risk score"""
        self._evict_if_needed()
        self.wallet_scores[wallet_address] = score
        self.wallet_history[wallet_address].append(score.risk_score)

        cache_key = f'wallet:{wallet_address}'
        if cache_key in self.access_order:
            self.access_order.remove(cache_key)
        self.access_order.append(cache_key)

    def get_token_score(self, token_address: str) -> Optional[RiskScore]:
        """Retrieve token risk score"""
        return self.token_scores.get(token_address)

    def get_wallet_score(self, wallet_address: str) -> Optional[RiskScore]:
        """Retrieve wallet risk score"""
        return self.wallet_scores.get(wallet_address)

    def get_token_history(self, token_address: str) -> List[float]:
        """Get historical token scores"""
        return list(self.token_history.get(token_address, []))

    def get_wallet_history(self, wallet_address: str) -> List[float]:
        """Get historical wallet scores"""
        return list(self.wallet_history.get(wallet_address, []))

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            'token_scores': len(self.token_scores),
            'wallet_scores': len(self.wallet_scores),
            'total_cached': len(self.token_scores) + len(self.wallet_scores),
            'max_size': self.max_size,
            'utilization': (len(self.token_scores) + len(self.wallet_scores)) / self.max_size
        }


# ============================================================
# RISK SCORING AGENT
# ============================================================

class RiskScoringAgent:
    """Main risk scoring and aggregation engine"""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client = None
        self.pubsub = None
        self.running = False

        # psycopg v3 connection pool - load from environment variables
        self.db_pool = None
        self._load_db_credentials()

        # Components
        self.cache = CacheManager(max_size=10000)
        self.calculator = RiskCalculator()
        self.bayesian = BayesianConfidence()
        self.trend_analyzer = TrendAnalyzer()

        # Statistics
        self.stats = {
            'tokens_scored': 0,
            'wallets_scored': 0,
            'critical_alerts': 0,
            'high_risk_count': 0,
            'total_updates': 0,
            'db_inserts': 0,
            'db_errors': 0,
            'start_time': time.time(),
            'redis_connected': False,
            'db_connected': False
        }

        # Input channels (subscribe to 8 channels)
        self.input_channels = [
            'godmode:wallet_profiles',
            'godmode:suspicious_wallets',
            'godmode:coordinated_trades',
            'godmode:wash_trades',
            'godmode:bundler_alerts',
            'godmode:sybil_clusters',
            'godmode:sybil_scores',
            'godmode:token_launches',
            'godmode:control'
        ]

        # Output channels
        self.output_channels = {
            'token_scores': 'godmode:token_risk_scores',
            'wallet_scores': 'godmode:wallet_risk_scores',
            'high_risk': 'godmode:high_risk_alerts',
            'heartbeat': 'godmode:heartbeat:risk_scoring'
        }

        logger.info("RISK_SCORING agent initialized")

    def _load_db_credentials(self):
        """Load TimescaleDB credentials from environment variables"""
        self.db_config = {
            'host': os.getenv('TIMESCALEDB_HOST', 'localhost'),
            'port': int(os.getenv('TIMESCALEDB_PORT', '5432')),
            'user': os.getenv('TIMESCALEDB_USER', 'godmodescanner'),
            'password': os.getenv('TIMESCALEDB_PASSWORD', 'password'),
            'database': os.getenv('TIMESCALEDB_DATABASE', 'godmodescanner')
        }
        logger.info(f"Database credentials loaded from environment variables")
        logger.info(f"  Host: {self.db_config['host']}")
        logger.info(f"  Port: {self.db_config['port']}")
        logger.info(f"  Database: {self.db_config['database']}")

    def _get_db_connection_string(self) -> str:
        """Build database connection string from config"""
        return (
            f"host={self.db_config['host']} "
            f"port={self.db_config['port']} "
            f"dbname={self.db_config['database']} "
            f"user={self.db_config['user']} "
            f"password={self.db_config['password']}"
        )

    async def connect_db(self):
        """Connect to TimescaleDB using psycopg v3 AsyncConnectionPool"""
        if not PSYCOPG_AVAILABLE:
            logger.warning("psycopg v3 not available - database persistence disabled")
            self.stats['db_connected'] = False
            return

        try:
            # Initialize async connection pool
            # Based on psycopg v3 documentation: https://www.psycopg.org/psycopg3/docs/advanced/pool.html
            self.db_pool = AsyncConnectionPool(
                self._get_db_connection_string(),
                min_size=2,
                max_size=10,
                timeout=30,
                max_lifetime=1800,  # 30 minutes
                open=False  # Defer opening until first use
            )
            await self.db_pool.open()
            
            # Test connection
            async with self.db_pool.connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT 1")
                    result = await cur.fetchone()
                    if result and result[0] == 1:
                        self.stats['db_connected'] = True
                        logger.info(f"✓ Connected to TimescaleDB: {self.db_config['host']}:{self.db_config['port']}")
                    else:
                        raise Exception("Database connection test failed")
                        
        except Exception as e:
            logger.warning(f"TimescaleDB connection failed: {e} - persistence disabled")
            self.stats['db_connected'] = False
            if self.db_pool:
                await self.db_pool.close()
                self.db_pool = None

    async def save_risk_score_to_db(self, score: RiskScore):
        """
        Persist risk score to TimescaleDB using psycopg v3.
        
        Uses async context managers for safe connection handling:
        https://www.psycopg.org/psycopg3/docs/basic/install.html
        """
        if not self.db_pool or not self.stats['db_connected']:
            logger.debug(f"[DB DISABLED] Would persist score for {score.token_address or score.wallet_address}")
            return

        try:
            async with self.db_pool.connection() as conn:
                async with conn.cursor() as cur:
                    # Upsert risk score into TimescaleDB hypertable
                    await cur.execute("""
                        INSERT INTO risk_scores (
                            time, token_address, wallet_address, risk_score, risk_level,
                            confidence_lower, confidence_upper, evidence_count, factor_scores
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        ON CONFLICT (time, token_address, wallet_address) DO UPDATE SET
                            risk_score = EXCLUDED.risk_score,
                            risk_level = EXCLUDED.risk_level,
                            confidence_lower = EXCLUDED.confidence_lower,
                            confidence_upper = EXCLUDED.confidence_upper,
                            evidence_count = EXCLUDED.evidence_count,
                            factor_scores = EXCLUDED.factor_scores
                    """, (
                        datetime.fromisoformat(score.timestamp.replace('Z', '+00:00')),
                        score.token_address,
                        score.wallet_address,
                        score.risk_score,
                        score.risk_level,
                        score.confidence_interval.lower_bound if score.confidence_interval else None,
                        score.confidence_interval.upper_bound if score.confidence_interval else None,
                        score.evidence_count,
                        json.dumps(asdict(score.factor_scores)) if score.factor_scores else None
                    ))
                    self.stats['db_inserts'] += 1
                    
        except Exception as e:
            self.stats['db_errors'] += 1
            logger.error(f"Failed to persist risk score: {e}")

    async def connect_redis(self):
        """Connect to Redis with fallback to in-memory"""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available - using in-memory mode")
            self.stats['redis_connected'] = False
            return

        try:
            self.redis_client = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis_client.ping()
            self.pubsub = self.redis_client.pubsub()
            await self.pubsub.subscribe(*self.input_channels)
            self.stats['redis_connected'] = True
            logger.info(f"✓ Connected to Redis: {self.redis_url}")
            logger.info(f"✓ Subscribed to {len(self.input_channels)} channels")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e} - using in-memory mode")
            self.stats['redis_connected'] = False

    async def publish_message(self, channel: str, message: Dict):
        """Publish message to Redis or log if unavailable"""
        try:
            if self.redis_client and self.stats['redis_connected']:
                await self.redis_client.publish(channel, json.dumps(message))
            else:
                logger.debug(f"[IN-MEMORY] Would publish to {channel}: {message.get('risk_level', 'N/A')}")
        except Exception as e:
            logger.error(f"Failed to publish to {channel}: {e}")

    def calculate_factor_scores_from_events(self, events: List[Dict]) -> Tuple[FactorScores, List[str]]:
        """
        Extract and calculate factor scores from aggregated events.

        Returns:
            (FactorScores, evidence_sources)
        """
        factors = FactorScores()
        evidence_sources = set()

        for event in events:
            event_type = event.get('type', '')

            # WALLET_ANALYZER events
            if event_type == 'wallet_profile':
                evidence_sources.add('WALLET_ANALYZER')
                # Extract insider score
                profile = event.get('profile', {})
                insider_confidence = profile.get('insider_confidence', 0.0)
                factors.insider = max(factors.insider, insider_confidence)

                # Extract reputation (higher is better)
                reputation = profile.get('reputation_score', 0.5)
                factors.reputation = reputation

                # Extract early buyer score
                ultra_early = profile.get('ultra_early_buys', 0)
                early_buys = profile.get('early_buys', 0)
                total_trades = profile.get('total_trades', 1)

                if ultra_early > 0:
                    factors.early_buyer = 0.99
                elif early_buys / total_trades >= 0.7:
                    factors.early_buyer = 0.85
                elif early_buys / total_trades >= 0.5:
                    factors.early_buyer = 0.65
                else:
                    factors.early_buyer = early_buys / total_trades

            elif event_type == 'suspicious_wallet':
                evidence_sources.add('WALLET_ANALYZER')
                # Already captured in wallet_profile

            # PATTERN_RECOGNITION events
            elif event_type == 'coordinated_trade':
                evidence_sources.add('PATTERN_RECOGNITION')
                confidence = event.get('pattern_confidence', 0.0)
                wallets = event.get('wallets', [])
                time_window = event.get('time_window_seconds', 999)

                if confidence >= 0.95 and len(wallets) >= 5 and time_window <= 5:
                    factors.coordinated_trading = 0.95
                elif confidence >= 0.89 and len(wallets) >= 3 and time_window <= 10:
                    factors.coordinated_trading = 0.89
                else:
                    factors.coordinated_trading = max(factors.coordinated_trading, confidence)

                # Pattern involvement for wallets
                factors.pattern_involvement = max(factors.pattern_involvement, confidence)

            elif event_type == 'wash_trade':
                evidence_sources.add('PATTERN_RECOGNITION')
                confidence = event.get('wash_trade_confidence', 0.0)

                if confidence >= 0.85:
                    factors.wash_trading = 0.85
                else:
                    factors.wash_trading = max(factors.wash_trading, confidence)

            elif event_type == 'bundler_alert':
                evidence_sources.add('PATTERN_RECOGNITION')
                tx_per_minute = event.get('tx_per_minute', 0)

                if tx_per_minute > 20:
                    factors.bundler = 0.95
                elif tx_per_minute > 10:
                    factors.bundler = 0.90
                else:
                    factors.bundler = min(tx_per_minute / 10, 1.0)

            # SYBIL_DETECTION events
            elif event_type == 'sybil_cluster':
                evidence_sources.add('SYBIL_DETECTION')
                confidence = event.get('cluster_confidence', 0.0)

                if confidence >= 0.90:
                    factors.sybil_cluster = 0.90
                elif confidence >= 0.80:
                    factors.sybil_cluster = 0.80
                else:
                    factors.sybil_cluster = max(factors.sybil_cluster, confidence)

            elif event_type == 'sybil_score':
                evidence_sources.add('SYBIL_DETECTION')
                sybil_prob = event.get('sybil_probability', 0.0)
                factors.sybil_probability = max(factors.sybil_probability, sybil_prob)

        return factors, list(evidence_sources)

    async def process_token_risk(self, token_address: str, events: List[Dict]):
        """
        Calculate and publish token risk score.
        """
        start_time = time.time()

        # Calculate factor scores
        factors, evidence_sources = self.calculate_factor_scores_from_events(events)
        evidence_count = len(evidence_sources)

        # Calculate risk score
        risk_score = self.calculator.calculate_token_risk(factors)
        risk_level = self.calculator.classify_token_risk(risk_score)

        # Calculate Bayesian confidence interval
        confidence_interval = self.bayesian.calculate_interval(risk_score, evidence_count)

        # Get historical trend
        previous_scores = self.cache.get_token_history(token_address)
        historical_trend = self.trend_analyzer.analyze_trend(risk_score, previous_scores)

        # Create risk score object
        score_obj = RiskScore(
            token_address=token_address,
            wallet_address=None,
            risk_score=risk_score,
            risk_level=risk_level,
            confidence_interval=confidence_interval,
            factor_scores=factors,
            evidence_sources=evidence_sources,
            evidence_count=evidence_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
            last_updated=datetime.now(timezone.utc).isoformat(),
            historical_trend=historical_trend
        )

        # Store in cache
        self.cache.set_token_score(token_address, score_obj)

        # Persist to TimescaleDB using psycopg v3
        await self.save_risk_score_to_db(score_obj)

        # Update statistics
        self.stats['tokens_scored'] += 1
        self.stats['total_updates'] += 1
        if risk_level in ['HIGH', 'CRITICAL']:
            self.stats['high_risk_count'] += 1
        if risk_level == 'CRITICAL':
            self.stats['critical_alerts'] += 1

        # Publish to token_risk_scores channel
        await self.publish_message(
            self.output_channels['token_scores'],
            {
                'type': 'token_risk_score',
                'token_address': token_address,
                'risk_score': risk_score,
                'risk_level': risk_level,
                'confidence_interval': asdict(confidence_interval),
                'evidence_count': evidence_count,
                'timestamp': score_obj.timestamp
            }
        )

        # Publish CRITICAL alert
        if risk_level == 'CRITICAL':
            await self.publish_message(
                self.output_channels['high_risk'],
                {
                    'type': 'critical_token_alert',
                    'token_address': token_address,
                    'risk_score': risk_score,
                    'confidence_interval': asdict(confidence_interval),
                    'factor_scores': asdict(factors),
                    'evidence_sources': evidence_sources,
                    'timestamp': score_obj.timestamp
                }
            )

        processing_time = (time.time() - start_time) * 1000  # Convert to ms
        logger.info(f"Token {token_address[:8]}... scored: {risk_score:.1f} ({risk_level}) [{processing_time:.1f}ms]")

    async def process_wallet_risk(self, wallet_address: str, events: List[Dict]):
        """
        Calculate and publish wallet risk score.
        """
        start_time = time.time()

        # Calculate factor scores
        factors, evidence_sources = self.calculate_factor_scores_from_events(events)
        evidence_count = len(evidence_sources)

        # Calculate risk score
        risk_score = self.calculator.calculate_wallet_risk(factors)
        risk_level = self.calculator.classify_wallet_risk(risk_score)

        # Calculate Bayesian confidence interval
        confidence_interval = self.bayesian.calculate_interval(risk_score, evidence_count)

        # Get historical trend
        previous_scores = self.cache.get_wallet_history(wallet_address)
        historical_trend = self.trend_analyzer.analyze_trend(risk_score, previous_scores)

        # Create risk score object
        score_obj = RiskScore(
            token_address=None,
            wallet_address=wallet_address,
            risk_score=risk_score,
            risk_level=risk_level,
            confidence_interval=confidence_interval,
            factor_scores=factors,
            evidence_sources=evidence_sources,
            evidence_count=evidence_count,
            timestamp=datetime.now(timezone.utc).isoformat(),
            last_updated=datetime.now(timezone.utc).isoformat(),
            historical_trend=historical_trend
        )

        # Store in cache
        self.cache.set_wallet_score(wallet_address, score_obj)

        # Persist to TimescaleDB using psycopg v3
        await self.save_risk_score_to_db(score_obj)

        # Update statistics
        self.stats['wallets_scored'] += 1
        self.stats['total_updates'] += 1
        if risk_level in ['HIGH', 'CRITICAL']:
            self.stats['high_risk_count'] += 1
        if risk_level == 'CRITICAL':
            self.stats['critical_alerts'] += 1

        # Publish to wallet_risk_scores channel
        await self.publish_message(
            self.output_channels['wallet_scores'],
            {
                'type': 'wallet_risk_score',
                'wallet_address': wallet_address,
                'risk_score': risk_score,
                'risk_level': risk_level,
                'confidence_interval': asdict(confidence_interval),
                'evidence_count': evidence_count,
                'timestamp': score_obj.timestamp
            }
        )

        # Publish CRITICAL alert
        if risk_level == 'CRITICAL':
            await self.publish_message(
                self.output_channels['high_risk'],
                {
                    'type': 'critical_wallet_alert',
                    'wallet_address': wallet_address,
                    'risk_score': risk_score,
                    'confidence_interval': asdict(confidence_interval),
                    'factor_scores': asdict(factors),
                    'evidence_sources': evidence_sources,
                    'timestamp': score_obj.timestamp
                }
            )

        processing_time = (time.time() - start_time) * 1000  # Convert to ms
        logger.info(f"Wallet {wallet_address[:8]}... scored: {risk_score:.1f} ({risk_level}) [{processing_time:.1f}ms]")

    async def handle_control_message(self, message: Dict):
        """Handle orchestrator control messages"""
        command = message.get('command')

        if command == 'shutdown':
            logger.info("Received shutdown command")
            self.running = False
        elif command == 'status':
            await self.publish_status()
        elif command == 'health':
            await self.publish_heartbeat()

    async def publish_heartbeat(self):
        """Publish heartbeat with current status"""
        uptime = time.time() - self.stats['start_time']
        updates_per_second = self.stats['total_updates'] / max(uptime, 1)

        cache_stats = self.cache.get_stats()
        avg_risk = 0.0

        # Calculate average risk score
        all_scores = (
            [s.risk_score for s in self.cache.token_scores.values()] +
            [s.risk_score for s in self.cache.wallet_scores.values()]
        )
        if all_scores:
            avg_risk = sum(all_scores) / len(all_scores)

        heartbeat = {
            'agent': 'RISK_SCORING',
            'status': 'OPERATIONAL' if self.running else 'STOPPED',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'uptime_seconds': uptime,
            'tokens_scored': self.stats['tokens_scored'],
            'wallets_scored': self.stats['wallets_scored'],
            'critical_alerts': self.stats['critical_alerts'],
            'high_risk_count': self.stats['high_risk_count'],
            'avg_risk_score': round(avg_risk, 2),
            'confidence_intervals_calculated': self.stats['total_updates'],
            'redis_connected': self.stats['redis_connected'],
            'db_connected': self.stats['db_connected'],
            'db_inserts': self.stats['db_inserts'],
            'db_errors': self.stats['db_errors'],
            'subscribed_channels': len(self.input_channels),
            'cache_size': cache_stats['total_cached'],
            'cache_utilization': round(cache_stats['utilization'] * 100, 1),
            'updates_per_second': round(updates_per_second, 2)
        }

        await self.publish_message(self.output_channels['heartbeat'], heartbeat)
        logger.info(f"💓 Heartbeat: {heartbeat['status']} | Tokens: {heartbeat['tokens_scored']} | Wallets: {heartbeat['wallets_scored']} | Alerts: {heartbeat['critical_alerts']} | DB: {'✓' if heartbeat['db_connected'] else '✗'}")

    async def publish_status(self):
        """Publish detailed status report"""
        await self.publish_heartbeat()

    async def aggregation_loop(self):
        """Main aggregation loop - process events every 5 seconds"""
        logger.info("Starting aggregation loop (5-second intervals)")

        # Event aggregation buffers
        token_events: Dict[str, List[Dict]] = defaultdict(list)
        wallet_events: Dict[str, List[Dict]] = defaultdict(list)

        while self.running:
            try:
                # Collect events for 5 seconds
                await asyncio.sleep(5)

                # Process aggregated events
                for token_address, events in token_events.items():
                    await self.process_token_risk(token_address, events)

                for wallet_address, events in wallet_events.items():
                    await self.process_wallet_risk(wallet_address, events)

                # Clear buffers
                token_events.clear()
                wallet_events.clear()

            except Exception as e:
                logger.error(f"Error in aggregation loop: {e}")
                await asyncio.sleep(5)

    async def message_listener(self):
        """Listen for messages from Redis pub/sub"""
        if not self.pubsub:
            logger.warning("No pub/sub connection - skipping listener")
            return

        logger.info("Starting message listener")

        try:
            async for message in self.pubsub.listen():
                if message['type'] != 'message':
                    continue

                try:
                    data = json.loads(message['data'])
                    channel = message['channel']

                    # Handle control messages
                    if channel == 'godmode:control':
                        await self.handle_control_message(data)
                        continue

                    # Extract entities and aggregate events
                    # (This would be implemented based on actual event structures)

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON in message: {message['data']}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except Exception as e:
            logger.error(f"Message listener error: {e}")

    async def heartbeat_loop(self):
        """Publish heartbeat every 10 seconds"""
        while self.running:
            try:
                await self.publish_heartbeat()
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(10)

    async def run(self):
        """Main run loop"""
        logger.info("="*60)
        logger.info("RISK_SCORING AGENT - STARTING")
        logger.info("="*60)

        self.running = True

        # Connect to TimescaleDB using psycopg v3
        await self.connect_db()

        # Connect to Redis
        await self.connect_redis()

        # Start background tasks
        tasks = [
            asyncio.create_task(self.heartbeat_loop()),
            asyncio.create_task(self.aggregation_loop())
        ]

        if self.pubsub:
            tasks.append(asyncio.create_task(self.message_listener()))

        # Initial status
        await self.publish_status()

        logger.info("✓ RISK_SCORING agent operational")
        logger.info(f"✓ Subscribed to {len(self.input_channels)} channels")
        logger.info(f"✓ Cache capacity: {self.cache.max_size} entries")
        logger.info(f"✓ Bayesian confidence: 95% intervals")
        logger.info(f"✓ psycopg v3: {'✓ Connected' if self.stats['db_connected'] else '✗ Disabled'}")

        try:
            # Run until shutdown
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            self.running = False
            # Close database pool
            if self.db_pool:
                await self.db_pool.close()
                logger.info("✓ TimescaleDB connection pool closed")
            if self.redis_client:
                await self.redis_client.close()
            logger.info("RISK_SCORING agent stopped")


# ============================================================
# MAIN ENTRY POINT
# ============================================================

async def main():
    """Main entry point"""
    agent = RiskScoringAgent(redis_url="redis://localhost:6379")
    await agent.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
