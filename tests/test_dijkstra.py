"""
Unit tests for Dijkstra's shortest-path algorithm.

Covers all required cases:
 1.  Simple route
 2.  Multiple possible routes
 3.  Lowest-cost route selection
 4.  Path reconstruction
 5.  Total cost verification
 6.  Source equals destination
 7.  Unreachable destination
 8.  Invalid source (not in graph)
 9.  Invalid destination (not in graph)
10.  Different edge weights
11.  Zero-cost edge

Run with:
    python -m pytest tests/ -v
"""

import math

import pytest

from emergency_intelligence.graph.dijkstra import RouteResult, dijkstra
from emergency_intelligence.graph.models import Edge, Graph, Node


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_graph(node_ids: list[str], edges: list[tuple]) -> Graph:
    """Construct a :class:`Graph` from lists of node ids and edge tuples.

    Edge tuples are ``(source_id, destination_id, cost)``.
    """
    g = Graph()
    for nid in node_ids:
        g.add_node(Node(nid))
    for src, dst, cost in edges:
        g.add_edge(Edge(src, dst, cost=cost))
    return g


# ---------------------------------------------------------------------------
# Test 1 — Simple route
# ---------------------------------------------------------------------------


class TestSimpleRoute:
    """A graph with a single direct edge between source and destination."""

    def test_simple_route_is_reachable(self):
        g = build_graph(["A", "B"], [("A", "B", 3.0)])
        result = dijkstra(g, "A", "B")
        assert result.reachable is True

    def test_simple_route_path(self):
        g = build_graph(["A", "B"], [("A", "B", 3.0)])
        result = dijkstra(g, "A", "B")
        assert result.path == ["A", "B"]

    def test_simple_route_cost(self):
        g = build_graph(["A", "B"], [("A", "B", 3.0)])
        result = dijkstra(g, "A", "B")
        assert result.total_cost == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Test 2 — Multiple possible routes (two paths exist)
# ---------------------------------------------------------------------------


class TestMultiplePossibleRoutes:
    """Graph with two paths from A to D; algorithm must find one."""

    def _graph(self) -> Graph:
        # A→B (cost 1), B→D (cost 10), A→C (cost 2), C→D (cost 3)
        return build_graph(
            ["A", "B", "C", "D"],
            [("A", "B", 1), ("B", "D", 10), ("A", "C", 2), ("C", "D", 3)],
        )

    def test_route_exists(self):
        result = dijkstra(self._graph(), "A", "D")
        assert result.reachable is True

    def test_path_is_valid(self):
        result = dijkstra(self._graph(), "A", "D")
        assert result.path[0] == "A"
        assert result.path[-1] == "D"


# ---------------------------------------------------------------------------
# Test 3 — Lowest-cost route selection
# ---------------------------------------------------------------------------


class TestLowestCostRoute:
    """Verify the algorithm selects the minimum-cost path, not the fewest hops."""

    def test_lowest_cost_path_chosen(self):
        # Path A→B→D: cost 1+10 = 11
        # Path A→C→D: cost 2+3  =  5   ← optimal
        g = build_graph(
            ["A", "B", "C", "D"],
            [("A", "B", 1), ("B", "D", 10), ("A", "C", 2), ("C", "D", 3)],
        )
        result = dijkstra(g, "A", "D")
        assert result.path == ["A", "C", "D"]
        assert result.total_cost == pytest.approx(5.0)

    def test_direct_edge_not_always_optimal(self):
        # Direct A→D costs 20; A→B→D costs 3+4=7 (cheaper)
        g = build_graph(
            ["A", "B", "D"],
            [("A", "D", 20), ("A", "B", 3), ("B", "D", 4)],
        )
        result = dijkstra(g, "A", "D")
        assert result.path == ["A", "B", "D"]
        assert result.total_cost == pytest.approx(7.0)


# ---------------------------------------------------------------------------
# Test 4 — Path reconstruction
# ---------------------------------------------------------------------------


class TestPathReconstruction:
    """Verify the reconstructed path is complete and ordered."""

    def test_path_starts_at_source(self):
        g = build_graph(["A", "B", "C"], [("A", "B", 1), ("B", "C", 2)])
        result = dijkstra(g, "A", "C")
        assert result.path[0] == "A"

    def test_path_ends_at_destination(self):
        g = build_graph(["A", "B", "C"], [("A", "B", 1), ("B", "C", 2)])
        result = dijkstra(g, "A", "C")
        assert result.path[-1] == "C"

    def test_path_is_contiguous(self):
        """Every consecutive pair (u, v) in the path must be an edge."""
        g = build_graph(
            ["A", "B", "C", "D"],
            [("A", "B", 1), ("B", "C", 2), ("C", "D", 3)],
        )
        result = dijkstra(g, "A", "D")
        for u, v in zip(result.path, result.path[1:]):
            neighbor_ids = {e.destination_id for e in g.get_neighbors(u)}
            assert v in neighbor_ids, f"Edge {u!r} → {v!r} does not exist"

    def test_path_length_chain(self):
        g = build_graph(
            ["A", "B", "C", "D"],
            [("A", "B", 1), ("B", "C", 1), ("C", "D", 1)],
        )
        result = dijkstra(g, "A", "D")
        assert result.path == ["A", "B", "C", "D"]


# ---------------------------------------------------------------------------
# Test 5 — Total cost verification
# ---------------------------------------------------------------------------


