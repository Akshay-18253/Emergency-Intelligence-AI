"""
Unit tests for benchmarking and algorithm comparison tools.
"""

import pytest

from emergency_intelligence.graph.benchmark import (
    BenchmarkComparison,
    compare_algorithms,
    create_grid_network,
)
from emergency_intelligence.graph.heuristics import euclidean_distance
from emergency_intelligence.graph.models import Edge, Graph, Node


class TestGridNetworkGeneration:
    def test_grid_node_and_edge_count(self):
        # 3x4 grid has 12 nodes.
        # Horizontal edges: 3 * (4-1) = 9
        # Vertical edges: (3-1) * 4 = 8
        # Total undirected: 17; bidirectional = 34
        grid = create_grid_network(rows=3, cols=4, bidirectional=True)
        assert grid.node_count() == 12
        assert grid.edge_count() == 34

    def test_grid_coordinates(self):
        grid = create_grid_network(rows=2, cols=2)
        n00 = grid.get_node("N_0_0")
        n11 = grid.get_node("N_1_1")
        assert n00.coordinates == (0.0, 0.0)
        assert n11.coordinates == (1.0, 1.0)

    def test_grid_invalid_dimensions(self):
        with pytest.raises(ValueError, match="at least 1x1"):
            create_grid_network(rows=0, cols=5)

    def test_grid_type_errors(self):
        with pytest.raises(TypeError, match="must be integers"):
            create_grid_network(rows="3", cols=3)  # type: ignore

        with pytest.raises(TypeError, match="must be integers"):
            create_grid_network(rows=3, cols=3.5)  # type: ignore

    def test_grid_negative_cost_raises(self):
        with pytest.raises(ValueError, match="non-negative number"):
            create_grid_network(rows=2, cols=2, unit_cost=-1.0)

    def test_grid_unidirectional(self):
        grid = create_grid_network(rows=2, cols=2, bidirectional=False)
        assert grid.node_count() == 4
        assert grid.edge_count() == 4


class TestCompareAlgorithms:
    def test_compare_on_grid_network(self):
        grid = create_grid_network(rows=8, cols=8, bidirectional=True)
        cmp = compare_algorithms(grid, "N_0_0", "N_7_7", heuristic=euclidean_distance)

        assert cmp.cost_match is True
        assert cmp.dijkstra_result.total_cost == pytest.approx(14.0)
        assert cmp.astar_result.total_cost == pytest.approx(14.0)
        assert cmp.explored_difference > 0
        assert cmp.explored_reduction_pct > 0.0

    def test_compare_same_node(self):
        grid = create_grid_network(rows=2, cols=2)
        cmp = compare_algorithms(grid, "N_0_0", "N_0_0")

        assert cmp.cost_match is True
        assert cmp.dijkstra_result.total_cost == 0.0
        assert cmp.astar_result.total_cost == 0.0

    def test_compare_unreachable(self):
        g = Graph()
        g.add_node(Node("A", coordinates=(0.0, 0.0)))
        g.add_node(Node("B", coordinates=(1.0, 1.0)))
        # No edges between A and B
        cmp = compare_algorithms(g, "A", "B")

        assert cmp.cost_match is True
        assert not cmp.dijkstra_result.reachable
        assert not cmp.astar_result.reachable

    def test_compare_cost_mismatch_detection(self, monkeypatch):
        grid = create_grid_network(rows=2, cols=2)
        # Create a mock astar result where reachable is False while Dijkstra is True
        from emergency_intelligence.graph import benchmark
        real_astar = benchmark.astar

        def mock_astar(graph, s, d, heuristic=None):
            from emergency_intelligence.graph.dijkstra import RouteResult
            return RouteResult(source=s, destination=d, path=[], total_cost=float("inf"), reachable=False, nodes_explored=1)

        monkeypatch.setattr(benchmark, "astar", mock_astar)
        cmp = benchmark.compare_algorithms(grid, "N_0_0", "N_1_1")
        assert cmp.cost_match is False

    def test_compare_zero_nodes_explored_branch(self, monkeypatch):
        grid = create_grid_network(rows=2, cols=2)
        from emergency_intelligence.graph import benchmark

        def mock_dijkstra(graph, s, d):
            from emergency_intelligence.graph.dijkstra import RouteResult
            return RouteResult(source=s, destination=d, path=[s], total_cost=0.0, reachable=True, nodes_explored=0)

        monkeypatch.setattr(benchmark, "dijkstra", mock_dijkstra)
        cmp = benchmark.compare_algorithms(grid, "N_0_0", "N_0_0")
        assert cmp.explored_reduction_pct == 0.0

    def test_benchmark_repr(self):
        grid = create_grid_network(rows=3, cols=3)
        cmp = compare_algorithms(grid, "N_0_0", "N_2_2")
        r = repr(cmp)
        assert "BenchmarkComparison" in r
        assert "cost_match=True" in r
        assert "nodes_explored" in r

