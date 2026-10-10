"""
Multi-Source Catchment Area Partitioning & Isochrone Engine.
============================================================
Provides network-topology Voronoi partitioning, multi-source Dijkstra expansion,
and isochrone travel-time frontier analysis for emergency municipal services.

Operates transparently on both standard `Graph` objects and dynamic disaster
overlays (`DynamicGraphView`), strictly using Python standard library.
"""

from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from emergency_intelligence.allocation.models import CatchmentPartition
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.graph.models import Graph


def compute_multi_source_catchment(
    graph: Union[Graph, DynamicGraphView],
    depot_node_ids: List[str],
    max_cost: Optional[float] = None,
) -> CatchmentPartition:
    """Computes network Voronoi catchment partitioning across multiple emergency depots.

    Expands simultaneously from all depot nodes using a Multi-Source Dijkstra priority queue.
    Each network node is assigned to the depot that can reach it with the minimum travel time.

    Parameters
    ----------
    graph : Graph or DynamicGraphView
        The road network graph or dynamic disaster overlay.
    depot_node_ids : List[str]
        Identifiers of candidate response depots or stations.
    max_cost : Optional[float]
        Optional travel impedance ceiling (seconds). Nodes exceeding this distance are omitted.

    Returns
    -------
    CatchmentPartition
        Partitioning metadata, node assignments, and individual catchment basins.
    """
    if not depot_node_ids:
        return CatchmentPartition(
            depot_node_ids=[],
            node_to_depot={},
            node_to_cost={},
            depot_catchment_nodes={},
        )

    # Filter to existing depot nodes
    valid_depots = [d for d in depot_node_ids if graph.has_node(d)]
    if not valid_depots:
        return CatchmentPartition(
            depot_node_ids=list(depot_node_ids),
            node_to_depot={},
            node_to_cost={},
            depot_catchment_nodes={d: [] for d in depot_node_ids},
        )

    # Min-heap entries: (cost, node_id, origin_depot_id)
    queue: List[Tuple[float, str, str]] = []
    node_to_cost: Dict[str, float] = {}
    node_to_depot: Dict[str, str] = {}

    for depot_id in valid_depots:
        heapq.heappush(queue, (0.0, depot_id, depot_id))
        node_to_cost[depot_id] = 0.0
        node_to_depot[depot_id] = depot_id

    while queue:
        curr_cost, curr_node, origin_depot = heapq.heappop(queue)

        # Skip stale heap states
        if curr_cost > node_to_cost.get(curr_node, math.inf):
            continue

        if max_cost is not None and curr_cost >= max_cost:
            continue

        for edge in graph.get_neighbors(curr_node, include_blocked=False):
            nbr = edge.destination_id
            new_cost = curr_cost + edge.cost

            if max_cost is not None and new_cost > max_cost:
                continue

            if new_cost < node_to_cost.get(nbr, math.inf):
                node_to_cost[nbr] = new_cost
                node_to_depot[nbr] = origin_depot
                heapq.heappush(queue, (new_cost, nbr, origin_depot))

    # Invert node_to_depot into depot_catchment_nodes
    depot_catchment: Dict[str, List[str]] = {d: [] for d in valid_depots}
    for node_id, depot_id in node_to_depot.items():
        if depot_id in depot_catchment:
            depot_catchment[depot_id].append(node_id)

    # Sort each catchment list for determinism
    for d in depot_catchment:
        depot_catchment[d].sort()

    return CatchmentPartition(
        depot_node_ids=valid_depots,
        node_to_depot=node_to_depot,
        node_to_cost=node_to_cost,
        depot_catchment_nodes=depot_catchment,
    )


