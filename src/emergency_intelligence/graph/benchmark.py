"""
Benchmarking and comparative analysis tools for routing algorithms.

Enables reproducible quantitative comparison between Dijkstra's algorithm
and the A* heuristic search algorithm across identical graph topologies.

Metrics evaluated
-----------------
- Optimal cost agreement (correctness validation)
- Nodes explored / expanded (search efficiency)
- Execution time in milliseconds (latency)
- Reduction percentage in nodes explored
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from .astar import astar
from .dijkstra import RouteResult, dijkstra
from .heuristics import HeuristicFn, euclidean_distance
from .models import Edge, Graph, Node


@dataclass
class BenchmarkComparison:
    """Quantitative comparison between Dijkstra and A* on a single query.

    Attributes
    ----------
    source:
        Starting node ID.
    destination:
        Target node ID.
    dijkstra_result:
        RouteResult produced by Dijkstra's algorithm.
    astar_result:
        RouteResult produced by A* search.
    cost_match:
        True if both algorithms found the exact same path cost.
    path_match:
        True if both algorithms found the exact same sequence of nodes.
    explored_difference:
        Difference in nodes explored (dijkstra.nodes_explored - astar.nodes_explored).
        Positive indicates A* explored fewer nodes.
    explored_reduction_pct:
        Percentage reduction in nodes explored achieved by A* relative to Dijkstra.
    """

    source: str
    destination: str
    dijkstra_result: RouteResult
    astar_result: RouteResult
    cost_match: bool
    path_match: bool
    explored_difference: int
    explored_reduction_pct: float

    def __repr__(self) -> str:
        return (
            f"BenchmarkComparison(\n"
            f"  query='{self.source}' -> '{self.destination}',\n"
            f"  cost_match={self.cost_match} (cost={self.dijkstra_result.total_cost}),\n"
            f"  nodes_explored: Dijkstra={self.dijkstra_result.nodes_explored}, "
            f"A*={self.astar_result.nodes_explored} "
            f"({self.explored_reduction_pct:+.1f}%),\n"
            f"  time_ms: Dijkstra={self.dijkstra_result.execution_time_ms:.3f}ms, "
            f"A*={self.astar_result.execution_time_ms:.3f}ms\n"
            f")"
        )


def compare_algorithms(
    graph: Graph,
    source: str,
    destination: str,
    heuristic: Optional[HeuristicFn] = None,
) -> BenchmarkComparison:
    """Run Dijkstra and A* on identical inputs and compare results.

    Parameters
    ----------
    graph:
        The road graph to evaluate.
    source:
        The starting node ID.
    destination:
        The target node ID.
    heuristic:
        Heuristic function for A*. If None, defaults to Euclidean distance.

    Returns
    -------
    BenchmarkComparison
        Structured comparison metrics.
    """
    d_res = dijkstra(graph, source, destination)
    a_res = astar(graph, source, destination, heuristic=heuristic)

    # Validate cost match
    if not d_res.reachable and not a_res.reachable:
        cost_match = True
    elif d_res.reachable and a_res.reachable:
        cost_match = math.isclose(d_res.total_cost, a_res.total_cost, rel_tol=1e-7, abs_tol=1e-9)
    else:
        cost_match = False

    path_match = d_res.path == a_res.path
    diff = d_res.nodes_explored - a_res.nodes_explored

    if d_res.nodes_explored > 0:
        reduction_pct = (diff / d_res.nodes_explored) * 100.0
    else:
        reduction_pct = 0.0

    return BenchmarkComparison(
        source=source,
        destination=destination,
        dijkstra_result=d_res,
        astar_result=a_res,
        cost_match=cost_match,
        path_match=path_match,
        explored_difference=diff,
        explored_reduction_pct=reduction_pct,
    )


def create_grid_network(
    rows: int,
    cols: int,
    bidirectional: bool = True,
    unit_cost: float = 1.0,
) -> Graph:
    """Generate a 2D grid road network with Cartesian coordinates.

    Each node is positioned at ``coordinates=(float(col), float(row))``.
    Adjacent horizontal and vertical nodes are connected by edges with
    weight ``unit_cost``.

    Parameters
    ----------
    rows:
        Number of rows in the grid (>= 1).
    cols:
        Number of columns in the grid (>= 1).
    bidirectional:
        If True, edges are created in both directions between neighbours.
    unit_cost:
        Cost of traversing between adjacent grid cells.

    Returns
    -------
    Graph
        A populated :class:`Graph` containing ``rows * cols`` nodes.
    """
    if rows < 1 or cols < 1:
        raise ValueError("Grid dimensions must be at least 1x1.")

    g = Graph()

    # Add nodes with coordinates
    for r in range(rows):
        for c in range(cols):
            node_id = f"N_{r}_{c}"
            g.add_node(
                Node(
                    node_id=node_id,
                    label=f"Intersection ({r}, {c})",
                    coordinates=(float(c), float(r)),
                )
            )

    # Add horizontal and vertical edges
    for r in range(rows):
        for c in range(cols):
            curr_id = f"N_{r}_{c}"

            # Right neighbour
            if c + 1 < cols:
                right_id = f"N_{r}_{c + 1}"
                g.add_edge(Edge(curr_id, right_id, cost=unit_cost))
                if bidirectional:
                    g.add_edge(Edge(right_id, curr_id, cost=unit_cost))

            # Down neighbour
            if r + 1 < rows:
                down_id = f"N_{r + 1}_{c}"
                g.add_edge(Edge(curr_id, down_id, cost=unit_cost))
                if bidirectional:
                    g.add_edge(Edge(down_id, curr_id, cost=unit_cost))

    return g
