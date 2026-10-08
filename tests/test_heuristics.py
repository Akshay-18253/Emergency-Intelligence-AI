"""
Unit tests for heuristic functions.

Tests Euclidean, Manhattan, and Zero heuristics for correctness, symmetry,
and validation of coordinate preconditions.
"""

import math
import pytest

from emergency_intelligence.graph.heuristics import (
    euclidean_distance,
    manhattan_distance,
    zero_heuristic,
)
from emergency_intelligence.graph.models import Node


class TestEuclideanHeuristic:
    def test_euclidean_distance_3_4_5_triangle(self):
        n1 = Node("A", coordinates=(0.0, 0.0))
        n2 = Node("B", coordinates=(3.0, 4.0))
        assert euclidean_distance(n1, n2) == pytest.approx(5.0)

    def test_euclidean_distance_same_location(self):
        n1 = Node("A", coordinates=(10.0, 20.0))
        n2 = Node("B", coordinates=(10.0, 20.0))
        assert euclidean_distance(n1, n2) == pytest.approx(0.0)

    def test_euclidean_distance_symmetry(self):
        n1 = Node("A", coordinates=(-2.5, 3.0))
        n2 = Node("B", coordinates=(4.0, -1.0))
        d_ab = euclidean_distance(n1, n2)
        d_ba = euclidean_distance(n2, n1)
        assert d_ab == pytest.approx(d_ba)

    def test_euclidean_missing_current_coords_raises(self):
        n1 = Node("A")
        n2 = Node("B", coordinates=(1.0, 1.0))
        with pytest.raises(ValueError, match="no coordinates defined"):
            euclidean_distance(n1, n2)

    def test_euclidean_missing_goal_coords_raises(self):
        n1 = Node("A", coordinates=(1.0, 1.0))
        n2 = Node("B")
        with pytest.raises(ValueError, match="no coordinates defined"):
            euclidean_distance(n1, n2)


class TestManhattanHeuristic:
    def test_manhattan_distance_known_value(self):
        n1 = Node("A", coordinates=(1.0, 2.0))
        n2 = Node("B", coordinates=(4.0, 6.0))
        # |4 - 1| + |6 - 2| = 3 + 4 = 7
        assert manhattan_distance(n1, n2) == pytest.approx(7.0)

    def test_manhattan_distance_same_location(self):
        n1 = Node("A", coordinates=(5.0, 5.0))
        n2 = Node("B", coordinates=(5.0, 5.0))
        assert manhattan_distance(n1, n2) == pytest.approx(0.0)

    def test_manhattan_distance_symmetry(self):
        n1 = Node("A", coordinates=(-3.0, 7.0))
        n2 = Node("B", coordinates=(2.0, -4.0))
        d_ab = manhattan_distance(n1, n2)
        d_ba = manhattan_distance(n2, n1)
        assert d_ab == pytest.approx(d_ba)

    def test_manhattan_missing_current_coords_raises(self):
        n1 = Node("A")
        n2 = Node("B", coordinates=(1.0, 1.0))
        with pytest.raises(ValueError, match="no coordinates defined"):
            manhattan_distance(n1, n2)

    def test_manhattan_missing_goal_coords_raises(self):
        n1 = Node("A", coordinates=(1.0, 1.0))
        n2 = Node("B")
        with pytest.raises(ValueError, match="no coordinates defined"):
            manhattan_distance(n1, n2)


class TestZeroHeuristic:
    def test_zero_heuristic_with_coordinates(self):
        n1 = Node("A", coordinates=(1.0, 2.0))
        n2 = Node("B", coordinates=(10.0, 20.0))
        assert zero_heuristic(n1, n2) == 0.0

    def test_zero_heuristic_without_coordinates(self):
        n1 = Node("A")
        n2 = Node("B")
        assert zero_heuristic(n1, n2) == 0.0
