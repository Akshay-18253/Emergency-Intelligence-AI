"""
Tests for the evaluation package (Milestone 6.3).

Verifies:
1. NFPA 1710 compliance analysis, statutory thresholds, and percentiles.
2. Path Stability Index (PSI) and Detour Delay Degradation Factor (DDF).
3. Microsecond latency profiling distribution and callable benchmarking.
4. Search space pruning profiler (A* heuristic vs. Dijkstra baseline).
5. Dynamic in-flight replanning latency profiling.
"""

from __future__ import annotations

import math
import pytest
from typing import List

from emergency_intelligence.evaluation.metrics import (
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
from emergency_intelligence.evaluation.profiler import (
    AlgorithmicProfiler,
    LatencyDistribution,
    PruningPairResult,
    SearchPruningSummary,
    compute_latency_distribution,
    profile_callable,
)
from emergency_intelligence.graph.heuristics import euclidean_distance
from emergency_intelligence.graph.models import Edge, Graph, Node


# ===========================================================================
# 1. Percentile Computation Tests
# ===========================================================================


def test_compute_percentile_empty_and_single() -> None:
    assert compute_percentile([], 50.0) == 0.0
    assert compute_percentile([42.0], 50.0) == 42.0
    assert compute_percentile([42.0], 0.0) == 42.0
    assert compute_percentile([42.0], 100.0) == 42.0


def test_compute_percentile_linear_interpolation() -> None:
    # 5 items: ranks 0, 1, 2, 3, 4
    data = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert compute_percentile(data, 0.0) == 10.0
    assert compute_percentile(data, 50.0) == 30.0
    assert compute_percentile(data, 100.0) == 50.0

    # 25th percentile: rank = 0.25 * 4 = 1.0 -> 20.0
    assert compute_percentile(data, 25.0) == 20.0

    # 75th percentile: rank = 0.75 * 4 = 3.0 -> 40.0
    assert compute_percentile(data, 75.0) == 40.0

    # Interpolated rank: 10th percentile: rank = 0.10 * 4 = 0.4 -> 10 + 0.4 * 10 = 14.0
    assert pytest.approx(compute_percentile(data, 10.0), rel=1e-5) == 14.0


# ===========================================================================
# 2. IncidentResponseRecord Properties
# ===========================================================================


def test_incident_response_record_properties() -> None:
    rec = IncidentResponseRecord(
        incident_id="inc-1",
        emergency_type="structure_fire",
        urgency="critical",
        report_time=10.0,
        first_dispatch_time=25.0,
        first_arrival_time=145.0,
        all_arrival_time=220.0,
        cleared_time=500.0,
        queue_delay_seconds=15.0,
        assigned_units=["E-1", "L-1"],
    )

    assert rec.turnout_time_seconds == 15.0  # 25 - 10
    assert rec.first_travel_time_seconds == 120.0  # 145 - 25
    assert rec.first_total_response_time_seconds == 135.0  # 145 - 10
    assert rec.full_alarm_travel_time_seconds == 195.0  # 220 - 25
    assert rec.full_alarm_total_response_time_seconds == 210.0  # 220 - 10


def test_incident_response_record_missing_and_invalid_times() -> None:
    rec = IncidentResponseRecord(incident_id="inc-pending", report_time=50.0)
    assert rec.turnout_time_seconds is None
    assert rec.first_travel_time_seconds is None
    assert rec.first_total_response_time_seconds is None
    assert rec.full_alarm_travel_time_seconds is None
    assert rec.full_alarm_total_response_time_seconds is None

    # Invalid chronological ordering safeguards
    invalid_rec = IncidentResponseRecord(
        incident_id="inc-inv",
        report_time=100.0,
        first_dispatch_time=90.0,  # dispatch before report
        first_arrival_time=80.0,  # arrival before dispatch
        all_arrival_time=70.0,
    )
    assert invalid_rec.turnout_time_seconds is None
    assert invalid_rec.first_travel_time_seconds is None
    assert invalid_rec.first_total_response_time_seconds is None
    assert invalid_rec.full_alarm_travel_time_seconds is None
    assert invalid_rec.full_alarm_total_response_time_seconds is None


# ===========================================================================
# 3. NFPA 1710 Compliance Evaluation Tests
# ===========================================================================


def test_evaluate_nfpa1710_empty() -> None:
    metrics = evaluate_nfpa1710_compliance([])
    assert metrics.total_incidents == 0
    assert metrics.serviced_incidents == 0
    assert metrics.is_overall_compliant is False
    assert metrics.first_arrival_compliance_rate == 0.0
    assert metrics.mean_first_travel_time == 0.0


def test_evaluate_nfpa1710_fully_compliant() -> None:
    # 10 incidents, all travel times under 200s (threshold is 240s)
    records: List[IncidentResponseRecord] = []
    for i in range(10):
        records.append(
            IncidentResponseRecord(
                incident_id=f"inc-{i}",
                report_time=0.0,
                first_dispatch_time=10.0,
                first_arrival_time=150.0 + i * 5.0,  # travel times: 140s to 185s
                all_arrival_time=250.0 + i * 5.0,  # full alarm times: 240s to 285s
                queue_delay_seconds=10.0,
            )
        )

    metrics = evaluate_nfpa1710_compliance(records)
    assert metrics.total_incidents == 10
    assert metrics.serviced_incidents == 10
    assert metrics.first_arrival_compliant_count == 10
    assert metrics.first_arrival_compliance_rate == 1.0
    assert metrics.full_alarm_compliant_count == 10
    assert metrics.full_alarm_compliance_rate == 1.0
    assert metrics.is_first_arrival_compliant is True
    assert metrics.is_full_alarm_compliant is True
    assert metrics.is_overall_compliant is True
    assert 140.0 <= metrics.mean_first_travel_time <= 185.0
    assert metrics.p90_first_travel_time <= 240.0


def test_evaluate_nfpa1710_non_compliant_rate() -> None:
    # 10 incidents, 8 compliant (150s), 2 non-compliant (300s)
    # Compliance rate = 8 / 10 = 0.80 < 0.90 requirement
    records: List[IncidentResponseRecord] = []
    for i in range(8):
        records.append(
            IncidentResponseRecord(
                incident_id=f"inc-ok-{i}",
                report_time=0.0,
                first_dispatch_time=10.0,
                first_arrival_time=160.0,  # travel time = 150s
                all_arrival_time=250.0,
            )
        )
    for i in range(2):
        records.append(
            IncidentResponseRecord(
                incident_id=f"inc-slow-{i}",
                report_time=0.0,
                first_dispatch_time=10.0,
                first_arrival_time=310.0,  # travel time = 300s > 240s
                all_arrival_time=520.0,  # full alarm = 510s > 480s
            )
        )

    metrics = evaluate_nfpa1710_compliance(records)
    assert metrics.first_arrival_compliant_count == 8
    assert metrics.first_arrival_compliance_rate == 0.80
    assert metrics.is_first_arrival_compliant is False
    assert metrics.is_full_alarm_compliant is False
    assert metrics.is_overall_compliant is False


def test_evaluate_nfpa1710_unserviced_and_partial_arrivals() -> None:
    # 3 incidents: 1 fully serviced, 1 first arrival only (no full alarm), 1 completely unserviced
    records = [
        IncidentResponseRecord(
            incident_id="inc-1",
            report_time=0.0,
            first_dispatch_time=10.0,
            first_arrival_time=150.0,
            all_arrival_time=250.0,
            queue_delay_seconds=10.0,
        ),
        IncidentResponseRecord(
            incident_id="inc-2",
            report_time=0.0,
            first_dispatch_time=10.0,
            first_arrival_time=160.0,
            all_arrival_time=None,  # No full alarm
            queue_delay_seconds=10.0,
        ),
        IncidentResponseRecord(
            incident_id="inc-3",
            report_time=0.0,
            first_dispatch_time=None,  # Never dispatched
            first_arrival_time=None,
            all_arrival_time=None,
            queue_delay_seconds=300.0,
        ),
    ]

    metrics = evaluate_nfpa1710_compliance(records)
    assert metrics.total_incidents == 3
    assert metrics.serviced_incidents == 2
    assert metrics.first_arrival_compliant_count == 2
    assert metrics.first_arrival_compliance_rate == 1.0
    assert metrics.full_alarm_compliant_count == 1
    assert metrics.full_alarm_compliance_rate == 1.0


def test_evaluate_nfpa1710_total_response_time_mode() -> None:
    # Test use_total_response_time=True
    rec = IncidentResponseRecord(
        incident_id="inc-1",
        report_time=0.0,
        first_dispatch_time=60.0,  # 60s turnout
        first_arrival_time=250.0,  # 250s total response, 190s travel time
        all_arrival_time=490.0,  # 490s total response, 430s travel time
    )
    # Under travel time (default): 190 <= 240 and 430 <= 480 -> compliant
    m_travel = evaluate_nfpa1710_compliance([rec], use_total_response_time=False)
    assert m_travel.is_overall_compliant is True

    # Under total response time: 250 > 240 and 490 > 480 -> non-compliant
    m_total = evaluate_nfpa1710_compliance([rec], use_total_response_time=True)
    assert m_total.is_first_arrival_compliant is False
    assert m_total.is_full_alarm_compliant is False


def test_records_from_dicts_and_metrics_serialization() -> None:
    raw_dicts = [
        {
            "incident_id": "INC-100",
            "emergency_type": "hazmat",
            "urgency": "critical",
            "report_time": 5.0,
            "first_dispatch_time": 10.0,
            "first_arrival_time": 95.0,
            "all_arrival_time": 120.0,
            "queue_delay_seconds": 5.0,
            "assigned_units": ["H-1"],
        }
    ]
    records = records_from_dicts(raw_dicts)
    assert len(records) == 1
    assert records[0].incident_id == "INC-100"
    assert records[0].first_travel_time_seconds == 85.0

    metrics = evaluate_nfpa1710_compliance(records)
    d = metrics.to_dict()
    assert d["total_incidents"] == 1
    assert d["first_arrival_compliance_rate"] == 1.0
    assert d["is_overall_compliant"] is True


# ===========================================================================
# 4. Path Stability Index & Detour Degradation Tests
# ===========================================================================


def test_path_stability_index_identical() -> None:
    path = ["A", "B", "C", "D"]
    assert compute_path_stability_index(path, path) == 1.0


def test_path_stability_index_disjoint() -> None:
    path1 = ["A", "B", "C"]
    path2 = ["X", "Y", "Z"]
    assert compute_path_stability_index(path1, path2) == 0.0


def test_path_stability_index_partial_detour() -> None:
    # Planned: A -> B -> C -> D (3 edges)
    # Executed: A -> B -> X -> Y -> D (4 edges: (A,B), (B,X), (X,Y), (Y,D))
    # Common edge: (A,B) (1 edge)
    # Union edges: 3 + 4 - 1 = 6 edges
    # Jaccard = 1 / 6 = 0.16667
    planned = ["A", "B", "C", "D"]
    executed = ["A", "B", "X", "Y", "D"]
    psi = compute_path_stability_index(planned, executed)
    assert pytest.approx(psi, rel=1e-4) == (1.0 / 6.0)


def test_path_stability_index_edge_cases() -> None:
    assert compute_path_stability_index(["A"], ["A"]) == 1.0
    assert compute_path_stability_index(["A"], ["B"]) == 0.0
    assert compute_path_stability_index([], []) == 1.0
    assert compute_path_stability_index(["A", "B"], []) == 0.0


def test_compute_detour_delay_degradation() -> None:
    # No degradation (same or faster)
    assert compute_detour_delay_degradation(100.0, 100.0) == 0.0
    assert compute_detour_delay_degradation(100.0, 90.0) == 0.0

    # 50% delay degradation
    assert compute_detour_delay_degradation(100.0, 150.0) == 0.5

    # Zero or negative initial time guard
    assert compute_detour_delay_degradation(0.0, 50.0) == 0.0
    assert compute_detour_delay_degradation(-10.0, 50.0) == 0.0


def test_evaluate_route_stability_and_to_dict() -> None:
    planned = ["N1", "N2", "N3"]
    executed = ["N1", "N2", "N4", "N3"]
    metrics = evaluate_route_stability(
        unit_id="U-1",
        initial_path=planned,
        executed_path=executed,
        initial_travel_time=50.0,
        actual_travel_time=75.0,
        reroute_count=1,
    )
    assert metrics.unit_id == "U-1"
    assert metrics.reroute_count == 1
    assert metrics.excess_delay_seconds == 25.0
    assert metrics.detour_delay_degradation_factor == 0.5
    assert 0.0 < metrics.path_stability_index < 1.0

    d = metrics.to_dict()
    assert d["unit_id"] == "U-1"
    assert d["reroute_count"] == 1
    assert d["excess_delay_seconds"] == 25.0


# ===========================================================================
# 5. Latency Distribution & Callable Profiler Tests
# ===========================================================================


def test_compute_latency_distribution_empty_and_single() -> None:
    empty_dist = compute_latency_distribution([])
    assert empty_dist.sample_count == 0
    assert empty_dist.mean_us == 0.0

    # 1 sample of 5,000 ns = 5.0 us
    single_dist = compute_latency_distribution([5000])
    assert single_dist.sample_count == 1
    assert single_dist.mean_us == 5.0
    assert single_dist.std_us == 0.0
    assert single_dist.p50_us == 5.0
    assert single_dist.max_us == 5.0


def test_latency_distribution_metrics_and_formatting() -> None:
    # 5 samples: 10us, 20us, 30us, 40us, 50us (in nanoseconds)
    ns_samples = [10000, 20000, 30000, 40000, 50000]
    dist = compute_latency_distribution(ns_samples)

    assert dist.sample_count == 5
    assert dist.min_us == 10.0
    assert dist.p50_us == 30.0
    assert dist.max_us == 50.0
    assert dist.mean_us == 30.0

    summary = dist.summary_string()
    assert "n=5" in summary
    assert "mean=30.0us" in summary

    d_us = dist.to_dict()
    assert d_us["p50_us"] == 30.0

    d_ms = dist.to_ms_dict()
    assert d_ms["p50_ms"] == 0.03


def test_profile_callable_executes_warmup_and_iterations() -> None:
    counter = 0

    def work() -> None:
        nonlocal counter
        counter += 1

    dist = profile_callable(work, iterations=25, warmup=5)
    assert counter == 30
    assert dist.sample_count == 25
    assert dist.mean_us > 0.0


# ===========================================================================
# 6. Algorithmic Profiler & Search Space Pruning Tests
# ===========================================================================


def _build_test_grid_graph() -> Graph:
    """Builds a 4x4 spatial grid graph with coordinate positions."""
    g = Graph()
    # Add 16 nodes in 4x4 grid (lon, lat)
    for r in range(4):
        for c in range(4):
            nid = f"{r}_{c}"
            g.add_node(Node(node_id=nid, coordinates=(-71.0 + c * 0.01, 42.0 + r * 0.01)))

    # Add bidirectional edges
    for r in range(4):
        for c in range(4):
            curr = f"{r}_{c}"
            if c < 3:
                nxt = f"{r}_{c+1}"
                g.add_edge(Edge(source_id=curr, destination_id=nxt, cost=100.0))
                g.add_edge(Edge(source_id=nxt, destination_id=curr, cost=100.0))
            if r < 3:
                nxt = f"{r+1}_{c}"
                g.add_edge(Edge(source_id=curr, destination_id=nxt, cost=100.0))
                g.add_edge(Edge(source_id=nxt, destination_id=curr, cost=100.0))
    return g


def test_profile_search_pruning_on_grid() -> None:
    grid = _build_test_grid_graph()
    profiler = AlgorithmicProfiler()

    queries = [
        ("0_0", "3_3"),  # Corner to corner
        ("0_1", "3_2"),
        ("1_0", "2_3"),
        ("non_existent", "3_3"),  # Should be skipped safely
    ]

    summary = profiler.profile_search_pruning(
        graph=grid,
        queries=queries,
        heuristic=euclidean_distance,
    )

    assert summary.total_queries == 3
    assert summary.all_optimal is True
    assert summary.total_nodes_pruned >= 0
    assert summary.average_pruning_ratio >= 0.0

    for pair in summary.pair_results:
        assert pair.is_optimal is True
        # A* visits less or equal nodes than Dijkstra
        assert pair.astar_nodes_explored <= pair.dijkstra_nodes_explored
        assert pytest.approx(pair.astar_cost, rel=1e-5) == pair.dijkstra_cost

    summary_dict = summary.to_dict()
    assert summary_dict["total_queries"] == 3
    assert summary_dict["all_optimal"] is True


def test_profile_search_pruning_empty_and_suboptimal() -> None:
    grid = _build_test_grid_graph()
    profiler = AlgorithmicProfiler()

    # Empty queries
    empty_summary = profiler.profile_search_pruning(grid, [])
    assert empty_summary.total_queries == 0
    assert empty_summary.total_nodes_pruned == 0
    assert empty_summary.to_dict()["speedup_factor"] == 1.0

    # Inadmissible heuristic (multiplied by 1000) that could produce suboptimal path
    def bad_heuristic(curr: Node, goal: Node) -> float:
        return euclidean_distance(curr, goal) * 1000.0

    sub_summary = profiler.profile_search_pruning(
        grid,
        [("0_0", "3_3")],
        heuristic=bad_heuristic,
    )
    assert sub_summary.total_queries == 1


def test_profile_dynamic_rerouting_latency() -> None:
    # Build graph with primary path and alternative detour:
    # A -> B -> D (primary, cost 200)
    # A -> C -> D (detour, cost 220)
    g = Graph()
    g.add_node(Node(node_id="A", coordinates=(-71.00, 42.00)))
    g.add_node(Node(node_id="B", coordinates=(-71.01, 42.00)))
    g.add_node(Node(node_id="C", coordinates=(-71.00, 42.01)))
    g.add_node(Node(node_id="D", coordinates=(-71.01, 42.01)))

    g.add_edge(Edge(source_id="A", destination_id="B", cost=100.0))
    g.add_edge(Edge(source_id="B", destination_id="D", cost=100.0))
    g.add_edge(Edge(source_id="A", destination_id="C", cost=110.0))
    g.add_edge(Edge(source_id="C", destination_id="D", cost=110.0))

    profiler = AlgorithmicProfiler()
    dist = profiler.profile_dynamic_rerouting_latency(
        graph=g,
        origin="A",
        target="D",
        edge_to_sever=("B", "D"),
        iterations=20,
        warmup=3,
    )

    assert dist.sample_count == 20
    assert dist.mean_us > 0.0
    assert dist.p50_us > 0.0
    assert dist.max_us >= dist.min_us
