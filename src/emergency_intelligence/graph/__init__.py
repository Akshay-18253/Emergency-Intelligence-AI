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
from .topology import (
    calculate_bearing,
    calculate_turn_angle,
    classify_turn_maneuver,
    contract_degree2_nodes,
    extract_largest_strongly_connected_component,
    tarjan_scc,
)

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
    # Topology and Contraction
    "tarjan_scc",
    "extract_largest_strongly_connected_component",
    "contract_degree2_nodes",
    "calculate_bearing",
    "calculate_turn_angle",
    "classify_turn_maneuver",
]
