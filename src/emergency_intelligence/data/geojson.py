"""
GeoJSON export, ingestion, and open geospatial interoperability.

Converts calculated RouteResult paths and Graph network features into standard
RFC 7946 GeoJSON FeatureCollections for visualization, spatial analysis, and round-trip
interoperability with open-source GIS ecosystems (e.g. QGIS, Leaflet, OpenLayers, geojson.io,
and PostGIS).

Standards Compliance
--------------------
- RFC 7946 (The GeoJSON Format Specification)
- Coordinate Reference System: WGS 84 (EPSG:4326)
- Coordinate order: [longitude, latitude] as mandated by RFC 7946 Section 3.1.1
- Bounding Box: [min_lon, min_lat, max_lon, max_lat] per RFC 7946 Section 5
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from emergency_intelligence.data.geo import haversine_distance
from emergency_intelligence.graph.dijkstra import RouteResult
from emergency_intelligence.graph.models import Edge, Graph, Node


def validate_wgs84_coordinates(lon: float, lat: float) -> None:
    """Validate that coordinates conform to WGS 84 geographic bounds.

    Parameters
    ----------
    lon:
        Longitude in degrees. Must be within [-180.0, 180.0].
    lat:
        Latitude in degrees. Must be within [-90.0, 90.0].

    Raises
    ------
    ValueError
        If coordinates are non-numeric, infinite, NaN, or out of range.
    """
    if not isinstance(lon, (int, float)) or not isinstance(lat, (int, float)):
        raise ValueError(
            f"Coordinates must be numeric floats or ints. Received lon={type(lon).__name__}, lat={type(lat).__name__}."
        )

    if not math.isfinite(lon) or not math.isfinite(lat):
        raise ValueError(f"Coordinates must be finite numbers. Received lon={lon}, lat={lat}.")

    if not (-180.0 <= lon <= 180.0):
        raise ValueError(
            f"Longitude {lon} is out of valid WGS 84 range [-180.0, 180.0]."
        )

    if not (-90.0 <= lat <= 90.0):
        raise ValueError(
            f"Latitude {lat} is out of valid WGS 84 range [-90.0, 90.0]."
        )


def compute_bounding_box(coordinates: List[List[float]]) -> List[float]:
    """Compute standard RFC 7946 bounding box [min_lon, min_lat, max_lon, max_lat].

    Parameters
    ----------
    coordinates:
        List of [lon, lat] pairs.

    Returns
    -------
    list of float
        [min_lon, min_lat, max_lon, max_lat]. If list is empty, returns [0.0, 0.0, 0.0, 0.0].
    """
    if not coordinates:
        return [0.0, 0.0, 0.0, 0.0]

    min_lon = min(c[0] for c in coordinates)
    min_lat = min(c[1] for c in coordinates)
    max_lon = max(c[0] for c in coordinates)
    max_lat = max(c[1] for c in coordinates)

    return [min_lon, min_lat, max_lon, max_lat]


def route_to_geojson(
    route: RouteResult,
    graph: Graph,
    algorithm_name: Optional[str] = None,
    include_bbox: bool = True,
) -> Dict[str, Any]:
    """Convert a :class:`RouteResult` into an RFC 7946 GeoJSON FeatureCollection.

    Includes:
      - A ``LineString`` Feature representing the full trajectory with cost and execution metadata.
      - A ``Point`` Feature for each traversed node classified as ``origin``, ``waypoint``, or ``destination``.
      - RFC 7946 standard ``bbox`` bounding box for automatic map centering.

    Parameters
    ----------
    route:
        The routing query result to serialize.
    graph:
        The :class:`Graph` containing node coordinates and labels.
    algorithm_name:
        Optional algorithm identifier (e.g. "A*", "Dijkstra") added to properties.
    include_bbox:
        Whether to calculate and attach the RFC 7946 bounding box.

    Returns
    -------
    dict
        RFC 7946 compliant GeoJSON dictionary.

    Raises
    ------
    ValueError
        If any node on the route path lacks defined spatial coordinates or has invalid coordinates.
    """
    if not route.reachable or not route.path:
        return {
            "type": "FeatureCollection",
            "features": [],
            "properties": {
                "source": route.source,
                "destination": route.destination,
                "reachable": False,
                "total_cost": route.total_cost,
                "nodes_explored": route.nodes_explored,
            },
        }

    # Extract coordinates in [longitude, latitude] order
    coordinates: List[List[float]] = []
    waypoint_features: List[Dict[str, Any]] = []

    for idx, nid in enumerate(route.path):
        node = graph.get_node(nid)
        if node.coordinates is None:
            raise ValueError(
                f"Node {nid!r} does not have coordinates defined. "
                "GeoJSON serialization requires (x, y) = (lon, lat) coordinates on all route nodes."
            )

        lon, lat = float(node.coordinates[0]), float(node.coordinates[1])
        validate_wGS84 = validate_wgs84_coordinates(lon, lat)

        point_coords = [lon, lat]
        coordinates.append(point_coords)

        # Classify role
        if idx == 0:
            role = "origin"
        elif idx == len(route.path) - 1:
            role = "destination"
        else:
            role = "waypoint"

        waypoint_features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": point_coords,
                },
                "properties": {
                    "node_id": nid,
                    "label": node.label or f"Node {nid}",
                    "role": role,
                    "step_index": idx,
                },
            }
        )

    # LineString feature for the active emergency route trajectory
    linestring_feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coordinates,
        },
        "properties": {
            "source": route.source,
            "destination": route.destination,
            "total_cost": route.total_cost,
            "distance_m": route.total_cost,
            "hops": len(route.path) - 1,
            "nodes_explored": route.nodes_explored,
            "execution_time_ms": route.execution_time_ms,
            "algorithm": algorithm_name or "Deterministic Routing",
            "path": route.path,
        },
    }

    result: Dict[str, Any] = {
        "type": "FeatureCollection",
        "features": [linestring_feature] + waypoint_features,
    }

    if include_bbox and coordinates:
        result["bbox"] = compute_bounding_box(coordinates)

    return result


def graph_to_geojson(graph: Graph, include_bbox: bool = True) -> Dict[str, Any]:
    """Convert an entire :class:`Graph` road network into an RFC 7946 GeoJSON FeatureCollection.

    Includes:
      - A ``LineString`` Feature for each directed road edge whose endpoints have spatial coordinates.
      - A ``Point`` Feature for each node with spatial coordinates and degree metadata.
      - RFC 7946 standard ``bbox`` bounding box.

    Parameters
    ----------
    graph:
        The graph to serialize.
    include_bbox:
        Whether to calculate and attach the RFC 7946 bounding box.

    Returns
    -------
    dict
        RFC 7946 compliant GeoJSON dictionary.
    """
    features: List[Dict[str, Any]] = []
    all_coordinates: List[List[float]] = []

    # 1. Export Node Points
    for nid in graph.node_ids():
        node = graph.get_node(nid)
        if node.coordinates is not None:
            lon, lat = float(node.coordinates[0]), float(node.coordinates[1])
            validate_wgs84_coordinates(lon, lat)
            point_coords = [lon, lat]
            all_coordinates.append(point_coords)

            out_degree = len(graph.get_neighbors(nid))
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": point_coords,
                    },
                    "properties": {
                        "node_id": nid,
                        "label": node.label or f"Node {nid}",
                        "out_degree": out_degree,
                    },
                }
            )

    # 2. Export Edge LineStrings
    for src_id in graph.node_ids():
        src_node = graph.get_node(src_id)
        if src_node.coordinates is None:
            continue

        src_coords = [float(src_node.coordinates[0]), float(src_node.coordinates[1])]

        for edge in graph.get_neighbors(src_id):
            dst_node = graph.get_node(edge.destination_id)
            if dst_node.coordinates is None:
                continue

            dst_coords = [float(dst_node.coordinates[0]), float(dst_node.coordinates[1])]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [src_coords, dst_coords],
                    },
                    "properties": {
                        "source": edge.source_id,
                        "destination": edge.destination_id,
                        "cost": edge.cost,
                    },
                }
            )

    result: Dict[str, Any] = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "node_count": graph.node_count(),
            "edge_count": graph.edge_count(),
        },
    }

    if include_bbox and all_coordinates:
        result["bbox"] = compute_bounding_box(all_coordinates)

    return result


def load_graph_from_geojson(data_or_path: Union[str, Path, Dict[str, Any]]) -> Graph:
    """Ingest an RFC 7946 GeoJSON FeatureCollection into a core :class:`Graph` model.

    Supports round-trip reconstruction from files produced by :func:`graph_to_geojson`
    or GIS road layers created in QGIS/Leaflet.

    Parameters
    ----------
    data_or_path:
        File path to a .geojson file, raw JSON string, or parsed GeoJSON dictionary.

    Returns
    -------
    Graph
        Populated directed weighted graph.

    Raises
    ------
    ValueError
        If the GeoJSON structure is invalid or lacks necessary geometry.
    FileNotFoundError
        If a provided file path does not exist.
    """
    if isinstance(data_or_path, (str, Path)):
        path = Path(data_or_path)
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            # Check if it's a raw JSON string
            try:
                data = json.loads(str(data_or_path))
            except json.JSONDecodeError as err:
                raise FileNotFoundError(f"GeoJSON file not found at: {path}") from err
    elif isinstance(data_or_path, dict):
        data = data_or_path
    else:
        raise ValueError(f"Expected file path, JSON string, or dict. Got {type(data_or_path).__name__}.")

    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError("Root GeoJSON object must be a 'FeatureCollection'.")

    features = data.get("features", [])
    if not isinstance(features, list):
        raise ValueError("GeoJSON 'features' field must be a list.")

    graph = Graph()

    # Pass 1: Ingest Point nodes
    for idx, feature in enumerate(features):
        geom = feature.get("geometry", {})
        if geom.get("type") == "Point":
            coords = geom.get("coordinates")
            if not coords or len(coords) < 2:
                continue
            lon, lat = float(coords[0]), float(coords[1])
            validate_wgs84_coordinates(lon, lat)

            props = feature.get("properties", {}) or {}
            node_id = str(props.get("node_id") or feature.get("id") or f"pt_{idx}")
            label = props.get("label") or f"Node {node_id}"

            if not graph.has_node(node_id):
                graph.add_node(Node(node_id, label=label, coordinates=(lon, lat)))

    # Pass 2: Ingest LineString edges
    for idx, feature in enumerate(features):
        geom = feature.get("geometry", {})
        if geom.get("type") == "LineString":
            coords = geom.get("coordinates", [])
            if len(coords) < 2:
                continue

            props = feature.get("properties", {}) or {}
            src_id = props.get("source")
            dst_id = props.get("destination")
            cost = props.get("cost")

            if src_id and dst_id:
                src_id_str = str(src_id)
                dst_id_str = str(dst_id)

                # Ensure nodes exist
                if not graph.has_node(src_id_str):
                    c0 = coords[0]
                    graph.add_node(Node(src_id_str, coordinates=(float(c0[0]), float(c0[1]))))
                if not graph.has_node(dst_id_str):
                    c1 = coords[-1]
                    graph.add_node(Node(dst_id_str, coordinates=(float(c1[0]), float(c1[1]))))

                if cost is None:
                    # Calculate Haversine distance between endpoints
                    c0 = coords[0]
                    c1 = coords[-1]
                    cost = haversine_distance((float(c0[0]), float(c0[1])), (float(c1[0]), float(c1[1])))
                else:
                    cost = float(cost)

                graph.add_edge(Edge(src_id_str, dst_id_str, cost=cost))
            else:
                # Segment-by-segment polyline ingestion
                for seg_i in range(len(coords) - 1):
                    p1 = coords[seg_i]
                    p2 = coords[seg_i + 1]
                    n1_id = f"line_{idx}_seg_{seg_i}"
                    n2_id = f"line_{idx}_seg_{seg_i + 1}"

                    if not graph.has_node(n1_id):
                        graph.add_node(Node(n1_id, coordinates=(float(p1[0]), float(p1[1]))))
                    if not graph.has_node(n2_id):
                        graph.add_node(Node(n2_id, coordinates=(float(p2[0]), float(p2[1]))))

                    seg_cost = haversine_distance((float(p1[0]), float(p1[1])), (float(p2[0]), float(p2[1])))
                    graph.add_edge(Edge(n1_id, n2_id, cost=seg_cost))

    return graph


def save_geojson(
    data: Dict[str, Any],
    file_path: Union[str, Path],
    indent: int = 2,
) -> Path:
    """Serialize a GeoJSON dictionary directly to a local ``.geojson`` file on disk.

    Parameters
    ----------
    data:
        The GeoJSON dictionary to write.
    file_path:
        Target output file path.
    indent:
        JSON indentation spaces (default 2).

    Returns
    -------
    Path
        Path to the saved GeoJSON file.
    """
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent)

    return target


def save_route_geojson(
    route: RouteResult,
    graph: Graph,
    file_path: Union[str, Path],
    algorithm_name: Optional[str] = None,
    indent: int = 2,
    include_bbox: bool = True,
) -> Path:
    """Serialize a route to a local ``.geojson`` file on disk.

    Parameters
    ----------
    route:
        The routing query result.
    graph:
        The graph containing spatial coordinates.
    file_path:
        Target file path.
    algorithm_name:
        Optional algorithm tag.
    indent:
        JSON indentation spaces (default 2).
    include_bbox:
        Whether to calculate and attach the RFC 7946 bounding box.

    Returns
    -------
    Path
        Path to the saved GeoJSON file.
    """
    geojson_dict = route_to_geojson(
        route,
        graph,
        algorithm_name=algorithm_name,
        include_bbox=include_bbox,
    )
    return save_geojson(geojson_dict, file_path, indent=indent)


def save_graph_geojson(
    graph: Graph,
    file_path: Union[str, Path],
    indent: int = 2,
    include_bbox: bool = True,
) -> Path:
    """Serialize an entire road network graph to a local ``.geojson`` file on disk.

    Parameters
    ----------
    graph:
        The graph to serialize.
    file_path:
        Target file path.
    indent:
        JSON indentation spaces (default 2).
    include_bbox:
        Whether to calculate and attach the RFC 7946 bounding box.

    Returns
    -------
    Path
        Path to the saved GeoJSON file.
    """
    geojson_dict = graph_to_geojson(graph, include_bbox=include_bbox)
    return save_geojson(geojson_dict, file_path, indent=indent)
