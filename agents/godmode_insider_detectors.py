"""GODMODESCANNER Insider Detectors

Complete insider trading detection for pump.fun with:
- Dev Insider detection (creator self-dealing)
- Telegram Alpha detection (coordinated buying)
- Sniper Bot detection (automated early entry)

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

# Detection thresholds
DEV_INSIDER_THRESHOLD = 0.85
TELEGRAM_ALPHA_THRESHOLD = 0.75
SNIPER_BOT_THRESHOLD = 0.80

# Timing thresholds (seconds)
EARLY_BUY_WINDOW = 60  # First 60 seconds = suspicious
SNIPER_WINDOW = 3  # First 3 seconds = likely bot
COORDINATED_WINDOW = 30  # 30 second window for coordinated buys

# =============================================================================
# DATA CLASSES
# =============================================================================

class InsiderType(Enum):
    """Types of insider trading patterns."""
    DEV_INSIDER = "dev_insider"
    TELEGRAM_ALPHA = "telegram_alpha"
    SNIPER_BOT = "sniper_bot"
    WASH_TRADER = "wash_trader"
    DELAYED_INSIDER = "delayed_insider"
    SYBIL_ARMY = "sybil_army"

@dataclass
class InsiderDetection:
    """Result of insider detection."""
    wallet_address: str
    insider_type: InsiderType
    confidence: float  # 0.0 to 1.0
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    evidence: List[str] = field(default_factory=list)
    related_wallets: List[str] = field(default_factory=list)
    token_mint: Optional[str] = None
    detection_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wallet_address": self.wallet_address,
            "insider_type": self.insider_type.value,
            "confidence": self.confidence,
            "severity": self.severity,
            "evidence": self.evidence,
            "related_wallets": self.related_wallets,
            "token_mint": self.token_mint,
            "detection_time": self.detection_time.isoformat()
        }

@dataclass
class TokenLaunchData:
    """Data about a token launch."""
    mint: str
    creator: str
    launch_time: datetime
    launch_slot: int
    bonding_curve: Optional[str] = None
    initial_supply: int = 0

@dataclass
class WalletActivity:
    """Activity data for a wallet."""
    address: str
    transactions: List[Dict[str, Any]] = field(default_factory=list)
    buy_times: List[datetime] = field(default_factory=list)
    sell_times: List[datetime] = field(default_factory=list)
    tokens_bought: Set[str] = field(default_factory=set)
    tokens_sold: Set[str] = field(default_factory=set)
    total_volume_sol: float = 0.0
    avg_hold_time_seconds: float = 0.0

# =============================================================================
# INSIDER DETECTORS
# =============================================================================

class GodModeInsiderDetectors:
    """Complete insider detection system for GODMODESCANNER."""

    def __init__(self, redis_client=None, db_pool=None):
        self.redis = redis_client
        self.db = db_pool

        # Detection stats
        self.stats = {
            "total_detections": 0,
            "dev_insider": 0,
            "telegram_alpha": 0,
            "sniper_bot": 0,
            "false_positives": 0
        }

        # Known patterns cache
        self.known_dev_wallets: Set[str] = set()
        self.known_sniper_bots: Set[str] = set()
        self.telegram_groups: Dict[str, Set[str]] = {}  # group_id -> wallets

    # =========================================================================
    # DEV INSIDER DETECTION (TODO #1)
    # =========================================================================

    async def detect_dev_insider(
        self,
        wallet_address: str,
        token_mint: str,
        token_launch: TokenLaunchData,
        wallet_activity: WalletActivity
    ) -> Optional[InsiderDetection]:
        """Detect dev insider trading (creator self-dealing).

        Patterns detected:
        - Creator buying their own token immediately after launch
        - Creator using alt wallets to accumulate
        - Creator front-running their own announcements
        - Suspicious token allocation to connected wallets

        Args:
            wallet_address: Wallet to analyze
            token_mint: Token being traded
            token_launch: Token launch data
            wallet_activity: Wallet's trading activity

        Returns:
            InsiderDetection if detected, None otherwise
        """
        evidence = []
        confidence = 0.0

        try:
            # Check 1: Is this the token creator?
            is_creator = wallet_address == token_launch.creator
            if is_creator:
                evidence.append("Wallet is token creator")
                confidence += 0.3

            # Check 2: Did wallet buy within first 60 seconds?
            for buy_time in wallet_activity.buy_times:
                seconds_after_launch = (buy_time - token_launch.launch_time).total_seconds()
                if 0 < seconds_after_launch <= EARLY_BUY_WINDOW:
                    evidence.append(f"Bought {seconds_after_launch:.1f}s after launch")
                    # Earlier = more suspicious
                    if seconds_after_launch <= 10:
                        confidence += 0.4
                    elif seconds_after_launch <= 30:
                        confidence += 0.3
                    else:
                        confidence += 0.2
                    break

            # Check 3: Check for connected wallets (funding relationship)
            connected_wallets = await self._find_connected_wallets(wallet_address)
            creator_connected = token_launch.creator in connected_wallets
            if creator_connected and not is_creator:
                evidence.append(f"Wallet connected to creator via funding")
                confidence += 0.35

            # Check 4: Check for pre-launch activity
            pre_launch_activity = await self._check_pre_launch_activity(
                wallet_address, token_launch
            )
            if pre_launch_activity:
                evidence.append("Suspicious pre-launch activity detected")
                confidence += 0.25

            # Check 5: Abnormal allocation percentage
            allocation_pct = await self._check_token_allocation(
                wallet_address, token_mint
            )
            if allocation_pct > 5.0:  # More than 5% of supply
                evidence.append(f"Holds {allocation_pct:.1f}% of token supply")
                confidence += 0.2

            # Check 6: Quick flip pattern (buy and sell within minutes)
            if wallet_activity.avg_hold_time_seconds < 300:  # Less than 5 minutes
                evidence.append(f"Quick flip: avg hold {wallet_activity.avg_hold_time_seconds:.0f}s")
                confidence += 0.15

            # Determine if detection threshold met
            confidence = min(confidence, 1.0)

            if confidence >= DEV_INSIDER_THRESHOLD:
                self.stats["total_detections"] += 1
                self.stats["dev_insider"] += 1
                self.known_dev_wallets.add(wallet_address)

                severity = self._calculate_severity(confidence)

                return InsiderDetection(
                    wallet_address=wallet_address,
                    insider_type=InsiderType.DEV_INSIDER,
                    confidence=confidence,
                    severity=severity,
                    evidence=evidence,
                    related_wallets=list(connected_wallets)[:10],
                    token_mint=token_mint
                )

            return None

        except Exception as e:
            logger.error(f"Dev insider detection failed: {e}")
            return None

    # =========================================================================
    # TELEGRAM ALPHA DETECTION (TODO #2)
    # =========================================================================

    async def detect_telegram_alpha(
        self,
        wallet_address: str,
        token_mint: str,
        token_launch: TokenLaunchData,
        all_buyers: List[WalletActivity]
    ) -> Optional[InsiderDetection]:
        """Detect Telegram alpha group coordinated buying.

        Patterns detected:
        - Multiple wallets buying within tight time window
        - Similar buy amounts across wallets
        - Wallets with shared funding sources
        - Repeated coordination across multiple tokens

        Args:
            wallet_address: Wallet to analyze
            token_mint: Token being traded
            token_launch: Token launch data
            all_buyers: All buyers of this token

        Returns:
            InsiderDetection if detected, None otherwise
        """
        evidence = []
        confidence = 0.0
        related_wallets = []

        try:
            # Get this wallet's buy time
            wallet_activity = next(
                (w for w in all_buyers if w.address == wallet_address),
                None
            )
            if not wallet_activity or not wallet_activity.buy_times:
                return None

            wallet_buy_time = wallet_activity.buy_times[0]

            # Check 1: Find wallets that bought within coordinated window
            coordinated_buyers = []
            for buyer in all_buyers:
                if buyer.address == wallet_address:
                    continue
                if not buyer.buy_times:
                    continue

                buyer_time = buyer.buy_times[0]
                time_diff = abs((buyer_time - wallet_buy_time).total_seconds())

                if time_diff <= COORDINATED_WINDOW:
                    coordinated_buyers.append(buyer)

            if len(coordinated_buyers) >= 3:
                evidence.append(f"{len(coordinated_buyers)} wallets bought within {COORDINATED_WINDOW}s")
                # More coordinated buyers = higher confidence
                confidence += min(0.1 * len(coordinated_buyers), 0.4)
                related_wallets.extend([b.address for b in coordinated_buyers])

            # Check 2: Similar buy amounts (within 20%)
            if coordinated_buyers:
                wallet_volume = wallet_activity.total_volume_sol
                similar_amounts = 0

                for buyer in coordinated_buyers:
                    if wallet_volume > 0:
                        diff_pct = abs(buyer.total_volume_sol - wallet_volume) / wallet_volume
                        if diff_pct <= 0.2:
                            similar_amounts += 1

                if similar_amounts >= 2:
                    evidence.append(f"{similar_amounts} wallets with similar buy amounts")
                    confidence += 0.2

            # Check 3: Shared funding sources
            funding_sources = await self._find_funding_sources(wallet_address)
            shared_funding_count = 0

            for buyer in coordinated_buyers:
                buyer_funding = await self._find_funding_sources(buyer.address)
                if funding_sources & buyer_funding:  # Intersection
                    shared_funding_count += 1

            if shared_funding_count >= 2:
                evidence.append(f"{shared_funding_count} wallets share funding sources")
                confidence += 0.25

            # Check 4: Check for repeated coordination pattern
            coordination_history = await self._check_coordination_history(
                wallet_address, [b.address for b in coordinated_buyers]
            )
            if coordination_history >= 3:  # Coordinated on 3+ tokens
                evidence.append(f"Coordinated on {coordination_history} previous tokens")
                confidence += 0.3

            # Check 5: All bought early (within first 2 minutes)
            early_buyers = sum(
                1 for b in coordinated_buyers
                if b.buy_times and (b.buy_times[0] - token_launch.launch_time).total_seconds() <= 120
            )
            if early_buyers >= 3:
                evidence.append(f"{early_buyers} coordinated early buyers")
                confidence += 0.15

            # Determine if detection threshold met
            confidence = min(confidence, 1.0)

            if confidence >= TELEGRAM_ALPHA_THRESHOLD:
                self.stats["total_detections"] += 1
                self.stats["telegram_alpha"] += 1

                # Track this group
                group_id = self._generate_group_id(wallet_address, related_wallets)
                if group_id not in self.telegram_groups:
                    self.telegram_groups[group_id] = set()
                self.telegram_groups[group_id].add(wallet_address)
                self.telegram_groups[group_id].update(related_wallets)

                severity = self._calculate_severity(confidence)

                return InsiderDetection(
                    wallet_address=wallet_address,
                    insider_type=InsiderType.TELEGRAM_ALPHA,
                    confidence=confidence,
                    severity=severity,
                    evidence=evidence,
                    related_wallets=related_wallets[:20],
                    token_mint=token_mint
                )

            return None

        except Exception as e:
            logger.error(f"Telegram alpha detection failed: {e}")
            return None

    # =========================================================================
    # SNIPER BOT DETECTION (TODO #3)
    # =========================================================================

    async def detect_sniper_bot(
        self,
        wallet_address: str,
        token_mint: str,
        token_launch: TokenLaunchData,
        wallet_activity: WalletActivity
    ) -> Optional[InsiderDetection]:
        """Detect automated sniper bot activity.

        Patterns detected:
        - Buying within first 3 seconds of launch
        - Consistent sub-second transaction timing
        - High transaction frequency
        - Programmatic behavior patterns

        Args:
            wallet_address: Wallet to analyze
            token_mint: Token being traded
            token_launch: Token launch data
            wallet_activity: Wallet's trading activity

        Returns:
            InsiderDetection if detected, None otherwise
        """
        evidence = []
        confidence = 0.0

        try:
            # Check 1: Ultra-fast buy (within 3 seconds)
            for buy_time in wallet_activity.buy_times:
                seconds_after_launch = (buy_time - token_launch.launch_time).total_seconds()
                if 0 < seconds_after_launch <= SNIPER_WINDOW:
                    evidence.append(f"Bought {seconds_after_launch:.2f}s after launch (bot speed)")
                    # Sub-second = definitely bot
                    if seconds_after_launch < 1.0:
                        confidence += 0.5
                    elif seconds_after_launch < 2.0:
                        confidence += 0.4
                    else:
                        confidence += 0.3
                    break

            # Check 2: High transaction frequency (bot-like)
            if len(wallet_activity.transactions) > 0:
                tx_count = len(wallet_activity.transactions)
                if tx_count >= 100:  # 100+ transactions
                    evidence.append(f"High tx frequency: {tx_count} transactions")
                    confidence += 0.2
                elif tx_count >= 50:
                    evidence.append(f"Elevated tx frequency: {tx_count} transactions")
                    confidence += 0.1

            # Check 3: Consistent timing patterns (programmatic)
            timing_variance = self._calculate_timing_variance(wallet_activity)
            if timing_variance < 0.1:  # Very consistent timing
                evidence.append(f"Programmatic timing pattern (variance: {timing_variance:.3f})")
                confidence += 0.25

            # Check 4: Known sniper bot patterns
            if wallet_address in self.known_sniper_bots:
                evidence.append("Previously identified as sniper bot")
                confidence += 0.3

            # Check 5: Multiple token snipes in short period
            snipe_count = await self._count_recent_snipes(wallet_address)
            if snipe_count >= 5:
                evidence.append(f"Sniped {snipe_count} tokens recently")
                confidence += 0.25
            elif snipe_count >= 3:
                evidence.append(f"Sniped {snipe_count} tokens recently")
                confidence += 0.15

            # Check 6: Immediate sell after buy (scalping)
            if wallet_activity.avg_hold_time_seconds < 60:  # Less than 1 minute
                evidence.append(f"Scalping pattern: {wallet_activity.avg_hold_time_seconds:.0f}s avg hold")
                confidence += 0.2

            # Check 7: Check for MEV/sandwich patterns
            mev_score = await self._check_mev_patterns(wallet_address, token_mint)
            if mev_score > 0.5:
                evidence.append(f"MEV/sandwich pattern detected (score: {mev_score:.2f})")
                confidence += 0.2

            # Determine if detection threshold met
            confidence = min(confidence, 1.0)

            if confidence >= SNIPER_BOT_THRESHOLD:
                self.stats["total_detections"] += 1
                self.stats["sniper_bot"] += 1
                self.known_sniper_bots.add(wallet_address)

                severity = self._calculate_severity(confidence)

                return InsiderDetection(
                    wallet_address=wallet_address,
                    insider_type=InsiderType.SNIPER_BOT,
                    confidence=confidence,
                    severity=severity,
                    evidence=evidence,
                    related_wallets=[],
                    token_mint=token_mint
                )

            return None

        except Exception as e:
            logger.error(f"Sniper bot detection failed: {e}")
            return None

    # =========================================================================
    # COMBINED DETECTION
    # =========================================================================

    async def detect_all(
        self,
        wallet_address: str,
        token_mint: str,
        token_launch: TokenLaunchData,
        wallet_activity: WalletActivity,
        all_buyers: Optional[List[WalletActivity]] = None
    ) -> List[InsiderDetection]:
        """Run all detection methods on a wallet.

        Args:
            wallet_address: Wallet to analyze
            token_mint: Token being traded
            token_launch: Token launch data
            wallet_activity: Wallet's trading activity
            all_buyers: All buyers (for coordination detection)

        Returns:
            List of all detections
        """
        detections = []

        # Run all detectors in parallel
        tasks = [
            self.detect_dev_insider(wallet_address, token_mint, token_launch, wallet_activity),
            self.detect_sniper_bot(wallet_address, token_mint, token_launch, wallet_activity),
        ]

        if all_buyers:
            tasks.append(
                self.detect_telegram_alpha(wallet_address, token_mint, token_launch, all_buyers)
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, InsiderDetection):
                detections.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Detection error: {result}")

        return detections

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _calculate_severity(self, confidence: float) -> str:
        """Calculate severity level from confidence."""
        if confidence >= 0.9:
            return "CRITICAL"
        elif confidence >= 0.8:
            return "HIGH"
        elif confidence >= 0.7:
            return "MEDIUM"
        else:
            return "LOW"

    async def _find_connected_wallets(self, wallet_address: str) -> Set[str]:
        """Find wallets connected via funding."""
        connected = set()

        try:
            if self.redis:
                # Check cached connections
                cache_key = f"wallet_connections:{wallet_address}"
                cached = await self.redis.smembers(cache_key)
                if cached:
                    return set(cached)

            if self.db:
                async with self.db.connection() as conn:
                    # Find wallets that funded this wallet or were funded by it
                    query = """
                        SELECT DISTINCT 
                            CASE WHEN source = $1 THEN destination ELSE source END as connected
                        FROM transactions
                        WHERE (source = $1 OR destination = $1)
                        AND amount > 0.1  -- Significant transfers only
                        LIMIT 100
                    """
                    async with conn.cursor() as cur:
                        await cur.execute(query, (wallet_address,))
                        rows = await cur.fetchall()
                        connected = {row[0] for row in rows if row[0]}

            # Cache result
            if self.redis and connected:
                cache_key = f"wallet_connections:{wallet_address}"
                await self.redis.sadd(cache_key, *connected)
                await self.redis.expire(cache_key, 3600)  # 1 hour TTL

        except Exception as e:
            logger.warning(f"Failed to find connected wallets: {e}")

        return connected

    async def _check_pre_launch_activity(self, wallet_address: str, token_launch: TokenLaunchData) -> bool:
        """Check for suspicious pre-launch activity."""
        try:
            if self.db:
                async with self.db.connection() as conn:
                    # Check for activity with creator before launch
                    query = """
                        SELECT COUNT(*) FROM transactions
                        WHERE (source = $1 AND destination = $2)
                           OR (source = $2 AND destination = $1)
                        AND timestamp < $3
                    """
                    async with conn.cursor() as cur:
                        await cur.execute(query, (
                            wallet_address,
                            token_launch.creator,
                            token_launch.launch_time
                        ))
                        row = await cur.fetchone()
                        return row[0] > 0 if row else False
        except Exception:
            pass
        return False

    async def _check_token_allocation(self, wallet_address: str, token_mint: str) -> float:
        """Check wallet's percentage of token supply."""
        try:
            if self.redis:
                cache_key = f"token_allocation:{token_mint}:{wallet_address}"
                cached = await self.redis.get(cache_key)
                if cached:
                    return float(cached)

            # Would query token accounts here
            # For now return 0
            return 0.0
        except Exception:
            return 0.0

    async def _find_funding_sources(self, wallet_address: str) -> Set[str]:
        """Find wallets that funded this wallet."""
        sources = set()

        try:
            if self.db:
                async with self.db.connection() as conn:
                    query = """
                        SELECT DISTINCT source FROM transactions
                        WHERE destination = $1
                        AND amount > 0.1
                        LIMIT 50
                    """
                    async with conn.cursor() as cur:
                        await cur.execute(query, (wallet_address,))
                        rows = await cur.fetchall()
                        sources = {row[0] for row in rows if row[0]}
        except Exception:
            pass

        return sources

    async def _check_coordination_history(
        self,
        wallet_address: str,
        related_wallets: List[str]
    ) -> int:
        """Check how many tokens these wallets have coordinated on."""
        try:
            if self.db and related_wallets:
                async with self.db.connection() as conn:
                    # Find tokens where both wallet and related wallets bought early
                    query = """
                        SELECT COUNT(DISTINCT token_mint) FROM trades
                        WHERE wallet_address = $1
                        AND token_mint IN (
                            SELECT token_mint FROM trades
                            WHERE wallet_address = ANY($2)
                        )
                    """
                    async with conn.cursor() as cur:
                        await cur.execute(query, (wallet_address, related_wallets))
                        row = await cur.fetchone()
                        return row[0] if row else 0
        except Exception:
            pass
        return 0

    def _generate_group_id(self, wallet: str, related: List[str]) -> str:
        """Generate unique ID for a coordination group."""
        import hashlib
        all_wallets = sorted([wallet] + related)
        data = ",".join(all_wallets[:5])  # Use first 5 wallets
        return hashlib.md5(data.encode()).hexdigest()[:12]

    def _calculate_timing_variance(self, wallet_activity: WalletActivity) -> float:
        """Calculate variance in transaction timing."""
        if len(wallet_activity.transactions) < 3:
            return 1.0  # Not enough data

        try:
            # Calculate time differences between transactions
            times = []
            for tx in wallet_activity.transactions:
                if "timestamp" in tx:
                    times.append(tx["timestamp"])

            if len(times) < 3:
                return 1.0

            times.sort()
            diffs = [times[i+1] - times[i] for i in range(len(times)-1)]

            if not diffs:
                return 1.0

            mean_diff = sum(diffs) / len(diffs)
            if mean_diff == 0:
                return 0.0

            variance = sum((d - mean_diff) ** 2 for d in diffs) / len(diffs)
            # Normalize by mean
            return (variance ** 0.5) / mean_diff

        except Exception:
            return 1.0

    async def _count_recent_snipes(self, wallet_address: str) -> int:
        """Count how many tokens wallet has sniped recently."""
        try:
            if self.redis:
                cache_key = f"snipe_count:{wallet_address}"
                cached = await self.redis.get(cache_key)
                if cached:
                    return int(cached)

            if self.db:
                async with self.db.connection() as conn:
                    # Count tokens bought within 60s of launch in last 24h
                    query = """
                        SELECT COUNT(DISTINCT t.token_mint)
                        FROM trades t
                        JOIN token_launches l ON t.token_mint = l.mint
                        WHERE t.wallet_address = $1
                        AND t.trade_type = 'buy'
                        AND t.timestamp - l.launch_time < INTERVAL '60 seconds'
                        AND t.timestamp > NOW() - INTERVAL '24 hours'
                    """
                    async with conn.cursor() as cur:
                        await cur.execute(query, (wallet_address,))
                        row = await cur.fetchone()
                        count = row[0] if row else 0

                        # Cache result
                        if self.redis:
                            await self.redis.setex(
                                f"snipe_count:{wallet_address}",
                                300,  # 5 min TTL
                                str(count)
                            )

                        return count
        except Exception:
            pass
        return 0

    async def _check_mev_patterns(self, wallet_address: str, token_mint: str) -> float:
        """Check for MEV/sandwich attack patterns."""
        try:
            if self.db:
                async with self.db.connection() as conn:
                    # Check for sandwich pattern: buy -> victim tx -> sell in same block
                    query = """
                        SELECT COUNT(*) FROM (
                            SELECT slot, 
                                   LAG(trade_type) OVER (ORDER BY slot, tx_index) as prev_type,
                                   trade_type,
                                   LEAD(trade_type) OVER (ORDER BY slot, tx_index) as next_type
                            FROM trades
                            WHERE wallet_address = $1
                            AND token_mint = $2
                        ) sub
                        WHERE prev_type = 'buy' AND next_type = 'sell'
                    """
                    async with conn.cursor() as cur:
                        await cur.execute(query, (wallet_address, token_mint))
                        row = await cur.fetchone()
                        sandwich_count = row[0] if row else 0

                        # Score based on sandwich count
                        if sandwich_count >= 5:
                            return 0.9
                        elif sandwich_count >= 3:
                            return 0.7
                        elif sandwich_count >= 1:
                            return 0.5
        except Exception:
            pass
        return 0.0

    def get_stats(self) -> Dict[str, Any]:
        """Get detection statistics."""
        return {
            **self.stats,
            "known_dev_wallets": len(self.known_dev_wallets),
            "known_sniper_bots": len(self.known_sniper_bots),
            "telegram_groups": len(self.telegram_groups)
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_detectors_instance: Optional[GodModeInsiderDetectors] = None

def get_insider_detectors(redis_client=None, db_pool=None) -> GodModeInsiderDetectors:
    """Get singleton insider detectors."""
    global _detectors_instance
    if _detectors_instance is None:
        _detectors_instance = GodModeInsiderDetectors(redis_client, db_pool)
    return _detectors_instance
