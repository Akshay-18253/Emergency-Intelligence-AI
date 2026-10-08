"""
Unit tests for the A* shortest-path algorithm.

Validates correctness, edge cases, heuristic behaviors, and algorithmic
equivalence with Dijkstra when uninformed.

Test coverage:
 1. Simple route (single edge)
 2. Multiple possible routes (optimal selection)
 3. Detour preference over expensive direct edge
 4. Path reconstruction (continuity, start, end)
 5. Source equals destination
 6. Unreachable destination (disconnected, directed reverse)
 7. Invalid source / destination handling (KeyError)
 8. Admissible heuristic behavior with 2D coordinates
 9. Zero heuristic equivalence to Dijkstra (cost & path match)
10. Default heuristic fallback behavior
11. Negative heuristic validation (ValueError)
12. Floating-point edge weights & zero-cost edges
13. Search efficiency: A* explores fewer nodes than Dijkstra on spatial graphs
"""

from __future__ import annotations

import math
from typing import List, Tuple

import pytest

from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.benchmark import create_grid_network
from emergency_intelligence.graph.dijkstra import dijkstra
from emergency_intelligence.graph.heuristics import (
    euclidean_distance,
    manhattan_distance,
    zero_heuristic,
)
from emergency_intelligence.graph.models import Edge, Graph, Node


def build_graph(
    nodes: List[Tuple[str, float, float]],
    edges: List[Tuple[str, str, float]],
) -> Graph:
    """Helper to build a graph with coordinates."""
    g = Graph()
    for nid, x, y in nodes:
        g.add_node(Node(nid, coordinates=(x, y)))
    for src, dst, cost in edges:
        g.add_edge(Edge(src, dst, cost=cost))
    return g


# ---------------------------------------------------------------------------
# Test 1 — Simple route
# ---------------------------------------------------------------------------


class TestAStarSimpleRoute:
    def test_simple_route_is_reachable(self):
        g = build_graph([("A", 0, 0), ("B", 3, 0)], [("A", "B", 3.0)])
        result = astar(g, "A", "B")
        assert result.reachable is True

    def test_simple_route_path(self):
        g = build_graph([("A", 0, 0), ("B", 3, 0)], [("A", "B", 3.0)])
        result = astar(g, "A", "B")
        assert result.path == ["A", "B"]

    def test_simple_route_cost(self):
        g = build_graph([("A", 0, 0), ("B", 3, 0)], [("A", "B", 3.0)])
        result = astar(g, "A", "B")
        assert result.total_cost == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Test 2 — Multiple possible routes (optimal selection)
# ---------------------------------------------------------------------------


class TestAStarMultipleRoutes:
    def _graph(self) -> Graph:
        # A(0,0) -> B(1,0) [cost 1] -> D(2,0) [cost 10] (total 11)
        # A(0,0) -> C(0,1) [cost 2] -> D(2,0) [cost 3]  (total 5, optimal)
        return build_graph(
            [("A", 0, 0), ("B", 1, 0), ("C", 0, 1), ("D", 2, 0)],
            [("A", "B", 1), ("B", "D", 10), ("A", "C", 2), ("C", "D", 3)],
        )

    def test_optimal_path_chosen(self):
        g = self._graph()
        result = astar(g, "A", "D")
        assert result.reachable is True
        assert result.path == ["A", "C", "D"]
        assert result.total_cost == pytest.approx(5.0)

    def test_direct_edge_not_always_optimal(self):
        # A->D direct costs 100, A->B->D costs 1+1=2
        g = build_graph(
            [("A", 0, 0), ("B", 1, 0), ("D", 2, 0)],
            [("A", "D", 100), ("A", "B", 1), ("B", "D", 1)],
        )
        result = astar(g, "A", "D")
        assert result.path == ["A", "B", "D"]
        assert result.total_cost == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Test 3 — Path reconstruction
# ---------------------------------------------------------------------------


class TestAStarPathReconstruction:
    def test_chain_path(self):
        g = build_graph(
            [("A", 0, 0), ("B", 1, 0), ("C", 2, 0), ("D", 3, 0)],
            [("A", "B", 1), ("B", "C", 1), ("C", "D", 1)],
        )
        result = astar(g, "A", "D")
        assert result.path == ["A", "B", "C", "D"]
        assert result.total_cost == pytest.approx(3.0)
        assert result.path[0] == "A"
        assert result.path[-1] == "D"


# ---------------------------------------------------------------------------
# Test 4 — Source equals destination
# ---------------------------------------------------------------------------


class TestAStarSourceEqualsDestination:
    def test_same_node_route(self):
        g = build_graph([("A", 0, 0)], [])
        result = astar(g, "A", "A")
        assert result.reachable is True
        assert result.path == ["A"]
        assert result.total_cost == 0.0
        assert result.nodes_explored == 1


# ---------------------------------------------------------------------------
# Test 5 — Unreachable destination
# ---------------------------------------------------------------------------


