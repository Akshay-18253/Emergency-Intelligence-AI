"""
Demonstration: Quantitative Metrics Harness & Algorithmic Profiler (Milestone 6.3).

Demonstrates:
1. NFPA 1710 Statutory Response Compliance Analysis across multi-incident disaster scenarios.
2. Search Space Pruning Benchmark comparing A* heuristic guidance against uniform Dijkstra.
3. Microsecond-accurate latency distribution profiling (p50, p90, p95, p99, max) for in-flight replanning.
4. Path Stability Index (PSI) and Detour Delay Degradation Factor (DDF) during bridge severance.
"""

from __future__ import annotations

import time

from emergency_intelligence.evaluation.metrics import (
    evaluate_nfpa1710_compliance,
    evaluate_route_stability,
    records_from_dicts,
)
from emergency_intelligence.evaluation.profiler import (
    AlgorithmicProfiler,
    profile_callable,
)
from emergency_intelligence.graph.heuristics import euclidean_distance
from emergency_intelligence.graph.models import Edge, Graph, Node
from emergency_intelligence.simulation.scenarios import (
    build_cascading_multi_alarm_scenario,
    build_infrastructure_severance_scenario,
    build_single_incident_baseline_scenario,
    ScenarioRunner,
)


def _build_urban_grid_network(rows: int = 5, cols: int = 5) -> Graph:
    """Builds an urban grid road network with spatial coordinates."""
    g = Graph()
    for r in range(rows):
        for c in range(cols):
            nid = f"N_{r}_{c}"
            g.add_node(Node(node_id=nid, coordinates=(-71.0 + c * 0.015, 42.0 + r * 0.015)))

    for r in range(rows):
        for c in range(cols):
            curr = f"N_{r}_{c}"
            if c < cols - 1:
                nxt = f"N_{r}_{c+1}"
                g.add_edge(Edge(source_id=curr, destination_id=nxt, cost=120.0))
                g.add_edge(Edge(source_id=nxt, destination_id=curr, cost=120.0))
            if r < rows - 1:
                nxt = f"N_{r+1}_{c}"
                g.add_edge(Edge(source_id=curr, destination_id=nxt, cost=120.0))
                g.add_edge(Edge(source_id=nxt, destination_id=curr, cost=120.0))
    return g


