"""
Road graph data model.

Defines the three core abstractions used by the routing engine:

    Node  — an intersection or location in the road network.
    Edge  — a directed, weighted connection between two nodes.
    Graph — a directed weighted graph containing nodes and edges.

Design notes
------------
- The graph is intentionally kept minimal for Day 1.
- Edge cost is a non-negative float representing traversal cost.
  On Day 1 this is an abstract numerical value.  Future phases will
  attach concrete semantics such as travel time, congestion penalty,
  risk score, or composite emergency cost.
- The graph is directed: an edge from A → B does not imply B → A.
- No external dependencies are used; only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


@dataclass
class Node:
    """Represents an intersection or named location in the road network.

    Attributes
    ----------
    node_id:
        A unique string identifier for this node (e.g. ``"A"``, ``"intersection_42"``).
    label:
        An optional human-readable description (e.g. ``"Main St / 1st Ave"``).
        Not used by the routing algorithm; provided for display and debugging.
    coordinates:
        Optional 2D spatial coordinates ``(x, y)`` (e.g. Cartesian plane or
        longitude/latitude). Used by heuristic-guided algorithms such as A*.
    """

    node_id: str
    label: Optional[str] = None
    coordinates: Optional[Tuple[float, float]] = None

    def __post_init__(self) -> None:
        if not self.node_id or not isinstance(self.node_id, str):
            raise ValueError("Node.node_id must be a non-empty string.")
        if self.coordinates is not None:
            if not isinstance(self.coordinates, (tuple, list)) or len(self.coordinates) != 2:
                raise ValueError(
                    f"Node.coordinates must be a pair of numbers (x, y), got {self.coordinates!r}."
                )
            x, y = self.coordinates
            if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
                raise ValueError(
                    f"Node.coordinates values must be numeric, got ({type(x).__name__}, {type(y).__name__})."
                )
            self.coordinates = (float(x), float(y))

    @property
    def x(self) -> Optional[float]:
        """Return the X-coordinate, or None if coordinates are not set."""
        return self.coordinates[0] if self.coordinates is not None else None

    @property
    def y(self) -> Optional[float]:
        """Return the Y-coordinate, or None if coordinates are not set."""
        return self.coordinates[1] if self.coordinates is not None else None

    def __hash__(self) -> int:
        return hash(self.node_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Node):
            return NotImplemented
        return self.node_id == other.node_id


# ---------------------------------------------------------------------------
# Edge
# ---------------------------------------------------------------------------


@dataclass
class Edge:
    """Represents a directed, weighted connection between two nodes.

    Attributes
    ----------
    source_id:
        The ``node_id`` of the origin node.
    destination_id:
        The ``node_id`` of the destination node.
    cost:
        Non-negative traversal cost. On Day 1 this was an abstract
        numerical value. In Phase 3, this reflects multi-criteria metrics
        such as physical distance (meters) or travel time (seconds).
    attributes:
        Optional dictionary carrying metadata such as physical distance (m),
        travel time (s), speed limit (km/h), road type, and intermediate geometry.
    """

    source_id: str
    destination_id: str
    cost: float
    attributes: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or not self.source_id:
            raise ValueError("Edge.source_id must be a non-empty string.")
        if not isinstance(self.destination_id, str) or not self.destination_id:
            raise ValueError("Edge.destination_id must be a non-empty string.")
        if not isinstance(self.cost, (int, float)):
            raise ValueError("Edge.cost must be a numeric value.")
        if self.cost < 0:
            raise ValueError(
                f"Edge.cost must be non-negative (got {self.cost!r}). "
                "Dijkstra's algorithm requires non-negative edge weights."
            )
        if not isinstance(self.attributes, dict):
            raise TypeError(
                f"Edge.attributes must be a dict, got {type(self.attributes).__name__}."
            )


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


class Graph:
    """A directed, weighted graph representing a simplified road network.

    Nodes represent intersections or locations.
    Edges represent directed road segments with a traversal cost.

    The graph is implemented using an adjacency-list representation,
    which is efficient for sparse graphs (typical of road networks).

    Example
    -------
    >>> g = Graph()
    >>> g.add_node(Node("A"))
    >>> g.add_node(Node("B"))
    >>> g.add_edge(Edge("A", "B", cost=5.0))
    >>> g.get_neighbors("A")
    [Edge(source_id='A', destination_id='B', cost=5.0)]
    """

    def __init__(self) -> None:
        # Maps node_id → Node object
        self._nodes: Dict[str, Node] = {}
        # Maps node_id → list of outgoing Edge objects (adjacency list)
        self._adjacency: Dict[str, List[Edge]] = {}

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Add a node to the graph.

        Parameters
        ----------
        node:
            The :class:`Node` to add.

        Raises
        ------
        TypeError
            If *node* is not a :class:`Node` instance.
        ValueError
            If a node with the same ``node_id`` already exists.
        """
        if not isinstance(node, Node):
            raise TypeError(f"Expected a Node instance, got {type(node).__name__!r}.")
        if node.node_id in self._nodes:
            raise ValueError(
                f"A node with id {node.node_id!r} already exists in the graph."
            )
        self._nodes[node.node_id] = node
        self._adjacency[node.node_id] = []

    def add_edge(self, edge: Edge) -> None:
        """Add a directed edge to the graph.

        Both the source and destination nodes must already exist in the graph.

        Parameters
        ----------
        edge:
            The :class:`Edge` to add.

        Raises
        ------
        TypeError
            If *edge* is not an :class:`Edge` instance.
        KeyError
            If the source or destination node does not exist in the graph.
        """
        if not isinstance(edge, Edge):
            raise TypeError(f"Expected an Edge instance, got {type(edge).__name__!r}.")
        if edge.source_id not in self._nodes:
            raise KeyError(
                f"Source node {edge.source_id!r} does not exist in the graph. "
                "Add the node before adding an edge."
            )
        if edge.destination_id not in self._nodes:
            raise KeyError(
                f"Destination node {edge.destination_id!r} does not exist in the "
                "graph.  Add the node before adding an edge."
            )
        self._adjacency[edge.source_id].append(edge)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def has_node(self, node_id: str) -> bool:
        """Return ``True`` if a node with *node_id* exists in the graph."""
        return node_id in self._nodes

    def has_edge(self, source_id: str, destination_id: str) -> bool:
        """Return ``True`` if a directed edge from *source_id* to *destination_id* exists."""
        if source_id not in self._adjacency:
            return False
        return any(edge.destination_id == destination_id for edge in self._adjacency[source_id])

    def get_node(self, node_id: str) -> Node:
        """Return the :class:`Node` for *node_id*.

        Raises
        ------
        KeyError
            If *node_id* is not in the graph.
        """
        if node_id not in self._nodes:
            raise KeyError(f"Node {node_id!r} does not exist in the graph.")
        return self._nodes[node_id]

    def get_neighbors(self, node_id: str) -> List[Edge]:
        """Return all outgoing edges from the node identified by *node_id*.

        Parameters
        ----------
        node_id:
            The identifier of the source node.

        Returns
        -------
        list[Edge]
            A list of outgoing :class:`Edge` objects.  Empty if the node
            has no outgoing edges.

        Raises
        ------
        KeyError
            If *node_id* is not in the graph.
        """
        if node_id not in self._adjacency:
            raise KeyError(f"Node {node_id!r} does not exist in the graph.")
        return list(self._adjacency[node_id])

    def node_count(self) -> int:
        """Return the number of nodes in the graph."""
        return len(self._nodes)

    def edge_count(self) -> int:
        """Return the total number of directed edges in the graph."""
        return sum(len(edges) for edges in self._adjacency.values())

    def node_ids(self) -> List[str]:
        """Return a sorted list of all node identifiers."""
        return sorted(self._nodes.keys())

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"Graph(nodes={self.node_count()}, edges={self.edge_count()})"
        )
