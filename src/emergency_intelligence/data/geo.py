"""
Geographic calculation utilities.

Provides spherical distance calculations using the Haversine formula
and admissible geographic heuristics for the routing engine.

Formulas
--------
The Haversine formula determines the great-circle distance between two
points on a sphere given their longitudes and latitudes:

    a = sin²(Δφ/2) + cos(φ₁) ⋅ cos(φ₂) ⋅ sin²(Δλ/2)
    c = 2 ⋅ atan2(√a, √(1−a))
    d = R ⋅ c

Where φ is latitude, λ is longitude, and R is Earth's mean radius (6,371,000 m).

Optimality & Admissibility
--------------------------
Because the great-circle distance represents the theoretical shortest path
between two points on Earth's surface, any actual physical road traversing
the terrain must have length >= Haversine distance. Therefore, Haversine
distance is a provably admissible and consistent heuristic for spatial
routing algorithms (A*).
"""

from __future__ import annotations

import math
from typing import Tuple

from emergency_intelligence.graph.models import Node

# Mean radius of Earth in meters (IUGG standard value)
EARTH_RADIUS_METERS: float = 6_371_000.0


def haversine_distance(
    coord1: Tuple[float, float],
    coord2: Tuple[float, float],
    unit: str = "m",
) -> float:
    """Calculate the great-circle distance between two geographic coordinates.

    Coordinates must be provided as ``(longitude, latitude)`` in decimal degrees,
    matching GIS and GeoJSON conventions (x = lon, y = lat).

    Parameters
    ----------
    coord1:
        ``(lon, lat)`` tuple for the origin point.
    coord2:
        ``(lon, lat)`` tuple for the destination point.
    unit:
        Distance unit: ``"m"`` (meters, default) or ``"km"`` (kilometers).

    Returns
    -------
    float
        The distance between the two points in the requested unit.

    Raises
    ------
    ValueError
        If an unsupported unit is specified.
    """
    if unit not in ("m", "km"):
        raise ValueError(f"Unsupported unit {unit!r}. Choose 'm' or 'km'.")

    lon1, lat1 = coord1
    lon2, lat2 = coord2

    # Convert degrees to radians
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    # Haversine formula
    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    # Clamp to handle potential floating point precision errors near antipodes
    a = min(1.0, max(0.0, a))
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    distance_m = EARTH_RADIUS_METERS * c

    if unit == "km":
        return distance_m / 1000.0
    return distance_m


def haversine_heuristic(current: Node, goal: Node) -> float:
    """Admissible A* heuristic function using Haversine distance in meters.

    Compatible with :data:`~emergency_intelligence.graph.heuristics.HeuristicFn`.

    Parameters
    ----------
    current:
        The current :class:`~emergency_intelligence.graph.models.Node`.
    goal:
        The destination :class:`~emergency_intelligence.graph.models.Node`.

    Returns
    -------
    float
        Great-circle distance in meters between *current* and *goal*.

    Raises
    ------
    ValueError
        If either node lacks defined coordinates.
    """
    if current.coordinates is None:
        raise ValueError(
            f"Node {current.node_id!r} has no coordinates defined for Haversine heuristic."
        )
    if goal.coordinates is None:
        raise ValueError(
            f"Goal node {goal.node_id!r} has no coordinates defined for Haversine heuristic."
        )

    return haversine_distance(current.coordinates, goal.coordinates, unit="m")
