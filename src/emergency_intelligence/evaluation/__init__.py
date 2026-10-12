"""
Evaluation package for Emergency Intelligence AI.

Provides quantitative performance metrics, statutory compliance analyzers,
microsecond-accurate algorithmic profilers, comparative routing baseline benchmarks,
and multi-format simulation telemetry exporters.
"""

from __future__ import annotations

from .benchmark import (
    ComparativeBenchmarkSummary,
    ComparativeRoutingBenchmark,
    RoutingStrategy,
    StrategyBenchmarkResult,
)
from .exporter import (
    export_incident_metrics_csv,
    export_spatial_replay_geojson,
    export_strategy_comparison_csv,
    export_telemetry_json,
)
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
    # Metrics
    "IncidentResponseRecord",
    "NFPA1710Metrics",
    "RouteStabilityMetrics",
    "compute_percentile",
    "evaluate_nfpa1710_compliance",
    "records_from_dicts",
    "compute_path_stability_index",
    "compute_detour_delay_degradation",
    "evaluate_route_stability",
    # Profiler
    "LatencyDistribution",
    "compute_latency_distribution",
    "profile_callable",
    "PruningPairResult",
    "SearchPruningSummary",
    "AlgorithmicProfiler",
    # Benchmark
    "RoutingStrategy",
    "StrategyBenchmarkResult",
    "ComparativeBenchmarkSummary",
    "ComparativeRoutingBenchmark",
    # Exporter
    "export_telemetry_json",
    "export_incident_metrics_csv",
    "export_strategy_comparison_csv",
    "export_spatial_replay_geojson",
]
