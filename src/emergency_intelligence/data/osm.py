"""
OpenStreetMap (OSM) ingestion and multi-criteria graph extraction.

Parses OSM Overpass JSON datasets and streaming OSM XML (.osm) datasets,
mapping real-world intersections and road segments into the Emergency
Intelligence AI :class:`~emergency_intelligence.graph.models.Graph` data model
with support for multi-criteria cost models, vehicular speed limits, and emergency
access privileges.

OpenStreetMap Data Model Mapping
--------------------------------
- OSM Node (with lat/lon)    --> Graph Node (with Cartesian/spherical coordinates)
- OSM Way (highway segment)  --> Graph Directed Edges (with distance or travel time costs)
- OSM oneway=* tag           --> Forward-only, reverse, or bidirectional edges
- OSM maxspeed=* tag         --> Speed limit parsing (km/h, mph, walk, conditions)
- OSM emergency / access     --> Emergency vehicle bypass privileges

References
----------
- OpenStreetMap Wiki: Key:highway (https://wiki.openstreetmap.org/wiki/Key:highway)
- OpenStreetMap Wiki: Key:oneway (https://wiki.openstreetmap.org/wiki/Key:oneway)
- OpenStreetMap Wiki: Key:maxspeed (https://wiki.openstreetmap.org/wiki/Key:maxspeed)
- OpenStreetMap Wiki: Key:access (https://wiki.openstreetmap.org/wiki/Key:access)
- Overpass API JSON Format (https://wiki.openstreetmap.org/wiki/Overpass_API/Language_Guide)
"""

from __future__ import annotations

import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, BinaryIO, Dict, List, Optional, Set, TextIO, Tuple, Union

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

# Default vehicular speeds (in km/h) per road classification
DEFAULT_SPEEDS_KMH: Dict[str, float] = {
    "motorway": 100.0,
    "motorway_link": 60.0,
    "trunk": 80.0,
    "trunk_link": 50.0,
    "primary": 60.0,
    "primary_link": 45.0,
    "secondary": 50.0,
    "secondary_link": 35.0,
    "tertiary": 40.0,
    "tertiary_link": 30.0,
    "unclassified": 30.0,
    "residential": 25.0,
    "living_street": 15.0,
    "service": 15.0,
}

# Priority multipliers for emergency vehicles (lights and sirens)
EMERGENCY_SPEED_FACTORS: Dict[str, float] = {
    "motorway": 1.20,
    "motorway_link": 1.15,
    "trunk": 1.20,
    "trunk_link": 1.15,
    "primary": 1.15,
    "primary_link": 1.10,
    "secondary": 1.10,
    "secondary_link": 1.05,
    "tertiary": 1.05,
    "tertiary_link": 1.00,
    "unclassified": 1.00,
    "residential": 1.00,
    "living_street": 1.00,
    "service": 1.00,
}


class WeightingProfile:
    """Weighting profiles for calculating road segment traversal cost."""

    DISTANCE = "distance"              # Traversal cost = physical distance in meters
    TRAVEL_TIME = "travel_time"        # Traversal cost = standard travel time in seconds
    EMERGENCY_TIME = "emergency_time"  # Traversal cost = emergency travel time in seconds

    VALID_PROFILES = {DISTANCE, TRAVEL_TIME, EMERGENCY_TIME}


def parse_maxspeed(
    maxspeed_val: Optional[Any],
    default_speed_kmh: float = 30.0,
) -> float:
    """Parse an OpenStreetMap ``maxspeed`` tag into speed in kilometers per hour.

    Supports numeric values, explicit units (``km/h``, ``kmh``, ``mph``, ``kph``),
    special tokens (``walk``, ``signals``, ``none``), and conditional definitions.

    Parameters
    ----------
    maxspeed_val:
        Raw tag value from OSM (e.g. ``"50"``, ``"30 mph"``, ``"walk"``).
    default_speed_kmh:
        Fallback speed in km/h if tag is absent or unparseable.

    Returns
    -------
    float
        Speed limit in km/h (guaranteed > 0.0).
    """
    if maxspeed_val is None:
        return max(default_speed_kmh, 1.0)

    if isinstance(maxspeed_val, (int, float)):
        val = float(maxspeed_val)
        return val if val > 0 else max(default_speed_kmh, 1.0)

    raw_str = str(maxspeed_val).strip().lower()
    if not raw_str or raw_str in ("none", "signals", "variable", "implicit"):
        return max(default_speed_kmh, 1.0)

    if raw_str == "walk":
        return 5.0

    # Extract primary portion before conditionals, semicolons, or annotations
    # e.g., "50 @ (06:00-20:00)" -> "50", "80; 60" -> "80"
    cleaned = re.split(r"[@;:]", raw_str)[0].strip()

    # Case A: Imperial speed limit (miles per hour)
    mph_match = re.search(r"^(\d+(?:\.\d+)?)\s*(?:mph|miles_per_hour)$", cleaned)
    if mph_match:
        val = float(mph_match.group(1)) * 1.609344
        return val if val > 0 else max(default_speed_kmh, 1.0)

    # Case B: Metric speed limit with explicit unit
    kmh_match = re.search(r"^(\d+(?:\.\d+)?)\s*(?:km/h|kmh|kph)$", cleaned)
    if kmh_match:
        val = float(kmh_match.group(1))
        return val if val > 0 else max(default_speed_kmh, 1.0)

    # Case C: Plain number (default metric km/h in OSM)
    num_match = re.search(r"^(\d+(?:\.\d+)?)$", cleaned)
    if num_match:
        val = float(num_match.group(1))
        return val if val > 0 else max(default_speed_kmh, 1.0)

    return max(default_speed_kmh, 1.0)


