"""
Milestone 3 demonstration: Real Road Network Ingestion (OpenStreetMap).

Demonstrates:
  1. Parsing real geographic data from an OpenStreetMap Overpass export
     into our core Graph model without modifying the routing engine.
  2. Computing optimal emergency routes on real city street topology
     with physical road segment lengths in meters.
  3. Enforcing real-world one-way transit street constraints.
  4. Evaluating Dijkstra vs A* (Haversine heuristic) on real geographic coordinates.

Run with:
    python examples/osm_demo.py
"""

from __future__ import annotations

from emergency_intelligence.data import (
    SAMPLE_HOSPITAL_DISTRICT_PATH,
    haversine_heuristic,
    load_osm_graph_from_file,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.dijkstra import dijkstra
from emergency_intelligence.graph.models import Graph


def print_banner(title: str) -> None:
    print("\n" + "=" * 72)
    print(f"  {title}")
    print("=" * 72)


def format_route_with_labels(graph: Graph, path: list[str]) -> str:
    labeled_hops = []
    for nid in path:
        node = graph.get_node(nid)
        name = node.label if node.label else f"Node {nid}"
        labeled_hops.append(f"{name} [{nid}]")
    return " \n      --> ".join(labeled_hops)


def main() -> None:
    print_banner("Emergency Intelligence AI — Milestone 3 Demonstration")
    print("  Real Road Network Ingestion: OpenStreetMap (OSM) Ingestion & Routing")

    print(f"\n1. Ingesting OpenStreetMap dataset: {SAMPLE_HOSPITAL_DISTRICT_PATH.name}")
    graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)

    print(f"   Successfully parsed:")
    print(f"   - {graph.node_count()} real intersections / nodes with GPS coordinates")
    print(f"   - {graph.edge_count()} directed road segments with Haversine physical costs (meters)")

    # -----------------------------------------------------------------------
    # Scenario: Rapid Emergency Transport
    # -----------------------------------------------------------------------
    print_banner("EMERGENCY DISPATCH: CODE 3 AMBULANCE TRANSPORT")
    src = "1001"  # Central Emergency Dispatch
    dst = "1008"  # Regional Trauma Center

    src_node = graph.get_node(src)
    dst_node = graph.get_node(dst)

    print(f"  Origin      : {src_node.label} (ID: {src}, GPS: {src_node.coordinates})")
    print(f"  Destination : {dst_node.label} (ID: {dst}, GPS: {dst_node.coordinates})")
    print("-" * 72)

    # 1. Dijkstra routing
    d_res = dijkstra(graph, src, dst)
    # 2. A* with Haversine heuristic
    a_res = astar(graph, src, dst, heuristic=haversine_heuristic)

    print(f"\n[Algorithm Comparison]")
    print(f"  * Dijkstra Result:")
    print(f"    - Status         : {'Reachable' if d_res.reachable else 'Unreachable'}")
    print(f"    - Road Distance  : {d_res.total_cost:.2f} meters ({d_res.total_cost / 1000.0:.3f} km)")
    print(f"    - Nodes Explored : {d_res.nodes_explored}")
    print(f"    - Execution Time : {d_res.execution_time_ms:.3f} ms")

    print(f"\n  * A* (Haversine Heuristic) Result:")
    print(f"    - Status         : {'Reachable' if a_res.reachable else 'Unreachable'}")
    print(f"    - Road Distance  : {a_res.total_cost:.2f} meters ({a_res.total_cost / 1000.0:.3f} km)")
    print(f"    - Nodes Explored : {a_res.nodes_explored}")
    print(f"    - Execution Time : {a_res.execution_time_ms:.3f} ms")

    assert d_res.total_cost == a_res.total_cost, "Cost mismatch between Dijkstra and A*!"
    print(f"\n  * Verification: 100% cost agreement between Dijkstra and A* ({d_res.total_cost:.2f} m).")

    print(f"\n[Computed Emergency Route Trajectory]")
    print("      " + format_route_with_labels(graph, d_res.path))

    # -----------------------------------------------------------------------
    # Scenario: Return Trip (One-way street constraint evaluation)
    # -----------------------------------------------------------------------
    print_banner("RETURN TRIP EVALUATION: REGIONAL TRAUMA CENTER -> DISPATCH")
    print("  Evaluating return trajectory (Node 1008 -> Node 1001)...")
    print("  Note: Mission St (Way 2002) is a strict one-way street pointing eastbound.")
    print("  Ambulance cannot take Mission St in reverse.\n")

    return_res = dijkstra(graph, dst, src)
    print(f"  Return Road Distance : {return_res.total_cost:.2f} meters ({return_res.total_cost / 1000.0:.3f} km)")
    print(f"\n[Return Route Trajectory]")
    print("      " + format_route_with_labels(graph, return_res.path))

    print_banner("Demonstration Complete")
    print("  Key Takeaways:")
    print("  - Real-world OpenStreetMap data is seamlessly consumed by the core engine.")
    print("  - The routing engine required 0 modifications to support real GIS road graphs.")
    print("  - One-way street semantics and physical distances are faithfully preserved.\n")


if __name__ == "__main__":
    main()
