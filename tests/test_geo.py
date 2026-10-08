"""
Unit tests for geographic calculations and Haversine distance.
"""

import math
import pytest

from emergency_intelligence.data.geo import (
    EARTH_RADIUS_METERS,
    haversine_distance,
    haversine_heuristic,
)
from emergency_intelligence.graph.models import Node


class TestHaversineDistance:
    def test_same_coordinate_is_zero(self):
        coord = (-122.4194, 37.7749)
        assert haversine_distance(coord, coord, unit="m") == pytest.approx(0.0)
        assert haversine_distance(coord, coord, unit="km") == pytest.approx(0.0)

    def test_known_distance_london_to_paris(self):
        # London: (-0.1278, 51.5074), Paris: (2.3522, 48.8566)
        london = (-0.1278, 51.5074)
        paris = (2.3522, 48.8566)
        dist_km = haversine_distance(london, paris, unit="km")
        dist_m = haversine_distance(london, paris, unit="m")

        # Standard great-circle distance is ~343.5 km
        assert dist_km == pytest.approx(343.55, rel=1e-2)
        assert dist_m == pytest.approx(dist_km * 1000.0)

    def test_distance_symmetry(self):
        ny = (-74.0060, 40.7128)
        sf = (-122.4194, 37.7749)
        d_fwd = haversine_distance(ny, sf, unit="km")
        d_rev = haversine_distance(sf, ny, unit="km")
        assert d_fwd == pytest.approx(d_rev)

    def test_invalid_unit_raises(self):
        p1 = (0.0, 0.0)
        p2 = (1.0, 1.0)
        with pytest.raises(ValueError, match="Unsupported unit"):
            haversine_distance(p1, p2, unit="miles")


class TestHaversineHeuristic:
    def test_haversine_heuristic_value(self):
        n1 = Node("H", coordinates=(-122.4194, 37.7749))
        n2 = Node("INC", coordinates=(-122.4175, 37.7776))

        h_val = haversine_heuristic(n1, n2)
        expected = haversine_distance(n1.coordinates, n2.coordinates, unit="m")
        assert h_val == pytest.approx(expected)
        assert h_val > 0.0

    def test_haversine_heuristic_missing_coords_raises(self):
        n1 = Node("A")
        n2 = Node("B", coordinates=(0.0, 0.0))
        with pytest.raises(ValueError, match="no coordinates defined"):
            haversine_heuristic(n1, n2)
        with pytest.raises(ValueError, match="no coordinates defined"):
            haversine_heuristic(n2, n1)

    def test_haversine_triangle_inequality(self):
        # Haversine distance obeys triangle inequality: d(A, C) <= d(A, B) + d(B, C)
        a = (-122.4194, 37.7749)
        b = (-122.4180, 37.7760)
        c = (-122.4150, 37.7780)

        d_ac = haversine_distance(a, c)
        d_ab = haversine_distance(a, b)
        d_bc = haversine_distance(b, c)

        assert d_ac <= (d_ab + d_bc) + 1e-9
