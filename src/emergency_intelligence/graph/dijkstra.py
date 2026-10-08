"""
Dijkstra's shortest-path algorithm.

Implements Dijkstra's algorithm manually using Python's standard library
``heapq`` module.  No external graph libraries are used.

Algorithm overview
------------------
1. Assign every node a tentative distance: 0 for the source, infinity for
   all others.
2. Maintain a min-heap priority queue keyed by tentative distance.
3. At each step, extract the node with the smallest tentative distance.
4. For each outgoing edge from that node, compute a *relaxed* distance.
   If the relaxed distance is smaller than the currently recorded
   distance, update it and push the neighbour onto the queue.
5. Repeat until the destination is reached or the queue is exhausted
   (destination is unreachable).
6. Reconstruct the path by following the ``previous`` map from
   destination back to source.

Correctness relies on all edge costs being non-negative, which is
enforced by :class:`~emergency_intelligence.graph.models.Edge`.

References
----------
- Dijkstra, E. W. (1959). A note on two problems in connexion with graphs.
  *Numerische Mathematik*, 1(1), 269–271.
"""

from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .models import Graph


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class RouteResult:
    """The result of a routing query (Dijkstra or A*).

    Attributes
    ----------
    source:
        The ``node_id`` where the route starts.
    destination:
        The ``node_id`` where the route ends.
    path:
        Ordered list of ``node_id`` values from source to destination.
        Contains only the source when ``source == destination``.
        Empty when the destination is unreachable.
    total_cost:
        The sum of edge costs along *path*.
        ``0.0`` when ``source == destination``.
        ``math.inf`` when the destination is unreachable.
    reachable:
        ``True`` when a path from source to destination exists.
    nodes_explored:
        The number of nodes expanded/visited during the search.
        Used for algorithmic efficiency analysis and benchmarking.
    execution_time_ms:
        Execution time in milliseconds spent computing the route.
    """

    source: str
    destination: str
    path: List[str]
    total_cost: float
    reachable: bool
    nodes_explored: int = 0
    execution_time_ms: float = 0.0

    def __repr__(self) -> str:
        if not self.reachable:
            return (
                f"RouteResult(source={self.source!r}, "
                f"destination={self.destination!r}, "
                f"reachable=False, "
                f"nodes_explored={self.nodes_explored})"
            )
        route_str = " → ".join(self.path)
        return (
            f"RouteResult(route={route_str!r}, "
            f"total_cost={self.total_cost}, "
            f"nodes_explored={self.nodes_explored})"
        )


# ---------------------------------------------------------------------------
# Dijkstra implementation
# ---------------------------------------------------------------------------


def dijkstra(graph: Graph, source: str, destination: str) -> RouteResult:
    """Compute the least-cost path between *source* and *destination*.

    Uses Dijkstra's algorithm with a binary min-heap.

    Parameters
    ----------
    graph:
        The directed weighted :class:`~emergency_intelligence.graph.models.Graph`
        to search.
    source:
        The ``node_id`` of the starting node.
    destination:
        The ``node_id`` of the target node.

    Returns
    -------
    RouteResult
        A :class:`RouteResult` describing the optimal path, its total
        cost, and whether the destination is reachable.

    Raises
    ------
    KeyError
        If *source* or *destination* does not exist in *graph*.

    Notes
    -----
    - Edge costs must be non-negative (enforced by
      :class:`~emergency_intelligence.graph.models.Edge`).
    - The algorithm finds the globally optimal solution for graphs with
      non-negative weights.
    - When multiple paths share the same minimum cost, the algorithm
      returns whichever it discovers first (deterministic for a fixed
      graph structure and insertion order).
    """
    start_time = time.perf_counter()

    # --- Validate inputs ---------------------------------------------------
    if not graph.has_node(source):
        raise KeyError(
            f"Source node {source!r} does not exist in the graph."
        )
    if not graph.has_node(destination):
        raise KeyError(
            f"Destination node {destination!r} does not exist in the graph."
        )

    # --- Trivial case: source IS destination -------------------------------
    if source == destination:
        return RouteResult(
            source=source,
            destination=destination,
            path=[source],
            total_cost=0.0,
            reachable=True,
            nodes_explored=1,
            execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
        )

    # --- Initialise data structures ----------------------------------------
    # dist[node_id] — best known cost from source to that node
    dist: Dict[str, float] = {node_id: math.inf for node_id in graph.node_ids()}
    dist[source] = 0.0

    # previous[node_id] — predecessor on the best-known path to that node
    previous: Dict[str, Optional[str]] = {node_id: None for node_id in graph.node_ids()}

    # visited — nodes whose shortest distance is finalised
    visited: set = set()

    # Min-heap entries: (cost, node_id)
    # A tie-breaking counter avoids comparison of node_id strings, keeping
    # the heap invariant simple and predictable.
    counter = 0
    heap: List = []
    heapq.heappush(heap, (0.0, counter, source))

    nodes_explored = 0

    # --- Main loop ---------------------------------------------------------
    while heap:
        current_cost, _, current_node = heapq.heappop(heap)

        # Skip if we have already finalised this node
        if current_node in visited:
            continue

        visited.add(current_node)
        nodes_explored += 1

        # Early exit: reached destination with optimal cost
        if current_node == destination:
            break

        # Relax outgoing edges
        for edge in graph.get_neighbors(current_node):
            neighbour = edge.destination_id

            if neighbour in visited:
                continue

            relaxed_cost = current_cost + edge.cost

            if relaxed_cost < dist[neighbour]:
                dist[neighbour] = relaxed_cost
                previous[neighbour] = current_node
                counter += 1
                heapq.heappush(heap, (relaxed_cost, counter, neighbour))

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    # --- Check reachability ------------------------------------------------
    if math.isinf(dist[destination]):
        return RouteResult(
            source=source,
            destination=destination,
            path=[],
            total_cost=math.inf,
            reachable=False,
            nodes_explored=nodes_explored,
            execution_time_ms=elapsed_ms,
        )

    # --- Reconstruct path --------------------------------------------------
    path = _reconstruct_path(previous, source, destination)

    return RouteResult(
        source=source,
        destination=destination,
        path=path,
        total_cost=dist[destination],
        reachable=True,
        nodes_explored=nodes_explored,
        execution_time_ms=elapsed_ms,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _reconstruct_path(
    previous: Dict[str, Optional[str]],
    source: str,
    destination: str,
) -> List[str]:
    """Trace the predecessor map to reconstruct the shortest path.

    Parameters
    ----------
    previous:
        Maps each ``node_id`` to its predecessor on the optimal path
        (or ``None`` for the source).
    source:
        The starting ``node_id``.
    destination:
        The ending ``node_id``.

    Returns
    -------
    list[str]
        Ordered list of ``node_id`` values from *source* to *destination*.
    """
    path: List[str] = []
    current: Optional[str] = destination

    while current is not None:
        path.append(current)
        current = previous[current]

    path.reverse()

    # Sanity check: path must start at source
    if not path or path[0] != source:
        return []  # Should never happen if the graph is consistent

    return path
