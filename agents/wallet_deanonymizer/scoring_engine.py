
"""
Cluster Scoring Engine - Risk Assessment for Wallet Clusters
=============================================================

Calculates risk scores for detected wallet clusters based on
multiple factors including structure, behavior, and connections.

Scoring Factors:
- Cluster structure (density, size, connectivity)
- Seed node proximity (distance to known insiders)
- Behavioral patterns (timing, volume, frequency)
- Network topology (hub presence, chain patterns)
- Historical performance (past insider involvement)
"""

import asyncio
import time
import math
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import structlog

try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

logger = structlog.get_logger(__name__)


class RiskLevel(Enum):
    """Risk level classifications."""
    CRITICAL = "critical"   # >= 0.85
    HIGH = "high"           # >= 0.70
    MEDIUM = "medium"       # >= 0.50
    LOW = "low"             # >= 0.30
    MINIMAL = "minimal"     # < 0.30


@dataclass
class ScoringWeights:
    """Configurable weights for scoring factors."""
    # Structure factors (25%)
    cluster_size: float = 0.08
    cluster_density: float = 0.08
    connectivity: float = 0.09

    # Seed proximity factors (30%)
    seed_node_ratio: float = 0.15
    min_seed_distance: float = 0.10
    seed_connection_strength: float = 0.05

    # Behavioral factors (25%)
    timing_correlation: float = 0.10
    volume_anomaly: float = 0.08
    frequency_pattern: float = 0.07

    # Network topology factors (20%)
    hub_presence: float = 0.08
    chain_pattern: float = 0.07
    bidirectional_ratio: float = 0.05

    def validate(self) -> bool:
        """Validate weights sum to 1.0."""
        total = (
            self.cluster_size + self.cluster_density + self.connectivity +
            self.seed_node_ratio + self.min_seed_distance + self.seed_connection_strength +
            self.timing_correlation + self.volume_anomaly + self.frequency_pattern +
            self.hub_presence + self.chain_pattern + self.bidirectional_ratio
        )
        return abs(total - 1.0) < 0.01


@dataclass
class ClusterScore:
    """Detailed score for a wallet cluster."""
    cluster_id: str

    # Overall score
    risk_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.MINIMAL
    confidence: float = 0.0

    # Component scores
    structure_score: float = 0.0
    proximity_score: float = 0.0
    behavioral_score: float = 0.0
    topology_score: float = 0.0

    # Detailed factors
    factors: Dict[str, float] = field(default_factory=dict)

    # Bayesian confidence interval
    confidence_lower: float = 0.0
    confidence_upper: float = 0.0

    # Metadata
    scored_at: float = field(default_factory=time.time)
    scoring_time_ms: float = 0.0

    # Explanation
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "cluster_id": self.cluster_id,
            "risk_score": round(self.risk_score, 4),
            "risk_level": self.risk_level.value,
            "confidence": round(self.confidence, 4),
            "confidence_interval": [
                round(self.confidence_lower, 4),
                round(self.confidence_upper, 4),
            ],
            "component_scores": {
                "structure": round(self.structure_score, 4),
                "proximity": round(self.proximity_score, 4),
                "behavioral": round(self.behavioral_score, 4),
                "topology": round(self.topology_score, 4),
            },
            "factors": {k: round(v, 4) for k, v in self.factors.items()},
            "explanation": self.explanation,
            "scoring_time_ms": round(self.scoring_time_ms, 2),
        }


@dataclass
class ScoringMetrics:
    """Metrics for the scoring engine."""
    total_scored: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0

    avg_score: float = 0.0
    max_score: float = 0.0
    avg_scoring_time_ms: float = 0.0

    last_scored_at: float = 0.0


