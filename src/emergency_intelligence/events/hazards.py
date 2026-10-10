"""
Spatial hazard polygons and vector geometric intersection engine.

Provides zero-dependency geometric algorithms for disaster events:
- Ray-casting point-in-polygon containment (Jordan Curve theorem)
- 2D orientation cross-product segment intersection
- Spatial boundary edge clipping for road network segment impact
- Hazard severity tiers and dynamic speed penalty calculation
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from emergency_intelligence.graph.models import Edge, Graph


class HazardType(str, Enum):
    """Categorization of physical environmental hazards and disaster zones."""

    FLOOD_INUNDATION = "flood_inundation"
    FLASH_FLOOD = "flash_flood"
    WILDFIRE_PERIMETER = "wildfire_perimeter"
    TOXIC_GAS_PLUME = "toxic_gas_plume"
    STRUCTURAL_DEBRIS = "structural_debris"
    ROAD_COLLAPSE = "road_collapse"
    CIVIL_UNREST = "civil_unrest"


class HazardSeverity(str, Enum):
    """Severity classification determining travel accessibility and speed penalties."""

    LOW = "low"                        # Caution: minor slowdown (speed factor ~0.75)
    MODERATE = "moderate"              # Warning: heavy slowdown (speed factor ~0.50)
    SEVERE = "severe"                  # Danger: extreme slowdown (speed factor ~0.20)
    CRITICAL_BLOCKED = "critical_blocked"  # Impassable: edge severed / infinite cost


DEFAULT_SEVERITY_SPEED_MULTIPLIERS: Dict[HazardSeverity, float] = {
    HazardSeverity.LOW: 0.75,
    HazardSeverity.MODERATE: 0.50,
    HazardSeverity.SEVERE: 0.20,
    HazardSeverity.CRITICAL_BLOCKED: 0.0,
}


# ---------------------------------------------------------------------------
# Pure-Python 2D Vector Geometry Routines
# ---------------------------------------------------------------------------


def _orientation(p: Tuple[float, float], q: Tuple[float, float], r: Tuple[float, float]) -> int:
    """Finds the orientation of an ordered triplet (p, q, r).

    Returns:
         0 -> Collinear
         1 -> Clockwise
         2 -> Counterclockwise
    """
    val = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
    if abs(val) < 1e-12:
        return 0
    return 1 if val > 0 else 2


def _on_segment(p: Tuple[float, float], q: Tuple[float, float], r: Tuple[float, float]) -> bool:
    """Checks if point q lies on line segment pr (assuming p, q, r are collinear)."""
    return (
        min(p[0], r[0]) - 1e-12 <= q[0] <= max(p[0], r[0]) + 1e-12
        and min(p[1], r[1]) - 1e-12 <= q[1] <= max(p[1], r[1]) + 1e-12
    )


def segments_intersect(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    p3: Tuple[float, float],
    p4: Tuple[float, float],
) -> bool:
    """Returns True if segment p1-p2 intersects segment p3-p4.

    Uses 2D orientation cross-products with robust floating-point epsilon handling.
    """
    o1 = _orientation(p1, p2, p3)
    o2 = _orientation(p1, p2, p4)
    o3 = _orientation(p3, p4, p1)
    o4 = _orientation(p3, p4, p2)

    # General case: segments cross each other
    if o1 != o2 and o3 != o4:
        return True

    # Special collinear cases
    if o1 == 0 and _on_segment(p1, p3, p2):
        return True
    if o2 == 0 and _on_segment(p1, p4, p2):
        return True
    if o3 == 0 and _on_segment(p3, p1, p4):
        return True
    if o4 == 0 and _on_segment(p3, p2, p4):
        return True

    return False


def point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    """Determines whether point (lon, lat) lies inside a polygon using ray-casting.

    Implements the Jordan Curve Theorem (Even-Odd Rule). Points directly on the
    polygon boundary or vertices are considered inside.

    Args:
        point: (lon, lat) query coordinate.
        polygon: Ordered list of (lon, lat) vertices representing the polygon.

    Returns:
        True if the point is inside or on the boundary of the polygon.
    """
    n = len(polygon)
    if n < 3:
        return False

    x, y = point[0], point[1]

    # Check if point lies directly on any polygon vertex or edge first
    for i in range(n):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n]
        if abs(p1[0] - x) < 1e-9 and abs(p1[1] - y) < 1e-9:
            return True
        if _orientation(p1, (x, y), p2) == 0 and _on_segment(p1, (x, y), p2):
            return True

    inside = False
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]
        if min(p1y, p2y) < y <= max(p1y, p2y):
            if x <= max(p1x, p2x):
                # Calculate X-intersection of the horizontal ray with the edge
                if p1y != p2y:
                    x_inters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= x_inters:
                        inside = not inside
        p1x, p1y = p2x, p2y

    return inside


def segment_intersects_polygon(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    polygon: List[Tuple[float, float]],
) -> bool:
    """Determines if line segment p1-p2 penetrates, touches, or lies within polygon.

    A segment intersects the polygon if:
    1. Either endpoint is strictly inside the polygon, OR
    2. The segment crosses any boundary edge of the polygon.
    """
    if len(polygon) < 3:
        return False

    # Condition 1: Check if either endpoint lies inside or on the boundary
    if point_in_polygon(p1, polygon) or point_in_polygon(p2, polygon):
        return True

    # Condition 2: Check if segment crosses any polygon edge
    n = len(polygon)
    for i in range(n):
        v1 = polygon[i]
        v2 = polygon[(i + 1) % n]
        if segments_intersect(p1, p2, v1, v2):
            return True

    return False


# ---------------------------------------------------------------------------
# Hazard Polygon Entity
# ---------------------------------------------------------------------------


@dataclass
class HazardPolygon:
    """Represents a geographic disaster hazard zone (flood, fire, gas cloud).

    Attributes:
        hazard_id: Unique identifier for this hazard instance.
        hazard_type: Type of environmental hazard.
        severity: Severity level (from LOW to CRITICAL_BLOCKED).
        boundary_coordinates: Ordered list of (lon, lat) vertices.
        speed_multiplier: Dynamic speed scaling factor (0.0 = severed/blocked, 1.0 = normal).
        description: Human-readable alert summary or description.
        created_at: Timestamp when hazard was reported.
        expires_at: Optional timestamp when hazard expires / clears.
        active: Boolean flag indicating if hazard is currently active.
        metadata: Additional metadata (e.g. water depth in meters, fire spread rate).
    """

    hazard_id: str
    hazard_type: HazardType
    severity: HazardSeverity
    boundary_coordinates: List[Tuple[float, float]]
    speed_multiplier: Optional[float] = None
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.hazard_id or not isinstance(self.hazard_id, str):
            raise ValueError("HazardPolygon.hazard_id must be a non-empty string.")

        if not isinstance(self.hazard_type, HazardType):
            if isinstance(self.hazard_type, str):
                self.hazard_type = HazardType(self.hazard_type)
            else:
                raise TypeError("HazardPolygon.hazard_type must be a HazardType enum.")

        if not isinstance(self.severity, HazardSeverity):
            if isinstance(self.severity, str):
                self.severity = HazardSeverity(self.severity)
            else:
                raise TypeError("HazardPolygon.severity must be a HazardSeverity enum.")

        if not isinstance(self.boundary_coordinates, (list, tuple)) or len(self.boundary_coordinates) < 3:
            raise ValueError("HazardPolygon.boundary_coordinates must contain at least 3 vertices.")

        sanitized_coords: List[Tuple[float, float]] = []
        for vertex in self.boundary_coordinates:
            if not isinstance(vertex, (list, tuple)) or len(vertex) != 2:
                raise ValueError(f"Invalid coordinate vertex: {vertex}")
            lon, lat = float(vertex[0]), float(vertex[1])
            if not (-180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0):
                raise ValueError(f"Vertex ({lon}, {lat}) out of WGS 84 coordinate bounds.")
            sanitized_coords.append((lon, lat))

        # Close polygon if last vertex != first vertex
        if sanitized_coords[0] == sanitized_coords[-1] and len(sanitized_coords) > 3:
            sanitized_coords.pop()  # Internal representation uses unrepeated vertex ring

        self.boundary_coordinates = sanitized_coords

        # Default speed multiplier based on severity if unspecified
        if self.speed_multiplier is None:
            self.speed_multiplier = DEFAULT_SEVERITY_SPEED_MULTIPLIERS.get(self.severity, 0.0)
        else:
            self.speed_multiplier = float(self.speed_multiplier)
            if self.speed_multiplier < 0.0 or self.speed_multiplier > 1.0:
                raise ValueError("HazardPolygon.speed_multiplier must be between 0.0 and 1.0.")

    def bounding_box(self) -> Tuple[float, float, float, float]:
        """Returns the envelope (min_lon, min_lat, max_lon, max_lat) for fast rejection."""
        lons = [pt[0] for pt in self.boundary_coordinates]
        lats = [pt[1] for pt in self.boundary_coordinates]
        return (min(lons), min(lats), max(lons), max(lats))

    def contains_point(self, lon: float, lat: float) -> bool:
        """Evaluates whether (lon, lat) falls within this hazard perimeter."""
        if not self.active:
            return False
        # Fast bounding box test
        min_lon, min_lat, max_lon, max_lat = self.bounding_box()
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            return False
        return point_in_polygon((lon, lat), self.boundary_coordinates)

    def intersects_segment(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> bool:
        """Evaluates whether line segment p1-p2 penetrates this hazard perimeter."""
        if not self.active:
            return False
        # Fast bounding box test
        min_lon, min_lat, max_lon, max_lat = self.bounding_box()
        seg_min_lon = min(p1[0], p2[0])
        seg_max_lon = max(p1[0], p2[0])
        seg_min_lat = min(p1[1], p2[1])
        seg_max_lat = max(p1[1], p2[1])

        # Bounding boxes do not overlap -> cannot intersect
        if (
            seg_max_lon < min_lon
            or seg_min_lon > max_lon
            or seg_max_lat < min_lat
            or seg_min_lat > max_lat
        ):
            return False

        return segment_intersects_polygon(p1, p2, self.boundary_coordinates)

    def is_blocking(self) -> bool:
        """Returns True if this hazard completely blocks vehicular traversal."""
        return self.active and (
            self.severity == HazardSeverity.CRITICAL_BLOCKED or self.speed_multiplier == 0.0
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the hazard polygon to a JSON-compatible dictionary."""
        # Output closed ring format for GeoJSON compatibility
        closed_ring = list(self.boundary_coordinates)
        if closed_ring and closed_ring[0] != closed_ring[-1]:
            closed_ring.append(closed_ring[0])

        return {
            "hazard_id": self.hazard_id,
            "hazard_type": self.hazard_type.value,
            "severity": self.severity.value,
            "boundary_coordinates": [[p[0], p[1]] for p in closed_ring],
            "speed_multiplier": self.speed_multiplier,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "active": self.active,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> HazardPolygon:
        """Constructs a HazardPolygon from a dictionary."""
        created_at_val = data.get("created_at")
        if isinstance(created_at_val, str):
            c_at = datetime.fromisoformat(created_at_val)
        elif isinstance(created_at_val, datetime):
            c_at = created_at_val
        else:
            c_at = datetime.now(timezone.utc)

        expires_at_val = data.get("expires_at")
        e_at = datetime.fromisoformat(expires_at_val) if isinstance(expires_at_val, str) else None

        coords = [(float(pt[0]), float(pt[1])) for pt in data["boundary_coordinates"]]

        return cls(
            hazard_id=str(data["hazard_id"]),
            hazard_type=HazardType(data["hazard_type"]),
            severity=HazardSeverity(data["severity"]),
            boundary_coordinates=coords,
            speed_multiplier=data.get("speed_multiplier"),
            description=str(data.get("description", "")),
            created_at=c_at,
            expires_at=e_at,
            active=bool(data.get("active", True)),
            metadata=dict(data.get("metadata", {})),
        )

    def to_geojson_feature(self) -> Dict[str, Any]:
        """Converts hazard polygon into an RFC 7946 GeoJSON Polygon Feature."""
        closed_ring = [[p[0], p[1]] for p in self.boundary_coordinates]
        if closed_ring and closed_ring[0] != closed_ring[-1]:
            closed_ring.append(closed_ring[0])

        return {
            "type": "Feature",
            "id": self.hazard_id,
            "geometry": {
                "type": "Polygon",
                "coordinates": [closed_ring],
            },
            "properties": {
                "hazard_id": self.hazard_id,
                "hazard_type": self.hazard_type.value,
                "severity": self.severity.value,
                "speed_multiplier": self.speed_multiplier,
                "description": self.description,
                "active": self.active,
                **self.metadata,
            },
        }


# ---------------------------------------------------------------------------
# Road Network Intersection Query Functions
# ---------------------------------------------------------------------------


def find_edges_intersecting_hazard(
    graph: Graph,
    hazard: HazardPolygon,
) -> List[Edge]:
    """Finds all road network edges intersecting or enclosed within an active hazard polygon.

    Evaluates both endpoint coordinates and any intermediate geometry polyline coordinates
    associated with contracted corridor edges.

    Args:
        graph: Road network graph containing nodes and edges.
        hazard: HazardPolygon zone to query against.

    Returns:
        List of directed Edge objects intersecting the hazard polygon.
    """
    if not hazard.active:
        return []

    intersecting_edges: List[Edge] = []

    for source_id in graph.node_ids():
        src_node = graph.get_node(source_id)
        if not src_node or src_node.lon is None or src_node.lat is None:
            continue

        p_src = (src_node.lon, src_node.lat)

        for edge in graph.get_neighbors(source_id):
            dst_node = graph.get_node(edge.destination_id)
            if not dst_node or dst_node.lon is None or dst_node.lat is None:
                continue

            p_dst = (dst_node.lon, dst_node.lat)

            # Check if edge has full polyline geometry (e.g. from degree-2 contraction)
            geom = edge.attributes.get("geometry")
            if geom and isinstance(geom, list) and len(geom) >= 2:
                # Check each sub-segment of the polyline
                hit = False
                for i in range(len(geom) - 1):
                    seg_p1 = (float(geom[i][0]), float(geom[i][1]))
                    seg_p2 = (float(geom[i + 1][0]), float(geom[i + 1][1]))
                    if hazard.intersects_segment(seg_p1, seg_p2):
                        hit = True
                        break
                if hit:
                    intersecting_edges.append(edge)
            else:
                # Direct straight-line segment between src and dst
                if hazard.intersects_segment(p_src, p_dst):
                    intersecting_edges.append(edge)

    return intersecting_edges


def find_hazards_affecting_edge(
    hazards: List[HazardPolygon],
    edge: Edge,
    graph: Graph,
) -> List[HazardPolygon]:
    """Returns all active hazards that intersect or encompass a specific directed edge."""
    src_node = graph.get_node(edge.source_id)
    dst_node = graph.get_node(edge.destination_id)
    if not src_node or not dst_node or src_node.lon is None or dst_node.lon is None:
        return []

    p_src = (src_node.lon, src_node.lat)
    p_dst = (dst_node.lon, dst_node.lat)

    affecting: List[HazardPolygon] = []
    geom = edge.attributes.get("geometry")

    for h in hazards:
        if not h.active:
            continue

        if geom and isinstance(geom, list) and len(geom) >= 2:
            hit = False
            for i in range(len(geom) - 1):
                seg_p1 = (float(geom[i][0]), float(geom[i][1]))
                seg_p2 = (float(geom[i + 1][0]), float(geom[i + 1][1]))
                if h.intersects_segment(seg_p1, seg_p2):
                    hit = True
                    break
            if hit:
                affecting.append(h)
        else:
            if h.intersects_segment(p_src, p_dst):
                affecting.append(h)

    return affecting


def compute_effective_edge_cost(
    base_cost: float,
    affecting_hazards: List[HazardPolygon],
) -> float:
    """Computes the penalized traversal cost of an edge under active disaster hazards.

    Rules:
    1. If any hazard is blocking (severity CRITICAL_BLOCKED or speed_multiplier == 0.0),
       returns math.inf (impassable road).
    2. Otherwise, divides base_cost by the most restrictive (lowest) speed multiplier:
       effective_cost = base_cost / min(speed_multipliers).
    """
    if not affecting_hazards:
        return base_cost

    min_multiplier = 1.0
    for h in affecting_hazards:
        if not h.active:
            continue
        if h.is_blocking():
            return math.inf
        if h.speed_multiplier is not None and h.speed_multiplier < min_multiplier:
            min_multiplier = h.speed_multiplier

    if min_multiplier <= 0.0:
        return math.inf

    return base_cost / min_multiplier
