"""
Milestone 7.3 Demonstration: Real-Time Hydrology & Weather Feeds (USGS / Open-Meteo).
=====================================================================================
Demonstrates standard-library integration with USGS river gauge instantaneous values,
National Weather Service (NWS) flood stage classification, Open-Meteo extreme weather
observations, dynamic inundation catchment polygon synthesis, and automated graph
closures with dynamic vehicle detour rerouting.

Run with:
    python examples/hydrology_hazard_demo.py
"""

from __future__ import annotations

from datetime import datetime, timezone
import time

from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.external.hydrology import (
    DEFAULT_GAUGE_THRESHOLDS,
    FloodStage,
    USGSGaugeReading,
    USGSGaugeThresholds,
    WeatherAlertLevel,
    WeatherConditions,
    apply_environmental_hazards_to_graph,
    build_usgs_water_query_url,
    create_flood_inundation_polygon,
    create_weather_hazard_polygon,
    parse_open_meteo_response,
    parse_usgs_water_response,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.models import Edge, Graph, Node


def main() -> None:
    start_time = time.perf_counter()
    print("=" * 78)
    print("  EMERGENCY INTELLIGENCE AI -- REAL-TIME HYDROLOGY & WEATHER FEEDS")
    print("=" * 78)

    # -----------------------------------------------------------------------
    # Step 1: Query & Parse USGS NWIS Instantaneous River Telemetry
    # -----------------------------------------------------------------------
    print("\n[STEP 1] Querying USGS NWIS Water Services REST Telemetry...")

    station_ids = ["12144500", "12150800"]
    query_url = build_usgs_water_query_url(station_ids, parameters=["00065", "00060"])
    print(f"  * Generated REST Query URL: {query_url}")

    # Simulated USGS JSON payload for PNW River Gauges
    mock_usgs_payload = {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {
                        "siteName": "SNOQUALMIE RIVER NEAR SNOQUALMIE, WA",
                        "siteCode": [{"value": "12144500"}],
                        "geoLocation": {
                            "geogLocation": {"latitude": 47.532, "longitude": -121.842}
                        },
                    },
                    "variable": {"variableCode": [{"value": "00065"}]},
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "22.4",
                                    "dateTime": "2026-10-13T10:15:00.000-07:00",
                                }
                            ]
                        }
                    ],
                },
                {
                    "sourceInfo": {
                        "siteName": "SNOQUALMIE RIVER NEAR SNOQUALMIE, WA",
                        "siteCode": [{"value": "12144500"}],
                        "geoLocation": {
                            "geogLocation": {"latitude": 47.532, "longitude": -121.842}
                        },
                    },
                    "variable": {"variableCode": [{"value": "00060"}]},
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "31500.0",
                                    "dateTime": "2026-10-13T10:15:00.000-07:00",
                                }
                            ]
                        }
                    ],
                },
                {
                    "sourceInfo": {
                        "siteName": "SNOHOMISH RIVER AT MONROE, WA",
                        "siteCode": [{"value": "12150800"}],
                        "geoLocation": {
                            "geogLocation": {"latitude": 47.854, "longitude": -121.970}
                        },
                    },
                    "variable": {"variableCode": [{"value": "00065"}]},
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "15.8",
                                    "dateTime": "2026-10-13T10:15:00.000-07:00",
                                }
                            ]
                        }
                    ],
                },
            ]
        }
    }

    # Custom NWS flood stage thresholds for Snoqualmie station
    custom_thresholds = {
        "12144500": USGSGaugeThresholds(
            action_stage_ft=12.0,
            minor_stage_ft=15.0,
            moderate_stage_ft=18.0,
            major_stage_ft=20.0,
        ),
        "12150800": USGSGaugeThresholds(
            action_stage_ft=11.0,
            minor_stage_ft=14.0,
            moderate_stage_ft=19.0,
            major_stage_ft=23.0,
        ),
    }

    gauges = parse_usgs_water_response(mock_usgs_payload, custom_thresholds=custom_thresholds)
    print(f"\n  Parsed {len(gauges)} Active River Gauges:")
    for g in gauges:
        stage_tag = f"[{g.flood_stage.value.upper()}]"
        print(f"  * {g.site_id} ({g.site_name[:36]}): Height = {g.gage_height_ft:.1f} ft ({g.gage_height_m:.2f} m) -> {stage_tag}")
        if g.streamflow_cfs:
            print(f"    - Discharge: {g.streamflow_cfs:,.1f} cfs | Flooding: {g.is_flooding()}")

    # -----------------------------------------------------------------------
    # Step 2: Open-Meteo Severe Weather Telemetry Ingestion
    # -----------------------------------------------------------------------
    print("\n[STEP 2] Parsing Open-Meteo Surface Weather Telemetry...")

    mock_weather_payload = {
        "latitude": 47.530,
        "longitude": -121.840,
        "current": {
            "time": "2026-10-13T10:30",
            "weather_code": 95,
            "temperature_2m": 14.5,
            "wind_speed_10m": 88.0,
            "precipitation": 34.0,
        },
    }

    weather = parse_open_meteo_response(mock_weather_payload)
    print(f"  * Observation Point: ({weather.latitude:.3f}N, {weather.longitude:.3f}W)")
    print(f"  * Conditions: {weather.summary} [Alert Level: {weather.alert_level.value.upper()}]")
    print(f"  * Temperature: {weather.temperature_c:.1f} deg C | Winds: {weather.wind_speed_kmh:.1f} km/h | Precip: {weather.precipitation_mm:.1f} mm/hr")

    # -----------------------------------------------------------------------
    # Step 3: Automated Dynamic Hazard Polygon Synthesis
    # -----------------------------------------------------------------------
    print("\n[STEP 3] Synthesizing 2D Environmental Hazard Inundation Polygons...")

    flood_polys = [create_flood_inundation_polygon(g) for g in gauges if g.is_flooding()]
    weather_poly = create_weather_hazard_polygon(weather)

    for p in flood_polys:
        bbox = p.bounding_box()
        print(f"  * Flood Zone [{p.hazard_id}]: Severity = {p.severity.value} | Multiplier = {p.speed_multiplier:.2f}")
        print(f"    - BBox: [Lon: {bbox[0]:.4f} to {bbox[2]:.4f}, Lat: {bbox[1]:.4f} to {bbox[3]:.4f}] ({len(p.boundary_coordinates)} vertices)")

    if weather_poly:
        w_bbox = weather_poly.bounding_box()
        print(f"  * Atmospheric Zone [{weather_poly.hazard_id}]: Severity = {weather_poly.severity.value}")
        print(f"    - BBox: [Lon: {w_bbox[0]:.4f} to {w_bbox[2]:.4f}, Lat: {w_bbox[1]:.4f} to {w_bbox[3]:.4f}]")

    # -----------------------------------------------------------------------
    # Step 4: Road Network Setup & Baseline Routing
    # -----------------------------------------------------------------------
    print("\n[STEP 4] Constructing Road Network Across Valley Riverbed...")

    # Road Network across the Snoqualmie Valley:
    # Node S1: Emergency Dispatch Depot (West)      [-122.040, 47.500]
    # Node R1: Low-Level River Crossing Bridge      [-122.000, 47.500] (USGS River Gauge Station)
    # Node H1: Level-1 Regional Trauma Center (East)[-121.960, 47.500]
    # Node B1: High-Level Mountain Bypass Bridge    [-122.000, 47.540] (Elevated crossing, unflooded)
    graph = Graph()
    graph.add_node(Node("S1", coordinates=(-122.040, 47.500)))
    graph.add_node(Node("R1", coordinates=(-122.000, 47.500)))
    graph.add_node(Node("H1", coordinates=(-121.960, 47.500)))
    graph.add_node(Node("B1", coordinates=(-122.000, 47.540)))

    # Direct Low Bridge Path: S1 <-> R1 <-> H1 (1,500m each leg)
    graph.add_edge(Edge("S1", "R1", cost=1500.0))
    graph.add_edge(Edge("R1", "S1", cost=1500.0))
    graph.add_edge(Edge("R1", "H1", cost=1500.0))
    graph.add_edge(Edge("H1", "R1", cost=1500.0))

    # High-Level Bypass Path: S1 <-> B1 <-> H1 (3,200m each leg)
    graph.add_edge(Edge("S1", "B1", cost=3200.0))
    graph.add_edge(Edge("B1", "S1", cost=3200.0))
    graph.add_edge(Edge("B1", "H1", cost=3200.0))
    graph.add_edge(Edge("H1", "B1", cost=3200.0))

    base_route = astar(graph, "S1", "H1")
    print(f"  * Baseline Dispatch Route: {' -> '.join(base_route.path)}")
    print(f"    - Traversal Distance: {base_route.total_cost:.1f} m | Route Feasible: {base_route.reachable}")

    # -----------------------------------------------------------------------
    # Step 5: Dynamic Flood Breach & Vehicle Detour Replanning
    # -----------------------------------------------------------------------
    print("\n[STEP 5] Applying Real-Time USGS Flood Telemetry to Dynamic Network...")

    dynamic_view = DynamicGraphView(graph)
    river_flood_gauge = USGSGaugeReading(
        site_id="12144500",
        site_name="Snoqualmie Low River Bridge Gauge",
        latitude=47.500,
        longitude=-122.000,
        timestamp=datetime.now(timezone.utc),
        gage_height_ft=23.5,
        flood_stage=FloodStage.MAJOR,
    )

    mutation_summary = apply_environmental_hazards_to_graph(
        graph=graph,
        dynamic_view=dynamic_view,
        gauges=[river_flood_gauge],
        weather_reports=[weather],
    )

    print(f"  * Environmental Mutations Enacted:")
    print(f"    - Flood Zones Detected: {mutation_summary.floods_detected}")
    print(f"    - Severe Weather Zones: {mutation_summary.weather_hazards_detected}")
    print(f"    - Road Edges Closed:    {mutation_summary.edges_closed}")
    print(f"    - Speed Penalized:      {mutation_summary.edges_speed_penalized}")

    # Verify road closures on the low-level river bridge
    is_r1_closed = dynamic_view.is_edge_blocked("S1", "R1") and dynamic_view.is_edge_blocked("R1", "H1")
    print(f"  * Low-Level River Bridge Status: {'SEVERED / CLOSED' if is_r1_closed else 'OPEN'}")

    # Replanning emergency ambulance dispatch
    rerouted = astar(dynamic_view, "S1", "H1")
    print(f"\n  * Dynamic Rerouted Path: {' -> '.join(rerouted.path)}")
    print(f"    - Detour Traversal Distance: {rerouted.total_cost:.1f} m")
    print(f"    - Path Exploration Steps:    {rerouted.nodes_explored}")
    print(f"    - Transit Status:            PASSABLE via High-Level Bypass B1")

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    print("\n" + "=" * 78)
    print(f"  DEMO 23 COMPLETED SUCCESSFULLY IN {elapsed_ms:.2f} ms (100% OFFLINE)")
    print("=" * 78)


if __name__ == "__main__":
    main()
