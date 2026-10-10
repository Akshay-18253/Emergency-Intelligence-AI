"""
Unit tests for HazardPolygon, vector ray-casting, segment intersection, and dynamic cost calculation.
"""

import math
from datetime import datetime, timezone
import pytest

from emergency_intelligence.events.hazards import (
    DEFAULT_SEVERITY_SPEED_MULTIPLIERS,
    HazardPolygon,
    HazardSeverity,
    HazardType,
    _on_segment,
    _orientation,
    compute_effective_edge_cost,
    find_edges_intersecting_hazard,
    find_hazards_affecting_edge,
    point_in_polygon,
    segment_intersects_polygon,
    segments_intersect,
)
from emergency_intelligence.graph.models import Edge, Graph, Node


# ---------------------------------------------------------------------------
# Vector Geometry Tests
# ---------------------------------------------------------------------------


class TestVectorGeometry:
    def test_orientation(self):
        # Collinear
        assert _orientation((0, 0), (1, 1), (2, 2)) == 0
        # Clockwise
        assert _orientation((0, 0), (0, 1), (1, 0)) == 1
        # Counter-Clockwise
        assert _orientation((0, 0), (1, 0), (0, 1)) == 2

    def test_on_segment(self):
        p = (0.0, 0.0)
        r = (4.0, 4.0)
        assert _on_segment(p, (2.0, 2.0), r) is True
        assert _on_segment(p, (0.0, 0.0), r) is True
        assert _on_segment(p, (4.0, 4.0), r) is True
        assert _on_segment(p, (5.0, 5.0), r) is False
        assert _on_segment(p, (-1.0, -1.0), r) is False

    def test_segments_intersect_crossing(self):
        # X-crossing
        p1, p2 = (0.0, 0.0), (2.0, 2.0)
        p3, p4 = (0.0, 2.0), (2.0, 0.0)
        assert segments_intersect(p1, p2, p3, p4) is True

    def test_segments_intersect_parallel_and_disjoint(self):
        p1, p2 = (0.0, 0.0), (2.0, 0.0)
        p3, p4 = (0.0, 1.0), (2.0, 1.0)
        assert segments_intersect(p1, p2, p3, p4) is False

    def test_segments_intersect_collinear_overlapping(self):
        p1, p2 = (0.0, 0.0), (3.0, 0.0)
        p3, p4 = (2.0, 0.0), (5.0, 0.0)
        assert segments_intersect(p1, p2, p3, p4) is True

    def test_segments_intersect_collinear_disjoint(self):
        p1, p2 = (0.0, 0.0), (1.0, 0.0)
        p3, p4 = (2.0, 0.0), (3.0, 0.0)
        assert segments_intersect(p1, p2, p3, p4) is False

    def test_segments_intersect_t_junction(self):
        p1, p2 = (0.0, 0.0), (4.0, 0.0)
        p3, p4 = (2.0, 0.0), (2.0, 2.0)
        assert segments_intersect(p1, p2, p3, p4) is True


class TestPointInPolygon:
    @pytest.fixture
    def unit_square(self):
        # (0,0) -> (2,0) -> (2,2) -> (0,2)
        return [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]

    @pytest.fixture
    def l_shaped_concave(self):
        # L-shape polygon with an indented notch
        return [
            (0.0, 0.0),
            (3.0, 0.0),
            (3.0, 1.0),
            (1.0, 1.0),
            (1.0, 3.0),
            (0.0, 3.0),
        ]

    def test_unit_square_inside(self, unit_square):
        assert point_in_polygon((1.0, 1.0), unit_square) is True

    def test_unit_square_outside(self, unit_square):
        assert point_in_polygon((3.0, 1.0), unit_square) is False
        assert point_in_polygon((-0.5, 1.0), unit_square) is False

    def test_unit_square_on_boundary_and_vertex(self, unit_square):
        # Exactly on vertex
        assert point_in_polygon((0.0, 0.0), unit_square) is True
        assert point_in_polygon((2.0, 2.0), unit_square) is True
        # Exactly on edge
        assert point_in_polygon((1.0, 0.0), unit_square) is True
        assert point_in_polygon((0.0, 1.0), unit_square) is True

    def test_concave_polygon(self, l_shaped_concave):
        # Inside main body
        assert point_in_polygon((0.5, 0.5), l_shaped_concave) is True
        assert point_in_polygon((0.5, 2.0), l_shaped_concave) is True
        assert point_in_polygon((2.0, 0.5), l_shaped_concave) is True
        # In the cut-out notch (should be False)
        assert point_in_polygon((2.0, 2.0), l_shaped_concave) is False

    def test_invalid_polygon_length(self):
        assert point_in_polygon((1.0, 1.0), [(0.0, 0.0), (1.0, 1.0)]) is False


