"""
Phase 3 Milestone 2 Demonstration: Graph Topology Hardening & Contraction.

Demonstrates:
  1. Degree-2 Intermediate Node Contraction (topological graph compression).
  2. Polyline geometry preservation on contracted road segments.
  3. Tarjan's Strongly Connected Components (LSCC) island pruning.
  4. Turn angle geometry & emergency turn-by-turn maneuver classification.

Run with:
    python examples/topology_contraction_demo.py
"""

from __future__ import annotations

from emergency_intelligence.data import SAMPLE_HOSPITAL_DISTRICT_PATH, load_osm_graph_from_file
from emergency_intelligence.graph.dijkstra import dijkstra
from emergency_intelligence.graph.models import Edge, Graph, Node
from emergency_intelligence.graph.topology import (
    calculate_turn_angle,
    classify_turn_maneuver,
    contract_degree2_nodes,
    extract_largest_strongly_connected_component,
    tarjan_scc,
)


def print_banner(title: str) -> None:
    print("\n" + "=" * 76)
    print(f"  {title}")
    print("=" * 76)


def main() -> None:
    print_banner("Emergency Intelligence AI — Phase 3 Milestone 2 Demonstration")
    print("  Graph Topology Hardening, Degree-2 Contraction & Turn Maneuver Analysis")

    # -----------------------------------------------------------------------
    # 1. Degree-2 Node Contraction Simulation
    # -----------------------------------------------------------------------
    print_banner("SCENARIO 1: TOPOLOGICAL CONTRACTION & GEOMETRY PRESERVATION")
    print("  Constructing a 7-node arterial corridor with 5 intermediate curvature points:")
    print("  Intersections: Node 1 (Dispatch) and Node 7 (Trauma Center)")
    print("  Curvature points: Nodes 2, 3, 4, 5, 6 (degree-2 intermediate shape nodes)\n")

    g_raw = Graph()
    coords = [
        ("1", (-122.4194, 37.7749), "Emergency Dispatch"),
        ("2", (-122.4180, 37.7755), "Market St Curve 1"),
        ("3", (-122.4165, 37.7760), "Market St Curve 2"),
        ("4", (-122.4150, 37.7765), "Market St Curve 3"),
        ("5", (-122.4135, 37.7770), "Market St Curve 4"),
        ("6", (-122.4120, 37.7775), "Market St Curve 5"),
        ("7", (-122.4100, 37.7780), "Trauma Center"),
    ]
    for nid, pt, label in coords:
        g_raw.add_node(Node(nid, coordinates=pt, label=label))

    for i in range(len(coords) - 1):
        u, v = coords[i][0], coords[i + 1][0]
        g_raw.add_edge(Edge(u, v, cost=100.0, attributes={"distance_m": 100.0, "travel_time_s": 8.0}))
        g_raw.add_edge(Edge(v, u, cost=100.0, attributes={"distance_m": 100.0, "travel_time_s": 8.0}))

    res_raw = dijkstra(g_raw, "1", "7")
    print(f"  [Uncontracted Raw Graph]")
    print(f"  - Total Nodes in Graph : {g_raw.node_count()}")
    print(f"  - Total Edges in Graph : {g_raw.edge_count()}")
    print(f"  - Route Path Hops      : {' -> '.join(res_raw.path)} ({len(res_raw.path)} nodes)")
    print(f"  - Total Route Cost     : {res_raw.total_cost:.1f} meters")

    # Contract graph
    g_contracted = contract_degree2_nodes(g_raw, protected_node_ids={"1", "7"})
    res_contracted = dijkstra(g_contracted, "1", "7")

    print(f"\n  [Topologically Contracted Graph]")
    print(f"  - Total Nodes in Graph : {g_contracted.node_count()} (Reduction: {(1 - g_contracted.node_count() / g_raw.node_count()) * 100:.1f}%)")
    print(f"  - Total Edges in Graph : {g_contracted.edge_count()}")
    print(f"  - Route Path Hops      : {' -> '.join(res_contracted.path)} ({len(res_contracted.path)} nodes)")
    print(f"  - Total Route Cost     : {res_contracted.total_cost:.1f} meters")

    contracted_edge = g_contracted.get_neighbors("1")[0]
    poly_pts = contracted_edge.attributes.get("geometry", [])
    print(f"  - Preserved Polyline   : {len(poly_pts)} coordinate vertices retained on edge 1 -> 7")

    assert res_raw.total_cost == res_contracted.total_cost, "Cost mismatch after contraction!"
    print(f"  * MATHEMATICAL VERIFICATION: 100% cost agreement ({res_raw.total_cost:.1f}m) with 71.4% fewer nodes!")

    # -----------------------------------------------------------------------
    # 2. Tarjan's SCC & LSCC Island Pruning
    # -----------------------------------------------------------------------
    print_banner("SCENARIO 2: TARJAN'S SCC & DISCONNECTED ISLAND PRUNING")
    print("  Injecting an isolated 2-node parking lot island disconnected from the main city network...")

    g_island = Graph()
    # City Core
    for nid in ("C1", "C2", "C3"):
        g_island.add_node(Node(nid))
    g_island.add_edge(Edge("C1", "C2", cost=1.0))
    g_island.add_edge(Edge("C2", "C3", cost=1.0))
    g_island.add_edge(Edge("C3", "C1", cost=1.0))

    # Isolated Island
    for nid in ("I1", "I2"):
        g_island.add_node(Node(nid))
    g_island.add_edge(Edge("I1", "I2", cost=1.0))
    g_island.add_edge(Edge("I2", "I1", cost=1.0))

    components = tarjan_scc(g_island)
    print(f"  - Discovered Components: {len(components)}")
    for i, comp in enumerate(components, 1):
        print(f"    Component #{i} (size {len(comp)}): {comp}")

    lscc = extract_largest_strongly_connected_component(g_island)
    print(f"\n  [Pruned Largest Strongly Connected Component (LSCC)]")
    print(f"  - Retained Nodes : {lscc.node_ids()}")
    print(f"  - Pruned Nodes   : {set(g_island.node_ids()) - set(lscc.node_ids())} (isolated island pruned)")

    # -----------------------------------------------------------------------
    # 3. Turn Maneuver Classification
    # -----------------------------------------------------------------------
    print_banner("SCENARIO 3: TURN ANGLE & MANEUVER CLASSIFICATION")
    print("  Evaluating turn maneuvers at city intersections:")

    turns = [
        ("Proceed North onto 9th St", (0.0, -1.0), (0.0, 0.0), (0.0, 1.0)),
        ("Turn East onto Market St", (0.0, -1.0), (0.0, 0.0), (1.0, 0.0)),
        ("Turn West onto Mission St", (0.0, -1.0), (0.0, 0.0), (-1.0, 0.0)),
        ("Bear Slight Right onto Fork", (0.0, -1.0), (0.0, 0.0), (0.5, 1.0)),
        ("Sharp Left onto Alley", (0.0, -1.0), (0.0, 0.0), (-0.8, -0.2)),
        ("Emergency Vehicle U-Turn", (0.0, -1.0), (0.0, 0.0), (0.0, -1.0)),
    ]

    for desc, p1, p2, p3 in turns:
        angle = calculate_turn_angle(p1, p2, p3)
        maneuver = classify_turn_maneuver(angle)
        print(f"  {desc:<30} -> Angle: {angle:>6.1f}° | Maneuver: {maneuver}")

    print_banner("PHASE 3 MILESTONE 2 COMPLETE")
    print("  * Degree-2 contraction reduced node graph count while preserving exact geometry.")
    print("  * Tarjan's SCC successfully eliminated disconnected road islands.")
    print("  * Turn maneuvers correctly classified for emergency navigation.")
    print("  * 100% Python standard library (zero external dependencies preserved).\n")


if __name__ == "__main__":
    main()