class ClusterScoringEngine:
    """
    Calculates risk scores for wallet clusters.

    The scoring engine uses a weighted multi-factor approach
    to assess the likelihood that a cluster represents
    coordinated insider activity.

    Features:
    - Configurable scoring weights
    - Bayesian confidence intervals
    - Multiple scoring factors
    - Explainable scoring with factor breakdown
    - Historical calibration support
    """

    # Thresholds for risk levels
    RISK_THRESHOLDS = {
        RiskLevel.CRITICAL: 0.85,
        RiskLevel.HIGH: 0.70,
        RiskLevel.MEDIUM: 0.50,
        RiskLevel.LOW: 0.30,
    }

    def __init__(
        self,
        weights: Optional[ScoringWeights] = None,
        enable_bayesian: bool = True,
        min_confidence: float = 0.5,
    ):
        """
        Initialize the scoring engine.

        Args:
            weights: Custom scoring weights
            enable_bayesian: Enable Bayesian confidence intervals
            min_confidence: Minimum confidence threshold
        """
        self.weights = weights or ScoringWeights()
        self.enable_bayesian = enable_bayesian and SCIPY_AVAILABLE
        self.min_confidence = min_confidence

        # Validate weights
        if not self.weights.validate():
            logger.warning("Scoring weights do not sum to 1.0")

        # Score history for calibration
        self.score_history: List[float] = []

        # Metrics
        self.metrics = ScoringMetrics()

        logger.info(
            "ClusterScoringEngine initialized",
            bayesian=self.enable_bayesian,
            scipy=SCIPY_AVAILABLE,
        )

    async def score_cluster(
        self,
        cluster: Any,  # WalletCluster
        graph_data: Dict[str, Any],
        seed_nodes: Set[str],
        historical_data: Optional[Dict[str, Any]] = None,
    ) -> ClusterScore:
        """
        Calculate risk score for a cluster.

        Args:
            cluster: WalletCluster object
            graph_data: Graph structure data
            seed_nodes: Known insider addresses
            historical_data: Historical performance data

        Returns:
            ClusterScore with detailed breakdown
        """
        start_time = time.time()

        score = ClusterScore(cluster_id=cluster.cluster_id)

        # Calculate component scores
        score.structure_score, structure_factors = await self._score_structure(
            cluster, graph_data
        )
        score.factors.update(structure_factors)

        score.proximity_score, proximity_factors = await self._score_proximity(
            cluster, seed_nodes, graph_data
        )
        score.factors.update(proximity_factors)

        score.behavioral_score, behavioral_factors = await self._score_behavioral(
            cluster, graph_data, historical_data
        )
        score.factors.update(behavioral_factors)

        score.topology_score, topology_factors = await self._score_topology(
            cluster, graph_data
        )
        score.factors.update(topology_factors)

        # Calculate weighted total
        score.risk_score = (
            score.structure_score * 0.25 +
            score.proximity_score * 0.30 +
            score.behavioral_score * 0.25 +
            score.topology_score * 0.20
        )

        # Clamp to [0, 1]
        score.risk_score = max(0.0, min(1.0, score.risk_score))

        # Determine risk level
        score.risk_level = self._determine_risk_level(score.risk_score)

        # Calculate confidence
        score.confidence = self._calculate_confidence(cluster, score)

        # Calculate Bayesian confidence interval
        if self.enable_bayesian:
            score.confidence_lower, score.confidence_upper = self._bayesian_interval(
                score.risk_score, score.confidence
            )
        else:
            # Simple interval
            margin = (1 - score.confidence) * 0.2
            score.confidence_lower = max(0, score.risk_score - margin)
            score.confidence_upper = min(1, score.risk_score + margin)

        # Generate explanation
        score.explanation = self._generate_explanation(score)

        # Record timing
        score.scoring_time_ms = (time.time() - start_time) * 1000

        # Update metrics
        self._update_metrics(score)

        return score

    async def score_clusters_batch(
        self,
        clusters: List[Any],
        graph_data: Dict[str, Any],
        seed_nodes: Set[str],
        historical_data: Optional[Dict[str, Any]] = None,
    ) -> List[ClusterScore]:
        """
        Score multiple clusters in parallel.
        """
        tasks = [
            self.score_cluster(cluster, graph_data, seed_nodes, historical_data)
            for cluster in clusters
        ]
        return await asyncio.gather(*tasks)

    async def _score_structure(
        self,
        cluster: Any,
        graph_data: Dict[str, Any],
    ) -> Tuple[float, Dict[str, float]]:
        """
        Score cluster structure factors.
        """
        factors = {}

        # Cluster size score (larger clusters more suspicious, up to a point)
        size = getattr(cluster, 'size', len(getattr(cluster, 'members', [])))
        if size <= 3:
            size_score = 0.3
        elif size <= 10:
            size_score = 0.5 + (size - 3) * 0.05
        elif size <= 50:
            size_score = 0.85 + (size - 10) * 0.003
        else:
            size_score = 1.0
        factors["cluster_size"] = size_score

        # Density score (denser clusters more suspicious)
        density = getattr(cluster, 'density', 0.0)
        density_score = min(1.0, density * 2)  # Scale up, cap at 1
        factors["cluster_density"] = density_score

        # Connectivity score (average degree)
        avg_degree = getattr(cluster, 'avg_degree', 0.0)
        connectivity_score = min(1.0, avg_degree / 10)  # Normalize
        factors["connectivity"] = connectivity_score

        # Weighted structure score
        structure_score = (
            size_score * self.weights.cluster_size +
            density_score * self.weights.cluster_density +
            connectivity_score * self.weights.connectivity
        ) / (self.weights.cluster_size + self.weights.cluster_density + self.weights.connectivity)

        return structure_score, factors

    async def _score_proximity(
        self,
        cluster: Any,
        seed_nodes: Set[str],
        graph_data: Dict[str, Any],
    ) -> Tuple[float, Dict[str, float]]:
        """
        Score proximity to known insiders.
        """
        factors = {}
        members = getattr(cluster, 'members', set())

        # Seed node ratio (what fraction are known insiders)
        seed_count = getattr(cluster, 'seed_node_count', len(members & seed_nodes))
        seed_ratio = seed_count / max(1, len(members))
        seed_ratio_score = min(1.0, seed_ratio * 5)  # 20% seeds = max score
        factors["seed_node_ratio"] = seed_ratio_score

        # Minimum distance to seed (from graph_data if available)
        min_distance = graph_data.get("min_seed_distance", {}).get(cluster.cluster_id, 999)
        if min_distance == 0:
            distance_score = 1.0  # Contains seed
        elif min_distance == 1:
            distance_score = 0.9  # Direct connection
        elif min_distance == 2:
            distance_score = 0.7  # 2 hops
        elif min_distance <= 3:
            distance_score = 0.5  # 3 hops
        else:
            distance_score = 0.2  # Far from seeds
        factors["min_seed_distance"] = distance_score

        # Seed connection strength (total edges to seeds)
        seed_edges = graph_data.get("seed_edge_count", {}).get(cluster.cluster_id, 0)
        strength_score = min(1.0, seed_edges / 10)  # Normalize
        factors["seed_connection_strength"] = strength_score

        # Weighted proximity score
        proximity_score = (
            seed_ratio_score * self.weights.seed_node_ratio +
            distance_score * self.weights.min_seed_distance +
            strength_score * self.weights.seed_connection_strength
        ) / (self.weights.seed_node_ratio + self.weights.min_seed_distance + self.weights.seed_connection_strength)

        return proximity_score, factors

    async def _score_behavioral(
        self,
        cluster: Any,
        graph_data: Dict[str, Any],
        historical_data: Optional[Dict[str, Any]],
    ) -> Tuple[float, Dict[str, float]]:
        """
        Score behavioral patterns.
        """
        factors = {}

        # Timing correlation (how synchronized are transactions)
        timing_corr = graph_data.get("timing_correlation", {}).get(cluster.cluster_id, 0.5)
        timing_score = timing_corr  # Already 0-1
        factors["timing_correlation"] = timing_score

        # Volume anomaly (unusual transaction volumes)
        volume_anomaly = graph_data.get("volume_anomaly", {}).get(cluster.cluster_id, 0.5)
        volume_score = volume_anomaly
        factors["volume_anomaly"] = volume_score

        # Frequency pattern (burst activity)
        frequency = graph_data.get("frequency_score", {}).get(cluster.cluster_id, 0.5)
        frequency_score = frequency
        factors["frequency_pattern"] = frequency_score

        # Weighted behavioral score
        behavioral_score = (
            timing_score * self.weights.timing_correlation +
            volume_score * self.weights.volume_anomaly +
            frequency_score * self.weights.frequency_pattern
        ) / (self.weights.timing_correlation + self.weights.volume_anomaly + self.weights.frequency_pattern)

        return behavioral_score, factors

    async def _score_topology(
        self,
        cluster: Any,
        graph_data: Dict[str, Any],
    ) -> Tuple[float, Dict[str, float]]:
        """
        Score network topology factors.
        """
        factors = {}

        # Hub presence (centralized funding sources)
        hub_count = graph_data.get("hub_count", {}).get(cluster.cluster_id, 0)
        hub_score = min(1.0, hub_count / 3)  # 3+ hubs = max
        factors["hub_presence"] = hub_score

        # Chain pattern (daisy chain presence)
        chain_count = graph_data.get("chain_count", {}).get(cluster.cluster_id, 0)
        chain_score = min(1.0, chain_count / 2)  # 2+ chains = max
        factors["chain_pattern"] = chain_score

        # Bidirectional ratio (mutual connections)
        bidir_ratio = graph_data.get("bidirectional_ratio", {}).get(cluster.cluster_id, 0.0)
        bidir_score = bidir_ratio  # Already 0-1
        factors["bidirectional_ratio"] = bidir_score

        # Weighted topology score
        topology_score = (
            hub_score * self.weights.hub_presence +
            chain_score * self.weights.chain_pattern +
            bidir_score * self.weights.bidirectional_ratio
        ) / (self.weights.hub_presence + self.weights.chain_pattern + self.weights.bidirectional_ratio)

        return topology_score, factors

    def _determine_risk_level(self, score: float) -> RiskLevel:
        """
        Determine risk level from score.
        """
        if score >= self.RISK_THRESHOLDS[RiskLevel.CRITICAL]:
            return RiskLevel.CRITICAL
        elif score >= self.RISK_THRESHOLDS[RiskLevel.HIGH]:
            return RiskLevel.HIGH
        elif score >= self.RISK_THRESHOLDS[RiskLevel.MEDIUM]:
            return RiskLevel.MEDIUM
        elif score >= self.RISK_THRESHOLDS[RiskLevel.LOW]:
            return RiskLevel.LOW
        else:
            return RiskLevel.MINIMAL

    def _calculate_confidence(self, cluster: Any, score: ClusterScore) -> float:
        """
        Calculate confidence in the score.
        """
        confidence_factors = []

        # More data = higher confidence
        size = getattr(cluster, 'size', 0)
        size_confidence = min(1.0, size / 20)  # 20+ members = full confidence
        confidence_factors.append(size_confidence)

        # Seed presence increases confidence
        seed_count = getattr(cluster, 'seed_node_count', 0)
        seed_confidence = min(1.0, seed_count / 3)  # 3+ seeds = full confidence
        confidence_factors.append(seed_confidence)

        # Detection method confidence
        method = getattr(cluster, 'detection_method', '')
        method_confidence = {
            'connected_components': 0.7,
            'louvain': 0.8,
            'dbscan_behavioral': 0.85,
            'temporal_correlation': 0.75,
        }.get(method, 0.6)
        confidence_factors.append(method_confidence)

        # Factor agreement (how consistent are the scores)
        factor_values = list(score.factors.values())
        if factor_values:
            factor_std = self._std(factor_values)
            agreement_confidence = max(0.5, 1.0 - factor_std)
            confidence_factors.append(agreement_confidence)

        # Average confidence
        confidence = sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.5
        return max(self.min_confidence, confidence)

    def _bayesian_interval(
        self,
        score: float,
        confidence: float,
    ) -> Tuple[float, float]:
        """
        Calculate Bayesian confidence interval using Beta distribution.
        """
        if not SCIPY_AVAILABLE:
            margin = (1 - confidence) * 0.2
            return max(0, score - margin), min(1, score + margin)

        # Use Beta distribution
        # Higher confidence = more observations = tighter interval
        n = int(confidence * 100)  # Effective sample size
        successes = int(score * n)
        failures = n - successes

        # Add prior (Beta(1,1) = uniform)
        alpha = successes + 1
        beta_param = failures + 1

        # 95% credible interval
        lower = stats.beta.ppf(0.025, alpha, beta_param)
        upper = stats.beta.ppf(0.975, alpha, beta_param)

        return lower, upper

    def _generate_explanation(
        self,
        score: ClusterScore,
    ) -> List[str]:
        """
        Generate human-readable explanation of the score.
        """
        explanations = []

        # Overall assessment
        explanations.append(
            f"Risk Level: {score.risk_level.value.upper()} "
            f"(score: {score.risk_score:.2f}, confidence: {score.confidence:.2f})"
        )

        # Top contributing factors
        sorted_factors = sorted(
            score.factors.items(),
            key=lambda x: x[1],
            reverse=True
        )

        top_factors = sorted_factors[:3]
        if top_factors:
            factor_strs = [f"{k}: {v:.2f}" for k, v in top_factors]
            explanations.append(f"Top risk factors: {', '.join(factor_strs)}")

        # Component breakdown
        components = [
            ("Structure", score.structure_score),
            ("Proximity", score.proximity_score),
            ("Behavioral", score.behavioral_score),
            ("Topology", score.topology_score),
        ]

        high_components = [(n, s) for n, s in components if s >= 0.7]
        if high_components:
            comp_strs = [f"{n}: {s:.2f}" for n, s in high_components]
            explanations.append(f"High-risk components: {', '.join(comp_strs)}")

        # Specific warnings
        if score.factors.get("seed_node_ratio", 0) > 0.5:
            explanations.append("⚠️ High concentration of known insiders")

        if score.factors.get("timing_correlation", 0) > 0.8:
            explanations.append("⚠️ Highly synchronized transaction timing")

        if score.factors.get("hub_presence", 0) > 0.7:
            explanations.append("⚠️ Centralized funding hub detected")

        return explanations

    def _std(self, values: List[float]) -> float:
        """Calculate standard deviation."""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)

    def _update_metrics(self, score: ClusterScore):
        """Update scoring metrics."""
        self.metrics.total_scored += 1
        self.metrics.last_scored_at = time.time()

        # Update level counts
        if score.risk_level == RiskLevel.CRITICAL:
            self.metrics.critical_count += 1
        elif score.risk_level == RiskLevel.HIGH:
            self.metrics.high_count += 1
        elif score.risk_level == RiskLevel.MEDIUM:
            self.metrics.medium_count += 1
        else:
            self.metrics.low_count += 1

        # Update averages
        self.score_history.append(score.risk_score)
        if len(self.score_history) > 1000:
            self.score_history = self.score_history[-500:]

        self.metrics.avg_score = sum(self.score_history) / len(self.score_history)
        self.metrics.max_score = max(self.metrics.max_score, score.risk_score)

        # Update timing
        self.metrics.avg_scoring_time_ms = (
            (self.metrics.avg_scoring_time_ms * (self.metrics.total_scored - 1) + score.scoring_time_ms) /
            self.metrics.total_scored
        )

    def get_metrics(self) -> Dict[str, Any]:
        """Get scoring metrics."""
        return {
            "total_scored": self.metrics.total_scored,
            "critical_count": self.metrics.critical_count,
            "high_count": self.metrics.high_count,
            "medium_count": self.metrics.medium_count,
            "low_count": self.metrics.low_count,
            "avg_score": round(self.metrics.avg_score, 4),
            "max_score": round(self.metrics.max_score, 4),
            "avg_scoring_time_ms": round(self.metrics.avg_scoring_time_ms, 2),
        }

    def calibrate_weights(
        self,
        labeled_data: List[Tuple[ClusterScore, bool]],
    ) -> ScoringWeights:
        """
        Calibrate weights based on labeled data.

        Args:
            labeled_data: List of (score, is_insider) tuples

        Returns:
            Optimized ScoringWeights
        """
        # Simple calibration: increase weights for factors
        # that correlate with insider status

        factor_correlations = {}

        for factor_name in [
            "cluster_size", "cluster_density", "connectivity",
            "seed_node_ratio", "min_seed_distance", "seed_connection_strength",
            "timing_correlation", "volume_anomaly", "frequency_pattern",
            "hub_presence", "chain_pattern", "bidirectional_ratio",
        ]:
            insider_values = [
                s.factors.get(factor_name, 0)
                for s, is_insider in labeled_data if is_insider
            ]
            non_insider_values = [
                s.factors.get(factor_name, 0)
                for s, is_insider in labeled_data if not is_insider
            ]

            if insider_values and non_insider_values:
                insider_mean = sum(insider_values) / len(insider_values)
                non_insider_mean = sum(non_insider_values) / len(non_insider_values)
                factor_correlations[factor_name] = insider_mean - non_insider_mean

        # Normalize correlations to weights
        if factor_correlations:
            total = sum(max(0, v) for v in factor_correlations.values())
            if total > 0:
                new_weights = ScoringWeights(
                    **{k: max(0.01, v / total) for k, v in factor_correlations.items()}
                )
                return new_weights

        return self.weights
