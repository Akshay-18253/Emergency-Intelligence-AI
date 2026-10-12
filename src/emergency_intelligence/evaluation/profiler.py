"""
Algorithmic profiler and search space pruning analyzer.

Provides microsecond-accurate latency distributions and comparative search space
pruning benchmarks between heuristic-directed search (A*) and uniform-cost
search (Dijkstra).

Key capabilities:
1. Microsecond Latency Profiler:
   - High-resolution monotonic timing using ``time.perf_counter_ns()``.
   - Percentile distribution analysis (p50, p90, p95, p99, min, max, mean, std).
   - Warm-up cycles to eliminate JIT/cache cold-start artifacts.
2. Search Space Pruning Harness:
   - Quantifies visited node reduction between A* and Dijkstra.
   - Evaluates heuristic pruning ratios across road network origin-destination pairs.
   - Strict optimality verification confirming cost parity.
3. In-Flight Dynamic Replanning Profiler:
   - Measures end-to-end latency of graph mutation and route recomputation.
"""

from __future__ import annotations

import math
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.dijkstra import dijkstra
from emergency_intelligence.graph.heuristics import HeuristicFn, euclidean_distance
from emergency_intelligence.graph.models import Graph
from .metrics import compute_percentile


# ---------------------------------------------------------------------------
# Latency Distribution
# ---------------------------------------------------------------------------


@dataclass
class LatencyDistribution:
    """Statistical distribution of execution latencies in microseconds (μs).

    Attributes
    ----------
    sample_count : int
        Number of measured samples.
    mean_us : float
        Arithmetic mean latency in microseconds.
    std_us : float
        Standard deviation in microseconds.
    min_us : float
        Minimum observed latency in microseconds.
    p50_us : float
        50th percentile (median) latency in microseconds.
    p90_us : float
        90th percentile latency in microseconds.
    p95_us : float
        95th percentile latency in microseconds.
    p99_us : float
        99th percentile latency in microseconds.
    max_us : float
        Maximum observed latency in microseconds.
    """

    sample_count: int
    mean_us: float
    std_us: float
    min_us: float
    p50_us: float
    p90_us: float
    p95_us: float
    p99_us: float
    max_us: float

    def to_dict(self) -> Dict[str, float]:
        """Serializes latency distribution in microseconds."""
        return {
            "sample_count": float(self.sample_count),
            "mean_us": round(self.mean_us, 2),
            "std_us": round(self.std_us, 2),
            "min_us": round(self.min_us, 2),
            "p50_us": round(self.p50_us, 2),
            "p90_us": round(self.p90_us, 2),
            "p95_us": round(self.p95_us, 2),
            "p99_us": round(self.p99_us, 2),
            "max_us": round(self.max_us, 2),
        }

    def to_ms_dict(self) -> Dict[str, float]:
        """Serializes latency distribution converted to milliseconds."""
        return {
            "sample_count": float(self.sample_count),
            "mean_ms": round(self.mean_us / 1000.0, 4),
            "std_ms": round(self.std_us / 1000.0, 4),
            "min_ms": round(self.min_us / 1000.0, 4),
            "p50_ms": round(self.p50_us / 1000.0, 4),
            "p90_ms": round(self.p90_us / 1000.0, 4),
            "p95_ms": round(self.p95_us / 1000.0, 4),
            "p99_ms": round(self.p99_us / 1000.0, 4),
            "max_ms": round(self.max_us / 1000.0, 4),
        }

    def summary_string(self) -> str:
        """Returns human-readable formatted summary string."""
        return (
            f"n={self.sample_count} | "
            f"mean={self.mean_us:.1f}us +/- {self.std_us:.1f}us | "
            f"min={self.min_us:.1f}us | "
            f"p50={self.p50_us:.1f}us | "
            f"p95={self.p95_us:.1f}us | "
            f"p99={self.p99_us:.1f}us | "
            f"max={self.max_us:.1f}us"
        )


def compute_latency_distribution(latencies_ns: Sequence[int | float]) -> LatencyDistribution:
    """Computes distribution statistics from nanosecond latency measurements.

    Parameters
    ----------
    latencies_ns : Sequence[int | float]
        Raw latency measurements in nanoseconds.

    Returns
    -------
    LatencyDistribution
        Microsecond-scaled distribution statistics.
    """
    if not latencies_ns:
        return LatencyDistribution(
            sample_count=0,
            mean_us=0.0,
            std_us=0.0,
            min_us=0.0,
            p50_us=0.0,
            p90_us=0.0,
            p95_us=0.0,
            p99_us=0.0,
            max_us=0.0,
        )

    # Convert to microseconds
    samples_us = [float(t) / 1000.0 for t in latencies_ns]
    n = len(samples_us)
    mean_val = sum(samples_us) / n
    std_val = statistics.stdev(samples_us) if n > 1 else 0.0
    min_val = min(samples_us)
    max_val = max(samples_us)

    p50 = compute_percentile(samples_us, 50.0)
    p90 = compute_percentile(samples_us, 90.0)
    p95 = compute_percentile(samples_us, 95.0)
    p99 = compute_percentile(samples_us, 99.0)

    return LatencyDistribution(
        sample_count=n,
        mean_us=mean_val,
        std_us=std_val,
        min_us=min_val,
        p50_us=p50,
        p90_us=p90,
        p95_us=p95,
        p99_us=p99,
        max_us=max_val,
    )


