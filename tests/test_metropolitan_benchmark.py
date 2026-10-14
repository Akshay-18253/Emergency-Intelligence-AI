"""
Unit tests for Milestone 7.5: Metropolitan City Benchmark & End-to-End Integration Suite.
========================================================================================
Validates:
  1. Synthetic and city-scale metropolitan district generation with road hierarchy and river bridges.
  2. Integration of all Phase 7 external subsystems (OSM, POIs, SRTM DEM, USGS Gauges, Weather).
  3. Execution of all 4 operational routing strategies (Flat Baseline, Elevation-Aware, Flood Detour, Clinical).
  4. Metric computations: DDF, EDF, search space pruning, and SHA-256 integrity hash.
  5. Zero-dependency Leaflet GIS interactive map export.
  6. Resilient edge cases: disconnected targets, missing clinical capabilities, extreme terrain.
"""

from __future__ import annotations

import os
import tempfile
from typing import Optional
import unittest

from emergency_intelligence.events.incidents import ApparatusType
from emergency_intelligence.external.benchmark import (
    MetropolitanBenchmarkRunner,
    MetropolitanDisasterScenario,
    build_metropolitan_benchmark_district,
)
from emergency_intelligence.external.elevation import (
    ElevationProvider,
)
from emergency_intelligence.external.hydrology import (
    FloodStage,
    WeatherAlertLevel,
    WeatherConditions,
)
from emergency_intelligence.external.overpass import (
    ClinicalCapability,
    EmergencyPOIType,
)
from emergency_intelligence.graph.models import Edge, Graph, Node


