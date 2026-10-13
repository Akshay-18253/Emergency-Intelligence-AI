"""
Milestone 7.4 Demonstration: Slippy Map Tile Math & Zero-Dependency Leaflet GIS Visualizer.
============================================================================================
Demonstrates Web Mercator slippy tile projection mathematics, ground resolution calculations,
and the generation of a standalone, self-contained interactive Leaflet GIS HTML/JS visualizer
displaying road topologies, clinical facilities, USGS flood gauges, hazard zones, and routes.

Run with:
    python examples/map_visualizer_demo.py
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

from emergency_intelligence.events.hazards import HazardPolygon, HazardSeverity, HazardType
from emergency_intelligence.external.binding import (
    ClinicalCapability,
    EmergencyPOIType,
    ExtractedEmergencyPOI,
)
from emergency_intelligence.external.hydrology import FloodStage, USGSGaugeReading
from emergency_intelligence.external.visualizer import (
    MapIsochroneOverlay,
    MapRouteOverlay,
    format_tile_url,
    get_tiles_for_bounding_box,
    lat_lon_to_tile_xy,
    render_interactive_map_html,
    resolution_meters_per_pixel,
    save_interactive_map_html,
    slippy_to_tms_y,
    tile_bounding_box,
    tile_xy_to_lat_lon,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.models import Edge, Graph, Node


def main() -> None:
    start_time = time.perf_counter()
    print("=" * 80)
    print("  EMERGENCY INTELLIGENCE AI -- SLIPPY MAP TILE MATH & LEAFLET GIS VISUALIZER")
    print("=" * 80)

    # -----------------------------------------------------------------------
    # Step 1: Web Mercator Tile Forward & Inverse Projection
    # -----------------------------------------------------------------------
    print("\n[STEP 1] Web Mercator Slippy Tile Mathematics (EPSG:3857 <-> WGS84)...")

    seattle_lat, seattle_lon = 47.6062, -122.3321
    zoom_levels = [10, 12, 14, 16]

    print(f"  * Reference Coordinate: ({seattle_lat:.4f} N, {seattle_lon:.4f} W) [Seattle Metropolitan Area]")
    for z in zoom_levels:
        tx, ty = lat_lon_to_tile_xy(seattle_lat, seattle_lon, zoom=z)
        bbox = tile_bounding_box(tx, ty, zoom=z)
        res_m = resolution_meters_per_pixel(seattle_lat, zoom=z)
        tms_y = slippy_to_tms_y(ty, zoom=z)
        url = format_tile_url(tx, ty, zoom=z)

        print(f"  * Zoom {z:2d}: Tile ({tx:5d}, {ty:5d}) | TMS Y = {tms_y:5d} | Resolution = {res_m:6.2f} m/px")
        print(f"    - BBox: [{bbox.min_lat:.4f}N, {bbox.min_lon:.4f}W] to [{bbox.max_lat:.4f}N, {bbox.max_lon:.4f}W]")
        print(f"    - Tile URL: {url}")

    # Bounding box multi-tile discovery
    metro_tiles = get_tiles_for_bounding_box(
        min_lat=47.50, min_lon=-122.40, max_lat=47.65, max_lon=-122.25, zoom=12
    )
    print(f"\n  * Metropolitan Region (Zoom 12): {len(metro_tiles)} tiles discovered covering bounding box.")

    # -----------------------------------------------------------------------
    # Step 2: Build Tactical Multi-Modal Emergency Network & POIs
    # -----------------------------------------------------------------------
    print("\n[STEP 2] Synthesizing Valley Road Network, POIs & USGS River Gauges...")

    graph = Graph()
    # Nodes in the Snoqualmie Valley
    graph.add_node(Node("S1", coordinates=(-122.040, 47.500)))  # Station 51
    graph.add_node(Node("R1", coordinates=(-122.000, 47.500)))  # River Bridge
    graph.add_node(Node("H1", coordinates=(-121.960, 47.500)))  # Regional Hospital
    graph.add_node(Node("B1", coordinates=(-122.000, 47.535)))  # Elevated Bypass

    # Direct Low-Level Bridge Route
    graph.add_edge(Edge("S1", "R1", cost=1800.0, attributes={"highway": "primary", "grade_percent": 1.2}))
    graph.add_edge(Edge("R1", "S1", cost=1800.0, attributes={"highway": "primary", "grade_percent": 1.2}))
    graph.add_edge(Edge("R1", "H1", cost=1800.0, attributes={"highway": "primary", "grade_percent": 1.0}))
    graph.add_edge(Edge("H1", "R1", cost=1800.0, attributes={"highway": "primary", "grade_percent": 1.0}))

    # High-Level Bypass Route
    graph.add_edge(Edge("S1", "B1", cost=3600.0, attributes={"highway": "secondary", "grade_percent": 4.5}))
    graph.add_edge(Edge("B1", "S1", cost=3600.0, attributes={"highway": "secondary", "grade_percent": 4.5}))
    graph.add_edge(Edge("B1", "H1", cost=3600.0, attributes={"highway": "secondary", "grade_percent": 4.2}))
    graph.add_edge(Edge("H1", "B1", cost=3600.0, attributes={"highway": "secondary", "grade_percent": 4.2}))

    # Specialized Emergency POIs
    pois = [
        ExtractedEmergencyPOI(
            osm_id=1001,
            osm_type="node",
            poi_type=EmergencyPOIType.FIRE_STATION,
            name="Snoqualmie Valley Fire & Rescue Station 51",
            latitude=47.500,
            longitude=-122.040,
            capabilities={ClinicalCapability.HAZMAT_DECON},
            apparatus_bays=4,
            phone="911",
        ),
        ExtractedEmergencyPOI(
            osm_id=2001,
            osm_type="way",
            poi_type=EmergencyPOIType.HOSPITAL,
            name="Valley Regional Level-1 Trauma & Burn Center",
            latitude=47.500,
            longitude=-121.960,
            capabilities={
                ClinicalCapability.TRAUMA_LEVEL_1,
                ClinicalCapability.BURN_CENTER,
                ClinicalCapability.CARDIAC_CARE,
                ClinicalCapability.HELIPAD,
            },
            trauma_level=1,
            apparatus_bays=6,
            phone="(425) 555-0199",
        ),
    ]

    # USGS River Flood Gauge
    river_gauge = USGSGaugeReading(
        site_id="12144500",
        site_name="Snoqualmie River Low Bridge Station",
        latitude=47.500,
        longitude=-122.000,
        timestamp=datetime.now(timezone.utc),
        gage_height_ft=24.2,
        streamflow_cfs=34800.0,
        flood_stage=FloodStage.MAJOR,
    )

    # Environmental Flood Inundation Hazard Polygon
    flood_hazard = HazardPolygon(
        hazard_id="usgs_flood_12144500_major",
        hazard_type=HazardType.FLOOD_INUNDATION,
        severity=HazardSeverity.CRITICAL_BLOCKED,
        boundary_coordinates=[
            (-122.012, 47.492),
            (-121.988, 47.492),
            (-121.988, 47.508),
            (-122.012, 47.508),
        ],
        description="Catastrophic River Overflow (USGS Gage 24.2ft)",
    )

    # -----------------------------------------------------------------------
    # Step 3: Compute Dispatch Routes & Isochrones
    # -----------------------------------------------------------------------
    print("\n[STEP 3] Computing Primary Dispatch & Dynamic Flood Bypass Detours...")

    res_baseline = astar(graph, "S1", "H1")
    route_baseline = MapRouteOverlay(
        route_id="route_baseline",
        label="Direct Dispatch (Low River Bridge)",
        path_nodes=res_baseline.path,
        color="#38BDF8",  # Light blue
        weight=4,
        dash_array="6, 6",
        total_cost=res_baseline.total_cost,
    )

    # Rerouted Path avoiding severed low bridge R1
    route_detour = MapRouteOverlay(
        route_id="route_detour",
        label="Emergency Detour via High-Level Bypass",
        path_nodes=["S1", "B1", "H1"],
        color="#F43F5E",  # Rose red
        weight=6,
        total_cost=7200.0,
    )

    # NFPA 1710 Response Isochrone
    isochrone_480s = MapIsochroneOverlay(
        isochrone_id="iso_480s",
        label="NFPA 1710 8-Minute Turnout Frontier",
        threshold_seconds=480.0,
        boundary_coordinates=[
            (-122.060, 47.480),
            (-121.940, 47.480),
            (-121.940, 47.540),
            (-122.060, 47.540),
        ],
        color="#10B981",
        fill_opacity=0.15,
    )

    print(f"  * Baseline Path: {' -> '.join(route_baseline.path_nodes)} ({route_baseline.total_cost:.1f} m)")
    print(f"  * Detour Path:   {' -> '.join(route_detour.path_nodes)} ({route_detour.total_cost:.1f} m)")

    # -----------------------------------------------------------------------
    # Step 4: Render Standalone Leaflet GIS HTML Document
    # -----------------------------------------------------------------------
    print("\n[STEP 4] Rendering Zero-Dependency Leaflet GIS HTML5 Visualizer...")

    html_content = render_interactive_map_html(
        center_lat=47.505,
        center_lon=-122.000,
        zoom=13,
        title="Emergency Tactical GIS — Snoqualmie Valley Incident Replay",
        graph=graph,
        pois=pois,
        gauges=[river_gauge],
        hazards=[flood_hazard],
        routes=[route_baseline, route_detour],
        isochrones=[isochrone_480s],
        show_playback_hud=True,
    )

    # Save to examples/output directory
    output_dir = Path("examples/output")
    output_path = output_dir / "tactical_emergency_map.html"
    saved_file = save_interactive_map_html(html_content, output_path)

    print(f"  * Output HTML Document: {saved_file.resolve()}")
    print(f"  * File Size: {saved_file.stat().st_size:,} bytes")
    print(f"  * HTML Structure: Single-file responsive dashboard, Dark Matter tiles, and playback HUD")

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    print("\n" + "=" * 80)
    print(f"  DEMO 24 COMPLETED SUCCESSFULLY IN {elapsed_ms:.2f} ms (100% OFFLINE)")
    print("=" * 80)


if __name__ == "__main__":
    main()