def is_way_accessible(
    tags: Dict[str, Any],
    allow_emergency_access: bool = True,
) -> bool:
    """Determine whether an OSM way is accessible for vehicular or emergency routing.

    Respects ``access``, ``motor_vehicle``, and ``motorcar`` restrictions while
    granting bypass privileges for emergency vehicles when ``emergency=yes`` or
    ``access=emergency`` tags are present.

    Parameters
    ----------
    tags:
        Dictionary of OSM tags attached to the way.
    allow_emergency_access:
        Whether emergency vehicles can bypass standard access closures.

    Returns
    -------
    bool
        True if the way can be traversed by vehicles, False otherwise.
    """
    if allow_emergency_access:
        emergency_tag = str(tags.get("emergency", "")).lower().strip()
        if emergency_tag in ("yes", "designated", "destination"):
            return True
        if str(tags.get("access", "")).lower().strip() == "emergency":
            return True

    disallowed = {"no", "private", "agricultural", "forestry", "delivery"}
    access = str(tags.get("access", "yes")).lower().strip()
    motor_vehicle = str(tags.get("motor_vehicle", access)).lower().strip()
    motorcar = str(tags.get("motorcar", motor_vehicle)).lower().strip()

    if motorcar in disallowed or motor_vehicle in disallowed or access in disallowed:
        return False

    return True


def compute_edge_cost_and_attributes(
    distance_meters: float,
    highway_type: str,
    tags: Dict[str, Any],
    weighting_profile: str,
) -> Tuple[float, Dict[str, Any]]:
    """Compute traversal cost and rich metadata attributes for a road segment.

    Parameters
    ----------
    distance_meters:
        Physical length of the road segment in meters.
    highway_type:
        OSM highway classification.
    tags:
        Dictionary of OSM tags.
    weighting_profile:
        Selected weighting mode (:class:`WeightingProfile`).

    Returns
    -------
    Tuple[float, Dict[str, Any]]
        The assigned traversal cost and attribute dictionary.
    """
    default_speed = DEFAULT_SPEEDS_KMH.get(highway_type, 30.0)
    maxspeed_kmh = parse_maxspeed(tags.get("maxspeed"), default_speed)
    speed_mps = (maxspeed_kmh * 1000.0) / 3600.0
    travel_time_s = distance_meters / max(speed_mps, 0.1)

    emergency_factor = EMERGENCY_SPEED_FACTORS.get(highway_type, 1.0)
    emergency_speed_kmh = maxspeed_kmh * emergency_factor
    emergency_speed_mps = (emergency_speed_kmh * 1000.0) / 3600.0
    emergency_time_s = distance_meters / max(emergency_speed_mps, 0.1)

    if weighting_profile == WeightingProfile.TRAVEL_TIME:
        cost = travel_time_s
    elif weighting_profile == WeightingProfile.EMERGENCY_TIME:
        cost = emergency_time_s
    else:
        cost = distance_meters

    attributes: Dict[str, Any] = {
        "distance_m": distance_meters,
        "travel_time_s": travel_time_s,
        "emergency_time_s": emergency_time_s,
        "maxspeed_kmh": maxspeed_kmh,
        "highway": highway_type,
        "name": tags.get("name"),
        "oneway": tags.get("oneway"),
        "surface": tags.get("surface"),
        "lanes": tags.get("lanes"),
        "emergency_accessible": is_way_accessible(tags, allow_emergency_access=True),
    }

    return cost, attributes


