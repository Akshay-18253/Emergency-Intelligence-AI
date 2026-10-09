"""
Phase 3 Milestone 3 Demonstration: Spatial Indexing, Snapping & Compiled Network Cache.

Demonstrates:
  1. Zero-dependency 2D Spatial Hash Grid Indexing with sub-millisecond lookups.
  2. Snapping arbitrary 911 emergency caller GPS coordinates onto the nearest road.
  3. End-to-end dispatch routing: Station -> Snapped Incident -> Trauma Center.
  4. Turn-by-turn maneuver instruction generation.
  5. Fast compiled network cache serialization (.json with SHA-256 hash) and instant re-loading.

Run with:
    python examples/spatial_indexing_demo.py
"""

from __future__ import annotations

import time
from pathlib import Path

from emergency_intelligence.data import (
    SAMPLE_HOSPITAL_DISTRICT_PATH,
    SpatialIndex,
    WeightingProfile,
    compute_file_checksum,
    load_graph_cache,
    load_osm_graph_from_file,
    save_graph_cache,
)
from emergency_intelligence.graph.dijkstra import dijkstra
from emergency_intelligence.graph.topology import calculate_turn_angle, classify_turn_maneuver


def print_banner(title: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {title}")
    print("=" * 76)


def main() -> None:
    print_banner("Emergency Intelligence AI — Phase 3 Milestone 3 Demonstration")
    print("  Spatial Indexing, Coordinate Snapping & Fast Compiled Network Caching")

    # -----------------------------------------------------------------------
    # 1. Load Real Road Network & Build Spatial Index
    # -----------------------------------------------------------------------
    print(f"\n1. Ingesting San Francisco Hospital District: {SAMPLE_HOSPITAL_DISTRICT_PATH.name}")
    t0 = time.perf_counter()
    graph = load_osm_graph_from_file(
        SAMPLE_HOSPITAL_DISTRICT_PATH,
        weighting_profile=WeightingProfile.EMERGENCY_TIME,
        simplify_topology=True,
        extract_lscc=True,
        protected_node_ids={"1001", "1008"},
    )
    load_ms = (time.perf_counter() - t0) * 1000.0
    print(f"   Loaded and contracted graph in {load_ms:.2f} ms:")
    print(f"   - Active Intersections : {graph.node_count()}")
    print(f"   - Directed Road Edges  : {graph.edge_count()}")

    print("\n2. Building 2D Spatial Hash Grid Index...")
    t0 = time.perf_counter()
    spatial_index = SpatialIndex(graph, cell_size_deg=0.001)
    index_ms = (time.perf_counter() - t0) * 1000.0
    print(f"   Indexed {spatial_index.indexed_nodes_count} nodes in {index_ms:.3f} ms.")

    # -----------------------------------------------------------------------
    # 2. Simulated 911 Emergency Caller (Off-Road GPS Incident)
    # -----------------------------------------------------------------------
    print_banner("SCENARIO 1: 911 CALLER OFF-ROAD GPS COORDINATE SNAPPING")
    # Caller inside a mid-block commercial building near Market & 9th St
    caller_gps = (-122.418250, 37.776350)
    print(f"  Raw 911 Caller GPS Coordinates: Lon: {caller_gps[0]:.6f}, Lat: {caller_gps[1]:.6f}")

    t0 = time.perf_counter()
    snapped = spatial_index.snap_to_road_network(caller_gps)
    snap_latency_us = (time.perf_counter() - t0) * 1_000_000.0

    print(f"\n  [Orthogonal Road Snapping Results]")
    print(f"  - Nearest Road Point    : Lon: {snapped.snapped_coordinates[0]:.6f}, Lat: {snapped.snapped_coordinates[1]:.6f}")
    print(f"  - Perpendicular Offset  : {snapped.distance_to_road_m:.2f} meters (distance from inside building to street)")
    print(f"  - Nearest Intersection  : Node {snapped.nearest_node_id} ({graph.get_node(snapped.nearest_node_id).label})")
    if snapped.nearest_edge:
        road_name = snapped.nearest_edge.attributes.get("name", "Unnamed Road")
        road_type = snapped.nearest_edge.attributes.get("highway", "general")
        print(f"  - Snapped Road Segment  : '{road_name}' ({road_type}) [Edge {snapped.nearest_edge.source_id} -> {snapped.nearest_edge.destination_id}]")
        print(f"  - Segment Interpolation : {snapped.projection_factor * 100.0:.1f}% along block")
    print(f"  - Spatial Snap Latency  : {snap_latency_us:.1f} microseconds (sub-millisecond $O(1)$ query)")

    # -----------------------------------------------------------------------
    # 3. Code 3 Dispatch Routing with Turn Maneuvers
    # -----------------------------------------------------------------------
    print_banner("SCENARIO 2: END-TO-END AMBULANCE DISPATCH & TURN-BY-TURN LOG")
    dispatch_origin = "1001"   # Central Emergency Dispatch
    incident_target = snapped.nearest_node_id  # Snapped junction
    trauma_hospital = "1008"   # Regional Trauma Center

    # Leg 1: Dispatch -> Incident
    route_leg1 = dijkstra(graph, dispatch_origin, incident_target)
    # Leg 2: Incident -> Trauma Center
    route_leg2 = dijkstra(graph, incident_target, trauma_hospital)

    print(f"  Leg 1: Station [1001] -> Incident [Node {incident_target}]:")
    print(f"  - Emergency Travel Time : {route_leg1.total_cost:.2f} seconds ({route_leg1.total_cost / 60.0:.2f} min)")
    print(f"  - Path Trajectory       : {' -> '.join(route_leg1.path)}")

    # Turn-by-turn maneuver extraction for Leg 1
    print("\n  [Leg 1 Navigation Instructions]")
    for i in range(len(route_leg1.path) - 1):
        u_node = graph.get_node(route_leg1.path[i])
        v_node = graph.get_node(route_leg1.path[i + 1])
        u_name = u_node.label or f"Node {u_node.node_id}"
        v_name = v_node.label or f"Node {v_node.node_id}"

        if i < len(route_leg1.path) - 2:
            w_node = graph.get_node(route_leg1.path[i + 2])
            turn_deg = calculate_turn_angle(u_node.coordinates, v_node.coordinates, w_node.coordinates)
            maneuver = classify_turn_maneuver(turn_deg)
            print(f"    Step {i + 1}: Traverse from {u_name} to {v_name} -> At {v_name}: {maneuver.upper()} ({turn_deg:+.1f}°)")
        else:
            print(f"    Step {i + 1}: Arrive at Emergency Scene: {v_name}")

    print(f"\n  Leg 2: Incident [Node {incident_target}] -> Trauma Center [{trauma_hospital}]:")
    print(f"  - Emergency Travel Time : {route_leg2.total_cost:.2f} seconds ({route_leg2.total_cost / 60.0:.2f} min)")
    print(f"  - Path Trajectory       : {' -> '.join(route_leg2.path)}")

    # -----------------------------------------------------------------------
    # 4. Compiled Fast Network Cache Serialization & Verification
    # -----------------------------------------------------------------------
    print_banner("SCENARIO 3: COMPILED NETWORK CACHE (FAST DISK RELOAD)")
    cache_path = Path("output_hospital_district.eig.json")
    src_chk = compute_file_checksum(SAMPLE_HOSPITAL_DISTRICT_PATH)

    print(f"  Raw OSM Dataset Checksum : {src_chk[:16]}... (SHA-256)")
    t0 = time.perf_counter()
    save_graph_cache(graph, cache_path, source_checksum=src_chk)
    save_ms = (time.perf_counter() - t0) * 1000.0
    print(f"  Compiled cache written to : {cache_path} ({cache_path.stat().st_size} bytes in {save_ms:.2f} ms)")

    t0 = time.perf_counter()
    reloaded_graph, metadata = load_graph_cache(cache_path, verify_checksum=True)
    reload_ms = (time.perf_counter() - t0) * 1000.0

    print(f"\n  [Compiled Cache Load Results]")
    print(f"  - Reload Time           : {reload_ms:.2f} ms (vs {load_ms:.2f} ms raw parse)")
    print(f"  - Speedup Factor        : {load_ms / max(reload_ms, 0.01):.1f}x faster start-up")
    print(f"  - Schema Version        : {metadata['schema_version']}")
    print(f"  - Checksum Verified     : SHA-256 payload verified intact")
    print(f"  - Retained Graph Size   : {reloaded_graph.node_count()} nodes, {reloaded_graph.edge_count()} edges")

    # Clean up demo artifact
    if cache_path.is_file():
        cache_path.unlink()

    print_banner("PHASE 3 MILESTONE 3 COMPLETE")
    print("  * Sub-millisecond 2D spatial indexing and orthogonal road projection operational.")
    print("  * End-to-end 911 dispatch and turn maneuver instructions generated.")
    print("  * Compiled network cache format verified with SHA-256 cryptographic integrity.")
    print("  * Zero external runtime dependencies preserved (100% Python standard library).\n")


if __name__ == "__main__":
    main()
