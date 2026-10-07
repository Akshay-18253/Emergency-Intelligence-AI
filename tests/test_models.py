"""
Unit tests for the road graph data model.

Tests cover Node, Edge, and Graph construction, validation, and query
behaviour.  All tests use Python's standard ``unittest`` framework.

Run with:
    python -m pytest tests/ -v
"""

import pytest

from emergency_intelligence.graph.models import Edge, Graph, Node


# ---------------------------------------------------------------------------
# Node tests
# ---------------------------------------------------------------------------


class TestNode:
    def test_node_basic_creation(self):
        node = Node("A")
        assert node.node_id == "A"
        assert node.label is None

    def test_node_with_label(self):
        node = Node("B", label="Main Street")
        assert node.node_id == "B"
        assert node.label == "Main Street"

    def test_node_equality(self):
        assert Node("A") == Node("A")
        assert Node("A") != Node("B")

    def test_node_hashable(self):
        node_set = {Node("A"), Node("B"), Node("A")}
        assert len(node_set) == 2

    def test_node_empty_id_raises(self):
        with pytest.raises(ValueError, match="non-empty string"):
            Node("")

    def test_node_non_string_id_raises(self):
        with pytest.raises((ValueError, TypeError)):
            Node(123)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Edge tests
# ---------------------------------------------------------------------------


class TestEdge:
    def test_edge_basic_creation(self):
        edge = Edge("A", "B", cost=5.0)
        assert edge.source_id == "A"
        assert edge.destination_id == "B"
        assert edge.cost == 5.0

    def test_edge_zero_cost_allowed(self):
        edge = Edge("A", "B", cost=0.0)
        assert edge.cost == 0.0

    def test_edge_integer_cost_allowed(self):
        edge = Edge("A", "B", cost=3)
        assert edge.cost == 3

    def test_edge_negative_cost_raises(self):
        with pytest.raises(ValueError, match="non-negative"):
            Edge("A", "B", cost=-1.0)

    def test_edge_empty_source_raises(self):
        with pytest.raises(ValueError):
            Edge("", "B", cost=1.0)

    def test_edge_empty_destination_raises(self):
        with pytest.raises(ValueError):
            Edge("A", "", cost=1.0)

    def test_edge_non_numeric_cost_raises(self):
        with pytest.raises((ValueError, TypeError)):
            Edge("A", "B", cost="fast")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Graph tests
# ---------------------------------------------------------------------------


class TestGraph:
    def _make_simple_graph(self) -> Graph:
        """Return a small graph: A → B (cost 1), A → C (cost 4), B → C (cost 2)."""
        g = Graph()
        for nid in ("A", "B", "C"):
            g.add_node(Node(nid))
        g.add_edge(Edge("A", "B", cost=1.0))
        g.add_edge(Edge("A", "C", cost=4.0))
        g.add_edge(Edge("B", "C", cost=2.0))
        return g

    def test_empty_graph(self):
        g = Graph()
        assert g.node_count() == 0
        assert g.edge_count() == 0

    def test_add_node(self):
        g = Graph()
        g.add_node(Node("X"))
        assert g.has_node("X")
        assert g.node_count() == 1

    def test_add_duplicate_node_raises(self):
        g = Graph()
        g.add_node(Node("X"))
        with pytest.raises(ValueError, match="already exists"):
            g.add_node(Node("X"))

    def test_add_non_node_raises(self):
        g = Graph()
        with pytest.raises(TypeError):
            g.add_node("X")  # type: ignore[arg-type]

    def test_add_edge(self):
        g = Graph()
        g.add_node(Node("A"))
        g.add_node(Node("B"))
        g.add_edge(Edge("A", "B", cost=3.0))
        assert g.edge_count() == 1

    def test_edge_missing_source_raises(self):
        g = Graph()
        g.add_node(Node("B"))
        with pytest.raises(KeyError, match="Source node"):
            g.add_edge(Edge("A", "B", cost=1.0))

    def test_edge_missing_destination_raises(self):
        g = Graph()
        g.add_node(Node("A"))
        with pytest.raises(KeyError, match="Destination node"):
            g.add_edge(Edge("A", "B", cost=1.0))

    def test_get_neighbors(self):
        g = self._make_simple_graph()
        neighbors = g.get_neighbors("A")
        dest_ids = {e.destination_id for e in neighbors}
        assert dest_ids == {"B", "C"}

    def test_get_neighbors_empty(self):
        g = Graph()
        g.add_node(Node("Z"))
        assert g.get_neighbors("Z") == []

    def test_get_neighbors_missing_node_raises(self):
        g = Graph()
        with pytest.raises(KeyError):
            g.get_neighbors("MISSING")

    def test_directed_edges(self):
        """Edge A → B must not imply B → A."""
        g = Graph()
        g.add_node(Node("A"))
        g.add_node(Node("B"))
        g.add_edge(Edge("A", "B", cost=1.0))
        assert g.get_neighbors("B") == []

    def test_node_ids_sorted(self):
        g = Graph()
        for nid in ("C", "A", "B"):
            g.add_node(Node(nid))
        assert g.node_ids() == ["A", "B", "C"]

    def test_repr(self):
        g = self._make_simple_graph()
        assert "Graph" in repr(g)
        assert "3" in repr(g)  # 3 nodes

    def test_get_node(self):
        g = Graph()
        g.add_node(Node("A", label="Start"))
        node = g.get_node("A")
        assert node.label == "Start"

    def test_get_node_missing_raises(self):
        g = Graph()
        with pytest.raises(KeyError):
            g.get_node("MISSING")
