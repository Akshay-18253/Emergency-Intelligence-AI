"""
OpenStreetMap (OSM) ingestion and graph extraction.

Parses OSM Overpass JSON datasets and maps real-world intersections and
road segments into the Emergency Intelligence AI :class:`~emergency_intelligence.graph.models.Graph`
data model without altering the routing engine.

OpenStreetMap Data Model Mapping
--------------------------------
- OSM Node (with lat/lon)    --> Graph Node (with Cartesian/spherical coordinates)
- OSM Way (highway segment)  --> Graph Directed Edges (with Haversine distance costs)
- OSM oneway=* tag           --> Forward-only, reverse, or bidirectional edges

References
----------
- OpenStreetMap Wiki: Key:highway (https://wiki.openstreetmap.org/wiki/Key:highway)
- OpenStreetMap Wiki: Key:oneway (https://wiki.openstreetmap.org/wiki/Key:oneway)
- Overpass API JSON Format (https://wiki.openstreetmap.org/wiki/Overpass_API/Language_Guide)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from emergency_intelligence.graph.models import Edge, Graph, Node
from .geo import haversine_distance

# Standard vehicular road classifications suitable for emergency routing
DEFAULT_HIGHWAY_TYPES: Set[str] = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "service",
    "living_street",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
}


def load_osm_graph_from_data(
    osm_data: Dict[str, Any],
    highway_filter: Optional[Set[str]] = None,
) -> Graph:
    """Parse an OpenStreetMap Overpass JSON dictionary into a :class:`Graph`.

    Parameters
    ----------
    osm_data:
        A dictionary containing an ``"elements"`` list formatted according
        to the standard Overpass JSON specification.
    highway_filter:
        Set of accepted ``highway`` tag values. If ``None``, defaults to
        :data:`DEFAULT_HIGHWAY_TYPES`.

    Returns
    -------
    Graph
        A directed weighted :class:`Graph` containing road intersections as
        nodes and road segments as directed edges weighted by physical length
        in meters.

    Raises
    ------
    ValueError
        If *osm_data* does not contain a valid ``"elements"`` list.
    """
    if not isinstance(osm_data, dict) or "elements" not in osm_data:
        raise ValueError("Invalid OSM data: expected dictionary with an 'elements' list.")

    elements: List[Dict[str, Any]] = osm_data["elements"]
    allowed_highways = highway_filter if highway_filter is not None else DEFAULT_HIGHWAY_TYPES

    # 1. Index raw nodes by ID: id -> raw_dict
    raw_nodes: Dict[int, Dict[str, Any]] = {}
    ways: List[Dict[str, Any]] = []

    for elem in elements:
        elem_type = elem.get("type")
        if elem_type == "node" and "id" in elem and "lat" in elem and "lon" in elem:
            raw_nodes[elem["id"]] = elem
        elif elem_type == "way" and "id" in elem and "nodes" in elem:
            tags = elem.get("tags", {})
            highway_tag = tags.get("highway")
            if highway_tag in allowed_highways:
                ways.append(elem)

    # 2. Identify nodes actually referenced by valid road ways (pruning orphaned nodes)
    active_node_ids: Set[int] = set()
    for way in ways:
        way_node_refs = way.get("nodes", [])
        for nid in way_node_refs:
            if nid in raw_nodes:
                active_node_ids.add(nid)

    # 3. Construct the Graph and add active Nodes
    graph = Graph()
    for nid in active_node_ids:
        raw_node = raw_nodes[nid]
        node_id_str = str(nid)
        lat = float(raw_node["lat"])
        lon = float(raw_node["lon"])
        tags = raw_node.get("tags", {})
        label = tags.get("name") or tags.get("ref")

        graph.add_node(
            Node(
                node_id=node_id_str,
                label=label,
                coordinates=(lon, lat),
            )
        )

    # 4. Construct directed Edges between consecutive way nodes
    for way in ways:
        tags = way.get("tags", {})
        way_node_refs = way.get("nodes", [])
        oneway_val = str(tags.get("oneway", "no")).lower().strip()
        is_roundabout = str(tags.get("junction", "")).lower() == "roundabout"

        # Determine directional properties
        if is_roundabout or oneway_val in ("yes", "1", "true"):
            forward = True
            reverse = False
        elif oneway_val in ("-1", "reverse"):
            forward = False
            reverse = True
        else:
            # Default for typical streets is two-way
            forward = True
            reverse = True

        for i in range(len(way_node_refs) - 1):
            u_id = way_node_refs[i]
            v_id = way_node_refs[i + 1]

            u_str = str(u_id)
            v_str = str(v_id)

            # Both endpoints must exist in the parsed graph
            if not graph.has_node(u_str) or not graph.has_node(v_str):
                continue

            node_u = graph.get_node(u_str)
            node_v = graph.get_node(v_str)

            # Assert coordinates are present
            assert node_u.coordinates is not None
            assert node_v.coordinates is not None

            # Calculate physical road segment length in meters
            cost_meters = haversine_distance(node_u.coordinates, node_v.coordinates, unit="m")

            if forward:
                graph.add_edge(Edge(source_id=u_str, destination_id=v_str, cost=cost_meters))
            if reverse:
                graph.add_edge(Edge(source_id=v_str, destination_id=u_str, cost=cost_meters))

    return graph


def load_osm_graph_from_file(
    file_path: Union[str, Path],
    highway_filter: Optional[Set[str]] = None,
) -> Graph:
    """Load an OpenStreetMap JSON export from a file path into a :class:`Graph`.

    Parameters
    ----------
    file_path:
        Path to the local ``.json`` file containing OSM Overpass elements.
    highway_filter:
        Optional set of allowed highway tag types.

    Returns
    -------
    Graph
        A populated :class:`Graph` ready for routing.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"OSM data file not found: {path.resolve()}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return load_osm_graph_from_data(data, highway_filter=highway_filter)
