"""
Graph topology hardening, degree-2 node contraction, and connectivity analysis.

Provides production-grade algorithms for:
- Degree-2 Intermediate Node Contraction (topological graph simplification)
- Strongly Connected Components (SCC) via Tarjan's algorithm
- Largest Strongly Connected Component (LSCC) extraction to prune isolated road islands
- Forward azimuth bearing calculation and turn maneuver classification
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Set, Tuple

from emergency_intelligence.graph.models import Edge, Graph, Node


# ---------------------------------------------------------------------------
# 1. Geographic Azimuth Bearing & Turn Maneuver Classification
# ---------------------------------------------------------------------------


def calculate_bearing(p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
    """Calculate the geographic forward azimuth bearing from *p1* to *p2*.

    Parameters
    ----------
    p1:
        Coordinates ``(lon, lat)`` of the origin location.
    p2:
        Coordinates ``(lon, lat)`` of the destination location.

    Returns
    -------
    float
        Forward azimuth bearing in degrees in the range ``[0.0, 360.0)``
        clockwise from true North.
    """
    lon1, lat1 = p1
    lon2, lat2 = p2

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    bearing_rad = math.atan2(y, x)
    bearing_deg = (math.degrees(bearing_rad) + 360.0) % 360.0
    return bearing_deg


def calculate_turn_angle(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
) -> float:
    """Calculate the relative turn angle at intersection *p2* between segments *p1*->*p2* and *p2*->*p3*.

    Parameters
    ----------
    p1:
        Coordinates ``(lon, lat)`` of the entry node.
    p2:
        Coordinates ``(lon, lat)`` of the intersection vertex.
    p3:
        Coordinates ``(lon, lat)`` of the exit node.

    Returns
    -------
    float
        Relative turn angle in degrees in the range ``[-180.0, 180.0]``.
        Positive angles designate right turns; negative angles designate left turns.
        An angle of ``0.0`` designates continuing straight ahead.
    """
    b1 = calculate_bearing(p1, p2)
    b2 = calculate_bearing(p2, p3)
    turn = (b2 - b1 + 540.0) % 360.0 - 180.0
    return turn


def classify_turn_maneuver(turn_angle_deg: float) -> str:
    """Classify a turn angle into standard navigation maneuver instructions.

    Parameters
    ----------
    turn_angle_deg:
        Turn angle in degrees in range ``[-180.0, 180.0]``.

    Returns
    -------
    str
        One of: ``"straight"``, ``"slight_right"``, ``"right"``, ``"sharp_right"``,
        ``"slight_left"``, ``"left"``, ``"sharp_left"``, ``"u_turn"``.
    """
    angle = turn_angle_deg
    if abs(angle) > 170.0:
        return "u_turn"
    if -20.0 <= angle <= 20.0:
        return "straight"
    if 20.0 < angle <= 45.0:
        return "slight_right"
    if 45.0 < angle <= 135.0:
        return "right"
    if 135.0 < angle <= 170.0:
        return "sharp_right"
    if -45.0 <= angle < -20.0:
        return "slight_left"
    if -135.0 <= angle < -45.0:
        return "left"
    if -170.0 <= angle < -135.0:
        return "sharp_left"
    return "u_turn"


# ---------------------------------------------------------------------------
# 2. Tarjan's Strongly Connected Components (SCC)
# ---------------------------------------------------------------------------


def tarjan_scc(graph: Graph) -> List[List[str]]:
    """Compute strongly connected components (SCCs) of a directed graph using Tarjan's algorithm.

    Implemented using an explicit call stack to eliminate Python recursion limits
    on massive road network graphs.

    Parameters
    ----------
    graph:
        A directed :class:`~emergency_intelligence.graph.models.Graph`.

    Returns
    -------
    List[List[str]]
        A list of strongly connected components (each a list of node IDs),
        sorted in descending order of component size.
    """
    index = 0
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    on_stack: Set[str] = set()
    stack: List[str] = []
    components: List[List[str]] = []

    for start_node in graph.node_ids():
        if start_node in indices:
            continue

        call_stack = [(start_node, iter(graph.get_neighbors(start_node)))]
        indices[start_node] = index
        lowlink[start_node] = index
        index += 1
        stack.append(start_node)
        on_stack.add(start_node)

        while call_stack:
            v, it = call_stack[-1]
            try:
                edge = next(it)
                w = edge.destination_id
                if w not in indices:
                    indices[w] = index
                    lowlink[w] = index
                    index += 1
                    stack.append(w)
                    on_stack.add(w)
                    call_stack.append((w, iter(graph.get_neighbors(w))))
                elif w in on_stack:
                    lowlink[v] = min(lowlink[v], indices[w])
            except StopIteration:
                call_stack.pop()
                if call_stack:
                    parent, _ = call_stack[-1]
                    lowlink[parent] = min(lowlink[parent], lowlink[v])

                if lowlink[v] == indices[v]:
                    component: List[str] = []
                    while True:
                        w = stack.pop()
                        on_stack.remove(w)
                        component.append(w)
                        if w == v:
                            break
                    components.append(component)

    components.sort(key=len, reverse=True)
    return components


def extract_largest_strongly_connected_component(graph: Graph) -> Graph:
    """Extract the Largest Strongly Connected Component (LSCC) of a directed graph.

    Prunes isolated dead-end clusters, disconnected parking lots, and unreachable
    islands, guaranteeing that any two nodes in the resulting graph have mutual reachability.

    Parameters
    ----------
    graph:
        Input :class:`Graph`.

    Returns
    -------
    Graph
        A new :class:`Graph` containing only the nodes and edges of the LSCC.
    """
    if graph.node_count() == 0:
        return Graph()

    sccs = tarjan_scc(graph)
    if not sccs:
        return Graph()

    largest_scc_nodes = set(sccs[0])
    subgraph = Graph()

    for nid in largest_scc_nodes:
        subgraph.add_node(graph.get_node(nid))

    for u in largest_scc_nodes:
        for edge in graph.get_neighbors(u):
            if edge.destination_id in largest_scc_nodes:
                subgraph.add_edge(
                    Edge(
                        source_id=edge.source_id,
                        destination_id=edge.destination_id,
                        cost=edge.cost,
                        attributes=dict(edge.attributes),
                    )
                )

    return subgraph


# ---------------------------------------------------------------------------
# 3. Degree-2 Intermediate Node Contraction (Topology Simplification)
# ---------------------------------------------------------------------------


def _merge_edge_attributes(
    e1_attrs: Dict[str, Any],
    e2_attrs: Dict[str, Any],
    node_n_coords: Optional[Tuple[float, float]],
    node_u_coords: Optional[Tuple[float, float]],
    node_v_coords: Optional[Tuple[float, float]],
) -> Dict[str, Any]:
    """Merge attributes and polyline geometry from two sequential edges."""
    merged = dict(e1_attrs)

    # Sum metric costs if present
    if "distance_m" in e1_attrs and "distance_m" in e2_attrs:
        merged["distance_m"] = e1_attrs["distance_m"] + e2_attrs["distance_m"]
    if "travel_time_s" in e1_attrs and "travel_time_s" in e2_attrs:
        merged["travel_time_s"] = e1_attrs["travel_time_s"] + e2_attrs["travel_time_s"]
    if "emergency_time_s" in e1_attrs and "emergency_time_s" in e2_attrs:
        merged["emergency_time_s"] = e1_attrs["emergency_time_s"] + e2_attrs["emergency_time_s"]

    # Stitch polyline geometry
    geom1: List[Tuple[float, float]] = []
    if "geometry" in e1_attrs and e1_attrs["geometry"]:
        geom1 = list(e1_attrs["geometry"])
    elif node_u_coords and node_n_coords:
        geom1 = [node_u_coords, node_n_coords]

    geom2: List[Tuple[float, float]] = []
    if "geometry" in e2_attrs and e2_attrs["geometry"]:
        geom2 = list(e2_attrs["geometry"])
    elif node_n_coords and node_v_coords:
        geom2 = [node_n_coords, node_v_coords]

    if geom1 and geom2:
        # Avoid duplicate coordinate at the stitching vertex
        merged["geometry"] = geom1 + geom2[1:]
    elif geom1:
        merged["geometry"] = geom1
    elif geom2:
        merged["geometry"] = geom2

    return merged


def contract_degree2_nodes(
    graph: Graph,
    protected_node_ids: Optional[Set[str]] = None,
) -> Graph:
    """Contract intermediate degree-2 nodes into consolidated edges while preserving polyline geometry.

    Removes shape-only curvature points that lie between intersections without
    altering shortest path topological distances. Intermediate coordinates are
    accumulated into the ``"geometry"`` attribute list of the contracted edge.

    Parameters
    ----------
    graph:
        Input :class:`Graph`.
    protected_node_ids:
        Optional set of node IDs that must NEVER be contracted (e.g. hospitals,
        fire stations, critical waypoints).

    Returns
    -------
    Graph
        A compacted :class:`Graph` containing only true intersections, dead ends,
        and protected nodes.
    """
    protected = protected_node_ids if protected_node_ids is not None else set()

    # Build active in-memory representation
    nodes: Dict[str, Node] = {nid: graph.get_node(nid) for nid in graph.node_ids()}
    out_edges: Dict[str, Dict[str, Edge]] = {nid: {} for nid in nodes}
    in_edges: Dict[str, Dict[str, Edge]] = {nid: {} for nid in nodes}

    for u in graph.node_ids():
        for edge in graph.get_neighbors(u):
            v = edge.destination_id
            # In case of duplicate edges, keep the lowest cost one
            if v not in out_edges[u] or edge.cost < out_edges[u][v].cost:
                out_edges[u][v] = edge
                in_edges[v][u] = edge

    changed = True
    while changed:
        changed = False
        candidates = list(nodes.keys())

        for n in candidates:
            if n not in nodes or n in protected:
                continue

            # Candidate must have no self-loops
            if n in out_edges[n] or n in in_edges[n]:
                continue

            # Case A: One-way intermediate node (1 in, 1 out)
            if len(in_edges[n]) == 1 and len(out_edges[n]) == 1:
                u = next(iter(in_edges[n].keys()))
                v = next(iter(out_edges[n].keys()))

                # Ensure u != n and v != n and u != v (prevent self-loops)
                if u != n and v != n and u != v:
                    e1 = in_edges[n][u]
                    e2 = out_edges[n][v]

                    new_cost = e1.cost + e2.cost
                    new_attrs = _merge_edge_attributes(
                        e1.attributes,
                        e2.attributes,
                        nodes[n].coordinates,
                        nodes[u].coordinates,
                        nodes[v].coordinates,
                    )

                    # Remove old edges from node n
                    del in_edges[n][u]
                    del out_edges[u][n]
                    del out_edges[n][v]
                    del in_edges[v][n]

                    # Add or update bypass edge u -> v
                    if v not in out_edges[u] or new_cost < out_edges[u][v].cost:
                        new_edge = Edge(source_id=u, destination_id=v, cost=new_cost, attributes=new_attrs)
                        out_edges[u][v] = new_edge
                        in_edges[v][u] = new_edge

                    del nodes[n]
                    del out_edges[n]
                    del in_edges[n]
                    changed = True
                    continue

            # Case B: Bidirectional street segment (2 in, 2 out with identical endpoints u, v)
            if len(in_edges[n]) == 2 and len(out_edges[n]) == 2:
                in_neighbors = set(in_edges[n].keys())
                out_neighbors = set(out_edges[n].keys())

                if in_neighbors == out_neighbors and len(in_neighbors) == 2:
                    u, v = tuple(in_neighbors)
                    if u != n and v != n and u != v:
                        # Forward: u -> n -> v
                        e_un = out_edges[u][n]
                        e_nv = out_edges[n][v]
                        cost_uv = e_un.cost + e_nv.cost
                        attrs_uv = _merge_edge_attributes(
                            e_un.attributes,
                            e_nv.attributes,
                            nodes[n].coordinates,
                            nodes[u].coordinates,
                            nodes[v].coordinates,
                        )

                        # Reverse: v -> n -> u
                        e_vn = out_edges[v][n]
                        e_nu = out_edges[n][u]
                        cost_vu = e_vn.cost + e_nu.cost
                        attrs_vu = _merge_edge_attributes(
                            e_vn.attributes,
                            e_nu.attributes,
                            nodes[n].coordinates,
                            nodes[v].coordinates,
                            nodes[u].coordinates,
                        )

                        # Remove edges involving n
                        del out_edges[u][n]
                        del in_edges[n][u]
                        del out_edges[n][v]
                        del in_edges[v][n]

                        del out_edges[v][n]
                        del in_edges[n][v]
                        del out_edges[n][u]
                        del in_edges[u][n]

                        # Add bypass edges
                        if v not in out_edges[u] or cost_uv < out_edges[u][v].cost:
                            edge_uv = Edge(source_id=u, destination_id=v, cost=cost_uv, attributes=attrs_uv)
                            out_edges[u][v] = edge_uv
                            in_edges[v][u] = edge_uv

                        if u not in out_edges[v] or cost_vu < out_edges[v][u].cost:
                            edge_vu = Edge(source_id=v, destination_id=u, cost=cost_vu, attributes=attrs_vu)
                            out_edges[v][u] = edge_vu
                            in_edges[u][v] = edge_vu

                        del nodes[n]
                        del out_edges[n]
                        del in_edges[n]
                        changed = True

    # Assemble output Graph
    contracted_graph = Graph()
    for nid, node in nodes.items():
        contracted_graph.add_node(node)

    for u in nodes:
        for v, edge in out_edges[u].items():
            contracted_graph.add_edge(edge)

    return contracted_graph
