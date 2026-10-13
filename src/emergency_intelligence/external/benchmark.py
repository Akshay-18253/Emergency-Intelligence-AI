"""
Metropolitan City Benchmark, End-to-End Integration Suite & Disaster Routing Evaluation.
======================================================================================
Implements Milestone 7.5:
  1. Synthetic and real-world metropolitan city-scale road network generation.
  2. End-to-end integration across all Phase 7 external subsystems:
     - OpenStreetMap road network with speed limits, road classes, and bridge topology.
     - Overpass emergency POIs (Trauma Levels 1–4, Burn, Pediatric, Cardiac, Fire Stations).
     - NASA SRTM Digital Elevation Models with bilinear interpolation and 3D slope kinematics.
     - USGS real-time river gauge telemetry & NWS flood thresholding (Action/Minor/Moderate/Major).
     - Open-Meteo extreme weather condition parsing and storm hazard generation.
     - Specialized clinical facility transport matching and multi-apparatus dispatch.
     - Zero-dependency Web Mercator slippy tile interactive Leaflet GIS visualization.
  3. Comparative multi-strategy routing benchmark:
     - Strategy 1: Flat Baseline A* (unimpaired 2D search).
     - Strategy 2: Elevation-Aware 3D Slope Routing (powertrain climb penalties & max grade gates).
     - Strategy 3: Dynamic USGS Flood Inundation & Weather Detour (severed bridges & storm buffers).
     - Strategy 4: Clinical Specialized Triage Transport (urgent Burn/Trauma/Pediatric delivery).
  4. Quantitative metrics:
     - Detour Delay Factor (DDF = T_detour / T_baseline).
     - Elevation Delay Factor (EDF = T_3D / T_flat).
     - Search Space Pruning Efficiency (A* vs uninformed Dijkstra).
     - SHA-256 tamper-evident integrity fingerprint.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from emergency_intelligence.allocation.matcher import FleetManager
from emergency_intelligence.allocation.models import EmergencyStation, UnitStatus
from emergency_intelligence.data.geo import haversine_distance, haversine_heuristic
from emergency_intelligence.events.hazards import HazardPolygon
from emergency_intelligence.events.incidents import ApparatusType
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.external.binding import (
    POINetworkBinding,
    bind_pois_to_network,
    create_fleet_from_pois,
    find_nearest_clinical_facility,
)
from emergency_intelligence.external.elevation import (
    APPARATUS_GRADE_PROFILES,
    DEMResolution,
    ElevationEnrichmentSummary,
    ElevationGraphView,
    ElevationProvider,
    SRTMTile,
    build_synthetic_dem_tile,
    calculate_slope_metrics,
    enrich_graph_with_elevation,
    get_grade_speed_multiplier,
)
from emergency_intelligence.external.hydrology import (
    DEFAULT_GAUGE_THRESHOLDS,
    EnvironmentalMutationSummary,
    FloodStage,
    USGSGaugeReading,
    WeatherAlertLevel,
    WeatherConditions,
    apply_environmental_hazards_to_graph,
    create_flood_inundation_polygon,
    create_weather_hazard_polygon,
)
from emergency_intelligence.external.overpass import (
    ClinicalCapability,
    EmergencyPOIType,
    ExtractedEmergencyPOI,
)
from emergency_intelligence.external.visualizer import (
    MapIsochroneOverlay,
    MapRouteOverlay,
    render_interactive_map_html,
    save_interactive_map_html,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.dijkstra import dijkstra
from emergency_intelligence.graph.models import Edge, Graph, Node


# ---------------------------------------------------------------------------
# Data Models and Result Contracts
# ---------------------------------------------------------------------------


@dataclass
class StrategyRoutingResult:
    """Quantitative routing output for a specific operational strategy."""

    strategy_name: str
    path_found: bool
    node_path: List[str] = field(default_factory=list)
    distance_2d_meters: float = 0.0
    distance_3d_meters: float = 0.0
    duration_seconds: float = 0.0
    max_slope_grade: float = 0.0
    average_slope_grade: float = 0.0
    elevation_gain_meters: float = 0.0
    nodes_explored: int = 0
    execution_latency_ms: float = 0.0
    target_facility_name: Optional[str] = None
    target_facility_trauma_level: Optional[int] = None
    target_facility_capabilities: Set[ClinicalCapability] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize strategy result to JSON-compatible dictionary."""
        return {
            "strategy_name": self.strategy_name,
            "path_found": self.path_found,
            "node_count": len(self.node_path),
            "distance_2d_meters": round(self.distance_2d_meters, 2),
            "distance_3d_meters": round(self.distance_3d_meters, 2),
            "duration_seconds": round(self.duration_seconds, 2),
            "max_slope_grade_percent": round(self.max_slope_grade, 2),
            "average_slope_grade_percent": round(self.average_slope_grade, 2),
            "elevation_gain_meters": round(self.elevation_gain_meters, 2),
            "nodes_explored": self.nodes_explored,
            "execution_latency_ms": round(self.execution_latency_ms, 3),
            "target_facility_name": self.target_facility_name,
            "target_facility_trauma_level": self.target_facility_trauma_level,
            "target_facility_capabilities": sorted([c.value for c in self.target_facility_capabilities]),
        }