class TestSegmentIntersectsPolygon:
    @pytest.fixture
    def square(self):
        return [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)]

    def test_segment_crossing_through(self, square):
        assert segment_intersects_polygon((-1.0, 2.0), (5.0, 2.0), square) is True

    def test_segment_fully_inside(self, square):
        assert segment_intersects_polygon((1.0, 1.0), (3.0, 3.0), square) is True

    def test_segment_one_endpoint_inside(self, square):
        assert segment_intersects_polygon((2.0, 2.0), (6.0, 2.0), square) is True

    def test_segment_completely_outside(self, square):
        assert segment_intersects_polygon((5.0, 0.0), (5.0, 4.0), square) is False
        assert segment_intersects_polygon((-2.0, -2.0), (-1.0, -1.0), square) is False

    def test_invalid_polygon_length(self):
        assert segment_intersects_polygon((0.0, 0.0), (1.0, 1.0), [(0.0, 0.0), (1.0, 1.0)]) is False


# ---------------------------------------------------------------------------
# HazardPolygon Model & Methods
# ---------------------------------------------------------------------------


class TestHazardPolygonModel:
    def test_hazard_creation_and_defaults(self):
        hazard = HazardPolygon(
            hazard_id="HAZ-001",
            hazard_type=HazardType.FLOOD_INUNDATION,
            severity=HazardSeverity.SEVERE,
            boundary_coordinates=[
                (-122.420, 37.770),
                (-122.410, 37.770),
                (-122.410, 37.780),
                (-122.420, 37.780),
            ],
            description="Mission Creek tidal storm surge flooding",
        )
        assert hazard.hazard_id == "HAZ-001"
        assert hazard.hazard_type == HazardType.FLOOD_INUNDATION
        assert hazard.severity == HazardSeverity.SEVERE
        # Default severe speed multiplier is 0.20
        assert hazard.speed_multiplier == 0.20
        assert hazard.is_blocking() is False
        assert hazard.active is True

    def test_hazard_string_enums_and_closed_ring(self):
        hazard = HazardPolygon(
            hazard_id="HAZ-002",
            hazard_type="wildfire_perimeter",
            severity="critical_blocked",
            boundary_coordinates=[
                (-122.40, 37.70),
                (-122.30, 37.70),
                (-122.30, 37.80),
                (-122.40, 37.70),  # closed duplicate
            ],
        )
        assert hazard.hazard_type == HazardType.WILDFIRE_PERIMETER
        assert hazard.severity == HazardSeverity.CRITICAL_BLOCKED
        assert hazard.speed_multiplier == 0.0
        assert hazard.is_blocking() is True
        assert len(hazard.boundary_coordinates) == 3  # Closed duplicate removed internally

    def test_custom_speed_multiplier(self):
        hazard = HazardPolygon(
            hazard_id="HAZ-003",
            hazard_type=HazardType.TOXIC_GAS_PLUME,
            severity=HazardSeverity.MODERATE,
            boundary_coordinates=[(0, 0), (2, 0), (2, 2), (0, 2)],
            speed_multiplier=0.45,
        )
        assert hazard.speed_multiplier == 0.45

    def test_bounding_box(self):
        hazard = HazardPolygon(
            hazard_id="HAZ-004",
            hazard_type=HazardType.ROAD_COLLAPSE,
            severity=HazardSeverity.CRITICAL_BLOCKED,
            boundary_coordinates=[(10.0, 20.0), (15.0, 20.0), (15.0, 25.0), (10.0, 25.0)],
        )
        assert hazard.bounding_box() == (10.0, 20.0, 15.0, 25.0)

    def test_contains_point_and_intersects_segment(self):
        hazard = HazardPolygon(
            hazard_id="HAZ-005",
            hazard_type=HazardType.FLASH_FLOOD,
            severity=HazardSeverity.MODERATE,
            boundary_coordinates=[(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0)],
        )
        assert hazard.contains_point(2.0, 2.0) is True
        assert hazard.contains_point(5.0, 5.0) is False
        assert hazard.intersects_segment((-1.0, 2.0), (5.0, 2.0)) is True
        assert hazard.intersects_segment((10.0, 10.0), (12.0, 12.0)) is False

        # Inactive hazard should return False
        hazard.active = False
        assert hazard.contains_point(2.0, 2.0) is False
        assert hazard.intersects_segment((-1.0, 2.0), (5.0, 2.0)) is False

    def test_validation_errors(self):
        with pytest.raises(ValueError, match="non-empty string"):
            HazardPolygon("", HazardType.FLASH_FLOOD, HazardSeverity.LOW, [(0, 0), (1, 1), (2, 2)])

        with pytest.raises(TypeError, match="HazardType enum"):
            HazardPolygon("1", 999, HazardSeverity.LOW, [(0, 0), (1, 1), (2, 2)])  # type: ignore

        with pytest.raises(TypeError, match="HazardSeverity enum"):
            HazardPolygon("1", HazardType.FLASH_FLOOD, 999, [(0, 0), (1, 1), (2, 2)])  # type: ignore

        with pytest.raises(ValueError, match="at least 3 vertices"):
            HazardPolygon("1", HazardType.FLASH_FLOOD, HazardSeverity.LOW, [(0, 0), (1, 1)])

        with pytest.raises(ValueError, match="Invalid coordinate vertex"):
            HazardPolygon("1", HazardType.FLASH_FLOOD, HazardSeverity.LOW, [(0, 0), (1, 1), (2,)])  # type: ignore

        with pytest.raises(ValueError, match="WGS 84 coordinate bounds"):
            HazardPolygon("1", HazardType.FLASH_FLOOD, HazardSeverity.LOW, [(0, 0), (250, 0), (0, 1)])

        with pytest.raises(ValueError, match="between 0.0 and 1.0"):
            HazardPolygon(
                "1",
                HazardType.FLASH_FLOOD,
                HazardSeverity.LOW,
                [(0, 0), (1, 0), (0, 1)],
                speed_multiplier=1.5,
            )

    def test_serialization_and_geojson_export(self):
        fixed_dt = datetime(2026, 10, 10, 14, 0, 0, tzinfo=timezone.utc)
        hazard = HazardPolygon(
            hazard_id="HAZ-777",
            hazard_type=HazardType.WILDFIRE_PERIMETER,
            severity=HazardSeverity.CRITICAL_BLOCKED,
            boundary_coordinates=[(1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)],
            description="Wildfire flank rapidly expanding east",
            created_at=fixed_dt,
            metadata={"wind_speed_mph": 25, "evacuation_zone": "Sector 4"},
        )

        d = hazard.to_dict()
        assert d["hazard_id"] == "HAZ-777"
        assert d["hazard_type"] == "wildfire_perimeter"
        assert d["severity"] == "critical_blocked"
        assert d["speed_multiplier"] == 0.0
        assert d["boundary_coordinates"][-1] == d["boundary_coordinates"][0]  # closed ring

        reconstructed = HazardPolygon.from_dict(d)
        assert reconstructed.hazard_id == hazard.hazard_id
        assert reconstructed.hazard_type == hazard.hazard_type
        assert reconstructed.severity == hazard.severity
        assert reconstructed.boundary_coordinates == hazard.boundary_coordinates

        feat = hazard.to_geojson_feature()
        assert feat["type"] == "Feature"
        assert feat["id"] == "HAZ-777"
        assert feat["geometry"]["type"] == "Polygon"
        assert feat["properties"]["hazard_type"] == "wildfire_perimeter"
        assert feat["properties"]["evacuation_zone"] == "Sector 4"


