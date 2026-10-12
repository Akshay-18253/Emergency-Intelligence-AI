"""
Evaluation package for Emergency Intelligence AI.

Provides quantitative performance metrics, statutory compliance analyzers,
and microsecond-accurate algorithmic profilers for emergency dispatch,
fleet allocation, and in-flight routing.
"""

from __future__ import annotations

from .metrics import (
    IncidentResponseRecord,
    NFPA1710Metrics,
    RouteStabilityMetrics,
    compute_detour_delay_degradation,
    compute_path_stability_index,
    compute_percentile,
    evaluate_nfpa1710_compliance,
    evaluate_route_stability,
    records_from_dicts,
)
from .profiler import (
    AlgorithmicProfiler,
    LatencyDistribution,
    PruningPairResult,
    SearchPruningSummary,
    compute_latency_distribution,
    profile_callable,
)

__all__ = [
    "IncidentResponseRecord",
    "NFPA1710Metrics",
    "RouteStabilityMetrics",
    "compute_percentile",
    "evaluate_nfpa1710_compliance",
    "records_from_dicts",
    "compute_path_stability_index",
    "compute_detour_delay_degradation",
    "evaluate_route_stability",
    "LatencyDistribution",
    "compute_latency_distribution",
    "profile_callable",
    "PruningPairResult",
    "SearchPruningSummary",
    "AlgorithmicProfiler",
]
