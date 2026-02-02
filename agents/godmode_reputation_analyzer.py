"""GODMODESCANNER Reputation Analyzer

Complete reputation analysis for wallet scoring with:
- Reputation calculation (0-100 score)
- Trading history analysis
- Red flag detection

"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Set, Tuple
from datetime import datetime, timezone, timedelta
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

# Reputation score weights
WEIGHTS = {
    "win_rate": 0.25,
    "consistency": 0.15,
    "volume_stability": 0.10,
    "hold_time": 0.15,
    "network_trust": 0.15,
    "age_factor": 0.10,
    "red_flag_penalty": 0.10
}

# Red flag types
class RedFlagType(Enum):
    WASH_TRADING = "wash_trading"
    PUMP_AND_DUMP = "pump_and_dump"
    SYBIL_ACTIVITY = "sybil_activity"
    FRONT_RUNNING = "front_running"
    RUG_PULL_ASSOCIATION = "rug_pull_association"
    COORDINATED_MANIPULATION = "coordinated_manipulation"
    ABNORMAL_PROFITS = "abnormal_profits"
    SUSPICIOUS_TIMING = "suspicious_timing"
    CLUSTER_MEMBERSHIP = "cluster_membership"
    TAINTED_FUNDS = "tainted_funds"

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class RedFlag:
    """Detected red flag."""
    flag_type: RedFlagType
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    confidence: float
    description: str
    evidence: List[str] = field(default_factory=list)
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flag_type": self.flag_type.value,
            "severity": self.severity,
            "confidence": self.confidence,
            "description": self.description,
            "evidence": self.evidence,
            "detected_at": self.detected_at.isoformat()
        }

@dataclass
class TradingHistoryAnalysis:
    """Analysis of trading history."""
    wallet_address: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_volume_sol: float
    avg_trade_size_sol: float
    avg_hold_time_seconds: float
    most_traded_tokens: List[str]
    trading_patterns: List[str]
    first_trade_date: Optional[datetime]
    last_trade_date: Optional[datetime]
    activity_score: float  # 0-1
    consistency_score: float  # 0-1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wallet_address": self.wallet_address,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "total_volume_sol": self.total_volume_sol,
            "avg_trade_size_sol": self.avg_trade_size_sol,
            "avg_hold_time_seconds": self.avg_hold_time_seconds,
            "most_traded_tokens": self.most_traded_tokens,
            "trading_patterns": self.trading_patterns,
            "activity_score": self.activity_score,
            "consistency_score": self.consistency_score
        }

@dataclass
class ReputationScore:
    """Complete reputation score."""
    wallet_address: str
    score: float  # 0-100
    grade: str  # A, B, C, D, F
    components: Dict[str, float]
    red_flags: List[RedFlag]
    trading_analysis: Optional[TradingHistoryAnalysis]
    trust_level: str  # TRUSTED, NEUTRAL, SUSPICIOUS, BLACKLISTED
    calculated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wallet_address": self.wallet_address,
            "score": self.score,
            "grade": self.grade,
            "components": self.components,
            "red_flags": [rf.to_dict() for rf in self.red_flags],
            "trust_level": self.trust_level,
            "calculated_at": self.calculated_at.isoformat()
        }

# =============================================================================
# REPUTATION ANALYZER
# =============================================================================

class GodModeReputationAnalyzer:
    """Complete reputation analysis for GODMODESCANNER."""

    def __init__(self, redis_client=None, db_pool=None):
        self.redis = redis_client
        self.db = db_pool

        # Caches
        self.reputation_cache: Dict[str, ReputationScore] = {}
        self.known_bad_actors: Set[str] = set()
        self.trusted_wallets: Set[str] = set()

        # Stats
        self.stats = {
            "total_analyzed": 0,
            "red_flags_detected": 0,
            "blacklisted": 0
        }

    # =========================================================================
    # CALCULATE REPUTATION (TODO #1)
    # =========================================================================

    async def calculate_reputation(
        self,
        wallet_address: str,
        wallet_data: Optional[Dict[str, Any]] = None,
        force_refresh: bool = False
    ) -> ReputationScore:
        """Calculate comprehensive reputation score (0-100).

        Args:
            wallet_address: Wallet to analyze
            wallet_data: Optional pre-fetched wallet data
            force_refresh: Force recalculation even if cached

        Returns:
            ReputationScore with all components
        """
        self.stats["total_analyzed"] += 1

        # Check cache
        if not force_refresh and wallet_address in self.reputation_cache:
            cached = self.reputation_cache[wallet_address]
            # Cache valid for 1 hour
            if (datetime.now(timezone.utc) - cached.calculated_at).seconds < 3600:
                return cached

        try:
            # Fetch wallet data if not provided
            if wallet_data is None:
                wallet_data = await self._fetch_wallet_data(wallet_address)

            # Analyze trading history
            trading_analysis = await self.analyze_trading_history(
                wallet_address, wallet_data
            )

            # Detect red flags
            red_flags = await self.detect_red_flags(
                wallet_address, wallet_data, trading_analysis
            )

            # Calculate component scores
            components = {}

            # 1. Win rate component (0-100)
            components["win_rate"] = min(trading_analysis.win_rate * 100, 100)

            # 2. Consistency component
            components["consistency"] = trading_analysis.consistency_score * 100

            # 3. Volume stability
            volume_stability = self._calculate_volume_stability(wallet_data)
            components["volume_stability"] = volume_stability * 100

            # 4. Hold time component (longer = better, up to a point)
            hold_score = min(trading_analysis.avg_hold_time_seconds / 3600, 24) / 24
            components["hold_time"] = hold_score * 100

            # 5. Network trust (connections to trusted wallets)
            network_trust = await self._calculate_network_trust(wallet_address)
            components["network_trust"] = network_trust * 100

            # 6. Age factor (older = more trusted)
            age_score = self._calculate_age_score(trading_analysis)
            components["age_factor"] = age_score * 100

            # 7. Red flag penalty
            red_flag_penalty = self._calculate_red_flag_penalty(red_flags)
            components["red_flag_penalty"] = (1 - red_flag_penalty) * 100

            # Calculate weighted score
            score = 0.0
            for component, weight in WEIGHTS.items():
                score += components.get(component, 50) * weight

            # Apply red flag penalty directly
            score = score * (1 - red_flag_penalty * 0.5)

            # Clamp to 0-100
            score = max(0, min(100, score))

            # Determine grade
            grade = self._score_to_grade(score)

            # Determine trust level
            trust_level = self._determine_trust_level(score, red_flags)

            # Update known actors
            if trust_level == "BLACKLISTED":
                self.known_bad_actors.add(wallet_address)
                self.stats["blacklisted"] += 1
            elif trust_level == "TRUSTED":
                self.trusted_wallets.add(wallet_address)

            reputation = ReputationScore(
                wallet_address=wallet_address,
                score=score,
                grade=grade,
                components=components,
                red_flags=red_flags,
                trading_analysis=trading_analysis,
                trust_level=trust_level
            )

            # Cache result
            self.reputation_cache[wallet_address] = reputation

            # Persist to Redis
            if self.redis:
                await self._cache_reputation(wallet_address, reputation)

            return reputation

        except Exception as e:
            logger.error(f"Reputation calculation failed: {e}")
            return ReputationScore(
                wallet_address=wallet_address,
                score=50.0,
                grade="C",
                components={},
                red_flags=[],
                trading_analysis=None,
                trust_level="NEUTRAL"
            )

    # =========================================================================
    # ANALYZE TRADING HISTORY (TODO #2)
    # =========================================================================

    async def analyze_trading_history(
        self,
        wallet_address: str,
        wallet_data: Optional[Dict[str, Any]] = None
    ) -> TradingHistoryAnalysis:
        """Analyze complete trading history.

        Args:
            wallet_address: Wallet to analyze
            wallet_data: Optional pre-fetched data

        Returns:
            TradingHistoryAnalysis with detailed metrics
        """
        try:
            if wallet_data is None:
                wallet_data = await self._fetch_wallet_data(wallet_address)

            # Extract trading data
            trades = wallet_data.get("trades", [])
            total_trades = len(trades)

            if total_trades == 0:
                return TradingHistoryAnalysis(
                    wallet_address=wallet_address,
                    total_trades=0,
                    winning_trades=0,
                    losing_trades=0,
                    win_rate=0.5,
                    total_volume_sol=0.0,
                    avg_trade_size_sol=0.0,
                    avg_hold_time_seconds=0.0,
                    most_traded_tokens=[],
                    trading_patterns=[],
                    first_trade_date=None,
                    last_trade_date=None,
                    activity_score=0.0,
                    consistency_score=0.5
                )

            # Calculate metrics
            winning_trades = sum(1 for t in trades if t.get("profit", 0) > 0)
            losing_trades = sum(1 for t in trades if t.get("profit", 0) < 0)
            win_rate = winning_trades / total_trades if total_trades > 0 else 0.5

            total_volume = sum(t.get("volume_sol", 0) for t in trades)
            avg_trade_size = total_volume / total_trades if total_trades > 0 else 0

            hold_times = [t.get("hold_time_seconds", 0) for t in trades if t.get("hold_time_seconds")]
            avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else 0

            # Most traded tokens
            token_counts: Dict[str, int] = {}
            for trade in trades:
                token = trade.get("token_mint", "")
                if token:
                    token_counts[token] = token_counts.get(token, 0) + 1

            most_traded = sorted(token_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            most_traded_tokens = [t[0] for t in most_traded]

            # Detect trading patterns
            patterns = self._detect_trading_patterns(trades)

            # Get date range
            timestamps = [t.get("timestamp") for t in trades if t.get("timestamp")]
            first_trade = min(timestamps) if timestamps else None
            last_trade = max(timestamps) if timestamps else None

            if isinstance(first_trade, (int, float)):
                first_trade = datetime.fromtimestamp(first_trade, tz=timezone.utc)
            if isinstance(last_trade, (int, float)):
                last_trade = datetime.fromtimestamp(last_trade, tz=timezone.utc)

            # Activity score (trades per day)
            if first_trade and last_trade:
                days_active = max((last_trade - first_trade).days, 1)
                trades_per_day = total_trades / days_active
                activity_score = min(trades_per_day / 10, 1.0)  # 10 trades/day = max
            else:
                activity_score = 0.0

            # Consistency score (variance in trade sizes)
            if len(trades) >= 3:
                volumes = [t.get("volume_sol", 0) for t in trades]
                mean_vol = sum(volumes) / len(volumes)
                if mean_vol > 0:
                    variance = sum((v - mean_vol) ** 2 for v in volumes) / len(volumes)
                    cv = (variance ** 0.5) / mean_vol  # Coefficient of variation
                    consistency_score = max(0, 1 - cv)  # Lower CV = more consistent
                else:
                    consistency_score = 0.5
            else:
                consistency_score = 0.5

            return TradingHistoryAnalysis(
                wallet_address=wallet_address,
                total_trades=total_trades,
                winning_trades=winning_trades,
                losing_trades=losing_trades,
                win_rate=win_rate,
                total_volume_sol=total_volume,
                avg_trade_size_sol=avg_trade_size,
                avg_hold_time_seconds=avg_hold_time,
                most_traded_tokens=most_traded_tokens,
                trading_patterns=patterns,
                first_trade_date=first_trade,
                last_trade_date=last_trade,
                activity_score=activity_score,
                consistency_score=consistency_score
            )

        except Exception as e:
            logger.error(f"Trading history analysis failed: {e}")
            return TradingHistoryAnalysis(
                wallet_address=wallet_address,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.5,
                total_volume_sol=0.0,
                avg_trade_size_sol=0.0,
                avg_hold_time_seconds=0.0,
                most_traded_tokens=[],
                trading_patterns=[],
                first_trade_date=None,
                last_trade_date=None,
                activity_score=0.0,
                consistency_score=0.5
            )

    # =========================================================================
    # DETECT RED FLAGS (TODO #3)
    # =========================================================================

    async def detect_red_flags(
        self,
        wallet_address: str,
        wallet_data: Optional[Dict[str, Any]] = None,
        trading_analysis: Optional[TradingHistoryAnalysis] = None
    ) -> List[RedFlag]:
        """Detect suspicious patterns and red flags.

        Args:
            wallet_address: Wallet to analyze
            wallet_data: Optional pre-fetched data
            trading_analysis: Optional pre-computed analysis

        Returns:
            List of detected RedFlag objects
        """
        red_flags = []

        try:
            if wallet_data is None:
                wallet_data = await self._fetch_wallet_data(wallet_address)

            if trading_analysis is None:
                trading_analysis = await self.analyze_trading_history(
                    wallet_address, wallet_data
                )

            # Check 1: Wash Trading
            wash_trading = self._detect_wash_trading(wallet_data, trading_analysis)
            if wash_trading:
                red_flags.append(wash_trading)

            # Check 2: Pump and Dump
            pump_dump = self._detect_pump_and_dump(wallet_data, trading_analysis)
            if pump_dump:
                red_flags.append(pump_dump)

            # Check 3: Sybil Activity
            sybil = await self._detect_sybil_activity(wallet_address, wallet_data)
            if sybil:
                red_flags.append(sybil)

            # Check 4: Front Running
            front_running = self._detect_front_running(wallet_data)
            if front_running:
                red_flags.append(front_running)

            # Check 5: Rug Pull Association
            rug_pull = await self._detect_rug_pull_association(wallet_address, wallet_data)
            if rug_pull:
                red_flags.append(rug_pull)

            # Check 6: Coordinated Manipulation
            coordination = await self._detect_coordinated_manipulation(
                wallet_address, wallet_data
            )
            if coordination:
                red_flags.append(coordination)

            # Check 7: Abnormal Profits
            abnormal_profits = self._detect_abnormal_profits(trading_analysis)
            if abnormal_profits:
                red_flags.append(abnormal_profits)

            # Check 8: Suspicious Timing
            suspicious_timing = self._detect_suspicious_timing(wallet_data)
            if suspicious_timing:
                red_flags.append(suspicious_timing)

            # Check 9: Cluster Membership
            cluster = await self._detect_cluster_membership(wallet_address)
            if cluster:
                red_flags.append(cluster)

            # Check 10: Tainted Funds
            tainted = await self._detect_tainted_funds(wallet_address)
            if tainted:
                red_flags.append(tainted)

            self.stats["red_flags_detected"] += len(red_flags)

        except Exception as e:
            logger.error(f"Red flag detection failed: {e}")

        return red_flags

    # =========================================================================
    # RED FLAG DETECTION HELPERS
    # =========================================================================

    def _detect_wash_trading(self, wallet_data: Dict, analysis: TradingHistoryAnalysis) -> Optional[RedFlag]:
        """Detect wash trading patterns."""
        trades = wallet_data.get("trades", [])
        if len(trades) < 5:
            return None

        # Check for rapid buy-sell cycles on same token
        token_cycles = {}
        for trade in trades:
            token = trade.get("token_mint", "")
            trade_type = trade.get("type", "")
            if token:
                if token not in token_cycles:
                    token_cycles[token] = {"buys": 0, "sells": 0}
                if trade_type == "buy":
                    token_cycles[token]["buys"] += 1
                elif trade_type == "sell":
                    token_cycles[token]["sells"] += 1

        # Suspicious if many tokens have equal buys and sells
        suspicious_tokens = sum(
            1 for t, c in token_cycles.items()
            if c["buys"] >= 3 and c["buys"] == c["sells"]
        )

        if suspicious_tokens >= 3:
            return RedFlag(
                flag_type=RedFlagType.WASH_TRADING,
                severity="HIGH",
                confidence=min(0.5 + suspicious_tokens * 0.1, 0.95),
                description=f"Wash trading pattern detected on {suspicious_tokens} tokens",
                evidence=[f"{suspicious_tokens} tokens with equal buy/sell cycles"]
            )

        return None

    def _detect_pump_and_dump(self, wallet_data: Dict, analysis: TradingHistoryAnalysis) -> Optional[RedFlag]:
        """Detect pump and dump patterns."""
        # Check for large buys followed by quick sells at profit
        trades = wallet_data.get("trades", [])

        pump_dump_count = 0
        for i, trade in enumerate(trades):
            if trade.get("type") == "buy" and trade.get("volume_sol", 0) > 1.0:
                # Look for quick sell
                for j in range(i+1, min(i+5, len(trades))):
                    next_trade = trades[j]
                    if (next_trade.get("type") == "sell" and 
                        next_trade.get("token_mint") == trade.get("token_mint") and
                        next_trade.get("profit", 0) > trade.get("volume_sol", 0) * 0.5):
                        pump_dump_count += 1
                        break

        if pump_dump_count >= 2:
            return RedFlag(
                flag_type=RedFlagType.PUMP_AND_DUMP,
                severity="CRITICAL",
                confidence=min(0.6 + pump_dump_count * 0.1, 0.95),
                description=f"Pump and dump pattern detected {pump_dump_count} times",
                evidence=[f"{pump_dump_count} instances of large buy followed by quick profitable sell"]
            )

        return None

    async def _detect_sybil_activity(self, wallet_address: str, wallet_data: Dict) -> Optional[RedFlag]:
        """Detect sybil attack patterns."""
        # Check for connections to many similar wallets
        connected_wallets = wallet_data.get("connected_wallets", [])

        if len(connected_wallets) >= 10:
            # Check if connected wallets have similar behavior
            similar_count = wallet_data.get("similar_wallet_count", 0)

            if similar_count >= 5:
                return RedFlag(
                    flag_type=RedFlagType.SYBIL_ACTIVITY,
                    severity="HIGH",
                    confidence=min(0.5 + similar_count * 0.05, 0.9),
                    description=f"Sybil network detected with {similar_count} similar wallets",
                    evidence=[f"Connected to {len(connected_wallets)} wallets, {similar_count} with similar behavior"]
                )

        return None

    def _detect_front_running(self, wallet_data: Dict) -> Optional[RedFlag]:
        """Detect front-running patterns."""
        front_run_count = wallet_data.get("front_run_count", 0)

        if front_run_count >= 3:
            return RedFlag(
                flag_type=RedFlagType.FRONT_RUNNING,
                severity="CRITICAL",
                confidence=min(0.7 + front_run_count * 0.05, 0.95),
                description=f"Front-running detected {front_run_count} times",
                evidence=[f"{front_run_count} transactions placed immediately before large trades"]
            )

        return None

    async def _detect_rug_pull_association(self, wallet_address: str, wallet_data: Dict) -> Optional[RedFlag]:
        """Detect association with rug pulls."""
        rug_pull_tokens = wallet_data.get("rug_pull_tokens", [])

        if len(rug_pull_tokens) >= 2:
            return RedFlag(
                flag_type=RedFlagType.RUG_PULL_ASSOCIATION,
                severity="CRITICAL",
                confidence=min(0.6 + len(rug_pull_tokens) * 0.1, 0.95),
                description=f"Associated with {len(rug_pull_tokens)} rug pull tokens",
                evidence=[f"Traded tokens: {', '.join(rug_pull_tokens[:3])}"]
            )

        return None

    async def _detect_coordinated_manipulation(self, wallet_address: str, wallet_data: Dict) -> Optional[RedFlag]:
        """Detect coordinated market manipulation."""
        coordination_score = wallet_data.get("coordination_score", 0)

        if coordination_score > 0.7:
            return RedFlag(
                flag_type=RedFlagType.COORDINATED_MANIPULATION,
                severity="HIGH",
                confidence=coordination_score,
                description="Coordinated trading manipulation detected",
                evidence=[f"Coordination score: {coordination_score:.2f}"]
            )

        return None

    def _detect_abnormal_profits(self, analysis: TradingHistoryAnalysis) -> Optional[RedFlag]:
        """Detect abnormally high profits."""
        if analysis.win_rate > 0.9 and analysis.total_trades >= 20:
            return RedFlag(
                flag_type=RedFlagType.ABNORMAL_PROFITS,
                severity="MEDIUM",
                confidence=min(analysis.win_rate, 0.9),
                description=f"Abnormally high win rate: {analysis.win_rate:.1%}",
                evidence=[f"{analysis.winning_trades}/{analysis.total_trades} winning trades"]
            )

        return None

    def _detect_suspicious_timing(self, wallet_data: Dict) -> Optional[RedFlag]:
        """Detect suspicious transaction timing."""
        early_buy_count = wallet_data.get("early_buy_count", 0)

        if early_buy_count >= 5:
            return RedFlag(
                flag_type=RedFlagType.SUSPICIOUS_TIMING,
                severity="HIGH",
                confidence=min(0.5 + early_buy_count * 0.05, 0.9),
                description=f"Consistently buys within seconds of token launch",
                evidence=[f"{early_buy_count} early buys detected"]
            )

        return None

    async def _detect_cluster_membership(self, wallet_address: str) -> Optional[RedFlag]:
        """Detect membership in suspicious wallet cluster."""
        if self.redis:
            try:
                cluster_id = await self.redis.get(f"wallet_cluster:{wallet_address}")
                if cluster_id:
                    cluster_risk = await self.redis.get(f"cluster_risk:{cluster_id}")
                    if cluster_risk and float(cluster_risk) > 0.7:
                        return RedFlag(
                            flag_type=RedFlagType.CLUSTER_MEMBERSHIP,
                            severity="HIGH",
                            confidence=float(cluster_risk),
                            description=f"Member of high-risk wallet cluster",
                            evidence=[f"Cluster ID: {cluster_id}, Risk: {float(cluster_risk):.2f}"]
                        )
            except Exception:
                pass

        return None

    async def _detect_tainted_funds(self, wallet_address: str) -> Optional[RedFlag]:
        """Detect funds from known bad actors."""
        if wallet_address in self.known_bad_actors:
            return RedFlag(
                flag_type=RedFlagType.TAINTED_FUNDS,
                severity="CRITICAL",
                confidence=0.95,
                description="Wallet is a known bad actor",
                evidence=["Previously blacklisted"]
            )

        # Check funding sources
        if self.db:
            try:
                async with self.db.connection() as conn:
                    query = """
                        SELECT source FROM transactions
                        WHERE destination = $1
                        AND source = ANY($2)
                        LIMIT 1
                    """
                    async with conn.cursor() as cur:
                        await cur.execute(query, (wallet_address, list(self.known_bad_actors)))
                        row = await cur.fetchone()
                        if row:
                            return RedFlag(
                                flag_type=RedFlagType.TAINTED_FUNDS,
                                severity="HIGH",
                                confidence=0.85,
                                description="Received funds from known bad actor",
                                evidence=[f"Funded by: {row[0][:16]}..."]
                            )
            except Exception:
                pass

        return None

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    async def _fetch_wallet_data(self, wallet_address: str) -> Dict[str, Any]:
        """Fetch wallet data from database/cache."""
        data = {"trades": [], "connected_wallets": []}

        # Try Redis cache first
        if self.redis:
            try:
                cached = await self.redis.hgetall(f"wallet_data:{wallet_address}")
                if cached:
                    return cached
            except Exception:
                pass

        # Fetch from database
        if self.db:
            try:
                async with self.db.connection() as conn:
                    query = """
                        SELECT * FROM trades
                        WHERE wallet_address = $1
                        ORDER BY timestamp DESC
                        LIMIT 1000
                    """
                    async with conn.cursor() as cur:
                        await cur.execute(query, (wallet_address,))
                        rows = await cur.fetchall()
                        data["trades"] = [dict(row) for row in rows] if rows else []
            except Exception:
                pass

        return data

    def _calculate_volume_stability(self, wallet_data: Dict) -> float:
        """Calculate volume stability score."""
        trades = wallet_data.get("trades", [])
        if len(trades) < 3:
            return 0.5

        volumes = [t.get("volume_sol", 0) for t in trades]
        mean_vol = sum(volumes) / len(volumes)
        if mean_vol == 0:
            return 0.5

        variance = sum((v - mean_vol) ** 2 for v in volumes) / len(volumes)
        cv = (variance ** 0.5) / mean_vol

        return max(0, 1 - cv)

    async def _calculate_network_trust(self, wallet_address: str) -> float:
        """Calculate trust based on network connections."""
        if not self.trusted_wallets:
            return 0.5

        # Check connections to trusted wallets
        trusted_connections = 0
        bad_connections = 0

        if self.db:
            try:
                async with self.db.connection() as conn:
                    # Check for trusted connections
                    query = """
                        SELECT COUNT(DISTINCT source) FROM transactions
                        WHERE destination = $1 AND source = ANY($2)
                    """
                    async with conn.cursor() as cur:
                        await cur.execute(query, (wallet_address, list(self.trusted_wallets)))
                        row = await cur.fetchone()
                        trusted_connections = row[0] if row else 0

                        await cur.execute(query, (wallet_address, list(self.known_bad_actors)))
                        row = await cur.fetchone()
                        bad_connections = row[0] if row else 0
            except Exception:
                pass

        if trusted_connections > 0 and bad_connections == 0:
            return min(0.5 + trusted_connections * 0.1, 1.0)
        elif bad_connections > 0:
            return max(0.5 - bad_connections * 0.1, 0.0)

        return 0.5

    def _calculate_age_score(self, analysis: TradingHistoryAnalysis) -> float:
        """Calculate age-based trust score."""
        if not analysis.first_trade_date:
            return 0.3

        age_days = (datetime.now(timezone.utc) - analysis.first_trade_date).days

        if age_days >= 365:
            return 1.0
        elif age_days >= 180:
            return 0.8
        elif age_days >= 90:
            return 0.6
        elif age_days >= 30:
            return 0.4
        else:
            return 0.2

    def _calculate_red_flag_penalty(self, red_flags: List[RedFlag]) -> float:
        """Calculate penalty from red flags."""
        if not red_flags:
            return 0.0

        severity_weights = {
            "LOW": 0.1,
            "MEDIUM": 0.2,
            "HIGH": 0.4,
            "CRITICAL": 0.6
        }

        total_penalty = 0.0
        for flag in red_flags:
            weight = severity_weights.get(flag.severity, 0.2)
            total_penalty += weight * flag.confidence

        return min(total_penalty, 1.0)

    def _score_to_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _determine_trust_level(self, score: float, red_flags: List[RedFlag]) -> str:
        """Determine trust level from score and flags."""
        critical_flags = sum(1 for f in red_flags if f.severity == "CRITICAL")

        if critical_flags >= 2 or score < 30:
            return "BLACKLISTED"
        elif critical_flags >= 1 or score < 50:
            return "SUSPICIOUS"
        elif score >= 80 and len(red_flags) == 0:
            return "TRUSTED"
        else:
            return "NEUTRAL"

    def _detect_trading_patterns(self, trades: List[Dict]) -> List[str]:
        """Detect trading patterns from trade history."""
        patterns = []

        if not trades:
            return patterns

        # Check for scalping
        quick_trades = sum(1 for t in trades if t.get("hold_time_seconds", 0) < 300)
        if quick_trades / len(trades) > 0.5:
            patterns.append("SCALPER")

        # Check for swing trading
        long_trades = sum(1 for t in trades if t.get("hold_time_seconds", 0) > 86400)
        if long_trades / len(trades) > 0.3:
            patterns.append("SWING_TRADER")

        # Check for high frequency
        if len(trades) > 100:
            patterns.append("HIGH_FREQUENCY")

        # Check for large trades
        large_trades = sum(1 for t in trades if t.get("volume_sol", 0) > 10)
        if large_trades > 5:
            patterns.append("WHALE")

        return patterns

    async def _cache_reputation(self, wallet_address: str, reputation: ReputationScore) -> None:
        """Cache reputation to Redis."""
        try:
            cache_key = f"reputation:{wallet_address}"
            await self.redis.hset(cache_key, mapping={
                "score": str(reputation.score),
                "grade": reputation.grade,
                "trust_level": reputation.trust_level,
                "red_flag_count": str(len(reputation.red_flags)),
                "calculated_at": reputation.calculated_at.isoformat()
            })
            await self.redis.expire(cache_key, 3600)  # 1 hour TTL
        except Exception as e:
            logger.warning(f"Failed to cache reputation: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get analyzer statistics."""
        return {
            **self.stats,
            "cached_reputations": len(self.reputation_cache),
            "known_bad_actors": len(self.known_bad_actors),
            "trusted_wallets": len(self.trusted_wallets)
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_analyzer_instance: Optional[GodModeReputationAnalyzer] = None

def get_reputation_analyzer(redis_client=None, db_pool=None) -> GodModeReputationAnalyzer:
    """Get singleton reputation analyzer."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = GodModeReputationAnalyzer(redis_client, db_pool)
    return _analyzer_instance
