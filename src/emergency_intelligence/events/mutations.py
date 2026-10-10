"""
Non-destructive graph mutation layer and transactional invalidation engine.

Provides zero-overhead dynamic overlays over road networks:
- EdgeMutation: Individual road segment overrides (closures, speed penalties, overrides)
- DynamicGraphView: Non-destructive wrapper around Graph conforming to the routing interface
- Transactional rollbacks and atomic undo operations
- Time-To-Live (TTL) expiration and automatic pruning for transient road closures
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from emergency_intelligence.events.hazards import HazardPolygon, find_edges_intersecting_hazard
from emergency_intelligence.graph.models import Edge, Graph, Node


class MutationType(str, Enum):
    """Classification of dynamic edge modification types."""

    ROAD_CLOSURE = "road_closure"        # Complete physical blockage (infinite cost / excluded)
    SPEED_PENALTY = "speed_penalty"      # Congestion, smoke, water depth slowing traffic
    COST_OVERRIDE = "cost_override"      # Fixed cost replacement value


@dataclass
class EdgeMutation:
    """Represents a dynamic modification overlay applied to a directed road segment.

    Attributes:
        mutation_id: Unique string identifier for this mutation.
        source_id: Starting node ID of the affected edge.
        destination_id: Ending node ID of the affected edge.
        mutation_type: Category of modification.
        blocked: True if the road segment is completely impassable.
        cost_multiplier: Scaling factor applied to base cost (e.g. 2.0 = double duration).
        cost_override: Explicit cost override value (if mutation_type is COST_OVERRIDE).
        reason: Human-readable incident reason (e.g. "Water main break", "Fallen power lines").
        created_at: Timestamp when mutation was enacted.
        expires_at: Optional TTL timestamp when mutation automatically clears.
        metadata: Arbitrary additional data (e.g. hazard_id, agency_reporting).
    """

    mutation_id: str
    source_id: str
    destination_id: str
    mutation_type: MutationType
    blocked: bool = False
    cost_multiplier: float = 1.0
    cost_override: Optional[float] = None
    reason: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.mutation_id or not isinstance(self.mutation_id, str):
            raise ValueError("EdgeMutation.mutation_id must be a non-empty string.")
        if not self.source_id or not isinstance(self.source_id, str):
            raise ValueError("EdgeMutation.source_id must be a non-empty string.")
        if not self.destination_id or not isinstance(self.destination_id, str):
            raise ValueError("EdgeMutation.destination_id must be a non-empty string.")

        if not isinstance(self.mutation_type, MutationType):
            if isinstance(self.mutation_type, str):
                self.mutation_type = MutationType(self.mutation_type)
            else:
                raise TypeError("EdgeMutation.mutation_type must be a MutationType enum.")

        if self.cost_multiplier < 0.0:
            raise ValueError("EdgeMutation.cost_multiplier cannot be negative.")

        if self.cost_override is not None and self.cost_override < 0.0:
            raise ValueError("EdgeMutation.cost_override cannot be negative.")

        if self.mutation_type == MutationType.ROAD_CLOSURE:
            self.blocked = True

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """Evaluates whether the mutation has expired past its Time-To-Live (TTL)."""
        if self.expires_at is None:
            return False
        current_time = now or datetime.now(timezone.utc)
        return current_time >= self.expires_at

    def effective_cost(self, base_cost: float, now: Optional[datetime] = None) -> float:
        """Calculates the effective traversal cost given this mutation."""
        if self.is_expired(now):
            return base_cost
        if self.blocked:
            return math.inf
        if self.mutation_type == MutationType.COST_OVERRIDE and self.cost_override is not None:
            return self.cost_override
        return base_cost * self.cost_multiplier

    def to_dict(self) -> Dict[str, Any]:
        """Serializes mutation into a JSON dictionary."""
        return {
            "mutation_id": self.mutation_id,
            "source_id": self.source_id,
            "destination_id": self.destination_id,
            "mutation_type": self.mutation_type.value,
            "blocked": self.blocked,
            "cost_multiplier": self.cost_multiplier,
            "cost_override": self.cost_override,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EdgeMutation:
        """Constructs an EdgeMutation from a dictionary."""
        created_val = data.get("created_at")
        if isinstance(created_val, str):
            c_at = datetime.fromisoformat(created_val)
        elif isinstance(created_val, datetime):
            c_at = created_val
        else:
            c_at = datetime.now(timezone.utc)

        expires_val = data.get("expires_at")
        e_at = datetime.fromisoformat(expires_val) if isinstance(expires_val, str) else None

        return cls(
            mutation_id=str(data["mutation_id"]),
            source_id=str(data["source_id"]),
            destination_id=str(data["destination_id"]),
            mutation_type=MutationType(data["mutation_type"]),
            blocked=bool(data.get("blocked", False)),
            cost_multiplier=float(data.get("cost_multiplier", 1.0)),
            cost_override=float(data["cost_override"]) if data.get("cost_override") is not None else None,
            reason=str(data.get("reason", "")),
            created_at=c_at,
            expires_at=e_at,
            metadata=dict(data.get("metadata", {})),
        )


class DynamicGraphView:
    """Non-destructive, transaction-aware graph overlay layer.

    Wraps a base road network Graph and dynamically modifies edge costs and availability
    without mutating or duplicating the underlying graph data structure. Conforms
    transparently to the Graph query interface for Dijkstra, A*, and heuristic search.
    """

    def __init__(self, base_graph: Graph) -> None:
        if not isinstance(base_graph, Graph):
            raise TypeError("base_graph must be an instance of Graph.")
        self._base_graph: Graph = base_graph
        # Key: (source_id, destination_id) -> active EdgeMutation
        self._mutations: Dict[Tuple[str, str], EdgeMutation] = {}
        # Transaction stack for multi-mutation atomic rollback
        self._transaction_stack: List[List[Tuple[str, str]]] = []

    @property
    def base_graph(self) -> Graph:
        """Returns the underlying base graph reference."""
        return self._base_graph

    @property
    def nodes(self) -> Dict[str, Node]:
        """Provides direct access to the base graph nodes dictionary."""
        return self._base_graph.nodes

    @property
    def edges(self) -> Dict[Tuple[str, str], Edge]:
        """Provides direct access to the base graph edges dictionary."""
        return self._base_graph.edges

    # -----------------------------------------------------------------------
    # Mutation Management & Transactions
    # -----------------------------------------------------------------------

    def apply_mutation(self, mutation: EdgeMutation, track_transaction: bool = True) -> None:
        """Applies an individual edge mutation overlay."""
        if not isinstance(mutation, EdgeMutation):
            raise TypeError("Expected an EdgeMutation instance.")

        key = (mutation.source_id, mutation.destination_id)
        if not self._base_graph.has_edge(mutation.source_id, mutation.destination_id):
            raise KeyError(
                f"Cannot mutate non-existent edge ({mutation.source_id} -> {mutation.destination_id})."
            )

        self._mutations[key] = mutation

        if track_transaction and self._transaction_stack:
            self._transaction_stack[-1].append(key)

    def apply_closure(
        self,
        source_id: str,
        destination_id: str,
        reason: str = "Road Closure",
        expires_at: Optional[datetime] = None,
        bidirectional: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[EdgeMutation]:
        """Convenience method to close one or both directions of a road segment."""
        mutations: List[EdgeMutation] = []
        self.begin_transaction()

        fwd_id = f"close_{source_id}_{destination_id}_{len(self._mutations)}"
        fwd_mut = EdgeMutation(
            mutation_id=fwd_id,
            source_id=source_id,
            destination_id=destination_id,
            mutation_type=MutationType.ROAD_CLOSURE,
            blocked=True,
            reason=reason,
            expires_at=expires_at,
            metadata=dict(metadata or {}),
        )
        self.apply_mutation(fwd_mut, track_transaction=True)
        mutations.append(fwd_mut)

        if bidirectional and self._base_graph.has_edge(destination_id, source_id):
            rev_id = f"close_{destination_id}_{source_id}_{len(self._mutations)}"
            rev_mut = EdgeMutation(
                mutation_id=rev_id,
                source_id=destination_id,
                destination_id=source_id,
                mutation_type=MutationType.ROAD_CLOSURE,
                blocked=True,
                reason=reason,
                expires_at=expires_at,
                metadata=dict(metadata or {}),
            )
            self.apply_mutation(rev_mut, track_transaction=True)
            mutations.append(rev_mut)

        self.commit_transaction()
        return mutations

    def apply_speed_penalty(
        self,
        source_id: str,
        destination_id: str,
        speed_factor: float,
        reason: str = "Speed Reduction",
        expires_at: Optional[datetime] = None,
        bidirectional: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[EdgeMutation]:
        """Applies a speed multiplier penalty to an edge (e.g. speed_factor 0.5 doubles cost)."""
        if speed_factor <= 0.0 or speed_factor > 1.0:
            raise ValueError("speed_factor must be in range (0.0, 1.0].")

        cost_multiplier = 1.0 / speed_factor
        mutations: List[EdgeMutation] = []
        self.begin_transaction()

        fwd_id = f"slow_{source_id}_{destination_id}_{len(self._mutations)}"
        fwd_mut = EdgeMutation(
            mutation_id=fwd_id,
            source_id=source_id,
            destination_id=destination_id,
            mutation_type=MutationType.SPEED_PENALTY,
            cost_multiplier=cost_multiplier,
            reason=reason,
            expires_at=expires_at,
            metadata=dict(metadata or {}),
        )
        self.apply_mutation(fwd_mut, track_transaction=True)
        mutations.append(fwd_mut)

        if bidirectional and self._base_graph.has_edge(destination_id, source_id):
            rev_id = f"slow_{destination_id}_{source_id}_{len(self._mutations)}"
            rev_mut = EdgeMutation(
                mutation_id=rev_id,
                source_id=destination_id,
                destination_id=source_id,
                mutation_type=MutationType.SPEED_PENALTY,
                cost_multiplier=cost_multiplier,
                reason=reason,
                expires_at=expires_at,
                metadata=dict(metadata or {}),
            )
            self.apply_mutation(rev_mut, track_transaction=True)
            mutations.append(rev_mut)

        self.commit_transaction()
        return mutations

    def apply_hazard(
        self,
        hazard: HazardPolygon,
        bidirectional: bool = True,
    ) -> List[EdgeMutation]:
        """Spatially intersects a hazard polygon with the road network and applies mutations."""
        if not hazard.active:
            return []

        intersecting_edges = find_edges_intersecting_hazard(self._base_graph, hazard)
        mutations: List[EdgeMutation] = []
        self.begin_transaction()

        is_block = hazard.is_blocking()
        mult = 1.0 / hazard.speed_multiplier if (hazard.speed_multiplier and hazard.speed_multiplier > 0) else 1.0

        for edge in intersecting_edges:
            mut_type = MutationType.ROAD_CLOSURE if is_block else MutationType.SPEED_PENALTY
            m_id = f"haz_{hazard.hazard_id}_{edge.source_id}_{edge.destination_id}"
            mut = EdgeMutation(
                mutation_id=m_id,
                source_id=edge.source_id,
                destination_id=edge.destination_id,
                mutation_type=mut_type,
                blocked=is_block,
                cost_multiplier=mult,
                reason=hazard.description or f"Hazard {hazard.hazard_id}",
                expires_at=hazard.expires_at,
                metadata={"hazard_id": hazard.hazard_id, "hazard_type": hazard.hazard_type.value},
            )
            self.apply_mutation(mut, track_transaction=True)
            mutations.append(mut)

            if bidirectional and self._base_graph.has_edge(edge.destination_id, edge.source_id):
                rev_key = (edge.destination_id, edge.source_id)
                if rev_key not in self._mutations:
                    r_id = f"haz_{hazard.hazard_id}_{edge.destination_id}_{edge.source_id}"
                    rev_mut = EdgeMutation(
                        mutation_id=r_id,
                        source_id=edge.destination_id,
                        destination_id=edge.source_id,
                        mutation_type=mut_type,
                        blocked=is_block,
                        cost_multiplier=mult,
                        reason=hazard.description or f"Hazard {hazard.hazard_id}",
                        expires_at=hazard.expires_at,
                        metadata={"hazard_id": hazard.hazard_id, "hazard_type": hazard.hazard_type.value},
                    )
                    self.apply_mutation(rev_mut, track_transaction=True)
                    mutations.append(rev_mut)

        self.commit_transaction()
        return mutations

    def begin_transaction(self) -> None:
        """Pushes a new transaction boundary onto the stack."""
        self._transaction_stack.append([])

    def commit_transaction(self) -> None:
        """Commits the current transaction boundary."""
        if self._transaction_stack:
            # Flatten into parent if nested, or pop
            committed = self._transaction_stack.pop()
            if self._transaction_stack:
                self._transaction_stack[-1].extend(committed)

    def rollback_transaction(self) -> int:
        """Rolls back all mutations applied during the most recent transaction."""
        if not self._transaction_stack:
            return 0
        keys_to_revert = self._transaction_stack.pop()
        count = 0
        for key in keys_to_revert:
            if key in self._mutations:
                del self._mutations[key]
                count += 1
        return count

    def remove_mutation(self, source_id: str, destination_id: str) -> bool:
        """Removes a mutation overlay from an edge."""
        key = (source_id, destination_id)
        if key in self._mutations:
            del self._mutations[key]
            return True
        return False

    def clear_mutations(self) -> None:
        """Removes all dynamic mutations, restoring graph to pure base state."""
        self._mutations.clear()
        self._transaction_stack.clear()

    def purge_expired(self, now: Optional[datetime] = None) -> int:
        """Prunes all mutations whose TTL has expired."""
        current_time = now or datetime.now(timezone.utc)
        expired_keys = [key for key, mut in self._mutations.items() if mut.is_expired(current_time)]
        for key in expired_keys:
            del self._mutations[key]
        return len(expired_keys)

    def active_mutation_count(self, now: Optional[datetime] = None) -> int:
        """Returns the number of active, non-expired mutations."""
        current_time = now or datetime.now(timezone.utc)
        return sum(1 for mut in self._mutations.values() if not mut.is_expired(current_time))

    def get_mutation(self, source_id: str, destination_id: str) -> Optional[EdgeMutation]:
        """Returns the active mutation overlay for an edge, or None."""
        key = (source_id, destination_id)
        mut = self._mutations.get(key)
        if mut and not mut.is_expired():
            return mut
        return None

    def is_edge_blocked(self, source_id: str, destination_id: str) -> bool:
        """Returns True if the directed edge is currently impassable."""
        mut = self.get_mutation(source_id, destination_id)
        return bool(mut and mut.blocked)

    # -----------------------------------------------------------------------
    # Graph Interface Implementation (Transparent Delegation)
    # -----------------------------------------------------------------------

    def has_node(self, node_id: str) -> bool:
        """Delegates directly to base graph."""
        return self._base_graph.has_node(node_id)

    def has_edge(self, source_id: str, destination_id: str, include_blocked: bool = False) -> bool:
        """Returns True if edge exists in base graph and is not blocked."""
        if not self._base_graph.has_edge(source_id, destination_id):
            return False
        if not include_blocked and self.is_edge_blocked(source_id, destination_id):
            return False
        return True

    def get_node(self, node_id: str) -> Node:
        """Delegates directly to base graph."""
        return self._base_graph.get_node(node_id)

    def node_ids(self) -> List[str]:
        """Delegates directly to base graph."""
        return self._base_graph.node_ids()

    def node_count(self) -> int:
        """Delegates directly to base graph."""
        return self._base_graph.node_count()

    def edge_count(self, include_blocked: bool = False) -> int:
        """Computes the effective edge count."""
        base_count = self._base_graph.edge_count()
        if include_blocked:
            return base_count
        blocked_count = sum(1 for mut in self._mutations.values() if mut.blocked and not mut.is_expired())
        return max(0, base_count - blocked_count)

    def get_neighbors(
        self,
        node_id: str,
        include_blocked: bool = False,
        now: Optional[datetime] = None,
    ) -> List[Edge]:
        """Returns outgoing edges from node_id with dynamic costs and closures applied.

        If an edge is blocked and include_blocked is False, it is omitted from the result.
        If an edge is modified, a mutated Edge instance with effective cost is returned.
        If unmutated, the original base Edge is returned with zero copy overhead.
        """
        base_neighbors = self._base_graph.get_neighbors(node_id)
        if not self._mutations:
            return base_neighbors

        effective_edges: List[Edge] = []
        current_time = now or datetime.now(timezone.utc)

        for edge in base_neighbors:
            key = (edge.source_id, edge.destination_id)
            mut = self._mutations.get(key)

            if mut is None or mut.is_expired(current_time):
                effective_edges.append(edge)
                continue

            if mut.blocked:
                if include_blocked:
                    # Return edge with infinite cost
                    mutated_edge = Edge(
                        source_id=edge.source_id,
                        destination_id=edge.destination_id,
                        cost=math.inf,
                        attributes=dict(edge.attributes),
                    )
                    effective_edges.append(mutated_edge)
                # Else: completely filter out blocked edge
                continue

            new_cost = mut.effective_cost(edge.cost, current_time)
            mutated_edge = Edge(
                source_id=edge.source_id,
                destination_id=edge.destination_id,
                cost=new_cost,
                attributes=dict(edge.attributes),
            )
            effective_edges.append(mutated_edge)

        return effective_edges

    # -----------------------------------------------------------------------
    # Snapshots & State Serialization
    # -----------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        """Captures a snapshot of current active mutations for rollback/branching."""
        return {
            "mutations": [mut.to_dict() for mut in self._mutations.values()],
        }

    def restore_snapshot(self, snapshot_data: Dict[str, Any]) -> None:
        """Restores mutations from a captured snapshot."""
        self.clear_mutations()
        for mut_dict in snapshot_data.get("mutations", []):
            mut = EdgeMutation.from_dict(mut_dict)
            self.apply_mutation(mut, track_transaction=False)
