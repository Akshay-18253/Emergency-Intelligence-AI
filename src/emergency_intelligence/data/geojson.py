"""
GeoJSON export and open geospatial interoperability.

Converts calculated RouteResult paths and Graph network features into standard
RFC 7946 GeoJSON FeatureCollections for visualization and analysis in open-source
GIS ecosystems (e.g. QGIS, Leaflet, OpenLayers, geojson.io).

Standards Compliance
--------------------
- RFC 7946 (The GeoJSON Format Specification)
- Coordinate order: [longitude, latitude] as mandated by RFC 7946
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from emergency_intelligence.graph.dijkstra import RouteResult
from emergency_intelligence.graph.models import Graph


def route_to_geojson(
    route: RouteResult,
    graph: Graph,
    algorithm_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert a :class:`RouteResult` into an RFC 7946 GeoJSON FeatureCollection.

    Includes:
      - A ``LineString`` Feature representing the full trajectory.
      - A ``Point`` Feature for the origin node.
      - A ``Point`` Feature for the destination node.
      - Intermediate intersection point Features with labels and metadata.

    Parameters
    ----------
    route:
        The routing query result to serialize.
    graph:
        The :class:`Graph` containing node coordinates and labels.
    algorithm_name:
        Optional algorithm identifier (e.g. "A*", "Dijkstra") added to properties.

    Returns
    -------
    dict
        RFC 7946 compliant GeoJSON dictionary.

    Raises
    ------
    ValueError
        If any node on the route path lacks defined spatial coordinates.
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

        lon, lat = node.coordinates
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

    return {
        "type": "FeatureCollection",
        "features": [linestring_feature] + waypoint_features,
    }


def save_route_geojson(
    route: RouteResult,
    graph: Graph,
    file_path: Union[str, Path],
    algorithm_name: Optional[str] = None,
    indent: int = 2,
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

    Returns
    -------
    Path
        Path to the saved GeoJSON file.
    """
    geojson_dict = route_to_geojson(route, graph, algorithm_name=algorithm_name)
    target = Path(file_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with open(target, "w", encoding="utf-8") as f:
        json.dump(geojson_dict, f, indent=indent)

    return target