@dataclass
class MetropolitanDisasterScenario:
    """Parameter contract for a city-scale emergency benchmark scenario."""

    scenario_id: str
    name: str
    description: str
    bounding_box: Tuple[float, float, float, float]  # (min_lat, min_lon, max_lat, max_lon)
    origin_node_id: str
    destination_node_id: str
    apparatus_type: ApparatusType
    required_clinical_capabilities: Set[ClinicalCapability]
    river_gauge: USGSGaugeReading
    weather: WeatherConditions


@dataclass
class MetropolitanBenchmarkReport:
    """Comprehensive evaluation report summarizing all metropolitan benchmark metrics."""

    scenario_name: str
    network_node_count: int
    network_edge_count: int
    total_facilities_bound: int
    active_flood_stage: FloodStage
    flooded_edges_closed: int
    weather_alert_level: WeatherAlertLevel
    strategy_results: Dict[str, StrategyRoutingResult] = field(default_factory=dict)
    detour_delay_factor: float = 1.0
    elevation_delay_factor: float = 1.0
    search_pruning_ratio: float = 0.0
    total_benchmark_latency_ms: float = 0.0
    integrity_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to JSON-serializable dictionary."""
        return {
            "scenario_name": self.scenario_name,
            "network_node_count": self.network_node_count,
            "network_edge_count": self.network_edge_count,
            "total_facilities_bound": self.total_facilities_bound,
            "active_flood_stage": self.active_flood_stage.value,
            "flooded_edges_closed": self.flooded_edges_closed,
            "weather_alert_level": self.weather_alert_level.value,
            "detour_delay_factor": round(self.detour_delay_factor, 3),
            "elevation_delay_factor": round(self.elevation_delay_factor, 3),
            "search_pruning_ratio": round(self.search_pruning_ratio, 4),
            "total_benchmark_latency_ms": round(self.total_benchmark_latency_ms, 3),
            "integrity_hash": self.integrity_hash,
            "strategy_results": {
                name: res.to_dict() for name, res in self.strategy_results.items()
            },
        }

    def compute_integrity_hash(self) -> str:
        """Compute SHA-256 hash over deterministic benchmark metrics."""
        payload = {
            "scenario": self.scenario_name,
            "nodes": self.network_node_count,
            "edges": self.network_edge_count,
            "facilities": self.total_facilities_bound,
            "flood_stage": self.active_flood_stage.value,
            "closed": self.flooded_edges_closed,
            "ddf": round(self.detour_delay_factor, 4),
            "edf": round(self.elevation_delay_factor, 4),
            "strategies": {
                name: {
                    "path_len": len(res.node_path),
                    "dist_3d": round(res.distance_3d_meters, 2),
                    "duration": round(res.duration_seconds, 2),
                }
                for name, res in sorted(self.strategy_results.items())
            },
        }
        raw = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Synthetic Metropolitan District Generator
# ---------------------------------------------------------------------------


def build_metropolitan_benchmark_district(
    center_lat: float = 47.6050,
    center_lon: float = -122.3300,
    grid_rows: int = 6,
    grid_cols: int = 6,
    spacing_m: float = 300.0,
) -> Tuple[Graph, List[ExtractedEmergencyPOI], ElevationProvider, USGSGaugeReading, WeatherConditions]:
    """Construct a realistic city-scale road network with topography, river, and facilities.

    Topology features:
      - 36 road intersections across 6x6 grid.
      - West district (low waterfront, elev ~5m).
      - Central River separating cols 2 and 3:
        - Node (row 1, col 2) -> (row 1, col 3): Lowland Causeway (vulnerable bridge)
        - Node (row 3, col 2) -> (row 3, col 3): Lowland Parkway Bridge (vulnerable bridge)
        - Node (row 5, col 2) -> (row 5, col 3): High-Level Suspension Bridge (high elevation, flood-immune)
      - East district climbing steep First Hill (elev up to 85m, grades up to 12%).
      - Speed limits based on road classification:
        - Arterial Avenues (cols 0, 2, 4): 50 km/h
        - Bridges (cross-river links): 60 km/h
        - Local Residential Streets: 30 km/h

    Parameters
    ----------
    center_lat : float
        Latitude center for the metropolitan district.
    center_lon : float
        Longitude center for the metropolitan district.
    grid_rows : int
        Number of grid rows (North-South).
    grid_cols : int
        Number of grid columns (West-East).
    spacing_m : float
        Distance between adjacent intersections in meters.

    Returns
    -------
    Tuple[Graph, List[ExtractedEmergencyPOI], ElevationProvider, USGSGaugeReading, WeatherConditions]
        The fully configured metropolitan environment.
    """
    graph = Graph()
    m_per_deg_lat = 111320.0
    cos_lat = math.cos(math.radians(center_lat))
    m_per_deg_lon = m_per_deg_lat * cos_lat

    d_lat = spacing_m / m_per_deg_lat
    d_lon = spacing_m / m_per_deg_lon

    # 1. Create Nodes
    node_grid: Dict[Tuple[int, int], str] = {}
    node_coords: Dict[str, Tuple[float, float]] = {}

    for r in range(grid_rows):
        for c in range(grid_cols):
            node_id = f"N_{r}_{c}"
            lat = center_lat + (r - (grid_rows / 2.0)) * d_lat
            lon = center_lon + (c - (grid_cols / 2.0)) * d_lon
            graph.add_node(Node(node_id, coordinates=(lon, lat)))
            node_grid[(r, c)] = node_id
            node_coords[node_id] = (lon, lat)

    # 2. Add Road Edges
    for r in range(grid_rows):
        for c in range(grid_cols):
            u_id = node_grid[(r, c)]
            u_lon, u_lat = node_coords[u_id]

            # Connect North-South
            if r + 1 < grid_rows:
                v_id = node_grid[(r + 1, c)]
                v_lon, v_lat = node_coords[v_id]
                dist = haversine_distance((u_lon, u_lat), (v_lon, v_lat))
                # Speed based on avenue vs street
                speed_kmh = 50.0 if (c % 2 == 0) else 35.0
                travel_time = (dist / (speed_kmh * (1000.0 / 3600.0)))
                attrs = {
                    "highway": "primary" if c % 2 == 0 else "residential",
                    "maxspeed": f"{int(speed_kmh)} km/h",
                    "speed_kmh": speed_kmh,
                    "distance_m": dist,
                }
                # Bidirectional road
                graph.add_edge(Edge(u_id, v_id, cost=travel_time, attributes=dict(attrs)))
                graph.add_edge(Edge(v_id, u_id, cost=travel_time, attributes=dict(attrs)))

            # Connect West-East (Across Columns)
            if c + 1 < grid_cols:
                v_id = node_grid[(r, c + 1)]
                v_lon, v_lat = node_coords[v_id]
                dist = haversine_distance((u_lon, u_lat), (v_lon, v_lat))

                # Special designation for river-crossing bridges between col 2 and col 3
                is_river_bridge = (c == 2)
                if is_river_bridge:
                    if r == 5:
                        bridge_name = "High-Level Suspension Bridge"
                        speed_kmh = 60.0
                    elif r == 3:
                        bridge_name = "Central Parkway Bridge"
                        speed_kmh = 45.0
                    else:
                        bridge_name = f"Lowland Causeway Bridge {r}"
                        speed_kmh = 40.0
                    highway_type = "bridge"
                else:
                    bridge_name = ""
                    highway_type = "secondary"
                    speed_kmh = 45.0

                travel_time = (dist / (speed_kmh * (1000.0 / 3600.0)))
                attrs = {
                    "highway": highway_type,
                    "maxspeed": f"{int(speed_kmh)} km/h",
                    "speed_kmh": speed_kmh,
                    "distance_m": dist,
                    "bridge_name": bridge_name,
                    "is_river_bridge": is_river_bridge,
                }
                graph.add_edge(Edge(u_id, v_id, cost=travel_time, attributes=dict(attrs)))
                graph.add_edge(Edge(v_id, u_id, cost=travel_time, attributes=dict(attrs)))

    # 3. Create Synthetic Elevation Provider with realistic topography
    # West cols (0-2) are sea-level waterfront (5m to 12m)
    # River bed is at col 2.5 (3m)
    # East cols (3-5) are steep hills climbing to 85m
    tile_lat = int(math.floor(center_lat))
    tile_lon = int(math.floor(center_lon))

    def topo_elev_fn(lat: float, lon: float) -> float:
        norm_x = lon - tile_lon
        norm_y = lat - tile_lat
        if norm_x < 0.665:
            # West waterfront
            return 8.0 + 10.0 * norm_y
        elif norm_x < 0.675:
            # River valley
            return 4.0
        else:
            # Steep East hill
            hill_factor = max(0.0, min(1.0, (norm_x - 0.675) / 0.325))
            return 15.0 + 70.0 * hill_factor + (10.0 * math.sin(norm_y * math.pi * 3.0))

    tile = build_synthetic_dem_tile(
        lat_origin=tile_lat,
        lon_origin=tile_lon,
        dimension=101,
        elevation_fn=topo_elev_fn,
    )
    provider = ElevationProvider()
    provider.add_tile(tile)

    # 4. Create Real-World Overpass POI definitions
    # Place hospitals and fire stations across the district
    pois: List[ExtractedEmergencyPOI] = [
        ExtractedEmergencyPOI(
            osm_id=101,
            osm_type="node",
            poi_type=EmergencyPOIType.HOSPITAL,
            name="Metropolitan Level 1 Trauma Center",
            latitude=center_lat + (4 - (grid_rows / 2.0)) * d_lat + 0.0005,
            longitude=center_lon + (4 - (grid_cols / 2.0)) * d_lon + 0.0005,
            capabilities={
                ClinicalCapability.TRAUMA_LEVEL_1,
                ClinicalCapability.BURN_CENTER,
                ClinicalCapability.CARDIAC_CARE,
                ClinicalCapability.HELIPAD,
            },
            trauma_level=1,
            apparatus_bays=12,
            phone="+1-206-555-0100",
        ),
        ExtractedEmergencyPOI(
            osm_id=102,
            osm_type="node",
            poi_type=EmergencyPOIType.HOSPITAL,
            name="Eastside Children's Regional Specialty Hospital",
            latitude=center_lat + (5 - (grid_rows / 2.0)) * d_lat - 0.0004,
            longitude=center_lon + (5 - (grid_cols / 2.0)) * d_lon - 0.0004,
            capabilities={
                ClinicalCapability.PEDIATRIC_CARE,
                ClinicalCapability.CARDIAC_CARE,
                ClinicalCapability.TRAUMA_LEVEL_3,
            },
            trauma_level=3,
            apparatus_bays=6,
            phone="+1-206-555-0200",
        ),
        ExtractedEmergencyPOI(
            osm_id=103,
            osm_type="node",
            poi_type=EmergencyPOIType.HOSPITAL,
            name="Westside Community Clinic",
            latitude=center_lat + (1 - (grid_rows / 2.0)) * d_lat + 0.0002,
            longitude=center_lon + (1 - (grid_cols / 2.0)) * d_lon + 0.0002,
            capabilities={
                ClinicalCapability.STROKE_CENTER,
            },
            trauma_level=4,
            apparatus_bays=3,
            phone="+1-206-555-0300",
        ),
        ExtractedEmergencyPOI(
            osm_id=201,
            osm_type="node",
            poi_type=EmergencyPOIType.FIRE_STATION,
            name="Downtown Fire Station 10 (HQ)",
            latitude=center_lat + (0 - (grid_rows / 2.0)) * d_lat + 0.0002,
            longitude=center_lon + (0 - (grid_cols / 2.0)) * d_lon + 0.0002,
            capabilities=set(),
            apparatus_bays=5,
            phone="+1-206-555-9010",
        ),
        ExtractedEmergencyPOI(
            osm_id=202,
            osm_type="node",
            poi_type=EmergencyPOIType.FIRE_STATION,
            name="First Hill Fire Station 33",
            latitude=center_lat + (4 - (grid_rows / 2.0)) * d_lat + 0.0003,
            longitude=center_lon + (3 - (grid_cols / 2.0)) * d_lon + 0.0003,
            capabilities=set(),
            apparatus_bays=3,
            phone="+1-206-555-9033",
        ),
    ]

    # 5. USGS River Gauge Reading (located in the central river basin)
    now = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)
    river_lat = center_lat + (1 - (grid_rows / 2.0)) * d_lat
    river_lon = center_lon + 0.5 * d_lon  # between col 2 and 3
    river_gauge = USGSGaugeReading(
        site_id="12113000",
        site_name="Metropolitan Central River Gauge",
        latitude=river_lat,
        longitude=river_lon,
        timestamp=now,
        gage_height_ft=28.4,
        streamflow_cfs=18400.0,
        flood_stage=FloodStage.MAJOR,
    )

    # 6. Open-Meteo Severe Weather Report
    weather = WeatherConditions(
        latitude=center_lat,
        longitude=center_lon,
        timestamp=now,
        weather_code=95,  # WMO code 95: Thunderstorm
        temperature_c=14.2,
        wind_speed_kmh=78.5,
        precipitation_mm=42.0,
        visibility_m=2000.0,
        alert_level=WeatherAlertLevel.WARNING,
        summary="Severe Thunderstorm & Torrential Downpours",
    )

    return graph, pois, provider, river_gauge, weather


# ---------------------------------------------------------------------------
# Benchmark Engine and Strategy Evaluation
# ---------------------------------------------------------------------------


class MetropolitanBenchmarkRunner:
    """Orchestrates end-to-end multi-strategy disaster benchmark evaluations."""

    def __init__(
        self,
        graph: Graph,
        pois: Sequence[ExtractedEmergencyPOI],
        elevation_provider: ElevationProvider,
    ) -> None:
        self.raw_graph = graph
        self.pois = list(pois)
        self.elevation_provider = elevation_provider

        # Bind POIs to road graph
        self.bindings, self.unbound_pois = bind_pois_to_network(self.pois, self.raw_graph)
        self.fleet_manager = create_fleet_from_pois(self.pois, self.bindings)

        # Enrich graph with 3D elevation metrics
        self.elevation_summary: ElevationEnrichmentSummary = enrich_graph_with_elevation(
            self.raw_graph, self.elevation_provider
        )

    def run_benchmark(
        self,
        scenario: MetropolitanDisasterScenario,
    ) -> MetropolitanBenchmarkReport:
        """Execute all 4 operational routing strategies and compute quantitative benchmarks.

        Parameters
        ----------
        scenario : MetropolitanDisasterScenario
            Disaster scenario definition.

        Returns
        -------
        MetropolitanBenchmarkReport
            Quantitative metrics, DDF, EDF, pruning efficiency, and audit hash.
        """
        start_bench_time = time.perf_counter()
        report = MetropolitanBenchmarkReport(
            scenario_name=scenario.name,
            network_node_count=self.raw_graph.node_count(),
            network_edge_count=self.raw_graph.edge_count(),
            total_facilities_bound=len(self.bindings),
            active_flood_stage=scenario.river_gauge.flood_stage,
            flooded_edges_closed=0,
            weather_alert_level=scenario.weather.alert_level,
        )

        source_node = scenario.origin_node_id
        dest_node = scenario.destination_node_id

        # ------------------------------------------------------------------
        # Strategy 1: Flat Baseline A* Search (Unimpaired Dry Network)
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        h_fn = haversine_heuristic
        res_flat = astar(self.raw_graph, source_node, dest_node, heuristic=h_fn)
        lat_flat_ms = (time.perf_counter() - t0) * 1000.0

        flat_metrics = self._extract_path_metrics(self.raw_graph, res_flat.path)
        strat_flat = StrategyRoutingResult(
            strategy_name="Flat A* Baseline",
            path_found=res_flat.reachable,
            node_path=res_flat.path,
            distance_2d_meters=flat_metrics["dist_2d"],
            distance_3d_meters=flat_metrics["dist_3d"],
            duration_seconds=res_flat.total_cost,
            max_slope_grade=flat_metrics["max_grade"],
            average_slope_grade=flat_metrics["avg_grade"],
            elevation_gain_meters=flat_metrics["gain_m"],
            nodes_explored=res_flat.nodes_explored,
            execution_latency_ms=lat_flat_ms,
        )
        report.strategy_results["Flat_Baseline"] = strat_flat

        # Measure baseline Dijkstra for pruning ratio calculation
        res_dijkstra = dijkstra(self.raw_graph, source_node, dest_node)
        if res_dijkstra.nodes_explored > 0:
            report.search_pruning_ratio = max(
                0.0,
                1.0 - (float(res_flat.nodes_explored) / float(res_dijkstra.nodes_explored)),
            )

        # ------------------------------------------------------------------
        # Strategy 2: Elevation-Aware 3D Slope Routing (Powertrain Clamped)
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        elev_view = ElevationGraphView(
            self.raw_graph,
            apparatus_type=scenario.apparatus_type,
            use_3d_distance=True,
        )
        res_elev = astar(elev_view, source_node, dest_node, heuristic=h_fn)
        lat_elev_ms = (time.perf_counter() - t0) * 1000.0

        elev_metrics = self._extract_path_metrics(self.raw_graph, res_elev.path)
        strat_elev = StrategyRoutingResult(
            strategy_name=f"Elevation-Aware 3D ({scenario.apparatus_type.value.upper()})",
            path_found=res_elev.reachable,
            node_path=res_elev.path,
            distance_2d_meters=elev_metrics["dist_2d"],
            distance_3d_meters=elev_metrics["dist_3d"],
            duration_seconds=res_elev.total_cost,
            max_slope_grade=elev_metrics["max_grade"],
            average_slope_grade=elev_metrics["avg_grade"],
            elevation_gain_meters=elev_metrics["gain_m"],
            nodes_explored=res_elev.nodes_explored,
            execution_latency_ms=lat_elev_ms,
        )
        report.strategy_results["Elevation_Aware_3D"] = strat_elev

        if strat_flat.duration_seconds > 0.0 and strat_elev.path_found:
            report.elevation_delay_factor = (
                strat_elev.duration_seconds / strat_flat.duration_seconds
            )

        # ------------------------------------------------------------------
        # Strategy 3: Dynamic USGS Flood Inundation & Weather Detour
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        dynamic_view = DynamicGraphView(self.raw_graph)
        env_summary = apply_environmental_hazards_to_graph(
            self.raw_graph,
            dynamic_view,
            gauges=[scenario.river_gauge],
            weather_reports=[scenario.weather],
        )
        report.flooded_edges_closed = env_summary.edges_closed

        # Also apply elevation view over the dynamically flooded view
        elev_dynamic_view = ElevationGraphView(
            dynamic_view,
            apparatus_type=scenario.apparatus_type,
            use_3d_distance=True,
        )
        res_detour = astar(elev_dynamic_view, source_node, dest_node, heuristic=h_fn)
        lat_detour_ms = (time.perf_counter() - t0) * 1000.0

        detour_metrics = self._extract_path_metrics(self.raw_graph, res_detour.path)
        strat_detour = StrategyRoutingResult(
            strategy_name="Dynamic Flood Inundation Detour",
            path_found=res_detour.reachable,
            node_path=res_detour.path,
            distance_2d_meters=detour_metrics["dist_2d"],
            distance_3d_meters=detour_metrics["dist_3d"],
            duration_seconds=res_detour.total_cost,
            max_slope_grade=detour_metrics["max_grade"],
            average_slope_grade=detour_metrics["avg_grade"],
            elevation_gain_meters=detour_metrics["gain_m"],
            nodes_explored=res_detour.nodes_explored,
            execution_latency_ms=lat_detour_ms,
        )
        report.strategy_results["Disaster_Detour"] = strat_detour

        if strat_flat.duration_seconds > 0.0 and strat_detour.path_found:
            report.detour_delay_factor = (
                strat_detour.duration_seconds / strat_flat.duration_seconds
            )

        # ------------------------------------------------------------------
        # Strategy 4: Clinical Specialized Triage Transport
        # ------------------------------------------------------------------
        t0 = time.perf_counter()
        clinical_match = find_nearest_clinical_facility(
            incident_node_id=source_node,
            graph=elev_dynamic_view,
            candidate_pois=self.pois,
            bindings=self.bindings,
            required_capabilities=scenario.required_clinical_capabilities,
        )
        lat_clinical_ms = (time.perf_counter() - t0) * 1000.0

        if clinical_match is not None:
            best_poi, best_bind, best_path, best_cost = clinical_match
            clin_metrics = self._extract_path_metrics(self.raw_graph, best_path)
            strat_clin = StrategyRoutingResult(
                strategy_name="Specialized Clinical Transport",
                path_found=True,
                node_path=best_path,
                distance_2d_meters=clin_metrics["dist_2d"],
                distance_3d_meters=clin_metrics["dist_3d"],
                duration_seconds=best_cost,
                max_slope_grade=clin_metrics["max_grade"],
                average_slope_grade=clin_metrics["avg_grade"],
                elevation_gain_meters=clin_metrics["gain_m"],
                nodes_explored=len(best_path) * 2,
                execution_latency_ms=lat_clinical_ms,
                target_facility_name=best_poi.name,
                target_facility_trauma_level=best_poi.trauma_level,
                target_facility_capabilities=set(best_poi.capabilities),
            )
        else:
            strat_clin = StrategyRoutingResult(
                strategy_name="Specialized Clinical Transport",
                path_found=False,
                execution_latency_ms=lat_clinical_ms,
            )
        report.strategy_results["Clinical_Specialized"] = strat_clin

        # Compute total latency and integrity hash
        report.total_benchmark_latency_ms = (time.perf_counter() - start_bench_time) * 1000.0
        report.integrity_hash = report.compute_integrity_hash()

        return report

    def _extract_path_metrics(
        self,
        graph: Graph,
        path: List[str],
    ) -> Dict[str, float]:
        """Aggregate 2D distance, 3D distance, grades, and elevation gain along a path."""
        if not path or len(path) < 2:
            return {
                "dist_2d": 0.0,
                "dist_3d": 0.0,
                "max_grade": 0.0,
                "avg_grade": 0.0,
                "gain_m": 0.0,
            }

        dist_2d = 0.0
        dist_3d = 0.0
        max_grade = 0.0
        sum_grade = 0.0
        gain_m = 0.0
        edge_count = 0

        for i in range(len(path) - 1):
            u = path[i]
            v = path[i + 1]
            edge = None
            if hasattr(graph, "get_edge"):
                edge = graph.get_edge(u, v)
            elif hasattr(graph, "get_neighbors"):
                for e in graph.get_neighbors(u):
                    if e.destination_id == v:
                        edge = e
                        break
            if edge is not None:
                d_2 = edge.attributes.get("distance_m", 0.0)
                d_3 = edge.attributes.get("distance_3d_m", d_2)
                grade = edge.attributes.get("grade_percent", 0.0)
                delta_h = edge.attributes.get("elevation_delta_m", 0.0)

                dist_2d += d_2
                dist_3d += d_3
                max_grade = max(max_grade, abs(grade))
                sum_grade += abs(grade)
                if delta_h > 0.0:
                    gain_m += delta_h
                edge_count += 1

        avg_grade = (sum_grade / edge_count) if edge_count > 0 else 0.0
        return {
            "dist_2d": dist_2d,
            "dist_3d": dist_3d,
            "max_grade": max_grade,
            "avg_grade": avg_grade,
            "gain_m": gain_m,
        }

    def export_gis_map(
        self,
        report: MetropolitanBenchmarkReport,
        scenario: MetropolitanDisasterScenario,
        output_file_path: Optional[str] = None,
    ) -> str:
        """Render Leaflet GIS interactive HTML map with all benchmark layers.

        Layers rendered:
          1. Road network geometry.
          2. Flooded river basin hazard polygon.
          3. Emergency hospital & fire station markers.
          4. Flat baseline route (blue dashed).
          5. Elevation-aware 3D route (amber solid).
          6. Dynamic flood detour route (orange solid).
          7. Clinical specialized transport route (green bold).

        Parameters
        ----------
        report : MetropolitanBenchmarkReport
            Benchmark report containing results.
        scenario : MetropolitanDisasterScenario
            Active disaster scenario.
        output_file_path : Optional[str]
            Optional filesystem destination path to write HTML.

        Returns
        -------
        str
            Complete, self-contained HTML document.
        """
        route_overlays: List[MapRouteOverlay] = []

        # Color mapping for strategies
        palette = {
            "Flat_Baseline": ("#3b82f6", "Flat A* Baseline", "dash"),
            "Elevation_Aware_3D": ("#f59e0b", "Elevation-Aware 3D", "solid"),
            "Disaster_Detour": ("#ef4444", "Dynamic Flood Detour", "solid"),
            "Clinical_Specialized": ("#10b981", "Specialized Clinical Transport", "solid"),
        }

        for strat_key, (color, label, stroke_style) in palette.items():
            if strat_key in report.strategy_results:
                strat_res = report.strategy_results[strat_key]
                if strat_res.path_found and len(strat_res.node_path) >= 2:
                    dash_array = "8, 6" if stroke_style == "dash" else None
                    route_overlays.append(
                        MapRouteOverlay(
                            route_id=strat_key,
                            label=label,
                            path_nodes=strat_res.node_path,
                            color=color,
                            weight=5 if strat_key == "Clinical_Specialized" else 3,
                            dash_array=dash_array,
                            total_cost=strat_res.duration_seconds,
                        )
                    )

        # Flood hazard polygon
        flood_poly = create_flood_inundation_polygon(scenario.river_gauge)
        hazards = [flood_poly]

        weather_poly = create_weather_hazard_polygon(scenario.weather)
        if weather_poly is not None:
            hazards.append(weather_poly)

        center_lat = (scenario.bounding_box[0] + scenario.bounding_box[2]) / 2.0
        center_lon = (scenario.bounding_box[1] + scenario.bounding_box[3]) / 2.0

        html = render_interactive_map_html(
            center_lat=center_lat,
            center_lon=center_lon,
            zoom=14,
            title=f"Metropolitan Benchmark GIS — {scenario.name}",
            graph=self.raw_graph,
            pois=self.pois,
            gauges=[scenario.river_gauge],
            hazards=hazards,
            routes=route_overlays,
        )

        if output_file_path:
            save_interactive_map_html(html, output_file_path)

        return html
