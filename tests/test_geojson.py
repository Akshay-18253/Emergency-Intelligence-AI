"""
Comprehensive unit tests for RFC 7946 GeoJSON export, ingestion, and GIS interoperability.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import pytest

from emergency_intelligence.data.geojson import (
    compute_bounding_box,
    graph_to_geojson,
    load_graph_from_geojson,
    route_to_geojson,
    save_geojson,
    save_graph_geojson,
    save_route_geojson,
    validate_wgs84_coordinates,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.dijkstra import RouteResult, dijkstra
from emergency_intelligence.graph.models import Edge, Graph, Node


def build_sample_geo_graph() -> Graph:
    """Build a deterministic small geographic graph for testing."""
    g = Graph()
    g.add_node(Node("A", label="Station Alpha", coordinates=(-122.4194, 37.7749)))
    g.add_node(Node("B", label="Waypoint Beta", coordinates=(-122.4180, 37.7755)))
    g.add_node(Node("C", label="Hospital Gamma", coordinates=(-122.4165, 37.7768)))
    g.add_edge(Edge("A", "B", cost=150.0))
    g.add_edge(Edge("B", "C", cost=200.0))
    g.add_edge(Edge("A", "C", cost=400.0))
    return g


# ===========================================================================
# 1. Coordinate Validation Tests
# ===========================================================================
class TestWGS84CoordinateValidation:
    def test_valid_coordinates_pass(self):
        # Standard San Francisco coordinates
        validate_wgs84_coordinates(-122.4194, 37.7749)
        # Extremes
        validate_wgs84_coordinates(-180.0, -90.0)
        validate_wgs84_coordinates(180.0, 90.0)
        validate_wgs84_coordinates(0.0, 0.0)

    def test_out_of_bounds_longitude_raises(self):
        with pytest.raises(ValueError, match="Longitude -180.1 is out of valid"):
            validate_wgs84_coordinates(-180.1, 0.0)

        with pytest.raises(ValueError, match="Longitude 180.05 is out of valid"):
            validate_wgs84_coordinates(180.05, 0.0)

    def test_out_of_bounds_latitude_raises(self):
        with pytest.raises(ValueError, match="Latitude -90.1 is out of valid"):
            validate_wgs84_coordinates(0.0, -90.1)

        with pytest.raises(ValueError, match="Latitude 95.0 is out of valid"):
            validate_wgs84_coordinates(0.0, 95.0)

    def test_non_finite_coordinates_raise(self):
        with pytest.raises(ValueError, match="finite"):
            validate_wgs84_coordinates(float("nan"), 37.0)

        with pytest.raises(ValueError, match="finite"):
            validate_wgs84_coordinates(-122.0, float("inf"))

    def test_non_numeric_coordinates_raise(self):
        with pytest.raises(ValueError, match="numeric"):
            validate_wgs84_coordinates("not_a_number", 37.0)  # type: ignore


# ===========================================================================
# 2. Bounding Box Tests
# ===========================================================================
class TestBoundingBoxComputation:
    def test_empty_coordinates_returns_zeros(self):
        assert compute_bounding_box([]) == [0.0, 0.0, 0.0, 0.0]

    def test_single_coordinate(self):
        assert compute_bounding_box([[-122.0, 37.0]]) == [-122.0, 37.0, -122.0, 37.0]

    def test_multiple_coordinates(self):
        coords = [
            [-122.419, 37.774],
            [-122.410, 37.780],
            [-122.430, 37.760],
        ]
        bbox = compute_bounding_box(coords)
        assert bbox == [-122.430, 37.760, -122.410, 37.780]


# ===========================================================================
# 3. Route to GeoJSON Tests
# ===========================================================================
class TestRouteToGeoJSON:
    def test_reachable_route_structure(self):
        graph = build_sample_geo_graph()
        route = RouteResult(
            source="A",
            destination="C",
            path=["A", "B", "C"],
            total_cost=350.0,
            reachable=True,
            nodes_explored=3,
            execution_time_ms=0.045,
        )

        geojson = route_to_geojson(route, graph, algorithm_name="A* Search")

        assert geojson["type"] == "FeatureCollection"
        assert "bbox" in geojson
        assert len(geojson["bbox"]) == 4

        features = geojson["features"]
        # 1 LineString + 3 Points
        assert len(features) == 4

        line = features[0]
        assert line["geometry"]["type"] == "LineString"
        assert line["geometry"]["coordinates"] == [
            [-122.4194, 37.7749],
            [-122.4180, 37.7755],
            [-122.4165, 37.7768],
        ]
        assert line["properties"]["total_cost"] == 350.0
        assert line["properties"]["hops"] == 2
        assert line["properties"]["algorithm"] == "A* Search"

        origin = features[1]
        assert origin["properties"]["role"] == "origin"
        assert origin["properties"]["node_id"] == "A"

        waypoint = features[2]
        assert waypoint["properties"]["role"] == "waypoint"
        assert waypoint["properties"]["node_id"] == "B"

        dest = features[3]
        assert dest["properties"]["role"] == "destination"
        assert dest["properties"]["node_id"] == "C"

    def test_unreachable_route(self):
        graph = build_sample_geo_graph()
        route = RouteResult(
            source="C",
            destination="A",
            path=[],
            total_cost=float("inf"),
            reachable=False,
            nodes_explored=1,
        )

        geojson = route_to_geojson(route, graph)
        assert geojson["type"] == "FeatureCollection"
        assert geojson["features"] == []
        assert geojson["properties"]["reachable"] is False

    def test_omit_bbox(self):
        graph = build_sample_geo_graph()
        route = dijkstra(graph, "A", "C")
        geojson = route_to_geojson(route, graph, include_bbox=False)
        assert "bbox" not in geojson

    def test_missing_coordinates_raises_value_error(self):
        g = Graph()
        g.add_node(Node("A"))  # No coordinates
        g.add_node(Node("B", coordinates=(-122.0, 37.0)))
        g.add_edge(Edge("A", "B", cost=10.0))

        route = dijkstra(g, "A", "B")
        with pytest.raises(ValueError, match="does not have coordinates defined"):
            route_to_geojson(route, g)

    def test_invalid_node_coordinate_bounds_raises_value_error(self):
        g = Graph()
        g.add_node(Node("A", coordinates=(-200.0, 37.0)))  # Invalid lon
        g.add_node(Node("B", coordinates=(-122.0, 37.0)))
        g.add_edge(Edge("A", "B", cost=10.0))

        route = dijkstra(g, "A", "B")
        with pytest.raises(ValueError, match="Longitude -200.0 is out of valid"):
            route_to_geojson(route, g)


# ===========================================================================
# 4. Graph to GeoJSON Tests
# ===========================================================================
class TestGraphToGeoJSON:
    def test_graph_export_structure(self):
        graph = build_sample_geo_graph()
        geojson = graph_to_geojson(graph)

        assert geojson["type"] == "FeatureCollection"
        assert "bbox" in geojson
        assert geojson["properties"]["node_count"] == 3
        assert geojson["properties"]["edge_count"] == 3

        features = geojson["features"]
        point_features = [f for f in features if f["geometry"]["type"] == "Point"]
        line_features = [f for f in features if f["geometry"]["type"] == "LineString"]

        assert len(point_features) == 3
        assert len(line_features) == 3

        # Check node properties
        station_a = next(f for f in point_features if f["properties"]["node_id"] == "A")
        assert station_a["properties"]["label"] == "Station Alpha"
        assert station_a["properties"]["out_degree"] == 2  # A -> B, A -> C

    def test_nodes_without_coordinates_gracefully_skipped(self):
        g = Graph()
        g.add_node(Node("A", coordinates=(-122.0, 37.0)))
        g.add_node(Node("B"))  # No coordinates
        g.add_edge(Edge("A", "B", cost=10.0))

        geojson = graph_to_geojson(g)
        # Only node A can be exported as a Point, Edge A->B omitted because B has no coords
        assert len(geojson["features"]) == 1
        assert geojson["features"][0]["properties"]["node_id"] == "A"


# ===========================================================================
# 5. Load Graph from GeoJSON (Round-Trip Fidelity)
# ===========================================================================
class TestLoadGraphFromGeoJSON:
    def test_round_trip_export_and_import(self):
        original_graph = build_sample_geo_graph()
        geojson_dict = graph_to_geojson(original_graph)

        # Ingest back
        reconstructed = load_graph_from_geojson(geojson_dict)

        assert reconstructed.node_count() == original_graph.node_count()
        assert reconstructed.edge_count() == original_graph.edge_count()

        # Test routing on reconstructed graph
        orig_route = dijkstra(original_graph, "A", "C")
        recon_route = dijkstra(reconstructed, "A", "C")

        assert orig_route.reachable is True
        assert recon_route.reachable is True
        assert orig_route.path == recon_route.path
        assert math.isclose(orig_route.total_cost, recon_route.total_cost, rel_tol=1e-6)

    def test_load_from_file(self, tmp_path: Path):
        graph = build_sample_geo_graph()
        target_file = tmp_path / "network.geojson"
        save_graph_geojson(graph, target_file)

        loaded_graph = load_graph_from_geojson(target_file)
        assert loaded_graph.node_count() == 3
        assert loaded_graph.edge_count() == 3

    def test_load_polyline_linestrings(self):
        # GeoJSON where LineString has multiple points without explicit source/dest props
        raw_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [-122.4194, 37.7749],
                            [-122.4180, 37.7755],
                            [-122.4165, 37.7768],
                        ],
                    },
                    "properties": {},
                }
            ],
        }

        graph = load_graph_from_geojson(raw_geojson)
        assert graph.node_count() == 3
        assert graph.edge_count() == 2

    def test_load_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_graph_from_geojson(Path("nonexistent_path_12345.geojson"))

    def test_load_invalid_json_type_raises(self):
        with pytest.raises(ValueError, match="FeatureCollection"):
            load_graph_from_geojson({"type": "Point", "coordinates": [0, 0]})

        with pytest.raises(ValueError, match="features"):
            load_graph_from_geojson({"type": "FeatureCollection", "features": "not_a_list"})

    def test_load_from_raw_json_string(self):
        json_str = json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-122.4, 37.7]},
                        "properties": {"node_id": "P1", "label": "Point One"},
                    }
                ],
            }
        )
        graph = load_graph_from_geojson(json_str)
        assert graph.node_count() == 1
        assert graph.get_node("P1").label == "Point One"

    def test_load_invalid_argument_type_raises(self):
        with pytest.raises(ValueError, match="Expected file path, JSON string, or dict"):
            load_graph_from_geojson(12345)  # type: ignore

    def test_load_linestring_with_implicit_nodes_and_auto_haversine_cost(self):
        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[-122.419, 37.774], [-122.418, 37.775]],
                    },
                    "properties": {
                        "source": "SrcNode",
                        "destination": "DstNode",
                        # Notice: no 'cost' property provided!
                    },
                }
            ],
        }
        graph = load_graph_from_geojson(data)
        assert graph.node_count() == 2
        assert graph.edge_count() == 1
        edge = graph.get_neighbors("SrcNode")[0]
        assert edge.destination_id == "DstNode"
        assert edge.cost > 0.0  # Computed via Haversine distance

    def test_skip_empty_coordinates_geometries(self):
        data = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": []},
                    "properties": {},
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[-122.4, 37.7]]},
                    "properties": {},
                },
            ],
        }
        graph = load_graph_from_geojson(data)
        assert graph.node_count() == 0
        assert graph.edge_count() == 0


# ===========================================================================
# 6. Disk Serialization Functions
# ===========================================================================
class TestDiskSerialization:
    def test_save_geojson_and_route(self, tmp_path: Path):
        graph = build_sample_geo_graph()
        route = dijkstra(graph, "A", "C")

        route_file = tmp_path / "sub" / "route.geojson"
        saved = save_route_geojson(route, graph, route_file)
        assert saved.is_file()

        with open(saved, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 4

    def test_save_graph_geojson(self, tmp_path: Path):
        graph = build_sample_geo_graph()
        graph_file = tmp_path / "sub" / "graph.geojson"
        saved = save_graph_geojson(graph, graph_file)
        assert saved.is_file()

        with open(saved, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) == 6