class TestAStarUnreachableDestination:
    def test_unreachable_flag_and_cost(self):
        g = build_graph([("A", 0, 0), ("B", 1, 0)], [])
        result = astar(g, "A", "B")
        assert result.reachable is False
        assert result.path == []
        assert math.isinf(result.total_cost)

    def test_one_way_edge_unreachable_reverse(self):
        g = build_graph([("A", 0, 0), ("B", 1, 0)], [("A", "B", 5.0)])
        result = astar(g, "B", "A")
        assert result.reachable is False
        assert result.path == []
        assert math.isinf(result.total_cost)


# ---------------------------------------------------------------------------
# Test 6 — Invalid source / destination
# ---------------------------------------------------------------------------


class TestAStarInvalidNodes:
    def test_missing_source_raises_key_error(self):
        g = build_graph([("A", 0, 0)], [])
        with pytest.raises(KeyError, match="Source node"):
            astar(g, "NONEXISTENT", "A")

    def test_missing_destination_raises_key_error(self):
        g = build_graph([("A", 0, 0)], [])
        with pytest.raises(KeyError, match="Destination node"):
            astar(g, "A", "NONEXISTENT")


# ---------------------------------------------------------------------------
# Test 7 — Algorithmic equivalence: A* with zero_heuristic == Dijkstra
# ---------------------------------------------------------------------------


class TestAStarZeroHeuristicEquivalence:
    def test_identical_to_dijkstra_on_complex_network(self):
        # A(0,0), B(2,0), C(1,2), D(3,2), E(4,0)
        g = build_graph(
            [
                ("A", 0, 0),
                ("B", 2, 0),
                ("C", 1, 2),
                ("D", 3, 2),
                ("E", 4, 0),
            ],
            [
                ("A", "B", 4.0),
                ("A", "C", 2.0),
                ("C", "B", 1.5),
                ("C", "D", 5.0),
                ("B", "E", 3.0),
                ("D", "E", 1.0),
            ],
        )

        d_res = dijkstra(g, "A", "E")
        a_res = astar(g, "A", "E", heuristic=zero_heuristic)

        assert d_res.reachable == a_res.reachable
        assert d_res.total_cost == pytest.approx(a_res.total_cost)
        assert d_res.path == a_res.path
        assert d_res.nodes_explored == a_res.nodes_explored


# ---------------------------------------------------------------------------
# Test 8 — Default heuristic resolution
# ---------------------------------------------------------------------------


class TestAStarDefaultHeuristic:
    def test_fallback_to_zero_heuristic_when_coords_missing(self):
        # Graph nodes without coordinates
        g = Graph()
        g.add_node(Node("A"))
        g.add_node(Node("B"))
        g.add_edge(Edge("A", "B", cost=10.0))

        # Should NOT raise ValueError; should gracefully default to zero_heuristic
        result = astar(g, "A", "B")
        assert result.reachable is True
        assert result.path == ["A", "B"]
        assert result.total_cost == pytest.approx(10.0)

    def test_uses_euclidean_when_coords_present(self):
        g = build_graph([("A", 0, 0), ("B", 3, 4)], [("A", "B", 5.0)])
        result = astar(g, "A", "B")  # default heuristic is euclidean
        assert result.reachable is True
        assert result.total_cost == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Test 9 — Invalid heuristic handling
# ---------------------------------------------------------------------------


class TestAStarInvalidHeuristic:
    def test_negative_heuristic_raises_value_error(self):
        g = build_graph([("A", 0, 0), ("B", 1, 0)], [("A", "B", 1.0)])

        def negative_h(curr, goal):
            return -5.0

        with pytest.raises(ValueError, match="negative value"):
            astar(g, "A", "B", heuristic=negative_h)


# ---------------------------------------------------------------------------
# Test 10 — Edge weights (floats, zero-cost)
# ---------------------------------------------------------------------------


class TestAStarEdgeWeights:
    def test_float_weights(self):
        g = build_graph(
            [("A", 0, 0), ("B", 1, 0), ("C", 2, 0)],
            [("A", "B", 1.25), ("B", "C", 2.75)],
        )
        result = astar(g, "A", "C")
        assert result.total_cost == pytest.approx(4.0)

    def test_zero_cost_edge(self):
        g = build_graph(
            [("A", 0, 0), ("B", 1, 0), ("C", 2, 0)],
            [("A", "B", 0.0), ("B", "C", 3.0)],
        )
        result = astar(g, "A", "C")
        assert result.total_cost == pytest.approx(3.0)
        assert result.path == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Test 11 — Search efficiency (A* explores <= nodes than Dijkstra)
# ---------------------------------------------------------------------------


class TestAStarSearchEfficiency:
    def test_astar_explores_fewer_nodes_on_grid(self):
        # 10x10 grid network
        grid = create_grid_network(rows=10, cols=10, bidirectional=True)
        src = "N_0_0"
        dst = "N_9_9"

        d_res = dijkstra(grid, src, dst)
        a_res = astar(grid, src, dst, heuristic=euclidean_distance)

        # Both find the exact same optimal cost: 9 steps down + 9 steps right = 18.0
        assert d_res.reachable is True
        assert a_res.reachable is True
        assert d_res.total_cost == pytest.approx(a_res.total_cost)
        assert d_res.total_cost == pytest.approx(18.0)

        # A* directed search must explore significantly fewer nodes than blind Dijkstra
        assert a_res.nodes_explored < d_res.nodes_explored
