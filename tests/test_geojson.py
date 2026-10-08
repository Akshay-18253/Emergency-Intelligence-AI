"""
Unit tests for RFC 7946 GeoJSON export functionality.
"""

import json
from pathlib import Path
import pytest

from emergency_intelligence.data.geojson import route_to_geojson, save_route_geojson
from emergency_intelligence.graph.dijkstra import RouteResult
from emergency_intelligence.graph.models import Edge, Graph, Node


def build_geo_graph() -> Graph:
    g = Graph()
    g.add_node(Node("A", label="Origin Point", coordinates=(-122.419, 37.774)))
    g.add_node(Node("B", label="Waypoint Intersection", coordinates=(-122.418, 37.775)))
    g.add_node(Node("C", label="Destination Hospital", coordinates=(-122.417, 37.776)))
    g.add_edge(Edge("A", "B", cost=150.0))
    g.add_edge(Edge("B", "C", cost=200.0))
    return g


class TestGeoJSONExport:
    def test_route_to_geojson_structure(self):
        graph = build_geo_graph()
        route = RouteResult(
            source="A",
            destination="C",
            path=["A", "B", "C"],
            total_cost=350.0,
            reachable=True,
            nodes_explored=3,
            execution_time_ms=0.045,
        )

        geojson_dict = route_to_geojson(route, graph, algorithm_name="A* Search")

        assert geojson_dict["type"] == "FeatureCollection"
        features = geojson_dict["features"]
        # 1 LineString + 3 Points (A, B, C)
        assert len(features) == 4

        # Verify LineString
        line = features[0]
        assert line["type"] == "Feature"
        assert line["geometry"]["type"] == "LineString"
        assert line["geometry"]["coordinates"] == [
            [-122.419, 37.774],
            [-122.418, 37.775],
            [-122.417, 37.776],
        ]
        assert line["properties"]["source"] == "A"
        assert line["properties"]["destination"] == "C"
        assert line["properties"]["total_cost"] == 350.0
        assert line["properties"]["algorithm"] == "A* Search"
        assert line["properties"]["hops"] == 2

        # Verify origin point
        p_origin = features[1]
        assert p_origin["geometry"]["type"] == "Point"
        assert p_origin["properties"]["role"] == "origin"
        assert p_origin["properties"]["node_id"] == "A"

        # Verify destination point
        p_dest = features[3]
        assert p_dest["geometry"]["type"] == "Point"
        assert p_dest["properties"]["role"] == "destination"
        assert p_dest["properties"]["node_id"] == "C"

    def test_unreachable_route_geojson(self):
        graph = build_geo_graph()
        route = RouteResult(
            source="A",
            destination="C",
            path=[],
            total_cost=float("inf"),
            reachable=False,
        )

        geojson_dict = route_to_geojson(route, graph)
        assert geojson_dict["type"] == "FeatureCollection"
        assert geojson_dict["features"] == []
        assert geojson_dict["properties"]["reachable"] is False

    def test_missing_coordinates_raises_value_error(self):
        graph = Graph()
        graph.add_node(Node("A"))  # Coordinates are None
        graph.add_node(Node("B", coordinates=(-122.418, 37.775)))
        graph.add_edge(Edge("A", "B", cost=10.0))

        route = RouteResult(
            source="A",
            destination="B",
            path=["A", "B"],
            total_cost=10.0,
            reachable=True,
        )

        with pytest.raises(ValueError, match="does not have coordinates"):
            route_to_geojson(route, graph)

    def test_save_route_geojson_to_disk(self, tmp_path: Path):
        graph = build_geo_graph()
        route = RouteResult(
            source="A",
            destination="B",
            path=["A", "B"],
            total_cost=150.0,
            reachable=True,
        )

        target_file = tmp_path / "test_output_route.geojson"
        saved_path = save_route_geojson(route, graph, target_file)

        assert saved_path.is_file()

        with open(saved_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 3
