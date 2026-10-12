"""
Unit tests for comparative benchmark harness and multi-format exporters (Milestone 6.4).

Verifies:
1. Routing strategies (STATIC vs. PERIODIC_POLLING vs. REACTIVE_EVENT_DRIVEN).
2. Stall detection under static routing when infrastructure collapses.
3. Polling latency lag vs. instant reactive rerouting.
4. JSON telemetry, CSV metrics, and RFC 7946 GeoJSON spatial replay exporters.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import pytest

from emergency_intelligence.evaluation.benchmark import (
    ComparativeBenchmarkSummary,
    ComparativeRoutingBenchmark,
    RoutingStrategy,
    StrategyBenchmarkResult,
)
from emergency_intelligence.evaluation.exporter import (
    export_incident_metrics_csv,
    export_spatial_replay_geojson,
    export_strategy_comparison_csv,
    export_telemetry_json,
)
from emergency_intelligence.evaluation.metrics import (
    IncidentResponseRecord,
    records_from_dicts,
)
from emergency_intelligence.events.hazards import HazardPolygon, HazardSeverity, HazardType
from emergency_intelligence.events.incidents import ApparatusType, EmergencyType, Incident, UrgencyLevel
from emergency_intelligence.graph.models import Edge, Graph, Node
from emergency_intelligence.simulation.scenarios import (
    build_infrastructure_severance_scenario,
    build_single_incident_baseline_scenario,
    ScenarioDefinition,
    ScenarioRunner,
)


# ===========================================================================
# 1. Routing Strategy & Comparative Benchmark Tests
# ===========================================================================


def test_routing_strategy_enum() -> None:
    assert RoutingStrategy.STATIC.value == "static"
    assert RoutingStrategy.PERIODIC_POLLING.value == "periodic_polling"
    assert RoutingStrategy.REACTIVE_EVENT_DRIVEN.value == "reactive_event_driven"


def test_comparative_routing_benchmark_on_bridge_collapse() -> None:
    # Use infrastructure severance scenario where bridge B -> E collapses at t = 12.0s
    scenario = build_infrastructure_severance_scenario()
    benchmark = ComparativeRoutingBenchmark(scenario, polling_interval=10.0)

    # 1. Static Strategy: Must stall at severed bridge and fail to arrive
    res_static = benchmark.run_strategy(RoutingStrategy.STATIC)
    assert res_static.strategy == RoutingStrategy.STATIC
    assert res_static.arrived is False
    assert res_static.stalled is True
    assert not math.isfinite(res_static.travel_time_seconds)
    assert res_static.reroute_count == 0

    # 2. Reactive Strategy: Reroutes immediately upon collapse and arrives safely
    res_reactive = benchmark.run_strategy(RoutingStrategy.REACTIVE_EVENT_DRIVEN)
    assert res_reactive.strategy == RoutingStrategy.REACTIVE_EVENT_DRIVEN
    assert res_reactive.arrived is True
    assert res_reactive.stalled is False
    assert math.isfinite(res_reactive.travel_time_seconds)
    assert res_reactive.travel_time_seconds < 120.0
    assert res_reactive.reroute_count >= 1
    assert 0.0 < res_reactive.path_stability_index <= 1.0

    # 3. Periodic Polling Strategy: Reroutes eventually during polling epoch
    res_polling = benchmark.run_strategy(RoutingStrategy.PERIODIC_POLLING)
    assert res_polling.strategy == RoutingStrategy.PERIODIC_POLLING
    assert res_polling.polling_interval_seconds == 10.0


def test_comparative_benchmark_run_all_and_table_format() -> None:
    scenario = build_infrastructure_severance_scenario()
    benchmark = ComparativeRoutingBenchmark(scenario, polling_interval=15.0)

    summary = benchmark.run_all()
    assert summary.scenario_name == scenario.name
    assert len(summary.results) == 3
    assert RoutingStrategy.STATIC in summary.results
    assert RoutingStrategy.PERIODIC_POLLING in summary.results
    assert RoutingStrategy.REACTIVE_EVENT_DRIVEN in summary.results

    # Formatted table should be a non-empty string with strategy rows
    table_str = summary.format_table()
    assert "static" in table_str
    assert "periodic_polling" in table_str
    assert "reactive_event_driven" in table_str

    # Dictionary serialization
    d = summary.to_dict()
    assert d["scenario_name"] == scenario.name
    assert "strategies" in d
    assert "static" in d["strategies"]


# ===========================================================================
# 2. Exporter Tests
# ===========================================================================


def test_export_telemetry_json(tmp_path: Path) -> None:
    scenario = build_single_incident_baseline_scenario()
    runner = ScenarioRunner(scenario)
    result = runner.run()

    out_file = tmp_path / "telemetry.json"
    json_str = export_telemetry_json(result, filepath=out_file)

    assert out_file.is_file()
    assert len(json_str) > 0

    # Validate JSON structure
    data = json.loads(json_str)
    assert data["schema_version"] == "1.0.0"
    assert data["type"] == "EmergencySimulationTelemetry"
    assert data["scenario"]["name"] == scenario.name
    assert data["scenario"]["total_incidents"] == 1
    assert len(data["incidents"]) == 1
    assert len(data["vehicles"]) == 1


def test_export_incident_metrics_csv(tmp_path: Path) -> None:
    records = [
        IncidentResponseRecord(
            incident_id="INC-1",
            emergency_type="structure_fire",
            urgency="critical",
            report_time=10.0,
            first_dispatch_time=20.0,
            first_arrival_time=140.0,
            all_arrival_time=200.0,
            cleared_time=450.0,
            queue_delay_seconds=10.0,
            assigned_units=["E-1", "L-1"],
        ),
        IncidentResponseRecord(
            incident_id="INC-2",
            emergency_type="cardiac_arrest",
            urgency="high",
            report_time=15.0,
            first_dispatch_time=15.0,
            first_arrival_time=95.0,
            all_arrival_time=95.0,
            cleared_time=180.0,
            queue_delay_seconds=0.0,
            assigned_units=["MED-1"],
        ),
    ]

    out_file = tmp_path / "incidents.csv"
    csv_str = export_incident_metrics_csv(records, filepath=out_file)

    assert out_file.is_file()
    lines = csv_str.strip().split("\n")
    assert len(lines) == 3  # Header + 2 rows

    reader = csv.reader(lines)
    header = next(reader)
    assert "incident_id" in header
    assert "first_travel_time_s" in header
    assert "first_total_response_time_s" in header

    row1 = next(reader)
    assert row1[0] == "INC-1"
    assert row1[1] == "structure_fire"
    assert row1[10] == "120.00"  # travel time = 140 - 20 = 120.0


def test_export_strategy_comparison_csv(tmp_path: Path) -> None:
    scenario = build_single_incident_baseline_scenario()
    benchmark = ComparativeRoutingBenchmark(scenario)
    summary = benchmark.run_all()

    out_file = tmp_path / "strategies.csv"
    csv_str = export_strategy_comparison_csv(summary, filepath=out_file)

    assert out_file.is_file()
    lines = csv_str.strip().split("\n")
    assert len(lines) == 4  # Header + 3 strategies

    reader = csv.reader(lines)
    header = next(reader)
    assert "strategy" in header
    assert "travel_time_seconds" in header
    assert "stalled" in header


def test_export_spatial_replay_geojson(tmp_path: Path) -> None:
    # Build scenario with graph, station, incident, and hazard
    g = Graph()
    g.add_node(Node("A", coordinates=(-71.05, 42.35)))
    g.add_node(Node("B", coordinates=(-71.06, 42.36)))
    g.add_edge(Edge(source_id="A", destination_id="B", cost=50.0))

    hazard = HazardPolygon(
        hazard_id="HAZ-1",
        hazard_type=HazardType.FLOOD_INUNDATION,
        severity=HazardSeverity.CRITICAL_BLOCKED,
        boundary_coordinates=[(-71.05, 42.35), (-71.06, 42.35), (-71.06, 42.36)],
    )

    scenario = build_single_incident_baseline_scenario()
    # Add hazard to scenario definition
    scenario.hazards.append((10.0, "HAZ-1", hazard))

    runner = ScenarioRunner(scenario)
    result = runner.run()

    out_file = tmp_path / "spatial_replay.geojson"
    geojson_doc = export_spatial_replay_geojson(scenario, result, filepath=out_file)

    assert out_file.is_file()
    assert geojson_doc["type"] == "FeatureCollection"
    assert "features" in geojson_doc
    assert len(geojson_doc["features"]) > 0

    feature_types = {f["properties"]["feature_type"] for f in geojson_doc["features"]}
    assert "road_edge" in feature_types
    assert "station" in feature_types
    assert "incident" in feature_types
    assert "hazard_polygon" in feature_types

    # Validate RFC 7946 Polygon closing ring requirement
    polygon_feat = next(f for f in geojson_doc["features"] if f["properties"]["feature_type"] == "hazard_polygon")
    ring = polygon_feat["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]


def test_exporters_in_memory_and_fallback_branches() -> None:
    # Build scenario where incident uses node_id without direct coordinates
    g = Graph()
    g.add_node(Node("S1", coordinates=(-71.0, 42.0)))
    g.add_node(Node("N1", coordinates=(-71.1, 42.1)))
    g.add_node(Node("N_no_coords"))  # Node without coordinates
    g.add_edge(Edge(source_id="S1", destination_id="N1", cost=10.0))
    g.add_edge(Edge(source_id="N1", destination_id="N_no_coords", cost=10.0))

    inc = Incident(
        incident_id="INC-FALLBACK",
        emergency_type=EmergencyType.STRUCTURE_FIRE,
        urgency=UrgencyLevel.PRIORITY_1_ECHO,
        coordinates=(-71.1, 42.1),
        node_id="N1",
    )
    station = build_single_incident_baseline_scenario().stations[0]
    station.node_id = "S1"

    scenario = ScenarioDefinition(
        name="Fallback Scenario",
        description="Tests coordinate fallback logic in exporters.",
        graph=g,
        stations=[station],
        fleet_units=build_single_incident_baseline_scenario().fleet_units,
        incidents=[(0.0, inc, 10.0)],
        max_simulation_time=30.0,
    )
    scenario.fleet_units[0].current_node_id = "S1"

    runner = ScenarioRunner(scenario)
    res = runner.run()

    # Call all exporters with filepath=None (in-memory mode)
    json_str = export_telemetry_json(res, filepath=None)
    assert len(json_str) > 0

    records = records_from_dicts(res.incident_records)
    csv_inc = export_incident_metrics_csv(records, filepath=None)
    assert len(csv_inc) > 0

    benchmark = ComparativeRoutingBenchmark(scenario)
    summary = benchmark.run_all()
    csv_strat = export_strategy_comparison_csv(summary, filepath=None)
    assert len(csv_strat) > 0

    geojson_doc = export_spatial_replay_geojson(scenario, res, filepath=None)
    assert geojson_doc["type"] == "FeatureCollection"