# ---------------------------------------------------------------------------
# Graph & Road Network Interaction Tests
# ---------------------------------------------------------------------------


class TestHazardGraphInteractions:
    @pytest.fixture
    def city_graph(self):
        g = Graph()
        # Node N1 (outside west), N2 (inside), N3 (outside east), N4 (outside south)
        g.add_node(Node("N1", coordinates=(0.0, 2.0)))
        g.add_node(Node("N2", coordinates=(2.0, 2.0)))
        g.add_node(Node("N3", coordinates=(4.0, 2.0)))
        g.add_node(Node("N4", coordinates=(2.0, -2.0)))

        # E1: N1 -> N2 (crosses into hazard)
        # E2: N2 -> N3 (crosses out of hazard)
        # E3: N1 -> N4 (completely outside hazard)
        g.add_edge(Edge("N1", "N2", cost=10.0))
        g.add_edge(Edge("N2", "N3", cost=10.0))
        g.add_edge(Edge("N1", "N4", cost=25.0))
        return g

    @pytest.fixture
    def hazard_zone(self):
        # Centered square: [1, 3] x [1, 3]
        return HazardPolygon(
            hazard_id="HAZ-CENTER",
            hazard_type=HazardType.FLASH_FLOOD,
            severity=HazardSeverity.MODERATE,  # 0.50 speed multiplier
            boundary_coordinates=[(1.0, 1.0), (3.0, 1.0), (3.0, 3.0), (1.0, 3.0)],
        )

    def test_find_edges_intersecting_hazard(self, city_graph, hazard_zone):
        intersecting = find_edges_intersecting_hazard(city_graph, hazard_zone)
        # E1 (N1 -> N2) and E2 (N2 -> N3) intersect
        edge_pairs = {(e.source_id, e.destination_id) for e in intersecting}
        assert ("N1", "N2") in edge_pairs
        assert ("N2", "N3") in edge_pairs
        assert ("N1", "N4") not in edge_pairs

    def test_find_edges_with_polyline_geometry(self, hazard_zone):
        g = Graph()
        # Direct line N1 -> N3 would pass above hazard (lat=4.0),
        # but intermediate polyline bends down into the hazard (lat=2.0)!
        g.add_node(Node("N1", coordinates=(0.0, 4.0)))
        g.add_node(Node("N3", coordinates=(4.0, 4.0)))

        edge = Edge("N1", "N3", cost=20.0)
        # Bent polyline geometry dipping down into hazard
        edge.attributes["geometry"] = [[0.0, 4.0], [2.0, 2.0], [4.0, 4.0]]
        g.add_edge(edge)

        intersecting = find_edges_intersecting_hazard(g, hazard_zone)
        assert len(intersecting) == 1
        assert intersecting[0].source_id == "N1"
        assert intersecting[0].destination_id == "N3"

    def test_compute_effective_edge_cost(self, hazard_zone):
        base_cost = 10.0
        # Moderate hazard (0.50 multiplier) -> cost doubles
        penalized = compute_effective_edge_cost(base_cost, [hazard_zone])
        assert penalized == 20.0

        # Severed hazard (CRITICAL_BLOCKED) -> infinite cost
        blocked_hazard = HazardPolygon(
            hazard_id="HAZ-BLOCKED",
            hazard_type=HazardType.ROAD_COLLAPSE,
            severity=HazardSeverity.CRITICAL_BLOCKED,
            boundary_coordinates=[(0, 0), (1, 0), (1, 1), (0, 1)],
        )
        assert compute_effective_edge_cost(base_cost, [blocked_hazard]) == math.inf

        # Multiple compounding hazards -> uses most restrictive multiplier
        light_hazard = HazardPolygon(
            hazard_id="HAZ-LIGHT",
            hazard_type=HazardType.STRUCTURAL_DEBRIS,
            severity=HazardSeverity.LOW,  # 0.75
            boundary_coordinates=[(0, 0), (1, 0), (1, 1), (0, 1)],
        )
        # Between 0.50 (moderate) and 0.75 (low), 0.50 is most restrictive -> cost 20.0
        assert compute_effective_edge_cost(base_cost, [hazard_zone, light_hazard]) == 20.0

        # No hazards -> base cost
        assert compute_effective_edge_cost(base_cost, []) == base_cost

        # Inactive hazard in list should be skipped
        inactive_h = HazardPolygon(
            hazard_id="HAZ-INACTIVE",
            hazard_type=HazardType.ROAD_COLLAPSE,
            severity=HazardSeverity.CRITICAL_BLOCKED,
            boundary_coordinates=[(0, 0), (1, 0), (1, 1), (0, 1)],
            active=False,
        )
        assert compute_effective_edge_cost(base_cost, [inactive_h]) == base_cost

    def test_find_hazards_affecting_edge(self, city_graph, hazard_zone):
        edge1 = city_graph.get_neighbors("N1")[0]  # N1 -> N2 crosses hazard
        edge3 = city_graph.get_neighbors("N1")[1]  # N1 -> N4 outside hazard

        affecting1 = find_hazards_affecting_edge([hazard_zone], edge1, city_graph)
        assert len(affecting1) == 1
        assert affecting1[0].hazard_id == "HAZ-CENTER"

        affecting3 = find_hazards_affecting_edge([hazard_zone], edge3, city_graph)
        assert len(affecting3) == 0

        # Inactive hazard should not affect edge
        hazard_zone.active = False
        assert len(find_hazards_affecting_edge([hazard_zone], edge1, city_graph)) == 0

    def test_find_hazards_affecting_edge_polyline(self, hazard_zone):
        g = Graph()
        g.add_node(Node("A", coordinates=(0.0, 4.0)))
        g.add_node(Node("B", coordinates=(4.0, 4.0)))
        edge = Edge("A", "B", cost=15.0)
        edge.attributes["geometry"] = [[0.0, 4.0], [2.0, 2.0], [4.0, 4.0]]
        g.add_edge(edge)

        hazard_zone.active = True
        affecting = find_hazards_affecting_edge([hazard_zone], edge, g)
        assert len(affecting) == 1
        assert affecting[0].hazard_id == "HAZ-CENTER"

    def test_find_edges_intersecting_hazard_inactive_and_missing_coords(self, city_graph, hazard_zone):
        hazard_zone.active = False
        assert find_edges_intersecting_hazard(city_graph, hazard_zone) == []

        # Graph with missing coords node
        g = Graph()
        g.add_node(Node("NO_COORD"))
        g.add_node(Node("WITH_COORD", coordinates=(1.0, 1.0)))
        g.add_edge(Edge("NO_COORD", "WITH_COORD", cost=1.0))
        g.add_edge(Edge("WITH_COORD", "NO_COORD", cost=1.0))

        hazard_zone.active = True
        assert find_edges_intersecting_hazard(g, hazard_zone) == []

    def test_hazard_expires_at_serialization(self):
        fixed_dt = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
        exp_dt = datetime(2026, 10, 10, 18, 0, 0, tzinfo=timezone.utc)
        h = HazardPolygon(
            hazard_id="EXP-1",
            hazard_type=HazardType.FLASH_FLOOD,
            severity=HazardSeverity.MODERATE,
            boundary_coordinates=[(0, 0), (2, 0), (2, 2), (0, 2)],
            created_at=fixed_dt,
            expires_at=exp_dt,
        )
        d = h.to_dict()
        assert d["expires_at"] == exp_dt.isoformat()

        reconstructed = HazardPolygon.from_dict(d)
        assert reconstructed.expires_at == exp_dt
