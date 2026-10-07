"""
Day 1 demonstration - Local Routing Engine Foundation.

Constructs a small artificial road graph and runs Dijkstra's algorithm
to find the least-cost path between two nodes.

This is an algorithm demonstration, not a production interface.
No graphical interface, no external APIs, no AI reasoning.

Run with:
    python examples/demo.py
"""

from emergency_intelligence.graph.dijkstra import dijkstra
from emergency_intelligence.graph.models import Edge, Graph, Node


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------
#
#  The artificial graph represents a simplified road network:
#
#       A ──(2)──► B ──(5)──► D
#       │                     ▲
#      (7)                   (1)
#       │                     │
#       └────────► C ──(3)────┘
#
#  Edge costs are abstract numerical traversal values on Day 1.
#
#  Path A -> B -> D: cost = 2 + 5 = 7
#  Path A -> C -> D: cost = 7 + 3 = 10    <- not optimal
#  Path A -> B -> D via C:               <- no such edge
#
#  NOTE: A->C costs 7, C->D costs 3, total 10.  A->B->D costs 7.
#  Both paths share the same cost (7).  The algorithm is deterministic
#  for a fixed graph; whichever it finds first will be reported.
#
#  A second scenario with a clearly optimal path is shown below.


def build_demo_graph() -> Graph:
    """Return the demonstration road graph."""
    g = Graph()

    # Nodes - intersections / locations
    for node_id, label in [
        ("A", "Origin"),
        ("B", "Waypoint Beta"),
        ("C", "Waypoint Charlie"),
        ("D", "Destination"),
    ]:
        g.add_node(Node(node_id, label=label))

    # Directed edges - road segments with traversal costs
    g.add_edge(Edge("A", "B", cost=2.0))
    g.add_edge(Edge("A", "C", cost=7.0))
    g.add_edge(Edge("B", "D", cost=5.0))
    g.add_edge(Edge("C", "D", cost=1.0))

    return g


def print_separator(title: str = "") -> None:
    width = 60
    if title:
        print(f"\n{'--'} {title} {'--'}")
    else:
        print("-" * width)


def print_result(graph: Graph, source: str, destination: str) -> None:
    """Run Dijkstra and print a human-readable summary."""
    result = dijkstra(graph, source, destination)

    src_label = graph.get_node(source).label or source
    dst_label = graph.get_node(destination).label or destination

    print(f"  Source      : {source}  ({src_label})")
    print(f"  Destination : {destination}  ({dst_label})")

    if result.reachable:
        route_str = " -> ".join(result.path)
        print(f"  Route       : {route_str}")
        print(f"  Total cost  : {result.total_cost}")
    else:
        print("  Route       : NO PATH FOUND - destination is unreachable")
        print("  Total cost  : inf")


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------


def main() -> None:
    print("\n" + "=" * 60)
    print("  Emergency Intelligence AI")
    print("  Day 1 - Local Routing Engine Demonstration")
    print("=" * 60)

    graph = build_demo_graph()

    print(f"\n  Graph: {graph.node_count()} nodes, {graph.edge_count()} edges")
    print()
    print("  Edges:")
    for node_id in graph.node_ids():
        for edge in graph.get_neighbors(node_id):
            src_label = graph.get_node(edge.source_id).label or edge.source_id
            dst_label = graph.get_node(edge.destination_id).label or edge.destination_id
            print(
                f"    {edge.source_id} ({src_label})"
                f"  ->  {edge.destination_id} ({dst_label})"
                f"  [cost: {edge.cost}]"
            )

    # --- Scenario 1: A -> D (two paths, one optimal) -----------------------
    print_separator("Scenario 1: A -> D")
    print("  Two possible paths:")
    print("    A -> B -> D   cost = 2 + 5 = 7")
    print("    A -> C -> D   cost = 7 + 1 = 8   <- higher cost")
    print()
    print_result(graph, "A", "D")

    # --- Scenario 2: B -> D ------------------------------------------------
    print_separator("Scenario 2: B -> D")
    print()
    print_result(graph, "B", "D")

    # --- Scenario 3: same source and destination --------------------------
    print_separator("Scenario 3: A -> A (same node)")
    print()
    print_result(graph, "A", "A")

    # --- Scenario 4: unreachable destination ------------------------------
    print_separator("Scenario 4: D -> A (no path exists)")
    print()
    print("  No edges leave D.  Destination is unreachable.")
    print()
    print_result(graph, "D", "A")

    print("\n" + "=" * 60)
    print("  Demonstration complete.")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