def main() -> None:
    print("=" * 82)
    print("  EMERGENCY INTELLIGENCE AI - QUANTITATIVE METRICS & ALGORITHMIC PROFILER")
    print("  Milestone 6.3 Demonstration")
    print("=" * 82)

    # -----------------------------------------------------------------------
    # Part 1: NFPA 1710 Compliance Audit Across Multi-Incident Disaster Scenarios
    # -----------------------------------------------------------------------
    print("\n--- [PART 1] NFPA 1710 STATUTORY RESPONSE COMPLIANCE AUDIT ---")
    print("Statutory Thresholds: Travel Time <= 240.0s (First Engine) | Full Alarm <= 480.0s")
    print("Statutory Target: >= 90.0% of responses must satisfy the standard.")
    print("-" * 82)

    scenarios = [
        ("Single Incident Baseline", build_single_incident_baseline_scenario()),
        ("Cascading Multi-Alarm", build_cascading_multi_alarm_scenario()),
        ("Infrastructure Severance", build_infrastructure_severance_scenario()),
    ]

    for label, scn_def in scenarios:
        runner = ScenarioRunner(scn_def)
        result = runner.run()

        records = records_from_dicts(result.incident_records)
        metrics = evaluate_nfpa1710_compliance(records)

        status_str = "[PASS] COMPLIANT" if metrics.is_overall_compliant else "[WARN] NON-COMPLIANT"
        print(f"\nScenario: {label}")
        print(f"  Overall NFPA 1710 Status: {status_str}")
        print(
            f"  First-Arrival Compliance: {metrics.first_arrival_compliant_count}/{metrics.serviced_incidents} "
            f"({metrics.first_arrival_compliance_rate * 100:.1f}%) [Req: >= 90%]"
        )
        print(
            f"  Travel Time Distribution: Mean={metrics.mean_first_travel_time:.1f}s | "
            f"Median={metrics.median_first_travel_time:.1f}s | "
            f"P90={metrics.p90_first_travel_time:.1f}s | "
            f"Max={metrics.max_first_travel_time:.1f}s"
        )
        print(
            f"  Municipal Queue Latency : Mean={metrics.mean_queue_delay:.1f}s | "
            f"Max={metrics.max_queue_delay:.1f}s"
        )

    # -----------------------------------------------------------------------
    # Part 2: Search Space Pruning Benchmark (A* vs. Dijkstra)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 82)
    print("--- [PART 2] SEARCH SPACE PRUNING BENCHMARK (A* vs. DIJKSTRA) ---")
    print("Evaluates heuristic pruning efficiency across a 25-node urban road network.")
    print("-" * 82)

    grid = _build_urban_grid_network(5, 5)
    profiler = AlgorithmicProfiler()

    od_queries = [
        ("N_0_0", "N_4_4"),  # Long diagonal
        ("N_0_1", "N_4_3"),
        ("N_1_0", "N_3_4"),
        ("N_0_4", "N_4_0"),  # Cross diagonal
        ("N_1_1", "N_3_3"),
        ("N_2_0", "N_2_4"),  # Horizontal traversal
        ("N_0_2", "N_4_2"),  # Vertical traversal
    ]

    summary = profiler.profile_search_pruning(
        graph=grid,
        queries=od_queries,
        heuristic=euclidean_distance,
    )

    print(f"{'Origin':<10} {'Target':<10} {'Dijkstra Nodes':<16} {'A* Nodes':<12} {'Pruning %':<12} {'Optimal?':<10}")
    print("-" * 75)
    for p in summary.pair_results:
        print(
            f"{p.source:<10} {p.destination:<10} "
            f"{p.dijkstra_nodes_explored:<16} {p.astar_nodes_explored:<12} "
            f"{p.pruning_ratio * 100:>8.1f}%    "
            f"{'YES' if p.is_optimal else 'NO':<10}"
        )
    print("-" * 75)
    print(
        f"Total Node Expansions: Dijkstra={summary.total_dijkstra_nodes} | "
        f"A*={summary.total_astar_nodes} | "
        f"Pruned={summary.total_nodes_pruned} ({summary.average_pruning_ratio * 100:.1f}% Avg)"
    )
    print(f"Cost Optimality Parity: {'100% VERIFIED' if summary.all_optimal else 'FAILED'}")

    # -----------------------------------------------------------------------
    # Part 3: Microsecond Latency Profiler (In-Flight Dynamic Replanning)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 82)
    print("--- [PART 3] IN-FLIGHT DYNAMIC REPLANNING LATENCY DISTRIBUTION ---")
    print("High-resolution profiling (us) of graph mutation & reactive route replanning.")
    print("-" * 82)

    dist = profiler.profile_dynamic_rerouting_latency(
        graph=grid,
        origin="N_0_0",
        target="N_4_4",
        edge_to_sever=("N_1_1", "N_1_2"),
        iterations=100,
        warmup=10,
    )

    print(f"Sample Count : {dist.sample_count} iterations (10 warm-up cycles discarded)")
    print(f"Mean Latency : {dist.mean_us:.2f} us (+/- {dist.std_us:.2f} us)")
    print(f"p50 (Median) : {dist.p50_us:.2f} us ({dist.p50_us / 1000.0:.4f} ms)")
    print(f"p90 Latency  : {dist.p90_us:.2f} us ({dist.p90_us / 1000.0:.4f} ms)")
    print(f"p95 Latency  : {dist.p95_us:.2f} us ({dist.p95_us / 1000.0:.4f} ms)")
    print(f"p99 Latency  : {dist.p99_us:.2f} us ({dist.p99_us / 1000.0:.4f} ms)")
    print(f"Max Latency  : {dist.max_us:.2f} us ({dist.max_us / 1000.0:.4f} ms)")

    # -----------------------------------------------------------------------
    # Part 4: Path Stability Index (PSI) & Detour Delay Degradation Factor (DDF)
    # -----------------------------------------------------------------------
    print("\n" + "=" * 82)
    print("--- [PART 4] PATH STABILITY INDEX & DETOUR DELAY DEGRADATION ---")
    print("Quantifying route churn and excess delay during unexpected infrastructure severance.")
    print("-" * 82)

    # In infrastructure severance: planned route was [1, 2, 3, 6], severed edge (3, 6)
    # executed detour was [1, 2, 3, 2, 1, 4, 5, 6]
    planned_route = ["1", "2", "3", "6"]
    executed_route = ["1", "2", "3", "2", "1", "4", "5", "6"]
    initial_tt = 54.0
    actual_tt = 92.5

    stability = evaluate_route_stability(
        unit_id="E-1",
        initial_path=planned_route,
        executed_path=executed_route,
        initial_travel_time=initial_tt,
        actual_travel_time=actual_tt,
        reroute_count=1,
    )

    print(f"Unit ID              : {stability.unit_id}")
    print(f"Initial Planned Route: {' -> '.join(planned_route)}")
    print(f"Executed Detour Route: {' -> '.join(executed_route)}")
    print(f"Path Stability Index : {stability.path_stability_index:.4f} (Jaccard edge similarity)")
    print(f"Initial Travel Time  : {stability.initial_travel_time:.1f} s")
    print(f"Actual Travel Time   : {stability.actual_travel_time:.1f} s")
    print(f"Excess Detour Delay  : +{stability.excess_delay_seconds:.1f} s")
    print(f"Detour Degradation   : +{stability.detour_delay_degradation_factor * 100:.1f}% relative delay increase")

    print("\n" + "=" * 82)
    print("  MILESTONE 6.3 EVALUATION DEMONSTRATION COMPLETE")
    print("=" * 82)


if __name__ == "__main__":
    main()
