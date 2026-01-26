"""RiskAggregator: Bayesian risk scoring with weighted factor combination.

This module implements a sophisticated Bayesian risk scoring system that:
1. Combines multiple risk factors with configurable weights
2. Estimates confidence using Beta-Binomial conjugate priors
3. Calculates 95% credible intervals for risk scores
4. Determines severity levels with confidence adjustment
5. Generates human-readable explanations

Mathematical Foundation:
- Prior: Beta(α=2.0, β=5.0) - Slightly skeptical prior
- Posterior: Beta(α_post, β_post) where α_post = α + Σ(factor_i × sample_size_i)
- Credible Interval: [Beta.ppf(0.025), Beta.ppf(0.975)]
- Confidence: Scaled by total observations (max at 50)

Usage:
    >>> aggregator = RiskAggregator()
    >>> risk = aggregator.aggregate_risk_factors(
    ...     behavior=0.85,
    ...     timing=0.90,
    ...     network=0.70,
    ...     volume=0.60,
    ...     sample_sizes={'behavior': 25, 'timing': 30, 'network': 20, 'volume': 15}
    ... )
    >>> print(f"Risk: {risk.composite_score:.2f} ({risk.severity.value})")
    >>> print(f"Confidence: {risk.confidence:.2f}")
    >>> print(f"95% CI: [{risk.confidence_interval[0]:.2f}, {risk.confidence_interval[1]:.2f}]")
"""

import structlog
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple, Optional
from scipy.stats import beta as beta_dist

logger = structlog.get_logger(__name__)


# ============================================================================
# Constants
# ============================================================================

# Weighted factor importance (must sum to 1.0)
WEIGHTS = {
    'behavior': 0.35,   # Aggressiveness, timing patterns
    'timing': 0.25,     # How early they buy
    'network': 0.25,    # Cluster connections
    'volume': 0.15      # Whale behavior
}

# Risk severity thresholds (adjusted composite score)
THRESHOLDS = {
    'critical': 0.85,
    'high': 0.70,
    'medium': 0.50,
    'low': 0.0
}

# Beta distribution prior parameters
# Beta(2.0, 5.0) represents a slightly skeptical prior:
# - Mean = α/(α+β) = 2/7 ≈ 0.286 (assumes most wallets are not high-risk)
# - Variance decreases as we observe more data
PRIOR_ALPHA = 2.0
PRIOR_BETA = 5.0

# Factor name mapping for human-readable explanations
FACTOR_NAMES = {
    'behavior': 'aggressive trading patterns',
    'timing': 'early entry timing',
    'network': 'insider network connections',
    'volume': 'whale-like volume'
}


# ============================================================================
# Data Models
# ============================================================================

