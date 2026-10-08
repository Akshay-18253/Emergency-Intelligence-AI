"""
A* shortest-path algorithm.

Implements the A* (A-star) heuristic search algorithm manually using
Python's standard library ``heapq`` module. No external graph libraries
are used.

Algorithm overview
------------------
1. Maintain two scores for each node:
   - g(n): the exact shortest distance discovered from the source to n.
   - f(n) = g(n) + h(n): estimated total cost of a path from source to
     destination passing through n, where h(n) is the heuristic estimate
     from n to the destination.
2. Maintain a min-heap priority queue keyed by f(n).
3. At each step, extract the node with the smallest f(n).
4. For each outgoing edge from that node, compute a relaxed g(neighbour).
   If this improves the neighbour's best known g-score:
   - Update g(neighbour).
   - Recompute f(neighbour) = g(neighbour) + h(neighbour, destination).
   - Record predecessor for path reconstruction.
   - Push the neighbour onto the priority queue.
5. Terminate when the destination node is extracted from the queue
   (guaranteed optimal path if h is admissible) or when the queue is
   exhausted (destination is unreachable).
6. Reconstruct the path by following the predecessor map.

Optimality & Admissibility
--------------------------
If h(n) is admissible (never overestimates the true remaining cost,
h(n) <= h*(n)) and consistent (satisfies triangle inequality
h(u) <= c(u, v) + h(v)), A* is guaranteed to find the optimal shortest path
while exploring fewer or equal nodes compared to uninformed search (Dijkstra).

References
----------
- Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). A Formal Basis for the
  Heuristic Determination of Minimum Cost Paths. IEEE Transactions on
  Systems Science and Cybernetics, 4(2), 100–107.
"""

from __future__ import annotations

import heapq
import math
import time
from typing import Dict, List, Optional

from .dijkstra import RouteResult, _reconstruct_path
from .heuristics import HeuristicFn, euclidean_distance, zero_heuristic
from .models import Graph, Node


def astar(
    graph: Graph,
    source: str,
    destination: str,
    heuristic: Optional[HeuristicFn] = None,
) -> RouteResult:
    """Compute the least-cost path between *source* and *destination* using A*.

    Parameters
    ----------
    graph:
        The directed weighted :class:`~emergency_intelligence.graph.models.Graph`
        to search.
    source:
        The ``node_id`` of the starting node.
    destination:
        The ``node_id`` of the target node.
    heuristic:
        An admissible heuristic callable ``(current: Node, goal: Node) -> float``.
        If ``None``, defaults to :func:`~emergency_intelligence.graph.heuristics.euclidean_distance`
        if both source and destination have coordinates defined, or
        :func:`~emergency_intelligence.graph.heuristics.zero_heuristic` otherwise.

    Returns
    -------
    RouteResult
        A :class:`RouteResult` describing the optimal path, its total
        cost, reachability, nodes explored, and execution time in ms.

    Raises
    ------
    KeyError
        If *source* or *destination* does not exist in *graph*.
    ValueError
        If *heuristic* returns a negative value.
    """
    start_time = time.perf_counter()

    # --- Validate inputs ---------------------------------------------------
    if not graph.has_node(source):
        raise KeyError(f"Source node {source!r} does not exist in the graph.")
    if not graph.has_node(destination):
        raise KeyError(
            f"Destination node {destination!r} does not exist in the graph."
        )

    source_node = graph.get_node(source)
    dest_node = graph.get_node(destination)

    # Resolve default heuristic if none was explicitly provided
    if heuristic is None:
        if (
            source_node.coordinates is not None
            and dest_node.coordinates is not None
        ):
            heuristic = euclidean_distance
        else:
            heuristic = zero_heuristic

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
    # g_score[node_id] — exact cost of the best known path from source to node
    g_score: Dict[str, float] = {
        node_id: math.inf for node_id in graph.node_ids()
    }
    g_score[source] = 0.0

    # previous[node_id] — predecessor on best known path
    previous: Dict[str, Optional[str]] = {
        node_id: None for node_id in graph.node_ids()
    }

    # visited (closed set) — nodes whose optimal distance is finalised
    visited: set = set()

    # Compute initial heuristic for source
    initial_h = heuristic(source_node, dest_node)
    if initial_h < 0:
        raise ValueError(
            f"Heuristic returned negative value {initial_h} for source node {source!r}."
        )

    # Priority queue min-heap entries: (f_score, h_score, counter, node_id)
    # When f_scores are equal, tie-breaking by smaller h_score prioritises
    # nodes closer to the destination, pruning unpromising branches.
    counter = 0
    heap: List = []
    heapq.heappush(heap, (initial_h, initial_h, counter, source))

    nodes_explored = 0

    # --- Main A* search loop -----------------------------------------------
    while heap:
        current_f, _, _, current_node = heapq.heappop(heap)

        if current_node in visited:
            continue

        visited.add(current_node)
        nodes_explored += 1

        # Goal reached: optimal path guaranteed when heuristic is admissible
        if current_node == destination:
            break

        current_g = g_score[current_node]

        # Relax outgoing edges
        for edge in graph.get_neighbors(current_node):
            neighbour = edge.destination_id

            if neighbour in visited:
                continue

            tentative_g = current_g + edge.cost

            if tentative_g < g_score[neighbour]:
                g_score[neighbour] = tentative_g
                previous[neighbour] = current_node

                neighbour_node = graph.get_node(neighbour)
                h_val = heuristic(neighbour_node, dest_node)
                if h_val < 0:
                    raise ValueError(
                        f"Heuristic returned negative value {h_val} for node {neighbour!r}."
                    )

                f_score = tentative_g + h_val
                counter += 1
                heapq.heappush(heap, (f_score, h_val, counter, neighbour))

    elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    # --- Check reachability ------------------------------------------------
    if math.isinf(g_score[destination]):
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
        total_cost=g_score[destination],
        reachable=True,
        nodes_explored=nodes_explored,
        execution_time_ms=elapsed_ms,
    )