def load_osm_graph_from_data(
    osm_data: Dict[str, Any],
    highway_filter: Optional[Set[str]] = None,
    weighting_profile: str = WeightingProfile.DISTANCE,
    allow_emergency_access: bool = True,
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
    weighting_profile:
        Cost calculation profile (:class:`WeightingProfile`).
    allow_emergency_access:
        Whether emergency bypass rules apply to restricted ways.

    Returns
    -------
    Graph
        A directed weighted :class:`Graph` containing road intersections as
        nodes and road segments as directed edges.

    Raises
    ------
    ValueError
        If *osm_data* does not contain an ``"elements"`` list or invalid profile.
    """
    if weighting_profile not in WeightingProfile.VALID_PROFILES:
        raise ValueError(
            f"Invalid weighting_profile {weighting_profile!r}. "
            f"Must be one of {sorted(WeightingProfile.VALID_PROFILES)}."
        )

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
            if highway_tag in allowed_highways and is_way_accessible(tags, allow_emergency_access):
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
        highway_type = tags.get("highway", "unclassified")
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
            forward = True
            reverse = True

        for i in range(len(way_node_refs) - 1):
            u_id = way_node_refs[i]
            v_id = way_node_refs[i + 1]

            u_str = str(u_id)
            v_str = str(v_id)

            if not graph.has_node(u_str) or not graph.has_node(v_str):
                continue

            node_u = graph.get_node(u_str)
            node_v = graph.get_node(v_str)

            assert node_u.coordinates is not None
            assert node_v.coordinates is not None

            distance_m = haversine_distance(node_u.coordinates, node_v.coordinates, unit="m")
            cost, attributes = compute_edge_cost_and_attributes(
                distance_meters=distance_m,
                highway_type=highway_type,
                tags=tags,
                weighting_profile=weighting_profile,
            )

            if forward:
                graph.add_edge(
                    Edge(source_id=u_str, destination_id=v_str, cost=cost, attributes=dict(attributes))
                )
            if reverse:
                graph.add_edge(
                    Edge(source_id=v_str, destination_id=u_str, cost=cost, attributes=dict(attributes))
                )

    return graph


def load_osm_graph_from_file(
    file_path: Union[str, Path],
    highway_filter: Optional[Set[str]] = None,
    weighting_profile: str = WeightingProfile.DISTANCE,
    allow_emergency_access: bool = True,
) -> Graph:
    """Load an OpenStreetMap JSON export from a file path into a :class:`Graph`.

    Parameters
    ----------
    file_path:
        Path to the local ``.json`` file containing OSM Overpass elements.
    highway_filter:
        Optional set of allowed highway tag types.
    weighting_profile:
        Cost calculation profile (:class:`WeightingProfile`).
    allow_emergency_access:
        Whether emergency bypass rules apply.

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

    return load_osm_graph_from_data(
        data,
        highway_filter=highway_filter,
        weighting_profile=weighting_profile,
        allow_emergency_access=allow_emergency_access,
    )


def load_osm_graph_from_xml_stream(
    source: Union[str, Path, BinaryIO, TextIO],
    highway_filter: Optional[Set[str]] = None,
    weighting_profile: str = WeightingProfile.DISTANCE,
    allow_emergency_access: bool = True,
) -> Graph:
    """Stream parse an OpenStreetMap XML (.osm) dataset into a :class:`Graph`.

    Uses streaming standard library :func:`xml.etree.ElementTree.iterparse` to
    extract intersections and road ways in a memory-efficient manner.

    Parameters
    ----------
    source:
        File path, open stream, or Path object pointing to an OSM XML document.
    highway_filter:
        Optional set of allowed highway tag types.
    weighting_profile:
        Cost calculation profile (:class:`WeightingProfile`).
    allow_emergency_access:
        Whether emergency vehicles can traverse restricted ways.

    Returns
    -------
    Graph
        A populated :class:`Graph` ready for routing.
    """
    if weighting_profile not in WeightingProfile.VALID_PROFILES:
        raise ValueError(
            f"Invalid weighting_profile {weighting_profile!r}. "
            f"Must be one of {sorted(WeightingProfile.VALID_PROFILES)}."
        )

    allowed_highways = highway_filter if highway_filter is not None else DEFAULT_HIGHWAY_TYPES

    # Node storage: id -> (lon, lat, label)
    raw_nodes: Dict[int, Tuple[float, float, Optional[str]]] = {}
    # Way storage: list of (way_id, node_refs, tags)
    ways: List[Tuple[int, List[int], Dict[str, str]]] = []

    # Parse with iterparse
    for event, elem in ET.iterparse(source, events=("end",)):
        tag_name = elem.tag.split("}")[-1]  # Strip any XML namespace

        if tag_name == "node":
            nid_str = elem.attrib.get("id")
            lat_str = elem.attrib.get("lat")
            lon_str = elem.attrib.get("lon")
            if nid_str is not None and lat_str is not None and lon_str is not None:
                nid = int(nid_str)
                lat = float(lat_str)
                lon = float(lon_str)
                node_tags = {
                    child.attrib.get("k", ""): child.attrib.get("v", "")
                    for child in elem
                    if child.tag.split("}")[-1] == "tag"
                }
                label = node_tags.get("name") or node_tags.get("ref")
                raw_nodes[nid] = (lon, lat, label)
            elem.clear()

        elif tag_name == "way":
            way_id_str = elem.attrib.get("id")
            if way_id_str is not None:
                way_id = int(way_id_str)
                node_refs: List[int] = []
                way_tags: Dict[str, str] = {}
                for child in elem:
                    child_tag = child.tag.split("}")[-1]
                    if child_tag == "nd":
                        ref = child.attrib.get("ref")
                        if ref is not None:
                            node_refs.append(int(ref))
                    elif child_tag == "tag":
                        k = child.attrib.get("k")
                        v = child.attrib.get("v")
                        if k and v:
                            way_tags[k] = v

                highway_val = way_tags.get("highway")
                if highway_val in allowed_highways and is_way_accessible(way_tags, allow_emergency_access):
                    ways.append((way_id, node_refs, way_tags))
            elem.clear()

    # Active node filtering
    active_node_ids: Set[int] = set()
    for _, node_refs, _ in ways:
        for nid in node_refs:
            if nid in raw_nodes:
                active_node_ids.add(nid)

    # Build Graph
    graph = Graph()
    for nid in active_node_ids:
        lon, lat, label = raw_nodes[nid]
        graph.add_node(
            Node(
                node_id=str(nid),
                label=label,
                coordinates=(lon, lat),
            )
        )

    # Build Edges
    for _, node_refs, way_tags in ways:
        highway_type = way_tags.get("highway", "unclassified")
        oneway_val = str(way_tags.get("oneway", "no")).lower().strip()
        is_roundabout = str(way_tags.get("junction", "")).lower() == "roundabout"

        if is_roundabout or oneway_val in ("yes", "1", "true"):
            forward = True
            reverse = False
        elif oneway_val in ("-1", "reverse"):
            forward = False
            reverse = True
        else:
            forward = True
            reverse = True

        for i in range(len(node_refs) - 1):
            u_id = str(node_refs[i])
            v_id = str(node_refs[i + 1])

            if not graph.has_node(u_id) or not graph.has_node(v_id):
                continue

            node_u = graph.get_node(u_id)
            node_v = graph.get_node(v_id)

            assert node_u.coordinates is not None
            assert node_v.coordinates is not None

            distance_m = haversine_distance(node_u.coordinates, node_v.coordinates, unit="m")
            cost, attributes = compute_edge_cost_and_attributes(
                distance_meters=distance_m,
                highway_type=highway_type,
                tags=way_tags,
                weighting_profile=weighting_profile,
            )

            if forward:
                graph.add_edge(
                    Edge(source_id=u_id, destination_id=v_id, cost=cost, attributes=dict(attributes))
                )
            if reverse:
                graph.add_edge(
                    Edge(source_id=v_id, destination_id=u_id, cost=cost, attributes=dict(attributes))
                )

    return graph


def load_osm_graph_from_xml_string(
    xml_string: str,
    highway_filter: Optional[Set[str]] = None,
    weighting_profile: str = WeightingProfile.DISTANCE,
    allow_emergency_access: bool = True,
) -> Graph:
    """Parse an OpenStreetMap XML string into a :class:`Graph`."""
    stream = io.StringIO(xml_string)
    return load_osm_graph_from_xml_stream(
        stream,
        highway_filter=highway_filter,
        weighting_profile=weighting_profile,
        allow_emergency_access=allow_emergency_access,
    )


def load_osm_graph_from_xml_file(
    file_path: Union[str, Path],
    highway_filter: Optional[Set[str]] = None,
    weighting_profile: str = WeightingProfile.DISTANCE,
    allow_emergency_access: bool = True,
) -> Graph:
    """Parse an OpenStreetMap XML file (.osm) into a :class:`Graph`."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"OSM XML file not found: {path.resolve()}")

    with open(path, "rb") as f:
        return load_osm_graph_from_xml_stream(
            f,
            highway_filter=highway_filter,
            weighting_profile=weighting_profile,
            allow_emergency_access=allow_emergency_access,
        )
