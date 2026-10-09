"""
Spatial indexing, coordinate snapping, and orthogonal geometric projection.

Provides zero-dependency, sub-millisecond geographic querying:
- 2D Spatial Grid Indexing for road network nodes and edges
- Nearest-node search with expanding circular bounding bounds
- Orthogonal point-to-segment projection onto road links and polylines
- SnappedLocation representation for real-world GPS emergency call dispatch
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from emergency_intelligence.graph.models import Edge, Graph, Node
from .geo import haversine_distance


@dataclass
class SnappedLocation:
    """Represents an emergency incident coordinate snapped to the road network.

    Attributes
    ----------
    original_coordinates:
        The raw GPS incident coordinates ``(lon, lat)``.
    snapped_coordinates:
        The nearest point ``(lon, lat)`` lying directly on a navigable road segment.
    distance_to_road_m:
        Perpendicular offset distance from the raw GPS coordinate to the road in meters.
    nearest_node_id:
        Identifier of the closest topological intersection / node on the graph.
    nearest_edge:
        The specific road segment :class:`~emergency_intelligence.graph.models.Edge`
        onto which the coordinate was projected, if an edge was found.
    projection_factor:
        The fractional interpolation factor :math:`t \\in [0.0, 1.0]` along the segment.
    """

    original_coordinates: Tuple[float, float]
    snapped_coordinates: Tuple[float, float]
    distance_to_road_m: float
    nearest_node_id: str
    nearest_edge: Optional[Edge] = None
    projection_factor: float = 0.0


def project_point_to_segment(
    point: Tuple[float, float],
    seg_start: Tuple[float, float],
    seg_end: Tuple[float, float],
) -> Tuple[Tuple[float, float], float, float]:
    """Orthogonally project a 2D coordinate point onto a line segment.

    Parameters
    ----------
    point:
        Coordinates ``(lon, lat)`` of the query point :math:`P`.
    seg_start:
        Coordinates ``(lon, lat)`` of segment origin :math:`A`.
    seg_end:
        Coordinates ``(lon, lat)`` of segment destination :math:`B`.

    Returns
    -------
    Tuple[Tuple[float, float], float, float]
        A 3-tuple containing:
        - ``projected_point``: Coordinates ``(lon, lat)`` of projected point :math:`Q`.
        - ``distance_m``: Physical perpendicular distance from :math:`P` to :math:`Q` in meters.
        - ``t``: Fractional parameter along the segment :math:`t \\in [0.0, 1.0]`.
    """
    px, py = point
    ax, ay = seg_start
    bx, by = seg_end

    dx = bx - ax
    dy = by - ay
    seg_len_sq = dx * dx + dy * dy

    if seg_len_sq < 1e-12:
        # Segment start and end are virtually identical
        projected = (ax, ay)
        dist_m = haversine_distance(point, projected, unit="m")
        return projected, dist_m, 0.0

    # Vector dot product projection: t = ((P - A) . (B - A)) / |B - A|^2
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
    t_clamped = max(0.0, min(1.0, t))

    qx = ax + t_clamped * dx
    qy = ay + t_clamped * dy
    projected = (qx, qy)

    dist_m = haversine_distance(point, projected, unit="m")
    return projected, dist_m, t_clamped


class SpatialIndex:
    """A zero-dependency 2D Spatial Hash Grid index for sub-millisecond coordinate lookups.

    Partitions geographic space into grid buckets of size ``cell_size_deg``,
    enabling :math:`O(1)` average nearest-neighbor queries without external geospatial C-libraries.

    Parameters
    ----------
    graph:
        The :class:`~emergency_intelligence.graph.models.Graph` to index.
    cell_size_deg:
        Size of each spatial grid cell in degrees (default 0.005°, approximately 550 meters).
    """

    def __init__(self, graph: Graph, cell_size_deg: float = 0.005) -> None:
        if cell_size_deg <= 0.0:
            raise ValueError("cell_size_deg must be strictly positive.")

        self._graph = graph
        self._cell_size = float(cell_size_deg)
        self._grid: Dict[Tuple[int, int], List[str]] = {}
        self._node_coords: Dict[str, Tuple[float, float]] = {}
        self._incident_edges: Dict[str, List[Edge]] = {nid: [] for nid in self._graph.node_ids()}

        self._build_index()

    def _coord_to_cell(self, lon: float, lat: float) -> Tuple[int, int]:
        return (math.floor(lon / self._cell_size), math.floor(lat / self._cell_size))

    def _build_index(self) -> None:
        for nid in self._graph.node_ids():
            node = self._graph.get_node(nid)
            if node.coordinates is not None:
                coords = node.coordinates
                self._node_coords[nid] = coords
                cell = self._coord_to_cell(coords[0], coords[1])
                if cell not in self._grid:
                    self._grid[cell] = []
                self._grid[cell].append(nid)

        for u in self._graph.node_ids():
            for edge in self._graph.get_neighbors(u):
                if edge.source_id in self._incident_edges:
                    self._incident_edges[edge.source_id].append(edge)
                if edge.destination_id in self._incident_edges:
                    self._incident_edges[edge.destination_id].append(edge)

    @property
    def indexed_nodes_count(self) -> int:
        """Return the number of nodes indexed with valid coordinates."""
        return len(self._node_coords)

    def nearest_node(
        self,
        query_coordinates: Tuple[float, float],
        max_search_radius_m: float = 50000.0,
    ) -> Tuple[str, float]:
        """Find the nearest indexed node to *query_coordinates*.

        Parameters
        ----------
        query_coordinates:
            Target GPS location ``(lon, lat)``.
        max_search_radius_m:
            Maximum distance threshold in meters to search before failing.

        Returns
        -------
        Tuple[str, float]
            A tuple of ``(nearest_node_id, distance_meters)``.

        Raises
        ------
        ValueError
            If the index is empty or no node is found within *max_search_radius_m*.
        """
        if not self._node_coords:
            raise ValueError("Cannot query an empty spatial index (no nodes with coordinates).")

        qx, qy = query_coordinates
        start_cell = self._coord_to_cell(qx, qy)

        best_node: Optional[str] = None
        best_dist: float = float("inf")

        # Expanding ring search
        ring = 0
        max_rings = max(5, int((max_search_radius_m / 111000.0) / self._cell_size) + 2)

        while ring <= max_rings:
            cells_to_check: List[Tuple[int, int]] = []
            if ring == 0:
                cells_to_check.append(start_cell)
            else:
                cx, cy = start_cell
                for dx in range(-ring, ring + 1):
                    for dy in range(-ring, ring + 1):
                        if abs(dx) == ring or abs(dy) == ring:
                            cells_to_check.append((cx + dx, cy + dy))

            for cell in cells_to_check:
                if cell in self._grid:
                    for nid in self._grid[cell]:
                        dist = haversine_distance(query_coordinates, self._node_coords[nid], unit="m")
                        if dist < best_dist:
                            best_dist = dist
                            best_node = nid

            ring_inner_dist_m = (ring * self._cell_size) * 111000.0 * 0.7
            if best_node is not None and ring_inner_dist_m > best_dist:
                break

            ring += 1

        if best_node is None or best_dist > max_search_radius_m:
            raise ValueError(
                f"No road node found within {max_search_radius_m:.1f} meters of {query_coordinates}."
            )

        return best_node, best_dist

    def snap_to_road_network(
        self,
        query_coordinates: Tuple[float, float],
        max_search_radius_m: float = 5000.0,
    ) -> SnappedLocation:
        """Snap an arbitrary incident GPS coordinate onto the nearest navigable road segment.

        Evaluates road segment geometries and intermediate polylines incident to
        nearby intersections, returning the exact perpendicular projection point.

        Parameters
        ----------
        query_coordinates:
            GPS coordinate ``(lon, lat)`` from 911 dispatch or vehicle telemetry.
        max_search_radius_m:
            Maximum distance search radius in meters.

        Returns
        -------
        SnappedLocation
            The projection result detailing snapped coordinates, road offset, and nearest node.
        """
        nearest_node_id, dist_to_nearest_node = self.nearest_node(
            query_coordinates,
            max_search_radius_m=max_search_radius_m,
        )

        candidate_edges: List[Edge] = list(self._incident_edges.get(nearest_node_id, []))
        for edge in self._graph.get_neighbors(nearest_node_id):
            candidate_edges.extend(self._incident_edges.get(edge.destination_id, []))

        seen_edges: Set[Tuple[str, str]] = set()
        unique_candidate_edges: List[Edge] = []
        for e in candidate_edges:
            pair = (e.source_id, e.destination_id)
            if pair not in seen_edges:
                seen_edges.add(pair)
                unique_candidate_edges.append(e)

        best_snapped: Tuple[float, float] = self._node_coords[nearest_node_id]
        best_dist: float = dist_to_nearest_node
        best_edge: Optional[Edge] = None
        best_t: float = 0.0

        for edge in unique_candidate_edges:
            u = edge.source_id
            v = edge.destination_id
            if u not in self._node_coords or v not in self._node_coords:
                continue

            geom: List[Tuple[float, float]] = edge.attributes.get("geometry", [])
            if not geom or len(geom) < 2:
                geom = [self._node_coords[u], self._node_coords[v]]

            for i in range(len(geom) - 1):
                p_proj, p_dist, t_val = project_point_to_segment(
                    query_coordinates,
                    geom[i],
                    geom[i + 1],
                )
                if p_dist < best_dist:
                    best_dist = p_dist
                    best_snapped = p_proj
                    best_edge = edge
                    best_t = t_val

        return SnappedLocation(
            original_coordinates=query_coordinates,
            snapped_coordinates=best_snapped,
            distance_to_road_m=best_dist,
            nearest_node_id=nearest_node_id,
            nearest_edge=best_edge,
            projection_factor=best_t,
        )
