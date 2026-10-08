"""
Graph sub-package.

Exposes the road-graph data model, routing algorithms (Dijkstra, A*),
distance heuristics, and comparative benchmarking tools used by the
Emergency Intelligence AI routing engine.
"""

from .astar import astar
from .benchmark import (
    BenchmarkComparison,
    compare_algorithms,
    create_grid_network,
)
from .dijkstra import RouteResult, dijkstra
from .heuristics import (
    HeuristicFn,
    euclidean_distance,
    manhattan_distance,
    zero_heuristic,
)
from .models import Edge, Graph, Node

__all__ = [
    # Data model
    "Node",
    "Edge",
    "Graph",
    "RouteResult",
    # Algorithms
    "dijkstra",
    "astar",
    # Heuristics
    "HeuristicFn",
    "euclidean_distance",
    "manhattan_distance",
    "zero_heuristic",
    # Benchmarking
    "BenchmarkComparison",
    "compare_algorithms",
    "create_grid_network",
]
