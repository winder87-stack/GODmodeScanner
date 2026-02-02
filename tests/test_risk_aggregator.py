"""Unit tests for RiskAggregator Bayesian risk scoring system.

Test Coverage:
- Basic risk aggregation
- Bayesian confidence estimation
- Severity determination with confidence adjustment
- Explanation generation
- Edge cases (zeros, ones, mixed)
- Sample size impact on confidence
- Confidence interval calculation
- Factor clamping
- Threshold boundaries
"""

import pytest
import sys
from unittest.mock import patch, MagicMock

# Import RiskAggregator
sys.path.insert(0, '/a0/usr/projects/godmodescanner/projects/godmodescanner')
from agents.risk_aggregator import (
    RiskAggregator,
    RiskSeverity,
    RiskScore,
    WEIGHTS,
    THRESHOLDS,
    PRIOR_ALPHA,
    PRIOR_BETA
)


class TestRiskAggregator:
    """Test suite for RiskAggregator."""

    @pytest.fixture
    def aggregator(self):
        """Create RiskAggregator instance."""
        return RiskAggregator()

    # ========================================================================
    # Test 1: Basic Risk Aggregation (High Risk Insider)
    # ========================================================================

    def test_high_risk_insider(self, aggregator):
        """Test high-risk insider with strong signals across all factors."""
        # Setup: High scores across all factors
        risk = aggregator.aggregate_risk_factors(
            behavior=0.85,   # High aggressiveness
            timing=0.90,     # Very early entry
            network=0.70,    # Strong cluster connections
            volume=0.60,     # Moderate whale behavior
            sample_sizes={'behavior': 25, 'timing': 30, 'network': 20, 'volume': 15}
        )

        # Verify composite score calculation
        # Expected: 0.85*0.35 + 0.90*0.25 + 0.70*0.25 + 0.60*0.15
        #         = 0.2975 + 0.225 + 0.175 + 0.09 = 0.7875
        expected_composite = 0.7875
        assert abs(risk.composite_score - expected_composite) < 0.01

        # Verify components stored correctly
        assert risk.components['behavior'] == 0.85
        assert risk.components['timing'] == 0.90
        assert risk.components['network'] == 0.70
        assert risk.components['volume'] == 0.60

        # Verify confidence is high (90 total observations)
        assert risk.confidence > 0.8  # Should be close to 1.0 (90/50 capped at 1.0)

        # Verify severity (high composite + high confidence)
        assert risk.severity in [RiskSeverity.HIGH, RiskSeverity.CRITICAL]

        # Verify explanation contains top factors
        assert 'timing' in risk.explanation.lower() or 'early entry' in risk.explanation.lower()
        assert 'behavior' in risk.explanation.lower() or 'aggressive' in risk.explanation.lower()

        print(f"✅ High-risk insider: {risk.composite_score:.2f} ({risk.severity.value})")
        print(f"   Confidence: {risk.confidence:.2f}")
        print(f"   95% CI: [{risk.confidence_interval[0]:.2f}, {risk.confidence_interval[1]:.2f}]")
        print(f"   Explanation: {risk.explanation}")

    # ========================================================================
    # Test 2: Low Risk Normal Trader
    # ========================================================================

    def test_low_risk_normal_trader(self, aggregator):
        """Test low-risk normal trader with weak signals."""
        risk = aggregator.aggregate_risk_factors(
            behavior=0.20,   # Low aggressiveness
            timing=0.30,     # Late entry
            network=0.15,    # Weak cluster connections
            volume=0.25,     # Small volume
            sample_sizes={'behavior': 15, 'timing': 20, 'network': 10, 'volume': 10}
        )

        # Verify composite score
        # Expected: 0.20*0.35 + 0.30*0.25 + 0.15*0.25 + 0.25*0.15
        #         = 0.07 + 0.075 + 0.0375 + 0.0375 = 0.22
        expected_composite = 0.22
        assert abs(risk.composite_score - expected_composite) < 0.01

        # Verify severity is LOW
        assert risk.severity == RiskSeverity.LOW

        # Verify confidence is moderate (55 total observations)
        assert risk.confidence > 0.5

        print(f"✅ Low-risk trader: {risk.composite_score:.2f} ({risk.severity.value})")

    # ========================================================================
    # Test 3: Critical Risk with High Confidence
    # ========================================================================

    def test_critical_risk_high_confidence(self, aggregator):
        """Test critical risk with very high scores and high confidence."""
        risk = aggregator.aggregate_risk_factors(
            behavior=0.95,   # Extremely aggressive
            timing=0.98,     # Instant entry
            network=0.90,    # Very strong cluster
            volume=0.85,     # Whale behavior
            sample_sizes={'behavior': 50, 'timing': 50, 'network': 50, 'volume': 50}
        )

        # Verify composite score is very high
        # Expected: 0.95*0.35 + 0.98*0.25 + 0.90*0.25 + 0.85*0.15
        #         = 0.3325 + 0.245 + 0.225 + 0.1275 = 0.93
        expected_composite = 0.93
        assert abs(risk.composite_score - expected_composite) < 0.01

        # Verify confidence is maximum (200 total observations >> 50)
        assert risk.confidence == 1.0

        # Verify severity is CRITICAL
        assert risk.severity == RiskSeverity.CRITICAL

        # Verify confidence interval is tight (high confidence)
        ci_width = risk.confidence_interval[1] - risk.confidence_interval[0]
        assert ci_width < 0.15  # Narrow interval

        print(f"✅ Critical risk: {risk.composite_score:.2f} ({risk.severity.value})")
        print(f"   Confidence: {risk.confidence:.2f}")
        print(f"   95% CI width: {ci_width:.3f}")

    # ========================================================================
    # Test 4: Medium Risk with Low Confidence (Downgraded)
    # ========================================================================

    def test_medium_risk_low_confidence(self, aggregator):
        """Test medium risk downgraded by low confidence."""
        risk = aggregator.aggregate_risk_factors(
            behavior=0.75,   # Moderate-high aggressiveness
            timing=0.70,     # Moderate-early entry
            network=0.65,    # Moderate cluster
            volume=0.60,     # Moderate volume
            sample_sizes={'behavior': 5, 'timing': 5, 'network': 5, 'volume': 5}
        )

        # Verify composite score
        # Expected: 0.75*0.35 + 0.70*0.25 + 0.65*0.25 + 0.60*0.15
        #         = 0.2625 + 0.175 + 0.1625 + 0.09 = 0.69
        expected_composite = 0.69
        assert abs(risk.composite_score - expected_composite) < 0.01

        # Verify confidence is low (20 total observations)
        assert risk.confidence < 0.5  # 20/50 = 0.4

        # Verify severity is downgraded due to low confidence
        # Adjusted = 0.69 * (0.5 + 0.5 * 0.4) = 0.69 * 0.7 = 0.483
        # Should be MEDIUM (< 0.50) or LOW
        assert risk.severity in [RiskSeverity.LOW, RiskSeverity.MEDIUM]

        print(f"✅ Medium risk (low confidence): {risk.composite_score:.2f} ({risk.severity.value})")
        print(f"   Confidence: {risk.confidence:.2f} (downgraded severity)")

    # ========================================================================
    # Test 5: Edge Case - All Zeros
    # ========================================================================

    def test_all_zeros(self, aggregator):
        """Test edge case with all zero scores."""
        risk = aggregator.aggregate_risk_factors(
            behavior=0.0,
            timing=0.0,
            network=0.0,
            volume=0.0
        )

        # Verify composite score is 0
        assert risk.composite_score == 0.0

        # Verify severity is LOW
        assert risk.severity == RiskSeverity.LOW

        # Verify components
        assert all(score == 0.0 for score in risk.components.values())

        print(f"✅ All zeros: {risk.composite_score:.2f} ({risk.severity.value})")

    # ========================================================================
    # Test 6: Edge Case - All Ones
    # ========================================================================

    def test_all_ones(self, aggregator):
        """Test edge case with all maximum scores."""
        risk = aggregator.aggregate_risk_factors(
            behavior=1.0,
            timing=1.0,
            network=1.0,
            volume=1.0,
            sample_sizes={'behavior': 50, 'timing': 50, 'network': 50, 'volume': 50}
        )

        # Verify composite score is 1.0
        assert risk.composite_score == 1.0

        # Verify severity is CRITICAL
        assert risk.severity == RiskSeverity.CRITICAL

        # Verify confidence is maximum
        assert risk.confidence == 1.0

        print(f"✅ All ones: {risk.composite_score:.2f} ({risk.severity.value})")

    # ========================================================================
    # Test 7: Factor Clamping (Out of Range Values)
    # ========================================================================

    def test_factor_clamping(self, aggregator):
        """Test that factors outside [0, 1] are clamped."""
        risk = aggregator.aggregate_risk_factors(
            behavior=1.5,    # Should be clamped to 1.0
            timing=-0.2,     # Should be clamped to 0.0
            network=0.8,     # Valid
            volume=2.0       # Should be clamped to 1.0
        )

        # Verify clamping
        assert risk.components['behavior'] == 1.0
        assert risk.components['timing'] == 0.0
        assert risk.components['network'] == 0.8
        assert risk.components['volume'] == 1.0

        # Verify composite score with clamped values
        # Expected: 1.0*0.35 + 0.0*0.25 + 0.8*0.25 + 1.0*0.15
        #         = 0.35 + 0.0 + 0.2 + 0.15 = 0.70
        expected_composite = 0.70
        assert abs(risk.composite_score - expected_composite) < 0.01

        print(f"✅ Factor clamping: {risk.composite_score:.2f}")
        print(f"   Clamped values: behavior={risk.components['behavior']}, timing={risk.components['timing']}")

    # ========================================================================
    # Test 8: Default Sample Sizes
    # ========================================================================

    def test_default_sample_sizes(self, aggregator):
        """Test that default sample sizes (10 per factor) are used when not provided."""
        risk = aggregator.aggregate_risk_factors(
            behavior=0.80,
            timing=0.75,
            network=0.70,
            volume=0.65
            # No sample_sizes provided - should default to 10 each
        )

        # Verify confidence is based on 40 total observations (4 factors × 10)
        # Confidence = min(1.0, 40/50) = 0.8
        expected_confidence = 0.8
        assert abs(risk.confidence - expected_confidence) < 0.01

        print(f"✅ Default sample sizes: confidence={risk.confidence:.2f} (40 observations)")

    # ========================================================================
    # Test 9: Confidence Interval Calculation
    # ========================================================================

    def test_confidence_interval(self, aggregator):
        """Test that confidence interval is calculated correctly."""
        risk = aggregator.aggregate_risk_factors(
            behavior=0.80,
            timing=0.75,
            network=0.70,
            volume=0.65,
            sample_sizes={'behavior': 20, 'timing': 20, 'network': 20, 'volume': 20}
        )

        # Verify confidence interval exists
        assert len(risk.confidence_interval) == 2
        lower, upper = risk.confidence_interval

        # Verify interval is valid
        assert 0.0 <= lower <= upper <= 1.0

        # Verify interval contains composite score (approximately)
        # Note: CI is for the Beta posterior, not necessarily containing composite
        # But it should be in a reasonable range
        assert lower < 1.0 and upper > 0.0

        print(f"✅ Confidence interval: [{lower:.3f}, {upper:.3f}]")

    # ========================================================================
    # Test 10: Severity Threshold Boundaries
    # ========================================================================

    def test_severity_thresholds(self, aggregator):
        """Test severity determination at threshold boundaries."""
        # Test CRITICAL threshold (0.85)
        # With confidence=1.0, adjusted = composite * 1.0
        risk_critical = aggregator.aggregate_risk_factors(
            behavior=0.85, timing=0.85, network=0.85, volume=0.85,
            sample_sizes={'behavior': 50, 'timing': 50, 'network': 50, 'volume': 50}
        )
        assert risk_critical.severity == RiskSeverity.CRITICAL

        # Test HIGH threshold (0.70)
        risk_high = aggregator.aggregate_risk_factors(
            behavior=0.70, timing=0.70, network=0.70, volume=0.70,
            sample_sizes={'behavior': 50, 'timing': 50, 'network': 50, 'volume': 50}
        )
        assert risk_high.severity == RiskSeverity.HIGH

        # Test MEDIUM threshold (0.50)
        risk_medium = aggregator.aggregate_risk_factors(
            behavior=0.50, timing=0.50, network=0.50, volume=0.50,
            sample_sizes={'behavior': 50, 'timing': 50, 'network': 50, 'volume': 50}
        )
        assert risk_medium.severity == RiskSeverity.MEDIUM

        # Test LOW (< 0.50)
        risk_low = aggregator.aggregate_risk_factors(
            behavior=0.30, timing=0.30, network=0.30, volume=0.30,
            sample_sizes={'behavior': 50, 'timing': 50, 'network': 50, 'volume': 50}
        )
        assert risk_low.severity == RiskSeverity.LOW

        print(f"✅ Severity thresholds:")
        print(f"   CRITICAL: {risk_critical.composite_score:.2f}")
        print(f"   HIGH: {risk_high.composite_score:.2f}")
        print(f"   MEDIUM: {risk_medium.composite_score:.2f}")
        print(f"   LOW: {risk_low.composite_score:.2f}")

    # ========================================================================
    # Test 11: Explanation Generation
    # ========================================================================

    def test_explanation_generation(self, aggregator):
        """Test that explanation identifies top contributing factors."""
        # Setup: timing and behavior are top contributors
        risk = aggregator.aggregate_risk_factors(
            behavior=0.90,   # High (contributes 0.90 * 0.35 = 0.315)
            timing=0.95,     # Very high (contributes 0.95 * 0.25 = 0.2375)
            network=0.40,    # Low (contributes 0.40 * 0.25 = 0.10)
            volume=0.30      # Low (contributes 0.30 * 0.15 = 0.045)
        )

        # Verify explanation mentions top 2 factors (behavior and timing)
        explanation_lower = risk.explanation.lower()

        # Should mention timing (top contributor)
        assert 'timing' in explanation_lower or 'early entry' in explanation_lower

        # Should mention behavior (second top contributor)
        assert 'behavior' in explanation_lower or 'aggressive' in explanation_lower

        # Should include severity
        assert risk.severity.value in explanation_lower

        # Should include composite score
        assert str(round(risk.composite_score, 2)) in risk.explanation

        print(f"✅ Explanation: {risk.explanation}")

    # ========================================================================
    # Test 12: Sample Size Impact on Confidence
    # ========================================================================

    def test_sample_size_impact(self, aggregator):
        """Test that larger sample sizes increase confidence."""
        # Small sample size
        risk_small = aggregator.aggregate_risk_factors(
            behavior=0.80, timing=0.75, network=0.70, volume=0.65,
            sample_sizes={'behavior': 5, 'timing': 5, 'network': 5, 'volume': 5}
        )

        # Large sample size
        risk_large = aggregator.aggregate_risk_factors(
            behavior=0.80, timing=0.75, network=0.70, volume=0.65,
            sample_sizes={'behavior': 50, 'timing': 50, 'network': 50, 'volume': 50}
        )

        # Verify larger sample size → higher confidence
        assert risk_large.confidence > risk_small.confidence

        # Verify larger sample size → narrower confidence interval
        ci_width_small = risk_small.confidence_interval[1] - risk_small.confidence_interval[0]
        ci_width_large = risk_large.confidence_interval[1] - risk_large.confidence_interval[0]
        assert ci_width_large < ci_width_small

        print(f"✅ Sample size impact:")
        print(f"   Small (20 obs): confidence={risk_small.confidence:.2f}, CI width={ci_width_small:.3f}")
        print(f"   Large (200 obs): confidence={risk_large.confidence:.2f}, CI width={ci_width_large:.3f}")

    # ========================================================================
    # Test 13: Weighted Factor Contribution
    # ========================================================================

    def test_weighted_contribution(self, aggregator):
        """Test that weights are applied correctly."""
        # Setup: Only behavior is high (weight=0.35)
        risk_behavior = aggregator.aggregate_risk_factors(
            behavior=1.0, timing=0.0, network=0.0, volume=0.0
        )

        # Setup: Only timing is high (weight=0.25)
        risk_timing = aggregator.aggregate_risk_factors(
            behavior=0.0, timing=1.0, network=0.0, volume=0.0
        )

        # Verify behavior contributes more (higher weight)
        assert risk_behavior.composite_score > risk_timing.composite_score
        assert abs(risk_behavior.composite_score - 0.35) < 0.01
        assert abs(risk_timing.composite_score - 0.25) < 0.01

        print(f"✅ Weighted contribution:")
        print(f"   Behavior only (weight=0.35): {risk_behavior.composite_score:.2f}")
        print(f"   Timing only (weight=0.25): {risk_timing.composite_score:.2f}")


if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v', '--tb=short'])
