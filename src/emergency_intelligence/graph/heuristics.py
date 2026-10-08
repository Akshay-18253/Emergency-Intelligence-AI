"""
Heuristic functions for informed search algorithms (e.g. A*).

Provides distance-based heuristics used to estimate the remaining cost
from a given node to the destination goal in a road graph.

Heuristics implemented
----------------------
- euclidean_distance : Straight-line Euclidean distance L2 norm.
                       Admissible and consistent on geometric networks
                       where edge traversal cost is >= Euclidean distance.
- manhattan_distance : Grid-based Manhattan distance L1 norm.
                       Admissible on 4-connected grid networks where edge
                       cost is >= grid distance.
- zero_heuristic     : Always returns 0.0. Trivially admissible and consistent.
                       Causes A* to behave identically to Dijkstra's algorithm.

References
----------
- Hart, P. E., Nilsson, N. J., & Raphael, B. (1968). A Formal Basis for the
  Heuristic Determination of Minimum Cost Paths. IEEE Transactions on
  Systems Science and Cybernetics, 4(2), 100–107.
"""

from __future__ import annotations

import math
from typing import Callable

from .models import Node

# Type alias for a heuristic function taking (current_node, goal_node) -> float
HeuristicFn = Callable[[Node, Node], float]


def euclidean_distance(current: Node, goal: Node) -> float:
    """Compute the straight-line Euclidean distance between two nodes.

    Calculates:
        sqrt((x_goal - x_curr)^2 + (y_goal - y_curr)^2)

    Parameters
    ----------
    current:
        The current :class:`~emergency_intelligence.graph.models.Node`.
    goal:
        The target :class:`~emergency_intelligence.graph.models.Node`.

    Returns
    -------
    float
        The Euclidean distance between *current* and *goal*.

    Raises
    ------
    ValueError
        If either node does not have ``coordinates`` defined.
    """
    if current.coordinates is None:
        raise ValueError(
            f"Node {current.node_id!r} has no coordinates defined. "
            "Euclidean heuristic requires (x, y) coordinates on all evaluated nodes."
        )
    if goal.coordinates is None:
        raise ValueError(
            f"Goal node {goal.node_id!r} has no coordinates defined. "
            "Euclidean heuristic requires (x, y) coordinates on all evaluated nodes."
        )

    dx = goal.coordinates[0] - current.coordinates[0]
    dy = goal.coordinates[1] - current.coordinates[1]
    return math.hypot(dx, dy)


def manhattan_distance(current: Node, goal: Node) -> float:
    """Compute the Manhattan (L1 norm) distance between two nodes.

    Calculates:
        |x_goal - x_curr| + |y_goal - y_curr|

    Parameters
    ----------
    current:
        The current :class:`~emergency_intelligence.graph.models.Node`.
    goal:
        The target :class:`~emergency_intelligence.graph.models.Node`.

    Returns
    -------
    float
        The Manhattan distance between *current* and *goal*.

    Raises
    ------
    ValueError
        If either node does not have ``coordinates`` defined.
    """
    if current.coordinates is None:
        raise ValueError(
            f"Node {current.node_id!r} has no coordinates defined. "
            "Manhattan heuristic requires (x, y) coordinates on all evaluated nodes."
        )
    if goal.coordinates is None:
        raise ValueError(
            f"Goal node {goal.node_id!r} has no coordinates defined. "
            "Manhattan heuristic requires (x, y) coordinates on all evaluated nodes."
        )

    dx = abs(goal.coordinates[0] - current.coordinates[0])
    dy = abs(goal.coordinates[1] - current.coordinates[1])
    return float(dx + dy)


def zero_heuristic(current: Node, goal: Node) -> float:
    """Trivially admissible heuristic that always returns 0.0.

    When passed to A*, the search expands nodes in pure order of g(n),
    making A* equivalent in behavior and optimal cost to Dijkstra's algorithm.

    Parameters
    ----------
    current:
        The current node (unused).
    goal:
        The target node (unused).

    Returns
    -------
    float
        Always ``0.0``.
    """
    return 0.0
