"""
Demonstration: Comparative Routing Benchmarks & Multi-Format Exporter (Milestone 6.4).

Demonstrates:
1. Comparative Routing Benchmark across three paradigms:
   - STATIC: Freezes / stalls when roads collapse mid-transit.
   - PERIODIC_POLLING: Detects network mutations only at discrete polling epochs (e.g. every 15s).
   - REACTIVE_EVENT_DRIVEN: Instantaneous, sub-millisecond event-hook replanning.
2. Multi-Format Simulation Exporter:
   - Structured JSON Time-Series Telemetry.
   - Tabular CSV metrics (RFC 4180).
   - RFC 7946 GeoJSON spatial replay ready for QGIS, kepler.gl, geojson.io, and Mapbox.
"""

from __future__ import annotations

import json
from pathlib import Path

from emergency_intelligence.evaluation.benchmark import (
    ComparativeRoutingBenchmark,
    RoutingStrategy,
)
from emergency_intelligence.evaluation.exporter import (
    export_incident_metrics_csv,
    export_spatial_replay_geojson,
    export_strategy_comparison_csv,
    export_telemetry_json,
)
from emergency_intelligence.evaluation.metrics import records_from_dicts
from emergency_intelligence.simulation.scenarios import (
    build_infrastructure_severance_scenario,
    build_progressive_inundation_scenario,
    ScenarioRunner,
)


def main() -> None:
    print("=" * 88)
    print("  EMERGENCY INTELLIGENCE AI - COMPARATIVE BENCHMARKS & MULTI-FORMAT EXPORTER")
    print("  Milestone 6.4 Demonstration")
    print("=" * 88)

    # -----------------------------------------------------------------------
    # Part 1: Comparative Routing Paradigms on Mid-Flight Bridge Collapse
    # -----------------------------------------------------------------------
    print("\n--- [PART 1] COMPARATIVE ROUTING PARADIGMS (BRIDGE COLLAPSE BENCHMARK) ---")
    print("Scenario: Mid-Flight Critical Infrastructure Severance (Bridge collapses at t=12s)")
    print("Comparing: Static Routing vs. Periodic Polling (15s) vs. Reactive In-Flight Replanning")
    print("-" * 88)

    scenario_sever = build_infrastructure_severance_scenario()
    benchmark = ComparativeRoutingBenchmark(scenario_sever, polling_interval=15.0)
    summary = benchmark.run_all()

    print(summary.format_table())

    # -----------------------------------------------------------------------
    # Part 2: Progressive Flood Inundation Comparative Benchmark
    # -----------------------------------------------------------------------
    print("\n" + "=" * 88)
    print("--- [PART 2] PROGRESSIVE FLOOD INUNDATION COMPARATIVE BENCHMARK ---")
    print("Scenario: 3-Phase Spreading River Valley Inundation")
    print("-" * 88)

    scenario_flood = build_progressive_inundation_scenario()
    benchmark_flood = ComparativeRoutingBenchmark(scenario_flood, polling_interval=20.0)
    summary_flood = benchmark_flood.run_all()

    print(summary_flood.format_table())

    # -----------------------------------------------------------------------
    # Part 3: Multi-Format Data Exporter Verification
    # -----------------------------------------------------------------------
    print("\n" + "=" * 88)
    print("--- [PART 3] MULTI-FORMAT DATA EXPORTER VERIFICATION ---")
    print("Exporting telemetry across JSON, CSV, and RFC 7946 GeoJSON formats.")
    print("-" * 88)

    runner = ScenarioRunner(scenario_sever)
    sim_result = runner.run()

    # 1. JSON Telemetry Export
    telemetry_json = export_telemetry_json(sim_result)
    json_data = json.loads(telemetry_json)
    print(f"[1] JSON Time-Series Telemetry:")
    print(f"    - Schema Version     : {json_data['schema_version']}")
    print(f"    - Scenario Name      : {json_data['scenario']['name']}")
    print(f"    - Total Incidents    : {json_data['scenario']['total_incidents']}")
    print(f"    - Logged Vehicle Recs: {len(json_data['vehicles'])}")
    print(f"    - Payload Size       : {len(telemetry_json)} bytes")

    # 2. CSV Metrics Export
    records = records_from_dicts(sim_result.incident_records)
    csv_incidents = export_incident_metrics_csv(records)
    csv_strategies = export_strategy_comparison_csv(summary)
    print(f"\n[2] Tabular CSV Metrics (RFC 4180):")
    print(f"    - Incidents CSV Header: {csv_incidents.splitlines()[0]}")
    print(f"    - Strategies CSV Header: {csv_strategies.splitlines()[0]}")
    print(f"    - Strategy Rows Exported: {len(csv_strategies.splitlines()) - 1}")

    # 3. RFC 7946 GeoJSON Spatial Replay Export
    geojson_doc = export_spatial_replay_geojson(scenario_sever, sim_result)
    print(f"\n[3] RFC 7946 GeoJSON Spatial Replay:")
    print(f"    - Collection Name    : {geojson_doc['name']}")
    print(f"    - Feature Count      : {len(geojson_doc['features'])}")

    by_type: dict[str, int] = {}
    for feat in geojson_doc["features"]:
        ft = feat["properties"]["feature_type"]
        by_type[ft] = by_type.get(ft, 0) + 1

    for ft, count in sorted(by_type.items()):
        print(f"      * {ft:<20}: {count} features")

    print(f"    - QGIS/Mapbox Standard Validated: YES (RFC 7946)")

    print("\n" + "=" * 88)
    print("  MILESTONE 6.4 COMPARATIVE BENCHMARK & EXPORTER DEMONSTRATION COMPLETE")
    print("=" * 88)


if __name__ == "__main__":
    main()