def profile_callable(
    fn: Callable[[], Any],
    iterations: int = 100,
    warmup: int = 10,
) -> LatencyDistribution:
    """Measures execution latency distribution for a nullary callable.

    Parameters
    ----------
    fn : Callable[[], Any]
        Zero-argument function to benchmark.
    iterations : int
        Number of measured trials (default 100).
    warmup : int
        Number of unmeasured warm-up executions (default 10).

    Returns
    -------
    LatencyDistribution
        Microsecond statistical distribution.
    """
    # Warm-up phase
    for _ in range(max(0, warmup)):
        fn()

    # Measurement phase
    latencies_ns: List[int] = []
    for _ in range(max(1, iterations)):
        t_start = time.perf_counter_ns()
        fn()
        t_end = time.perf_counter_ns()
        latencies_ns.append(t_end - t_start)

    return compute_latency_distribution(latencies_ns)


# ---------------------------------------------------------------------------
# Search Space Pruning Benchmark
# ---------------------------------------------------------------------------


@dataclass
class PruningPairResult:
    """Comparative routing result for a single origin-destination query pair.

    Attributes
    ----------
    source : str
        Origin node identifier.
    destination : str
        Target node identifier.
    dijkstra_nodes_explored : int
        Nodes expanded by Dijkstra search.
    dijkstra_cost : float
        Optimal path cost found by Dijkstra.
    dijkstra_latency_us : float
        Dijkstra execution latency in microseconds.
    astar_nodes_explored : int
        Nodes expanded by A* search.
    astar_cost : float
        Optimal path cost found by A*.
    astar_latency_us : float
        A* execution latency in microseconds.
    nodes_pruned : int
        Absolute reduction in node expansions (Dijkstra - A*).
    pruning_ratio : float
        Relative search space reduction in range [0.0, 1.0].
    is_optimal : bool
        True if A* found the identical cost to Dijkstra within numerical precision.
    """

    source: str
    destination: str
    dijkstra_nodes_explored: int
    dijkstra_cost: float
    dijkstra_latency_us: float
    astar_nodes_explored: int
    astar_cost: float
    astar_latency_us: float
    nodes_pruned: int
    pruning_ratio: float
    is_optimal: bool