def compute_isochrone_frontiers(
    graph: Union[Graph, DynamicGraphView],
    origin_node_id: str,
    cutoffs_seconds: List[float],
) -> Dict[float, List[str]]:
    """Calculates isochrone reachability frontiers from a given origin node.

    Parameters
    ----------
    graph : Graph or DynamicGraphView
        The road network graph.
    origin_node_id : str
        The starting node (e.g. fire station or ambulance base).
    cutoffs_seconds : List[float]
        Sorted list of travel time horizons (e.g. [240.0, 480.0, 720.0]).

    Returns
    -------
    Dict[float, List[str]]
        Mapping from cutoff seconds to the list of node IDs reachable within that threshold.
    """
    if not graph.has_node(origin_node_id):
        raise KeyError(f"Origin node '{origin_node_id}' not found in graph.")

    sorted_cutoffs = sorted(cutoffs_seconds)
    if not sorted_cutoffs:
        return {}

    max_cutoff = sorted_cutoffs[-1]
    distances: Dict[str, float] = {origin_node_id: 0.0}
    queue: List[Tuple[float, str]] = [(0.0, origin_node_id)]

    while queue:
        curr_dist, curr_node = heapq.heappop(queue)

        if curr_dist > distances.get(curr_node, math.inf):
            continue

        if curr_dist >= max_cutoff:
            continue

        for edge in graph.get_neighbors(curr_node, include_blocked=False):
            nbr = edge.destination_id
            new_dist = curr_dist + edge.cost

            if new_dist <= max_cutoff and new_dist < distances.get(nbr, math.inf):
                distances[nbr] = new_dist
                heapq.heappush(queue, (new_dist, nbr))

    results: Dict[float, List[str]] = {}
    for cutoff in sorted_cutoffs:
        results[cutoff] = [
            nid for nid, cost in distances.items()
            if cost <= cutoff
        ]
        results[cutoff].sort()

    return results


def compute_eta_matrix(
    graph: Union[Graph, DynamicGraphView],
    sources: List[str],
    destinations: List[str],
) -> Dict[Tuple[str, str], float]:
    """Computes an all-pairs or source-to-targets travel time matrix.

    Uses individual single-source Dijkstra expansions with early-stopping
    once all target destinations for that source have been settled.

    Parameters
    ----------
    graph : Graph or DynamicGraphView
        The network graph.
    sources : List[str]
        List of candidate vehicle origin node IDs.
    destinations : List[str]
        List of incident or patient destination node IDs.

    Returns
    -------
    Dict[Tuple[str, str], float]
        Dictionary mapping (source_id, destination_id) to travel time in seconds.
        Unreachable pairs evaluate to math.inf.
    """
    matrix: Dict[Tuple[str, str], float] = {}
    dest_set = set(destinations)

    for src in sources:
        if not graph.has_node(src):
            for dst in destinations:
                matrix[(src, dst)] = math.inf
            continue

        # Single source Dijkstra to dest_set
        distances: Dict[str, float] = {src: 0.0}
        queue: List[Tuple[float, str]] = [(0.0, src)]
        settled_dests: Set[str] = set()

        while queue and len(settled_dests) < len(dest_set):
            curr_dist, curr_node = heapq.heappop(queue)

            if curr_dist > distances.get(curr_node, math.inf):
                continue

            if curr_node in dest_set:
                settled_dests.add(curr_node)

            for edge in graph.get_neighbors(curr_node, include_blocked=False):
                nbr = edge.destination_id
                new_dist = curr_dist + edge.cost

                if new_dist < distances.get(nbr, math.inf):
                    distances[nbr] = new_dist
                    heapq.heappush(queue, (new_dist, nbr))

        for dst in destinations:
            matrix[(src, dst)] = distances.get(dst, math.inf)

    return matrix


def find_closest_depot(
    graph: Union[Graph, DynamicGraphView],
    target_node_id: str,
    depot_node_ids: List[str],
) -> Optional[Tuple[str, float]]:
    """Identifies the closest depot to target_node_id and its travel time.

    Returns None if no depot can reach target_node_id.
    """
    if not graph.has_node(target_node_id) or not depot_node_ids:
        return None

    catchment = compute_multi_source_catchment(graph, depot_node_ids)
    assigned_depot = catchment.get_assigned_depot(target_node_id)
    if assigned_depot is None:
        return None

    cost = catchment.get_travel_cost(target_node_id)
    if math.isinf(cost):
        return None

    return (assigned_depot, cost)