class TestTotalCost:
    def test_total_cost_chain(self):
        # A→B (2) + B→C (3) + C→D (5) = 10
        g = build_graph(
            ["A", "B", "C", "D"],
            [("A", "B", 2), ("B", "C", 3), ("C", "D", 5)],
        )
        result = dijkstra(g, "A", "D")
        assert result.total_cost == pytest.approx(10.0)

    def test_total_cost_single_edge(self):
        g = build_graph(["X", "Y"], [("X", "Y", 7.5)])
        result = dijkstra(g, "X", "Y")
        assert result.total_cost == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# Test 6 — Source equals destination
# ---------------------------------------------------------------------------


class TestSourceEqualsDestination:
    def test_same_node_is_reachable(self):
        g = build_graph(["A"], [])
        result = dijkstra(g, "A", "A")
        assert result.reachable is True

    def test_same_node_zero_cost(self):
        g = build_graph(["A"], [])
        result = dijkstra(g, "A", "A")
        assert result.total_cost == pytest.approx(0.0)

    def test_same_node_path_is_singleton(self):
        g = build_graph(["A"], [])
        result = dijkstra(g, "A", "A")
        assert result.path == ["A"]


# ---------------------------------------------------------------------------
# Test 7 — Unreachable destination
# ---------------------------------------------------------------------------


class TestUnreachableDestination:
    def test_unreachable_flag(self):
        # B has no incoming edges from A
        g = build_graph(["A", "B"], [])
        result = dijkstra(g, "A", "B")
        assert result.reachable is False

    def test_unreachable_cost_is_infinity(self):
        g = build_graph(["A", "B"], [])
        result = dijkstra(g, "A", "B")
        assert math.isinf(result.total_cost)

    def test_unreachable_path_is_empty(self):
        g = build_graph(["A", "B"], [])
        result = dijkstra(g, "A", "B")
        assert result.path == []

    def test_one_way_edge_unreachable_reverse(self):
        # Edge only goes A→B; travelling B→A is unreachable
        g = build_graph(["A", "B"], [("A", "B", 5)])
        result = dijkstra(g, "B", "A")
        assert result.reachable is False

    def test_disconnected_component(self):
        # A→B connected; C→D connected; A cannot reach D
        g = build_graph(
            ["A", "B", "C", "D"],
            [("A", "B", 1), ("C", "D", 1)],
        )
        result = dijkstra(g, "A", "D")
        assert result.reachable is False


# ---------------------------------------------------------------------------
# Test 8 — Invalid source
# ---------------------------------------------------------------------------


class TestInvalidSource:
    def test_missing_source_raises_key_error(self):
        g = build_graph(["A", "B"], [("A", "B", 1)])
        with pytest.raises(KeyError, match="Source node"):
            dijkstra(g, "MISSING", "B")


# ---------------------------------------------------------------------------
# Test 9 — Invalid destination
# ---------------------------------------------------------------------------


class TestInvalidDestination:
    def test_missing_destination_raises_key_error(self):
        g = build_graph(["A", "B"], [("A", "B", 1)])
        with pytest.raises(KeyError, match="Destination node"):
            dijkstra(g, "A", "MISSING")


# ---------------------------------------------------------------------------
# Test 10 — Different edge weights
# ---------------------------------------------------------------------------


class TestDifferentEdgeWeights:
    def test_large_weight_not_chosen(self):
        # Two direct edges from A to B; algorithm uses whichever is lower
        # (Only one directed edge per pair is valid in our model, so test
        # via detour)
        # A→B (cost 100), A→C (cost 1), C→B (cost 1)  → optimal: A→C→B (2)
        g = build_graph(
            ["A", "B", "C"],
            [("A", "B", 100), ("A", "C", 1), ("C", "B", 1)],
        )
        result = dijkstra(g, "A", "B")
        assert result.path == ["A", "C", "B"]
        assert result.total_cost == pytest.approx(2.0)

    def test_float_weights(self):
        g = build_graph(
            ["A", "B", "C"],
            [("A", "B", 1.5), ("B", "C", 2.25)],
        )
        result = dijkstra(g, "A", "C")
        assert result.total_cost == pytest.approx(3.75)


# ---------------------------------------------------------------------------
# Test 11 — Zero-cost edge
# ---------------------------------------------------------------------------


class TestZeroCostEdge:
    def test_zero_cost_edge_is_traversed(self):
        g = build_graph(["A", "B", "C"], [("A", "B", 0.0), ("B", "C", 5.0)])
        result = dijkstra(g, "A", "C")
        assert result.reachable is True
        assert result.path == ["A", "B", "C"]
        assert result.total_cost == pytest.approx(5.0)

    def test_zero_cost_path(self):
        g = build_graph(["A", "B"], [("A", "B", 0.0)])
        result = dijkstra(g, "A", "B")
        assert result.total_cost == pytest.approx(0.0)
        assert result.reachable is True


# ---------------------------------------------------------------------------
# Test — RouteResult repr does not raise
# ---------------------------------------------------------------------------


class TestRouteResultRepr:
    def test_reachable_repr(self):
        r = RouteResult("A", "D", ["A", "B", "D"], 5.0, True)
        assert "A" in repr(r) and "D" in repr(r)

    def test_unreachable_repr(self):
        r = RouteResult("A", "D", [], math.inf, False)
        assert "False" in repr(r)
