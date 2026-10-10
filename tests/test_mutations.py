"""
Unit tests for non-destructive DynamicGraphView, EdgeMutation overlays, and transactional invalidation.
"""

from datetime import datetime, timedelta, timezone
import math
import pytest

from emergency_intelligence.events.hazards import HazardPolygon, HazardSeverity, HazardType
from emergency_intelligence.events.mutations import (
    DynamicGraphView,
    EdgeMutation,
    MutationType,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.dijkstra import dijkstra
from emergency_intelligence.graph.models import Edge, Graph, Node


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_diamond_graph():
    r"""Diamond graph:
         A
       /   \
      B     C
       \   /
         D
    Paths A -> D:
    Path 1: A -> B -> D (cost 2 + 3 = 5)
    Path 2: A -> C -> D (cost 4 + 4 = 8)
    """
    g = Graph()
    g.add_node(Node("A", coordinates=(0.0, 2.0)))
    g.add_node(Node("B", coordinates=(-1.0, 1.0)))
    g.add_node(Node("C", coordinates=(1.0, 1.0)))
    g.add_node(Node("D", coordinates=(0.0, 0.0)))

    g.add_edge(Edge("A", "B", cost=2.0))
    g.add_edge(Edge("B", "D", cost=3.0))
    g.add_edge(Edge("A", "C", cost=4.0))
    g.add_edge(Edge("C", "D", cost=4.0))
    return g


# ---------------------------------------------------------------------------
# EdgeMutation Model Tests
# ---------------------------------------------------------------------------


class TestEdgeMutationModel:
    def test_basic_creation_and_defaults(self):
        mut = EdgeMutation(
            mutation_id="MUT-1",
            source_id="A",
            destination_id="B",
            mutation_type=MutationType.SPEED_PENALTY,
            cost_multiplier=2.5,
            reason="Heavy localized rainfall",
        )
        assert mut.mutation_id == "MUT-1"
        assert mut.source_id == "A"
        assert mut.destination_id == "B"
        assert mut.mutation_type == MutationType.SPEED_PENALTY
        assert mut.cost_multiplier == 2.5
        assert mut.blocked is False
        assert mut.is_expired() is False

    def test_road_closure_auto_sets_blocked(self):
        mut = EdgeMutation(
            mutation_id="MUT-2",
            source_id="A",
            destination_id="B",
            mutation_type=MutationType.ROAD_CLOSURE,
        )
        assert mut.blocked is True
        assert mut.effective_cost(10.0) == math.inf

    def test_cost_override_calculation(self):
        mut = EdgeMutation(
            mutation_id="MUT-3",
            source_id="A",
            destination_id="B",
            mutation_type=MutationType.COST_OVERRIDE,
            cost_override=42.0,
        )
        assert mut.effective_cost(10.0) == 42.0

    def test_ttl_expiration(self):
        now = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
        past_expire = now - timedelta(minutes=5)
        future_expire = now + timedelta(minutes=15)

        expired_mut = EdgeMutation(
            mutation_id="MUT-EXP",
            source_id="A",
            destination_id="B",
            mutation_type=MutationType.ROAD_CLOSURE,
            expires_at=past_expire,
        )
        assert expired_mut.is_expired(now) is True
        # Once expired, effective cost falls back to base cost!
        assert expired_mut.effective_cost(10.0, now) == 10.0

        active_mut = EdgeMutation(
            mutation_id="MUT-ACT",
            source_id="A",
            destination_id="B",
            mutation_type=MutationType.ROAD_CLOSURE,
            expires_at=future_expire,
        )
        assert active_mut.is_expired(now) is False
        assert active_mut.effective_cost(10.0, now) == math.inf

    def test_validation_errors(self):
        with pytest.raises(ValueError, match="non-empty string"):
            EdgeMutation("", "A", "B", MutationType.ROAD_CLOSURE)

        with pytest.raises(ValueError, match="non-empty string"):
            EdgeMutation("1", "", "B", MutationType.ROAD_CLOSURE)

        with pytest.raises(ValueError, match="non-empty string"):
            EdgeMutation("1", "A", "", MutationType.ROAD_CLOSURE)

        with pytest.raises(TypeError, match="MutationType enum"):
            EdgeMutation("1", "A", "B", 12345)  # type: ignore

        with pytest.raises(ValueError, match="cannot be negative"):
            EdgeMutation("1", "A", "B", MutationType.SPEED_PENALTY, cost_multiplier=-1.0)

        with pytest.raises(ValueError, match="cannot be negative"):
            EdgeMutation("1", "A", "B", MutationType.COST_OVERRIDE, cost_override=-5.0)

    def test_serialization_round_trip(self):
        fixed_dt = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
        exp_dt = datetime(2026, 10, 10, 13, 0, 0, tzinfo=timezone.utc)
        original = EdgeMutation(
            mutation_id="MUT-SER",
            source_id="A",
            destination_id="B",
            mutation_type=MutationType.SPEED_PENALTY,
            cost_multiplier=3.0,
            reason="Construction narrowing to single lane",
            created_at=fixed_dt,
            expires_at=exp_dt,
            metadata={"lane_reduction": "3 to 1"},
        )
        d = original.to_dict()
        assert d["mutation_id"] == "MUT-SER"
        assert d["mutation_type"] == "speed_penalty"
        assert d["cost_multiplier"] == 3.0

        reconstructed = EdgeMutation.from_dict(d)
        assert reconstructed.mutation_id == original.mutation_id
        assert reconstructed.source_id == original.source_id
        assert reconstructed.destination_id == original.destination_id
        assert reconstructed.mutation_type == original.mutation_type
        assert reconstructed.created_at == fixed_dt
        assert reconstructed.expires_at == exp_dt
        assert reconstructed.metadata == original.metadata


# ---------------------------------------------------------------------------
# DynamicGraphView & Rerouting Tests
# ---------------------------------------------------------------------------


class TestDynamicGraphView:
    def test_view_delegates_to_base_graph(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)
        assert view.base_graph is sample_diamond_graph
        assert view.has_node("A") is True
        assert view.has_node("NONEXISTENT") is False
        assert view.node_count() == 4
        assert view.edge_count() == 4
        assert view.node_ids() == ["A", "B", "C", "D"]
        assert view.get_node("A").node_id == "A"

    def test_invalid_construction_and_mutation(self, sample_diamond_graph):
        with pytest.raises(TypeError, match="instance of Graph"):
            DynamicGraphView("not_a_graph")  # type: ignore

        view = DynamicGraphView(sample_diamond_graph)
        with pytest.raises(TypeError, match="EdgeMutation instance"):
            view.apply_mutation("not_a_mutation")  # type: ignore

        # Mutating non-existent edge
        invalid_edge_mut = EdgeMutation("M", "A", "D", MutationType.ROAD_CLOSURE)
        with pytest.raises(KeyError, match="non-existent edge"):
            view.apply_mutation(invalid_edge_mut)

    def test_transparent_dijkstra_baseline(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)
        res = dijkstra(view, "A", "D")
        assert res.reachable is True
        assert res.path == ["A", "B", "D"]
        assert res.total_cost == 5.0

    def test_closure_forces_detour_rerouting(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)

        # Baseline: path is A -> B -> D (cost 5)
        res1 = dijkstra(view, "A", "D")
        assert res1.path == ["A", "B", "D"]

        # Close edge B -> D!
        view.apply_closure("B", "D", reason="Sinkhole collapse")
        assert view.is_edge_blocked("B", "D") is True
        assert view.edge_count(include_blocked=False) == 3

        # Dijkstra on view now automatically diverts onto A -> C -> D (cost 8)!
        res2 = dijkstra(view, "A", "D")
        assert res2.reachable is True
        assert res2.path == ["A", "C", "D"]
        assert res2.total_cost == 8.0

        # Base graph was never touched or modified!
        base_res = dijkstra(sample_diamond_graph, "A", "D")
        assert base_res.path == ["A", "B", "D"]
        assert base_res.total_cost == 5.0

    def test_speed_penalty_forces_detour_rerouting(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)

        # Speed factor 0.20 on A -> B (cost 2.0 / 0.20 = 10.0)
        # Now path A -> B -> D costs 10 + 3 = 13.0,
        # so path A -> C -> D (cost 8.0) becomes the optimal route!
        view.apply_speed_penalty("A", "B", speed_factor=0.20, reason="Flash flood ponding")
        assert view.active_mutation_count() == 1

        res = dijkstra(view, "A", "D")
        assert res.path == ["A", "C", "D"]
        assert res.total_cost == 8.0

    def test_bidirectional_closure(self, sample_diamond_graph):
        # Add reverse edge D -> B to base graph
        sample_diamond_graph.add_edge(Edge("D", "B", cost=3.0))
        view = DynamicGraphView(sample_diamond_graph)

        muts = view.apply_closure("B", "D", bidirectional=True)
        assert len(muts) == 2
        assert view.is_edge_blocked("B", "D") is True
        assert view.is_edge_blocked("D", "B") is True

    def test_transactional_rollback(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)

        view.begin_transaction()
        view.apply_closure("A", "B", reason="Incident 1")
        view.apply_closure("A", "C", reason="Incident 2")

        # Both paths severed -> unreachable!
        res_blocked = dijkstra(view, "A", "D")
        assert res_blocked.reachable is False

        # Roll back transaction!
        rolled_back_count = view.rollback_transaction()
        assert rolled_back_count == 2
        assert view.active_mutation_count() == 0

        # Route immediately restored to original optimal path
        res_restored = dijkstra(view, "A", "D")
        assert res_restored.reachable is True
        assert res_restored.path == ["A", "B", "D"]
        assert res_restored.total_cost == 5.0

    def test_ttl_purge_expired(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)
        now = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
        past_time = now - timedelta(hours=1)

        mut = EdgeMutation(
            mutation_id="M-EXP",
            source_id="A",
            destination_id="B",
            mutation_type=MutationType.ROAD_CLOSURE,
            expires_at=past_time,
        )
        view.apply_mutation(mut)

        # Before explicit purge, get_neighbors already filters out expired mutation
        neighbors = view.get_neighbors("A", now=now)
        assert len(neighbors) == 2  # A->B and A->C both available

        # Purge removes it from dictionary
        purged = view.purge_expired(now=now)
        assert purged == 1
        assert view.active_mutation_count() == 0

    def test_apply_hazard_spatial_intersection(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)
        # Hazard enclosing node B (lon: -1.0, lat: 1.0)
        hazard = HazardPolygon(
            hazard_id="HAZ-B",
            hazard_type=HazardType.WILDFIRE_PERIMETER,
            severity=HazardSeverity.CRITICAL_BLOCKED,
            boundary_coordinates=[
                (-1.5, 0.5),
                (-0.5, 0.5),
                (-0.5, 1.5),
                (-1.5, 1.5),
            ],
        )

        applied = view.apply_hazard(hazard)
        assert len(applied) >= 2  # Both A->B and B->D intersect hazard!
        assert view.is_edge_blocked("A", "B") is True
        assert view.is_edge_blocked("B", "D") is True

        # Rerouting diverts to C
        res = dijkstra(view, "A", "D")
        assert res.path == ["A", "C", "D"]

    def test_snapshot_and_restore(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)
        view.apply_closure("A", "B")
        view.apply_speed_penalty("A", "C", speed_factor=0.5)

        snap = view.snapshot()
        assert len(snap["mutations"]) == 2

        # Clear mutations
        view.clear_mutations()
        assert view.active_mutation_count() == 0

        # Restore from snapshot
        view.restore_snapshot(snap)
        assert view.active_mutation_count() == 2
        assert view.is_edge_blocked("A", "B") is True

    def test_remove_mutation(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)
        view.apply_closure("A", "B")
        assert view.is_edge_blocked("A", "B") is True

        assert view.remove_mutation("A", "B") is True
        assert view.is_edge_blocked("A", "B") is False
        assert view.remove_mutation("A", "B") is False

    def test_include_blocked_flags_and_edge_queries(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)
        view.apply_closure("A", "B")

        # Edge count with and without blocked
        assert view.edge_count(include_blocked=False) == 3
        assert view.edge_count(include_blocked=True) == 4

        # has_edge with and without blocked
        assert view.has_edge("A", "B", include_blocked=False) is False
        assert view.has_edge("A", "B", include_blocked=True) is True
        assert view.has_edge("A", "NONEXISTENT") is False

        # get_neighbors with include_blocked=True returns infinite cost edge
        neighbors_with_blocked = view.get_neighbors("A", include_blocked=True)
        assert len(neighbors_with_blocked) == 2
        edge_ab = next(e for e in neighbors_with_blocked if e.destination_id == "B")
        assert edge_ab.cost == math.inf

    def test_nested_transactions(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)
        # Empty rollback returns 0
        assert view.rollback_transaction() == 0

        # Nested transaction
        view.begin_transaction()
        view.apply_closure("A", "B")
        view.begin_transaction()
        view.apply_closure("B", "D")
        view.commit_transaction()  # merges into outer
        view.commit_transaction()

        assert view.active_mutation_count() == 2

    def test_apply_hazard_inactive(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)
        hazard = HazardPolygon(
            hazard_id="INACTIVE",
            hazard_type=HazardType.FLASH_FLOOD,
            severity=HazardSeverity.CRITICAL_BLOCKED,
            boundary_coordinates=[(0, 0), (1, 0), (1, 1), (0, 1)],
            active=False,
        )
        assert view.apply_hazard(hazard) == []

    def test_invalid_speed_penalty_factors(self, sample_diamond_graph):
        view = DynamicGraphView(sample_diamond_graph)
        with pytest.raises(ValueError, match="speed_factor must be in range"):
            view.apply_speed_penalty("A", "B", speed_factor=0.0)

        with pytest.raises(ValueError, match="speed_factor must be in range"):
            view.apply_speed_penalty("A", "B", speed_factor=1.5)