class TestMetropolitanBenchmark(unittest.TestCase):
    """Test suite for the metropolitan disaster benchmark and integration harness."""

    def setUp(self) -> None:
        """Construct a standardized metropolitan benchmark environment."""
        (
            self.graph,
            self.pois,
            self.elevation_provider,
            self.river_gauge,
            self.weather,
        ) = build_metropolitan_benchmark_district(
            center_lat=47.6050,
            center_lon=-122.3300,
            grid_rows=6,
            grid_cols=6,
            spacing_m=300.0,
        )
        self.runner = MetropolitanBenchmarkRunner(
            graph=self.graph,
            pois=self.pois,
            elevation_provider=self.elevation_provider,
        )
        self.scenario = MetropolitanDisasterScenario(
            scenario_id="scenario_seattle_flood_trauma",
            name="Seattle Central Flood & Trauma Scenario",
            description="Major river flooding severing lowland causeways with critical trauma triage.",
            bounding_box=(47.59, -122.35, 47.62, -122.31),
            origin_node_id="N_0_0",       # West Waterfront bottom
            destination_node_id="N_3_5",  # East First Hill center
            apparatus_type=ApparatusType.LADDER_TRUCK,
            required_clinical_capabilities={ClinicalCapability.TRAUMA_LEVEL_1, ClinicalCapability.BURN_CENTER},
            river_gauge=self.river_gauge,
            weather=self.weather,
        )

    def test_district_construction_integrity(self) -> None:
        """Validate topological and geographic properties of the generated metropolitan district."""
        self.assertEqual(self.graph.node_count(), 36)
        self.assertGreater(self.graph.edge_count(), 100)

        # Verify all nodes have valid coordinates
        for node_id in self.graph.node_ids():
            node = self.graph.get_node(node_id)
            self.assertIsNotNone(node.coordinates)
            lon, lat = node.coordinates
            self.assertAlmostEqual(lat, 47.6050, delta=0.03)
            self.assertAlmostEqual(lon, -122.3300, delta=0.03)

        # Verify cross-river bridges exist
        river_bridges = [
            e for node_id in self.graph.node_ids()
            for e in self.graph.get_neighbors(node_id)
            if e.attributes.get("is_river_bridge")
        ]
        self.assertGreaterEqual(len(river_bridges), 6)

        # Verify POIs
        self.assertEqual(len(self.pois), 5)
        hospitals = [p for p in self.pois if p.poi_type == EmergencyPOIType.HOSPITAL]
        stations = [p for p in self.pois if p.poi_type == EmergencyPOIType.FIRE_STATION]
        self.assertEqual(len(hospitals), 3)
        self.assertEqual(len(stations), 2)

        # Verify elevation and hydrology
        self.assertEqual(self.river_gauge.flood_stage, FloodStage.MAJOR)
        self.assertEqual(self.weather.alert_level, WeatherAlertLevel.WARNING)

    def test_benchmark_runner_initialization(self) -> None:
        """Verify runner successfully binds POIs, creates fleet, and enriches graph with elevation."""
        self.assertEqual(len(self.runner.bindings), 5)
        self.assertGreaterEqual(self.runner.elevation_summary.edges_enriched, 100)
        self.assertGreater(self.runner.elevation_summary.max_elevation_m, self.runner.elevation_summary.min_elevation_m)
        self.assertGreater(len(self.runner.fleet_manager.list_units()), 0)

    def test_full_benchmark_execution(self) -> None:
        """Execute end-to-end benchmark and verify all 4 operational routing strategies."""
        report = self.runner.run_benchmark(self.scenario)

        # Validate scenario header
        self.assertEqual(report.scenario_name, self.scenario.name)
        self.assertEqual(report.network_node_count, 36)
        self.assertEqual(report.total_facilities_bound, 5)
        self.assertEqual(report.active_flood_stage, FloodStage.MAJOR)
        self.assertGreater(report.flooded_edges_closed, 0)

        # Verify Strategy 1: Flat Baseline
        self.assertIn("Flat_Baseline", report.strategy_results)
        flat_res = report.strategy_results["Flat_Baseline"]
        self.assertTrue(flat_res.path_found)
        self.assertGreater(len(flat_res.node_path), 2)
        self.assertGreater(flat_res.distance_2d_meters, 0.0)
        self.assertGreater(flat_res.duration_seconds, 0.0)
        self.assertGreater(flat_res.nodes_explored, 0)
        self.assertGreater(flat_res.execution_latency_ms, 0.0)

        # Verify Strategy 2: Elevation-Aware 3D
        self.assertIn("Elevation_Aware_3D", report.strategy_results)
        elev_res = report.strategy_results["Elevation_Aware_3D"]
        self.assertTrue(elev_res.path_found)
        self.assertGreaterEqual(elev_res.distance_3d_meters, elev_res.distance_2d_meters)
        self.assertGreaterEqual(elev_res.duration_seconds, flat_res.duration_seconds)
        self.assertGreaterEqual(report.elevation_delay_factor, 1.0)
        self.assertGreater(elev_res.elevation_gain_meters, 0.0)

        # Verify Strategy 3: Dynamic Disaster Detour
        self.assertIn("Disaster_Detour", report.strategy_results)
        detour_res = report.strategy_results["Disaster_Detour"]
        self.assertTrue(detour_res.path_found)
        # Because low-lying causeway bridges are closed, detour takes longer or equal time
        self.assertGreaterEqual(report.detour_delay_factor, 1.0)

        # Verify Strategy 4: Specialized Clinical Transport
        self.assertIn("Clinical_Specialized", report.strategy_results)
        clin_res = report.strategy_results["Clinical_Specialized"]
        self.assertTrue(clin_res.path_found)
        self.assertEqual(clin_res.target_facility_trauma_level, 1)
        self.assertIn(ClinicalCapability.BURN_CENTER, clin_res.target_facility_capabilities)
        self.assertIn(ClinicalCapability.TRAUMA_LEVEL_1, clin_res.target_facility_capabilities)
        self.assertIsNotNone(clin_res.target_facility_name)

        # Verify algorithmic and audit metrics
        self.assertGreaterEqual(report.search_pruning_ratio, 0.0)
        self.assertGreater(report.total_benchmark_latency_ms, 0.0)
        self.assertEqual(len(report.integrity_hash), 64)
        self.assertEqual(report.integrity_hash, report.compute_integrity_hash())

        # Verify serialization
        data = report.to_dict()
        self.assertEqual(data["scenario_name"], self.scenario.name)
        self.assertEqual(data["active_flood_stage"], "major")
        self.assertIn("Flat_Baseline", data["strategy_results"])

    def test_export_gis_map(self) -> None:
        """Verify HTML GIS interactive map generation and disk export."""
        report = self.runner.run_benchmark(self.scenario)

        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = os.path.join(tmpdir, "test_map.html")
            html = self.runner.export_gis_map(report, self.scenario, output_file_path=out_file)

            self.assertTrue(os.path.exists(out_file))
            self.assertGreater(os.path.getsize(out_file), 5000)
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("leaflet", html.lower())
            self.assertIn("Metropolitan Benchmark GIS", html)
            self.assertIn("Metropolitan Level 1 Trauma Center", html)
            self.assertIn("Specialized Clinical Transport", html)

    def test_unreachable_clinical_capability_fallback(self) -> None:
        """Verify scenario with impossible capability requirements cleanly returns path_found=False."""
        unreal_scenario = MetropolitanDisasterScenario(
            scenario_id="scenario_unreal",
            name="Unreachable Capability Scenario",
            description="Testing requirement for capability no hospital possesses.",
            bounding_box=(47.59, -122.35, 47.62, -122.31),
            origin_node_id="N_0_0",
            destination_node_id="N_3_5",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            required_clinical_capabilities={ClinicalCapability.HAZMAT_DECON},
            river_gauge=self.river_gauge,
            weather=self.weather,
        )
        report = self.runner.run_benchmark(unreal_scenario)
        clin_res = report.strategy_results["Clinical_Specialized"]
        self.assertFalse(clin_res.path_found)
        self.assertIsNone(clin_res.target_facility_name)

    def test_path_metrics_extractor_edge_cases(self) -> None:
        """Verify _extract_path_metrics handles empty, single-node, and invalid paths."""
        empty_metrics = self.runner._extract_path_metrics(self.graph, [])
        self.assertEqual(empty_metrics["dist_2d"], 0.0)
        self.assertEqual(empty_metrics["gain_m"], 0.0)

        single_metrics = self.runner._extract_path_metrics(self.graph, ["N_0_0"])
        self.assertEqual(single_metrics["dist_2d"], 0.0)

        # Path with missing edge
        missing_edge_metrics = self.runner._extract_path_metrics(self.graph, ["N_0_0", "NON_EXISTENT"])
        self.assertEqual(missing_edge_metrics["dist_2d"], 0.0)

    def test_disconnected_destination_node(self) -> None:
        """Verify scenario with disconnected isolated destination handles unreachable results."""
        self.graph.add_node(Node("ISOLATED_NODE", coordinates=(-122.33, 47.60)))
        disconnected_scenario = MetropolitanDisasterScenario(
            scenario_id="scenario_disconnected",
            name="Disconnected Destination Scenario",
            description="Testing unreachable isolated node.",
            bounding_box=(47.59, -122.35, 47.62, -122.31),
            origin_node_id="N_0_0",
            destination_node_id="ISOLATED_NODE",
            apparatus_type=ApparatusType.FIRE_ENGINE,
            required_clinical_capabilities={ClinicalCapability.CARDIAC_CARE},
            river_gauge=self.river_gauge,
            weather=self.weather,
        )
        report = self.runner.run_benchmark(disconnected_scenario)
        self.assertFalse(report.strategy_results["Flat_Baseline"].path_found)
        self.assertFalse(report.strategy_results["Elevation_Aware_3D"].path_found)
        self.assertFalse(report.strategy_results["Disaster_Detour"].path_found)

    def test_export_gis_map_with_calm_weather(self) -> None:
        """Verify export_gis_map handles scenarios with no weather alert without error."""
        calm_scenario = MetropolitanDisasterScenario(
            scenario_id="scenario_calm",
            name="Calm Weather Scenario",
            description="Testing map export with no weather hazard polygon.",
            bounding_box=(47.59, -122.35, 47.62, -122.31),
            origin_node_id="N_0_0",
            destination_node_id="N_3_5",
            apparatus_type=ApparatusType.FIRE_ENGINE,
            required_clinical_capabilities={ClinicalCapability.TRAUMA_LEVEL_1},
            river_gauge=self.river_gauge,
            weather=WeatherConditions(
                latitude=47.60,
                longitude=-122.33,
                timestamp=self.weather.timestamp,
                weather_code=0,
                temperature_c=20.0,
                wind_speed_kmh=5.0,
                precipitation_mm=0.0,
                alert_level=WeatherAlertLevel.NONE,
            ),
        )
        report = self.runner.run_benchmark(calm_scenario)
        html = self.runner.export_gis_map(report, calm_scenario)
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Calm Weather Scenario", html)

    def test_extract_path_metrics_with_custom_graph_having_get_edge(self) -> None:
        """Verify _extract_path_metrics uses graph.get_edge if provided."""
        class MockGraphWithGetEdge:
            def __init__(self, inner: Graph) -> None:
                self.inner = inner

            def get_edge(self, u: str, v: str) -> Optional[Edge]:
                for e in self.inner.get_neighbors(u):
                    if e.destination_id == v:
                        return e
                return None

        mock_g = MockGraphWithGetEdge(self.graph)
        metrics = self.runner._extract_path_metrics(mock_g, ["N_0_0", "N_1_0"])
        self.assertGreater(metrics["dist_2d"], 0.0)


if __name__ == "__main__":
    unittest.main()
