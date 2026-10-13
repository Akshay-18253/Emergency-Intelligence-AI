"""
Milestone 7.2 Demonstration: Digital Elevation Models & Incline Routing.
========================================================================
Demonstrates NASA SRTM HGT binary parsing, continuous sub-grid bilinear
elevation interpolation, 3D slope grade physics, apparatus powertrain
penalties, and dynamic elevation-aware emergency routing.

Run with:
    python examples/elevation_routing_demo.py
"""

from __future__ import annotations

import time

from emergency_intelligence.events.incidents import ApparatusType
from emergency_intelligence.external.elevation import (
    APPARATUS_GRADE_PROFILES,
    ElevationGraphView,
    ElevationProvider,
    build_synthetic_dem_tile,
    calculate_slope_metrics,
    enrich_graph_with_elevation,
    get_grade_speed_multiplier,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.models import Edge, Graph, Node


def main() -> None:
    start_time = time.perf_counter()
    print("=" * 76)
    print("  EMERGENCY INTELLIGENCE AI -- DIGITAL ELEVATION MODEL & INCLINE ROUTING")
    print("=" * 76)

    # -----------------------------------------------------------------------
    # Step 1: Ingest / Generate Synthetic NASA SRTM Digital Elevation Tile
    # -----------------------------------------------------------------------
    print("\n[STEP 1] Generating NASA SRTM HGT Binary Elevation Grid (1x1 degree)...")

    # Construct a synthetic SRTM tile representing a mountain ridge:
    # Latitude 37.0 to 38.0 N, Longitude -123.0 to -122.0 W
    # Southwest base: 120m, Ridge summit: 780m
    tile = build_synthetic_dem_tile(
        lat_origin=37,
        lon_origin=-123,
        dimension=101,  # 101 x 101 elevation matrix
        base_elevation=120.0,
        slope_north_per_deg=660.0,
        slope_east_per_deg=220.0,
    )

    provider = ElevationProvider()
    provider.add_tile(tile)

    print(f"  * SRTM Tile: {tile.tile_name} (Dimension: {tile.dimension}x{tile.dimension})")
    print(f"  * Bounding Box: [{tile.lat_origin}.0N, {tile.lat_origin+1}.0N] x [{tile.lon_origin}.0W, {tile.lon_origin+1}.0W]")

    # Query continuous coordinates using bilinear interpolation
    test_points = [
        ("Valley Floor", 37.10, -122.90),
        ("Midway Slope", 37.50, -122.50),
        ("Ridge Summit", 37.90, -122.10),
    ]
    print("\n  Sub-Grid Bilinear Interpolation Sampling:")
    for label, lat, lon in test_points:
        elev = provider.get_elevation(lat, lon, interpolate=True)
        assert elev is not None
        print(f"    - {label:<14} ({lat:.2f}N, {lon:.2f}W) -> {elev:.1f} m above sea level")

    # -----------------------------------------------------------------------
    # Step 2: 3D Slope Incline & Physical Grade Metrics
    # -----------------------------------------------------------------------
    print("\n[STEP 2] Calculating 3D Slope Grade & Euclidean Traversal Distance...")

    p1 = (-122.50, 37.50)
    elev1 = provider.get_elevation_or_default(37.50, -122.50)
    p2 = (-122.50, 37.51)  # 0.01 deg north (~1113 m)
    elev2 = provider.get_elevation_or_default(37.51, -122.50)

    slope = calculate_slope_metrics(p1, elev1, p2, elev2)
    print(f"  * Segment Vector: ({p1[1]:.2f}N, {p1[0]:.2f}W) -> ({p2[1]:.2f}N, {p2[0]:.2f}W)")
    print(f"  * 2D Haversine Distance: {slope.horizontal_distance_m:.1f} m")
    print(f"  * Vertical Delta (dh):   {slope.vertical_delta_m:+.1f} m")
    print(f"  * 3D True Distance:      {slope.distance_3d_m:.1f} m")
    print(f"  * Slope Grade:           {slope.grade_percent:+.2f}%")
    print(f"  * Pitch Angle:           {slope.slope_angle_deg:+.2f} deg")

    # -----------------------------------------------------------------------
    # Step 3: Apparatus Powertrain Incline Speed Penalties
    # -----------------------------------------------------------------------
    print("\n[STEP 3] Apparatus Powertrain Climb & Descent Degradation Models:")
    test_grades = [0.0, 4.0, 8.0, 12.0, 15.0, 20.0, -8.0, -18.0]

    apparatuses = [
        ApparatusType.AMBULANCE_ALS,
        ApparatusType.FIRE_ENGINE,
        ApparatusType.LADDER_TRUCK,
        ApparatusType.BATTALION_CHIEF,
    ]

    header = f"  {'Grade (%)':<10}" + "".join(f"{app.name[:12]:<15}" for app in apparatuses)
    print(header)
    print("  " + "-" * 68)

    for g in test_grades:
        row = f"  {g:+5.1f}%     "
        for app in apparatuses:
            mult = get_grade_speed_multiplier(app, g)
            if mult == 0.0:
                row += f"{'BLOCKED':<15}"
            else:
                pct = mult * 100.0
                row += f"{pct:5.1f}% speed   "
        print(row)

    # -----------------------------------------------------------------------
    # Step 4: Building Municipal Hill District Road Network
    # -----------------------------------------------------------------------
    print("\n[STEP 4] Constructing Municipal Hill District Road Network...")
    graph = Graph()

    # Station Depot (S), Steep Hill Ridge (H), Valley Flat Bypass (V), Hospital Dest (D)
    graph.add_node(Node("DEPOT_STATION", coordinates=(-122.50, 37.50)))
    graph.add_node(Node("STEEP_RIDGE", coordinates=(-122.50, 37.51)))
    graph.add_node(Node("VALLEY_BYPASS", coordinates=(-122.53, 37.505)))
    graph.add_node(Node("HOSPITAL_DEST", coordinates=(-122.50, 37.52)))

    # Direct Mountain Ridge Road: 15.0% uphill climb
    graph.add_edge(Edge("DEPOT_STATION", "STEEP_RIDGE", cost=120.0, attributes={"grade_percent": 15.0}))
    graph.add_edge(Edge("STEEP_RIDGE", "HOSPITAL_DEST", cost=120.0, attributes={"grade_percent": 2.0}))

    # Valley Bypass Road: 0% flat grade, longer distance (360s base cost)
    graph.add_edge(Edge("DEPOT_STATION", "VALLEY_BYPASS", cost=180.0, attributes={"grade_percent": 0.0}))
    graph.add_edge(Edge("VALLEY_BYPASS", "HOSPITAL_DEST", cost=180.0, attributes={"grade_percent": 0.0}))

    # -----------------------------------------------------------------------
    # Step 5: Comparative Apparatus Routing on Incline-Aware Graph Views
    # -----------------------------------------------------------------------
    print("\n[STEP 5] Incline-Constrained Apparatus Dispatch & Routing:")

    # Scenario A: Paramedic Ambulance (ALS)
    amb_view = ElevationGraphView(graph, apparatus_type=ApparatusType.AMBULANCE_ALS)
    amb_route = astar(amb_view, "DEPOT_STATION", "HOSPITAL_DEST")

    print(f"\n  [Vehicle A: ALS Ambulance (Max Climb: {APPARATUS_GRADE_PROFILES[ApparatusType.AMBULANCE_ALS].max_climb_grade_percent}%)]")
    print(f"  * Route Selected:  {' -> '.join(amb_route.path)}")
    print(f"  * Effective ETA:   {amb_route.total_cost:.1f} seconds")
    print(f"  * Decision:        High power-to-weight ratio allows direct climb over 15% steep ridge.")

    # Scenario B: Heavy Aerial Ladder Truck (60,000 lbs)
    ladder_view = ElevationGraphView(graph, apparatus_type=ApparatusType.LADDER_TRUCK)
    ladder_route = astar(ladder_view, "DEPOT_STATION", "HOSPITAL_DEST")

    print(f"\n  [Vehicle B: Aerial Ladder Truck (Max Climb: {APPARATUS_GRADE_PROFILES[ApparatusType.LADDER_TRUCK].max_climb_grade_percent}%)]")
    print(f"  * Route Selected:  {' -> '.join(ladder_route.path)}")
    print(f"  * Effective ETA:   {ladder_route.total_cost:.1f} seconds")
    print(f"  * Decision:        15% grade exceeds 14% max climb threshold. Direct road impassable!")
    print(f"                     A* automatically diverts ladder truck around ridge via Valley Bypass.")

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0
    print("\n" + "=" * 76)
    print(f"  DEM INCLINE ROUTING DEMONSTRATION COMPLETE in {elapsed_ms:.1f} ms")
    print("=" * 76)


if __name__ == "__main__":
    main()