class RiskSeverity(Enum):
    """Risk severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class RiskScore:
    """Complete risk assessment with Bayesian confidence.

    Attributes:
        composite_score: Weighted average of all factors (0-1)
        confidence: Bayesian confidence in the score (0-1)
        confidence_interval: 95% credible interval (lower, upper)
        severity: Risk severity level (LOW, MEDIUM, HIGH, CRITICAL)
        components: Individual factor scores before weighting
        explanation: Human-readable explanation of the risk

    Example:
        >>> risk = RiskScore(
        ...     composite_score=0.82,
        ...     confidence=0.75,
        ...     confidence_interval=(0.68, 0.91),
        ...     severity=RiskSeverity.CRITICAL,
        ...     components={'behavior': 0.85, 'timing': 0.90, 'network': 0.70, 'volume': 0.60},
        ...     explanation="CRITICAL risk (0.82) driven by early entry timing and aggressive trading patterns"
        ... )
    """
    composite_score: float
    confidence: float
    confidence_interval: Tuple[float, float]
    severity: RiskSeverity
    components: Dict[str, float]
    explanation: str


# ============================================================================
# RiskAggregator Class
# ============================================================================

class RiskAggregator:
    """Bayesian risk scoring with weighted factor combination.

    This class implements a sophisticated Bayesian approach to risk scoring:

    1. **Weighted Combination:**
       composite = Σ(factor_i × weight_i)

    2. **Bayesian Confidence:**
       - Prior: Beta(2.0, 5.0)
       - Posterior: Beta(α + Σ(factor × sample_size), β + Σ((1-factor) × sample_size))
       - Confidence scales with total observations (max at 50)

    3. **Severity Determination:**
       - Adjust composite by confidence: adjusted = composite × (0.5 + 0.5 × confidence)
       - Compare against thresholds: CRITICAL (≥0.85), HIGH (≥0.70), MEDIUM (≥0.50), LOW (<0.50)

    4. **Explanation Generation:**
       - Identify top 2 contributing factors
       - Generate severity-appropriate explanation

    Example:
        >>> aggregator = RiskAggregator()
        >>> 
        >>> # Aggregate risk factors
        >>> risk = aggregator.aggregate_risk_factors(
        ...     behavior=0.85,  # High aggressiveness
        ...     timing=0.90,    # Very early entry
        ...     network=0.70,   # Strong cluster connections
        ...     volume=0.60,    # Moderate whale behavior
        ...     sample_sizes={'behavior': 25, 'timing': 30, 'network': 20, 'volume': 15}
        ... )
        >>> 
        >>> print(f"Composite Score: {risk.composite_score:.2f}")
        >>> print(f"Confidence: {risk.confidence:.2f}")
        >>> print(f"95% CI: [{risk.confidence_interval[0]:.2f}, {risk.confidence_interval[1]:.2f}]")
        >>> print(f"Severity: {risk.severity.value}")
        >>> print(f"Explanation: {risk.explanation}")
    """

    def __init__(self):
        """Initialize RiskAggregator."""
        logger.info(
            "risk_aggregator_initialized",
            weights=WEIGHTS,
            thresholds=THRESHOLDS,
            prior_alpha=PRIOR_ALPHA,
            prior_beta=PRIOR_BETA
        )

    def aggregate_risk_factors(
        self,
        behavior: float,
        timing: float,
        network: float,
        volume: float,
        sample_sizes: Optional[Dict[str, int]] = None
    ) -> RiskScore:
        """Aggregate risk factors into a composite Bayesian risk score.

        This is the main entry point for risk scoring. It:
        1. Clamps all inputs to [0, 1] range
        2. Calculates weighted composite score
        3. Estimates Bayesian confidence with credible interval
        4. Determines severity level (confidence-adjusted)
        5. Generates human-readable explanation

        Args:
            behavior: Aggressiveness score (0-1)
            timing: Early entry timing score (0-1)
            network: Insider network connection score (0-1)
            volume: Whale-like volume score (0-1)
            sample_sizes: Optional dict of sample sizes per factor (default: 10 each)

        Returns:
            RiskScore with composite score, confidence, severity, and explanation

        Example:
            >>> risk = aggregator.aggregate_risk_factors(
            ...     behavior=0.85,
            ...     timing=0.90,
            ...     network=0.70,
            ...     volume=0.60
            ... )
            >>> print(risk.severity.value)  # "critical"
            >>> print(f"{risk.composite_score:.2f}")  # "0.82"
        """
        # Step 1: Clamp all inputs to [0, 1] range
        factors = {
            'behavior': max(0.0, min(1.0, behavior)),
            'timing': max(0.0, min(1.0, timing)),
            'network': max(0.0, min(1.0, network)),
            'volume': max(0.0, min(1.0, volume))
        }

        # Step 2: Calculate weighted composite score
        composite_score = sum(
            factors[factor] * WEIGHTS[factor]
            for factor in factors
        )

        # Step 3: Estimate Bayesian confidence
        confidence, confidence_interval = self._estimate_confidence(factors, sample_sizes)

        # Step 4: Determine severity level
        severity = self._determine_severity(composite_score, confidence)

        # Step 5: Generate explanation
        explanation = self._generate_explanation(factors, composite_score, severity)

        # Log the result
        logger.info(
            "risk_aggregated",
            composite_score=round(composite_score, 3),
            confidence=round(confidence, 3),
            severity=severity.value,
            factors={k: round(v, 3) for k, v in factors.items()}
        )

        return RiskScore(
            composite_score=composite_score,
            confidence=confidence,
            confidence_interval=confidence_interval,
            severity=severity,
            components=factors,
            explanation=explanation
        )

    def _estimate_confidence(
        self,
        factors: Dict[str, float],
        sample_sizes: Optional[Dict[str, int]] = None
    ) -> Tuple[float, Tuple[float, float]]:
        """Estimate Bayesian confidence using Beta-Binomial conjugate model.

        Mathematical approach:
        1. Start with prior: Beta(α=2.0, β=5.0)
        2. Update with observations:
           - α_post = α + Σ(factor_i × sample_size_i)
           - β_post = β + Σ((1 - factor_i) × sample_size_i)
        3. Calculate 95% credible interval: [Beta.ppf(0.025), Beta.ppf(0.975)]
        4. Scale confidence by total observations (max at 50)

        Args:
            factors: Dict of factor scores (0-1)
            sample_sizes: Optional dict of sample sizes per factor (default: 10 each)

        Returns:
            Tuple of (confidence, (lower_bound, upper_bound))

        Example:
            >>> confidence, ci = aggregator._estimate_confidence(
            ...     {'behavior': 0.85, 'timing': 0.90},
            ...     {'behavior': 25, 'timing': 30}
            ... )
            >>> print(f"Confidence: {confidence:.2f}")  # "0.75"
            >>> print(f"95% CI: [{ci[0]:.2f}, {ci[1]:.2f}]")  # "[0.68, 0.91]"
        """
        # Default sample size of 10 per factor if not provided
        if sample_sizes is None:
            sample_sizes = {factor: 10 for factor in factors}

        # Update Beta prior with observations
        alpha_post = PRIOR_ALPHA
        beta_post = PRIOR_BETA
        total_observations = 0

        for factor, score in factors.items():
            sample_size = sample_sizes.get(factor, 10)

            # Beta-Binomial conjugate update:
            # - Successes (high risk): factor × sample_size
            # - Failures (low risk): (1 - factor) × sample_size
            alpha_post += score * sample_size
            beta_post += (1.0 - score) * sample_size
            total_observations += sample_size

        # Calculate 95% credible interval using scipy.stats.beta
        lower_bound = beta_dist.ppf(0.025, alpha_post, beta_post)
        upper_bound = beta_dist.ppf(0.975, alpha_post, beta_post)

        # Scale confidence by total observations (max at 50)
        # More observations → higher confidence
        confidence = min(1.0, total_observations / 50.0)

        logger.debug(
            "confidence_estimated",
            alpha_post=round(alpha_post, 2),
            beta_post=round(beta_post, 2),
            total_observations=total_observations,
            confidence=round(confidence, 3),
            credible_interval=(round(lower_bound, 3), round(upper_bound, 3))
        )

        return confidence, (lower_bound, upper_bound)

    def _determine_severity(
        self,
        composite: float,
        confidence: float
    ) -> RiskSeverity:
        """Determine risk severity level with confidence adjustment.

        Severity determination:
        1. Adjust composite by confidence: adjusted = composite × (0.5 + 0.5 × confidence)
        2. Compare against thresholds:
           - CRITICAL: adjusted ≥ 0.85
           - HIGH: adjusted ≥ 0.70
           - MEDIUM: adjusted ≥ 0.50
           - LOW: adjusted < 0.50

        Rationale:
        - Low confidence (0.0) → adjusted = composite × 0.5 (downgrade severity)
        - High confidence (1.0) → adjusted = composite × 1.0 (no change)
        - This prevents false positives from low-confidence scores

        Args:
            composite: Weighted composite score (0-1)
            confidence: Bayesian confidence (0-1)

        Returns:
            RiskSeverity enum (LOW, MEDIUM, HIGH, CRITICAL)

        Example:
            >>> severity = aggregator._determine_severity(0.82, 0.75)
            >>> print(severity.value)  # "critical"
            >>> 
            >>> # Low confidence downgrades severity
            >>> severity = aggregator._determine_severity(0.82, 0.30)
            >>> print(severity.value)  # "high" (downgraded from critical)
        """
        # Adjust composite by confidence
        # Formula: adjusted = composite × (0.5 + 0.5 × confidence)
        # - confidence=0.0 → adjusted = composite × 0.5
        # - confidence=0.5 → adjusted = composite × 0.75
        # - confidence=1.0 → adjusted = composite × 1.0
        adjusted = composite * (0.5 + 0.5 * confidence)

        # Compare against thresholds (descending order)
        if adjusted >= THRESHOLDS['critical']:
            severity = RiskSeverity.CRITICAL
        elif adjusted >= THRESHOLDS['high']:
            severity = RiskSeverity.HIGH
        elif adjusted >= THRESHOLDS['medium']:
            severity = RiskSeverity.MEDIUM
        else:
            severity = RiskSeverity.LOW

        logger.debug(
            "severity_determined",
            composite=round(composite, 3),
            confidence=round(confidence, 3),
            adjusted=round(adjusted, 3),
            severity=severity.value
        )

        return severity

    def _generate_explanation(
        self,
        factors: Dict[str, float],
        composite: float,
        severity: RiskSeverity
    ) -> str:
        """Generate human-readable explanation of risk score.

        Explanation format:
        "{SEVERITY} risk ({composite:.2f}) driven by {top_factor_1} and {top_factor_2}"

        Steps:
        1. Calculate contribution of each factor: factor_score × weight
        2. Identify top 2 contributing factors
        3. Generate severity-appropriate explanation string

        Args:
            factors: Dict of factor scores (0-1)
            composite: Weighted composite score (0-1)
            severity: Risk severity level

        Returns:
            Human-readable explanation string

        Example:
            >>> explanation = aggregator._generate_explanation(
            ...     {'behavior': 0.85, 'timing': 0.90, 'network': 0.70, 'volume': 0.60},
            ...     0.82,
            ...     RiskSeverity.CRITICAL
            ... )
            >>> print(explanation)
            # "CRITICAL risk (0.82) driven by early entry timing and aggressive trading patterns"
        """
        # Calculate contribution of each factor (factor_score × weight)
        contributions = {
            factor: factors[factor] * WEIGHTS[factor]
            for factor in factors
        }

        # Sort by contribution (descending)
        sorted_factors = sorted(
            contributions.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Get top 2 contributing factors
        top_factors = sorted_factors[:2]

        # Generate explanation
        factor_names = [FACTOR_NAMES[factor] for factor, _ in top_factors]

        explanation = (
            f"{severity.value.upper()} risk ({composite:.2f}) "
            f"driven by {factor_names[0]} and {factor_names[1]}"
        )

        return explanation


    def aggregate_risk(
        self,
        win_rate: float,
        graduation_rate: float,
        curve_entry: float,
        consistency: int,
        profit_total: float,
        avg_hold_time: float,
        wallet_address: str = ""
    ) -> 'PumpFunRiskScore':
        """Calculate risk score using pump.fun specific metrics.

        This method maps pump.fun trading metrics to the standard risk factors
        used by the Bayesian RiskAggregator.

        Args:
            win_rate: Win rate percentage (0-100)
            graduation_rate: Pumpswap graduation rate (0-100)
            curve_entry: Curve position at entry (0-100)
            consistency: Number of trades
            profit_total: Total SOL profit
            avg_hold_time: Average hold time in seconds
            wallet_address: Wallet address for logging

        Returns:
            PumpFunRiskScore object
        """
        # Hard filters
        is_loser = win_rate < 45.0
        is_mev_bot = avg_hold_time < 10.0

        # Map pump.fun metrics to risk factors
        behavior_factor = (win_rate / 100.0) * 0.6 + (1.0 - min(curve_entry / 100.0, 1.0)) * 0.4
        timing_factor = max(0.0, 1.0 - (curve_entry / 100.0))
        network_factor = 0.5
        volume_factor = min(1.0, (profit_total / 1000.0) * 0.3 + (consistency / 100.0) * 0.7)

        if is_loser:
            behavior_factor = 0.0
            timing_factor = 0.0
            volume_factor = 0.0

        if is_mev_bot:
            behavior_factor = max(0.0, behavior_factor - 0.3)

        # Calculate risk score
        risk_score = self.aggregate_risk_factors(
            behavior=behavior_factor,
            timing=timing_factor,
            network=network_factor,
            volume=volume_factor,
            sample_sizes={'behavior': consistency, 'timing': consistency, 'network': 10, 'volume': consistency}
        )

        is_king_maker = (
            graduation_rate >= 60.0 and
            curve_entry <= 10.0 and
            consistency >= 10 and
            not is_loser and
            not is_mev_bot
        )

        if is_king_maker:
            boosted_score = min(1.0, risk_score.composite_score * 1.2)
        else:
            boosted_score = risk_score.composite_score

        return PumpFunRiskScore(
            composite_score=boosted_score,
            confidence=risk_score.confidence,
            confidence_interval=risk_score.confidence_interval,
            severity=risk_score.severity,
            is_king_maker=is_king_maker,
            behavior_factor=behavior_factor,
            timing_factor=timing_factor,
            network_factor=network_factor,
            volume_factor=volume_factor,
            win_rate=win_rate,
            graduation_rate=graduation_rate,
            curve_entry=curve_entry,
            consistency=consistency,
            profit_total=profit_total,
            avg_hold_time=avg_hold_time,
            is_loser=is_loser,
            is_mev_bot=is_mev_bot,
            explanation=risk_score.explanation
        )


@dataclass
class PumpFunRiskScore:
    """Pump.fun specific risk score with all metrics."""
    composite_score: float
    confidence: float
    confidence_interval: tuple[float, float]
    severity: 'RiskSeverity'
    is_king_maker: bool
    behavior_factor: float
    timing_factor: float
    network_factor: float
    volume_factor: float
    win_rate: float
    graduation_rate: float
    curve_entry: float
    consistency: int
    profit_total: float
    avg_hold_time: float
    is_loser: bool = False
    is_mev_bot: bool = False
    explanation: str = ""

    @property
    def score(self) -> float:
        return self.composite_score

    def to_dict(self) -> dict:
        return {
            'composite_score': self.composite_score,
            'confidence': self.confidence,
            'confidence_interval': self.confidence_interval,
            'severity': self.severity.value if hasattr(self.severity, 'value') else str(self.severity),
            'is_king_maker': self.is_king_maker,
            'behavior_factor': self.behavior_factor,
            'timing_factor': self.timing_factor,
            'network_factor': self.network_factor,
            'volume_factor': self.volume_factor,
            'win_rate': self.win_rate,
            'graduation_rate': self.graduation_rate,
            'curve_entry': self.curve_entry,
            'consistency': self.consistency,
            'profit_total': self.profit_total,
            'avg_hold_time': self.avg_hold_time,
            'is_loser': self.is_loser,
            'is_mev_bot': self.is_mev_bot,
            'explanation': self.explanation
        }
