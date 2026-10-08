"""
Phase 2 Demonstration: RFC 7946 GeoJSON Export, Ingestion & GIS Interoperability.

Demonstrates:
  1. Ingesting real OpenStreetMap road topology from the bundled hospital district.
  2. Computing an optimal emergency ambulance trajectory using A* with Haversine heuristic.
  3. Serializing the computed route into standard RFC 7946 GeoJSON format with bounding box.
  4. Serializing the entire hospital district road network as a GeoJSON layer.
  5. Ingesting the GeoJSON network back to prove complete round-trip GIS fidelity.
  6. Writing artifacts to disk for visualization in QGIS, Leaflet, or geojson.io.

Run with:
    python examples/geojson_export_demo.py
"""

from __future__ import annotations

import json
from pathlib import Path

from emergency_intelligence.data import (
    SAMPLE_HOSPITAL_DISTRICT_PATH,
    haversine_heuristic,
    load_graph_from_geojson,
    load_osm_graph_from_file,
    route_to_geojson,
    save_graph_geojson,
    save_route_geojson,
)
from emergency_intelligence.graph.astar import astar


def print_banner(title: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {title}")
    print("=" * 76)


def main() -> None:
    print_banner("Emergency Intelligence AI — Phase 2: Open GIS Interoperability Demo")
    print("  RFC 7946 GeoJSON Serialization & Round-Trip Network Interoperability\n")

    # 1. Load OSM road graph
    print(f"1. Loading real road network from: {SAMPLE_HOSPITAL_DISTRICT_PATH.name}")
    graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)
    print(f"   Parsed {graph.node_count()} intersections and {graph.edge_count()} directed road links.")

    # 2. Compute emergency route: Dispatch to Trauma Center
    src = "1001"  # Central Emergency Dispatch
    dst = "1008"  # Regional Trauma Center
    src_node = graph.get_node(src)
    dst_node = graph.get_node(dst)

    print("\n2. Computing optimal emergency route (Code 3 Dispatch):")
    print(f"   Origin      : {src_node.label} [{src}] (GPS: {src_node.coordinates})")
    print(f"   Destination : {dst_node.label} [{dst}] (GPS: {dst_node.coordinates})")

    route = astar(graph, src, dst, heuristic=haversine_heuristic)
    print(f"   Status      : {'Reachable' if route.reachable else 'Unreachable'}")
    print(f"   Path Length : {route.total_cost:.2f} meters ({route.total_cost / 1000.0:.3f} km)")
    print(f"   Nodes Visited: {route.nodes_explored} / {graph.node_count()}")
    print(f"   Hops ({len(route.path)}): {' -> '.join(route.path)}")

    # 3. Export Route to RFC 7946 GeoJSON
    print("\n3. Converting route trajectory to RFC 7946 GeoJSON FeatureCollection...")
    geojson_data = route_to_geojson(route, graph, algorithm_name="A* (Haversine)")

    features = geojson_data.get("features", [])
    linestring_features = [f for f in features if f["geometry"]["type"] == "LineString"]
    point_features = [f for f in features if f["geometry"]["type"] == "Point"]

    print(f"   - Total Features    : {len(features)}")
    print(f"   - LineString Roads  : {len(linestring_features)}")
    print(f"   - Waypoint Markers  : {len(point_features)}")
    print(f"   - Bounding Box bbox : {geojson_data.get('bbox')}")
    if linestring_features:
        print(f"   - Route Properties  : {linestring_features[0]['properties']}")

    # 4. Display coordinate stream
    print("\n4. GeoJSON LineString Trajectory Coordinates [longitude, latitude]:")
    coords = linestring_features[0]["geometry"]["coordinates"]
    for idx, (lon, lat) in enumerate(coords):
        nid = route.path[idx]
        label = graph.get_node(nid).label or f"Node {nid}"
        print(f"   [{idx + 1:02d}] {nid} ({label[:28]:<28}) -> Lon: {lon:11.6f}, Lat: {lat:10.6f}")

    # 5. Save Route and Full Road Network GeoJSON to disk
    examples_dir = Path(__file__).parent
    route_output_path = examples_dir / "output_emergency_route.geojson"
    network_output_path = examples_dir / "output_hospital_network.geojson"

    print(f"\n5. Saving GeoJSON artifacts to disk:")
    save_route_geojson(route, graph, route_output_path, algorithm_name="A* (Haversine)")
    save_graph_geojson(graph, network_output_path)

    print(f"   - Route file   : {route_output_path.name} ({route_output_path.stat().st_size} bytes)")
    print(f"   - Network file : {network_output_path.name} ({network_output_path.stat().st_size} bytes)")

    # 6. Verify Round-Trip Ingestion Fidelity
    print("\n6. Verifying Round-Trip GeoJSON Ingestion Fidelity:")
    reconstructed_graph = load_graph_from_geojson(network_output_path)
    print(f"   - Ingested Nodes: {reconstructed_graph.node_count()} (Expected {graph.node_count()})")
    print(f"   - Ingested Edges: {reconstructed_graph.edge_count()} (Expected {graph.edge_count()})")

    recon_route = astar(reconstructed_graph, src, dst, heuristic=haversine_heuristic)
    assert recon_route.reachable is True
    assert recon_route.path == route.path
    assert abs(recon_route.total_cost - route.total_cost) < 1e-4

    print(f"   - Re-routed Path Cost: {recon_route.total_cost:.2f} meters (100% agreement with original)")
    print(f"   - Re-routed Trajectory: {' -> '.join(recon_route.path)}")

    print("\n[Open-Source GIS Ecosystem Compatibility]")
    print("  * GeoJSON outputs are 100% compliant with RFC 7946.")
    print("  * Can be directly dragged into:")
    print("      - https://geojson.io for instant interactive web inspection")
    print("      - QGIS (Quantum GIS) for multi-layer spatial analysis")
    print("      - Leaflet / MapLibre GL for client-side map rendering")
    print("      - PostGIS (ST_GeomFromGeoJSON) for database ingestion")
    print_banner("PHASE 2 MILESTONE 1 DEMO COMPLETE")


if __name__ == "__main__":
    main()