@dataclass
class SearchPruningSummary:
    """Aggregated search space pruning evaluation across multiple queries.

    Attributes
    ----------
    total_queries : int
        Total number of origin-destination queries evaluated.
    total_dijkstra_nodes : int
        Cumulative nodes explored by Dijkstra.
    total_astar_nodes : int
        Cumulative nodes explored by A*.
    total_nodes_pruned : int
        Total node expansions pruned by heuristic guidance.
    average_pruning_ratio : float
        Mean pruning ratio across all evaluated queries.
    max_pruning_ratio : float
        Maximum pruning ratio achieved in a single query.
    all_optimal : bool
        True if A* achieved exact cost optimality across all queries.
    dijkstra_latency : LatencyDistribution
        Latency distribution for Dijkstra queries.
    astar_latency : LatencyDistribution
        Latency distribution for A* queries.
    pair_results : List[PruningPairResult]
        Detailed individual query records.
    """

    total_queries: int
    total_dijkstra_nodes: int
    total_astar_nodes: int
    total_nodes_pruned: int
    average_pruning_ratio: float
    max_pruning_ratio: float
    all_optimal: bool
    dijkstra_latency: LatencyDistribution
    astar_latency: LatencyDistribution
    pair_results: List[PruningPairResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes pruning summary to dictionary."""
        return {
            "total_queries": self.total_queries,
            "total_dijkstra_nodes": self.total_dijkstra_nodes,
            "total_astar_nodes": self.total_astar_nodes,
            "total_nodes_pruned": self.total_nodes_pruned,
            "average_pruning_ratio": round(self.average_pruning_ratio, 4),
            "max_pruning_ratio": round(self.max_pruning_ratio, 4),
            "all_optimal": self.all_optimal,
            "dijkstra_latency_p50_us": self.dijkstra_latency.p50_us,
            "astar_latency_p50_us": self.astar_latency.p50_us,
            "speedup_factor": round(
                (self.dijkstra_latency.p50_us / self.astar_latency.p50_us)
                if self.astar_latency.p50_us > 0
                else 1.0,
                2,
            ),
        }


# ---------------------------------------------------------------------------
# Algorithmic Profiler Class
# ---------------------------------------------------------------------------


class AlgorithmicProfiler:
    """Harness for profiling search algorithms, pruning efficiency, and dynamic replanning."""

    def __init__(self) -> None:
        pass

    def profile_search_pruning(
        self,
        graph: Graph,
        queries: Sequence[Tuple[str, str]],
        heuristic: Optional[HeuristicFn] = None,
    ) -> SearchPruningSummary:
        """Profiles search space pruning comparing A* against Dijkstra.

        Parameters
        ----------
        graph : Graph
            Network topology graph.
        queries : Sequence[Tuple[str, str]]
            List of (origin, target) node ID pairs to benchmark.
        heuristic : Optional[HeuristicFn]
            Admissible heuristic function (defaults to Euclidean if available).

        Returns
        -------
        SearchPruningSummary
            Comparative benchmark results.
        """
        pair_results: List[PruningPairResult] = []
        dijkstra_times_ns: List[int] = []
        astar_times_ns: List[int] = []

        total_dijkstra_nodes = 0
        total_astar_nodes = 0
        all_optimal = True

        for src, dst in queries:
            if not graph.has_node(src) or not graph.has_node(dst):
                continue

            # Benchmark Dijkstra
            t0 = time.perf_counter_ns()
            res_dijkstra = dijkstra(graph, src, dst)
            t1 = time.perf_counter_ns()
            dijk_ns = t1 - t0
            dijkstra_times_ns.append(dijk_ns)

            # Benchmark A*
            t2 = time.perf_counter_ns()
            res_astar = astar(graph, src, dst, heuristic=heuristic)
            t3 = time.perf_counter_ns()
            astar_ns = t3 - t2
            astar_times_ns.append(astar_ns)

            # Verify optimality
            cost_gap = abs(res_dijkstra.total_cost - res_astar.total_cost)
            is_opt = cost_gap < 1e-6
            if not is_opt and (res_dijkstra.reachable and res_astar.reachable):
                all_optimal = False

            d_nodes = res_dijkstra.nodes_explored
            a_nodes = res_astar.nodes_explored
            total_dijkstra_nodes += d_nodes
            total_astar_nodes += a_nodes

            pruned = max(0, d_nodes - a_nodes)
            ratio = (pruned / d_nodes) if d_nodes > 0 else 0.0

            pair_results.append(
                PruningPairResult(
                    source=src,
                    destination=dst,
                    dijkstra_nodes_explored=d_nodes,
                    dijkstra_cost=res_dijkstra.total_cost,
                    dijkstra_latency_us=dijk_ns / 1000.0,
                    astar_nodes_explored=a_nodes,
                    astar_cost=res_astar.total_cost,
                    astar_latency_us=astar_ns / 1000.0,
                    nodes_pruned=pruned,
                    pruning_ratio=ratio,
                    is_optimal=is_opt,
                )
            )

        n_queries = len(pair_results)
        total_pruned = max(0, total_dijkstra_nodes - total_astar_nodes)
        avg_ratio = (
            sum(p.pruning_ratio for p in pair_results) / n_queries
            if n_queries > 0
            else 0.0
        )
        max_ratio = max((p.pruning_ratio for p in pair_results), default=0.0)

        dist_dijkstra = compute_latency_distribution(dijkstra_times_ns)
        dist_astar = compute_latency_distribution(astar_times_ns)

        return SearchPruningSummary(
            total_queries=n_queries,
            total_dijkstra_nodes=total_dijkstra_nodes,
            total_astar_nodes=total_astar_nodes,
            total_nodes_pruned=total_pruned,
            average_pruning_ratio=avg_ratio,
            max_pruning_ratio=max_ratio,
            all_optimal=all_optimal,
            dijkstra_latency=dist_dijkstra,
            astar_latency=dist_astar,
            pair_results=pair_results,
        )

    def profile_dynamic_rerouting_latency(
        self,
        graph: Graph,
        origin: str,
        target: str,
        edge_to_sever: Tuple[str, str],
        iterations: int = 50,
        warmup: int = 5,
    ) -> LatencyDistribution:
        """Profiles latency distribution for dynamic in-flight replanning under road severance.

        Measures the microsecond duration to:
        1. Apply dynamic edge closure in DynamicGraphView.
        2. Recompute the shortest alternate route via A*.
        3. Restore edge mutation.

        Parameters
        ----------
        graph : Graph
            Base network topology.
        origin : str
            Current vehicle location node.
        target : str
            Incident destination node.
        edge_to_sever : Tuple[str, str]
            Directed edge (u, v) severed mid-flight.
        iterations : int
            Number of measurement trials.
        warmup : int
            Number of warm-up cycles.

        Returns
        -------
        LatencyDistribution
            Distribution of end-to-end replanning latencies in microseconds.
        """
        dynamic_view = DynamicGraphView(graph)
        u, v = edge_to_sever

        def _replan_cycle() -> None:
            # Apply closure
            dynamic_view.apply_closure(u, v, reason="profiling_closure")
            # Recompute route
            res = astar(dynamic_view, origin, target)
            _ = res.reachable
            # Restore
            dynamic_view.remove_mutation(u, v)

        return profile_callable(_replan_cycle, iterations=iterations, warmup=warmup)
