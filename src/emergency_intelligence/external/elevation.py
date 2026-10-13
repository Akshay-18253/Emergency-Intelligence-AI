"""
Topographic Digital Elevation Models (DEM) & Slope Cost Weighting.
==================================================================
Provides pure-Python standard-library ingestion of NASA SRTM binary elevation
tiles (.hgt), bilinear sub-grid spatial interpolation, 3D incline grade
computation, apparatus-specific climb/descent speed penalty modeling, and
dynamic elevation-aware routing graph views.

NASA SRTM Specification
-----------------------
- SRTM1: 1 arc-second grid (3601 x 3601 signed 16-bit big-endian integers, ~25.9 MB)
- SRTM3: 3 arc-second grid (1201 x 1201 signed 16-bit big-endian integers, ~2.88 MB)
- Binary format: Big-endian 16-bit signed integer ('>h') per grid sample point.
- Void / Missing data value: -32768 (or any sample < -1000m or > 9000m).
- Row ordering: North to South (Row 0 = lat_origin + 1.0, Row N-1 = lat_origin).
- Col ordering: West to East (Col 0 = lon_origin, Col N-1 = lon_origin + 1.0).

Strict zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from pathlib import Path
import re
import struct
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from emergency_intelligence.data.geo import haversine_distance
from emergency_intelligence.events.incidents import ApparatusType
from emergency_intelligence.graph.models import Edge, Graph, Node

# Standard SRTM invalid / void elevation sentinel
SRTM_VOID_VALUE: int = -32768
MIN_TERRESTRIAL_ELEVATION_M: float = -500.0  # Dead Sea lowest point is ~-430m
MAX_TERRESTRIAL_ELEVATION_M: float = 9000.0  # Mt Everest peak is ~8848m


class DEMResolution(Enum):
    """Standard NASA SRTM grid dimensions."""

    SRTM1 = 3601  # 1 arc-second (~30m resolution)
    SRTM3 = 1201  # 3 arc-second (~90m resolution)
    CUSTOM = -1


def parse_srtm_tile_name(tile_name: str) -> Tuple[int, int]:
    """Extract southwest coordinate origin (lat_origin, lon_origin) from an SRTM tile name.

    Standard naming:
        - 'N37W123.hgt' -> (37, -123)
        - 'S12E045.hgt' -> (-12, 45)

    Parameters
    ----------
    tile_name : str
        Filename or base name of the SRTM tile.

    Returns
    -------
    Tuple[int, int]
        (lat_origin, lon_origin) in integer degrees.

    Raises
    ------
    ValueError
        If the tile name does not match the NASA SRTM specification.
    """
    clean_name = Path(tile_name).name.strip()
    match = re.match(
        r"^([NSns])(\d{2})([EWew])(\d{3})(?:\.hgt)?$", clean_name
    )
    if not match:
        raise ValueError(
            f"Invalid SRTM tile filename {tile_name!r}. Expected format '[N|S]yy[E|W]xxx.hgt'."
        )

    lat_hemi, lat_str, lon_hemi, lon_str = match.groups()
    lat = int(lat_str)
    lon = int(lon_str)

    if lat_hemi.upper() == "S":
        lat = -lat
    if lon_hemi.upper() == "W":
        lon = -lon

    if not (-90 <= lat <= 90):
        raise ValueError(f"SRTM latitude {lat} out of valid range [-90, 90].")
    if not (-180 <= lon <= 180):
        raise ValueError(f"SRTM longitude {lon} out of valid range [-180, 180].")

    return lat, lon


def format_srtm_tile_name(lat_origin: int, lon_origin: int) -> str:
    """Format southwest coordinate origin into canonical SRTM tile name.

    Parameters
    ----------
    lat_origin : int
        Southwest corner latitude [-90, 90].
    lon_origin : int
        Southwest corner longitude [-180, 180].

    Returns
    -------
    str
        Canonical filename (e.g., 'N37W123.hgt').
    """
    lat_prefix = "N" if lat_origin >= 0 else "S"
    lon_prefix = "E" if lon_origin >= 0 else "W"
    abs_lat = abs(int(lat_origin))
    abs_lon = abs(int(lon_origin))
    return f"{lat_prefix}{abs_lat:02d}{lon_prefix}{abs_lon:03d}.hgt"


@dataclass
class SRTMTile:
    """Represents a 1x1 degree NASA SRTM digital elevation grid.

    Supports efficient on-demand byte extraction and sub-grid bilinear interpolation.
    """

    tile_name: str
    lat_origin: int
    lon_origin: int
    dimension: int
    _buffer: Optional[bytes] = None
    _samples: Optional[Tuple[int, ...]] = None

    def __post_init__(self) -> None:
        if self.dimension < 2:
            raise ValueError(
                f"SRTMTile dimension must be at least 2, got {self.dimension}."
            )
        if self._buffer is None and self._samples is None:
            raise ValueError("SRTMTile must have either _buffer or _samples provided.")
        if self._buffer is not None:
            expected_bytes = self.dimension * self.dimension * 2
            if len(self._buffer) != expected_bytes:
                raise ValueError(
                    f"Buffer size {len(self._buffer)} bytes does not match expected "
                    f"{expected_bytes} bytes for dimension {self.dimension}x{self.dimension}."
                )
        if self._samples is not None:
            expected_samples = self.dimension * self.dimension
            if len(self._samples) != expected_samples:
                raise ValueError(
                    f"Sample count {len(self._samples)} does not match expected "
                    f"{expected_samples} for dimension {self.dimension}x{self.dimension}."
                )

    @classmethod
    def from_file(cls, filepath: Union[str, Path]) -> SRTMTile:
        """Load an SRTM tile directly from a .hgt file on disk."""
        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"SRTM tile file not found: {filepath}")

        lat_orig, lon_orig = parse_srtm_tile_name(path.name)
        data = path.read_bytes()
        file_size = len(data)

        # Detect resolution by file size
        if file_size == 3601 * 3601 * 2:
            dimension = 3601
        elif file_size == 1201 * 1201 * 2:
            dimension = 1201
        else:
            # Check if square 16-bit integer
            sample_count = file_size // 2
            root = int(math.isqrt(sample_count))
            if root * root == sample_count and file_size % 2 == 0:
                dimension = root
            else:
                raise ValueError(
                    f"Unrecognized SRTM file size {file_size} bytes for {path.name}."
                )

        return cls(
            tile_name=path.name,
            lat_origin=lat_orig,
            lon_origin=lon_orig,
            dimension=dimension,
            _buffer=data,
        )

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        tile_name: str,
        dimension: Optional[int] = None,
    ) -> SRTMTile:
        """Instantiate an SRTM tile from an in-memory binary byte buffer."""
        lat_orig, lon_orig = parse_srtm_tile_name(tile_name)
        file_size = len(data)

        if dimension is None:
            if file_size == 3601 * 3601 * 2:
                dimension = 3601
            elif file_size == 1201 * 1201 * 2:
                dimension = 1201
            else:
                sample_count = file_size // 2
                root = int(math.isqrt(sample_count))
                if root * root == sample_count and file_size % 2 == 0:
                    dimension = root
                else:
                    raise ValueError(
                        f"Cannot deduce dimension for buffer of {file_size} bytes."
                    )

        return cls(
            tile_name=tile_name,
            lat_origin=lat_orig,
            lon_origin=lon_orig,
            dimension=dimension,
            _buffer=data,
        )

    @classmethod
    def from_samples(
        cls,
        samples: Sequence[int],
        lat_origin: int,
        lon_origin: int,
        dimension: int,
        tile_name: Optional[str] = None,
    ) -> SRTMTile:
        """Instantiate an SRTM tile from an in-memory sequence of integer elevation values."""
        name = tile_name or format_srtm_tile_name(lat_origin, lon_origin)
        return cls(
            tile_name=name,
            lat_origin=lat_origin,
            lon_origin=lon_origin,
            dimension=dimension,
            _samples=tuple(int(s) for s in samples),
        )

    def get_sample(self, row: int, col: int) -> int:
        """Retrieve the raw elevation sample at grid position (row, col)."""
        if not (0 <= row < self.dimension and 0 <= col < self.dimension):
            raise IndexError(
                f"Grid coordinates ({row}, {col}) out of bounds for dimension {self.dimension}."
            )

        if self._buffer is not None:
            offset = (row * self.dimension + col) * 2
            return struct.unpack_from(">h", self._buffer, offset)[0]
        elif self._samples is not None:
            return self._samples[row * self.dimension + col]
        raise RuntimeError("SRTMTile has no buffer or samples available.")

    def contains(self, lat: float, lon: float) -> bool:
        """Check if geographic coordinate (lat, lon) lies within this tile's bounds."""
        lat_max = self.lat_origin + 1.0
        lon_max = self.lon_origin + 1.0
        return (
            self.lat_origin <= lat <= lat_max
            and self.lon_origin <= lon <= lon_max
        )

    def get_elevation(
        self,
        lat: float,
        lon: float,
        interpolate: bool = True,
    ) -> Optional[float]:
        """Query elevation in meters at geographic position (lat, lon).

        Parameters
        ----------
        lat : float
            Latitude in decimal degrees.
        lon : float
            Longitude in decimal degrees.
        interpolate : bool
            If True (default), performs bilinear sub-grid interpolation.
            If False, returns nearest sampled grid cell.

        Returns
        -------
        Optional[float]
            Elevation in meters above sea level, or None if outside tile or void.
        """
        if not self.contains(lat, lon):
            return None

        # SRTM Grid Coordinate Mapping
        # Row 0 is at northern boundary (lat_origin + 1.0)
        # Row N-1 is at southern boundary (lat_origin)
        # Col 0 is at western boundary (lon_origin)
        # Col N-1 is at eastern boundary (lon_origin + 1.0)
        max_idx = self.dimension - 1

        row_float = (self.lat_origin + 1.0 - lat) * max_idx
        col_float = (lon - self.lon_origin) * max_idx

        # Clamp to bounds to protect float precision edge cases
        row_float = max(0.0, min(float(max_idx), row_float))
        col_float = max(0.0, min(float(max_idx), col_float))

        if not interpolate:
            nearest_row = int(round(row_float))
            nearest_col = int(round(col_float))
            val = self.get_sample(nearest_row, nearest_col)
            if self._is_valid_elevation(val):
                return float(val)
            return None

        # Bilinear Sub-Grid Interpolation
        r0 = int(math.floor(row_float))
        c0 = int(math.floor(col_float))
        r1 = min(max_idx, r0 + 1)
        c1 = min(max_idx, c0 + 1)

        dr = row_float - r0
        dc = col_float - c0

        # Read 4 surrounding corner vertices
        z00 = self.get_sample(r0, c0)
        z01 = self.get_sample(r0, c1)
        z10 = self.get_sample(r1, c0)
        z11 = self.get_sample(r1, c1)

        # Bilinear weights
        corners = [
            (z00, (1.0 - dr) * (1.0 - dc)),
            (z01, (1.0 - dr) * dc),
            (z10, dr * (1.0 - dc)),
            (z11, dr * dc),
        ]

        valid_weighted_sum = 0.0
        total_valid_weight = 0.0

        for val, weight in corners:
            if self._is_valid_elevation(val):
                valid_weighted_sum += float(val) * weight
                total_valid_weight += weight

        if total_valid_weight <= 0.0:
            return None

        # Normalize across valid samples to bridge isolated void points
        return valid_weighted_sum / total_valid_weight

    @staticmethod
    def _is_valid_elevation(val: int) -> bool:
        """Determines whether a raw elevation integer is physically valid."""
        return (
            val != SRTM_VOID_VALUE
            and MIN_TERRESTRIAL_ELEVATION_M <= val <= MAX_TERRESTRIAL_ELEVATION_M
        )


def build_synthetic_dem_tile(
    lat_origin: int,
    lon_origin: int,
    dimension: int = 11,
    elevation_fn: Optional[Callable[[float, float], float]] = None,
    base_elevation: float = 100.0,
    slope_north_per_deg: float = 0.0,
    slope_east_per_deg: float = 0.0,
    void_coordinates: Optional[Sequence[Tuple[int, int]]] = None,
) -> SRTMTile:
    """Construct an in-memory synthetic SRTM tile for fast offline testing.

    Parameters
    ----------
    lat_origin : int
        Southwest corner latitude.
    lon_origin : int
        Southwest corner longitude.
    dimension : int
        Grid dimension (N x N). Defaults to 11.
    elevation_fn : Optional[Callable[[float, float], float]]
        Custom lambda or callable (lat, lon) -> elevation_m.
    base_elevation : float
        Base elevation in meters at (lat_origin, lon_origin).
    slope_north_per_deg : float
        Elevation increase in meters per degree north.
    slope_east_per_deg : float
        Elevation increase in meters per degree east.
    void_coordinates : Optional[Sequence[Tuple[int, int]]]
        List of (row, col) indices to populate with SRTM_VOID_VALUE.

    Returns
    -------
    SRTMTile
        A fully initialized, verified in-memory SRTMTile.
    """
    if dimension < 2:
        raise ValueError("Dimension must be at least 2.")

    samples: List[int] = []
    max_idx = dimension - 1
    void_set = set(void_coordinates or [])

    for r in range(dimension):
        lat = lat_origin + 1.0 - (r / max_idx)
        for c in range(dimension):
            if (r, c) in void_set:
                samples.append(SRTM_VOID_VALUE)
                continue

            lon = lon_origin + (c / max_idx)
            if elevation_fn is not None:
                elev = elevation_fn(lat, lon)
            else:
                d_lat = lat - lat_origin
                d_lon = lon - lon_origin
                elev = (
                    base_elevation
                    + (d_lat * slope_north_per_deg)
                    + (d_lon * slope_east_per_deg)
                )

            clamped = int(
                round(
                    max(
                        MIN_TERRESTRIAL_ELEVATION_M,
                        min(MAX_TERRESTRIAL_ELEVATION_M, elev),
                    )
                )
            )
            samples.append(clamped)

    tile_name = format_srtm_tile_name(lat_origin, lon_origin)
    buffer = struct.pack(f">{len(samples)}h", *samples)
    return SRTMTile.from_bytes(buffer, tile_name=tile_name, dimension=dimension)


class ElevationProvider:
    """Manages cached SRTM elevation tiles across municipal or regional bounding boxes."""

    def __init__(
        self,
        tile_directory: Optional[Union[str, Path]] = None,
        default_elevation: float = 0.0,
    ) -> None:
        self.tile_directory = Path(tile_directory) if tile_directory else None
        self.default_elevation = float(default_elevation)
        self._tiles: Dict[Tuple[int, int], SRTMTile] = {}

    def add_tile(self, tile: SRTMTile) -> None:
        """Register an in-memory SRTMTile into the provider cache."""
        key = (tile.lat_origin, tile.lon_origin)
        self._tiles[key] = tile

    def load_tile_file(self, filepath: Union[str, Path]) -> SRTMTile:
        """Load and cache an SRTM file from disk."""
        tile = SRTMTile.from_file(filepath)
        self.add_tile(tile)
        return tile

    def get_elevation(
        self,
        lat: float,
        lon: float,
        interpolate: bool = True,
    ) -> Optional[float]:
        """Query elevation across all registered tiles or from tile directory.

        Parameters
        ----------
        lat : float
            Latitude in decimal degrees.
        lon : float
            Longitude in decimal degrees.
        interpolate : bool
            Whether to use bilinear interpolation.

        Returns
        -------
        Optional[float]
            Interpolated elevation in meters, or None if unavailable/void.
        """
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return None

        lat_origin = int(math.floor(lat))
        lon_origin = int(math.floor(lon))
        key = (lat_origin, lon_origin)

        # Check in-memory cache
        if key in self._tiles:
            return self._tiles[key].get_elevation(lat, lon, interpolate=interpolate)

        # Attempt to load from directory if specified
        if self.tile_directory and self.tile_directory.is_dir():
            canonical_name = format_srtm_tile_name(lat_origin, lon_origin)
            candidate_path = self.tile_directory / canonical_name
            if candidate_path.is_file():
                tile = self.load_tile_file(candidate_path)
                return tile.get_elevation(lat, lon, interpolate=interpolate)

        return None

    def get_elevation_or_default(
        self,
        lat: float,
        lon: float,
        interpolate: bool = True,
    ) -> float:
        """Query elevation with guaranteed fallback to default_elevation."""
        elev = self.get_elevation(lat, lon, interpolate=interpolate)
        if elev is None or not math.isfinite(elev):
            return self.default_elevation
        return elev


# ---------------------------------------------------------------------------
# Slope & Incline Physics Modeling
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlopeMetrics:
    """Quantitative terrain slope and geometric incline metrics for a road segment.

    Attributes
    ----------
    horizontal_distance_m : float
        2D great-circle distance along Earth's sphere.
    vertical_delta_m : float
        Vertical elevation difference (dest_elevation - source_elevation).
    distance_3d_m : float
        True 3D Euclidean traversal length accounting for vertical rise/drop.
    grade_percent : float
        Slope gradient percentage: (vertical_delta / horizontal_distance) * 100%.
        Positive values indicate an uphill climb; negative values indicate downhill descent.
    slope_angle_deg : float
        Angular pitch in decimal degrees (-90 to +90).
    """

    horizontal_distance_m: float
    vertical_delta_m: float
    distance_3d_m: float
    grade_percent: float
    slope_angle_deg: float


def calculate_slope_metrics(
    coord1: Tuple[float, float],
    elev1_m: float,
    coord2: Tuple[float, float],
    elev2_m: float,
) -> SlopeMetrics:
    """Compute physical 3D traversal distance, vertical delta, and grade percentage.

    Parameters
    ----------
    coord1 : Tuple[float, float]
        (lon, lat) of origin.
    elev1_m : float
        Origin elevation in meters.
    coord2 : Tuple[float, float]
        (lon, lat) of destination.
    elev2_m : float
        Destination elevation in meters.

    Returns
    -------
    SlopeMetrics
        Calculated geometric incline metrics.
    """
    d_horiz = haversine_distance(coord1, coord2, unit="m")
    v_delta = float(elev2_m - elev1_m)
    d_3d = math.hypot(d_horiz, v_delta)

    if d_horiz < 0.001:
        grade_pct = 0.0
        angle_deg = 0.0
    else:
        grade_pct = (v_delta / d_horiz) * 100.0
        angle_deg = math.degrees(math.atan2(v_delta, d_horiz))

    return SlopeMetrics(
        horizontal_distance_m=d_horiz,
        vertical_delta_m=v_delta,
        distance_3d_m=d_3d,
        grade_percent=grade_pct,
        slope_angle_deg=angle_deg,
    )


@dataclass(frozen=True)
class ApparatusGradeLimits:
    """Physical apparatus powertrain climb constraints and downhill braking limits.

    Attributes
    ----------
    max_climb_grade_percent : float
        Maximum passable uphill incline. Grades exceeding this are impassable.
    max_descent_grade_percent : float
        Maximum safe downhill decline before runaway brake failure hazard.
    climb_decay_rate : float
        Rate of velocity degradation on uphill climbs.
    min_crawl_speed_multiplier : float
        Floor speed multiplier on extreme climbs (e.g. 0.15 = 15% of flat speed).
    """

    max_climb_grade_percent: float
    max_descent_grade_percent: float
    climb_decay_rate: float = 0.05
    min_crawl_speed_multiplier: float = 0.15


# Statutory and engineering grade limits for municipal emergency vehicles
# Based on NFPA apparatus weight classifications, gross vehicle weight rating (GVWR),
# and municipal fire access road gradient standards (typically 12-16% maximum).
APPARATUS_GRADE_PROFILES: Dict[ApparatusType, ApparatusGradeLimits] = {
    ApparatusType.AMBULANCE_ALS: ApparatusGradeLimits(
        max_climb_grade_percent=26.0,
        max_descent_grade_percent=28.0,
        climb_decay_rate=0.035,
        min_crawl_speed_multiplier=0.25,
    ),
    ApparatusType.AMBULANCE_BLS: ApparatusGradeLimits(
        max_climb_grade_percent=26.0,
        max_descent_grade_percent=28.0,
        climb_decay_rate=0.035,
        min_crawl_speed_multiplier=0.25,
    ),
    ApparatusType.FIRE_ENGINE: ApparatusGradeLimits(
        max_climb_grade_percent=18.0,
        max_descent_grade_percent=20.0,
        climb_decay_rate=0.055,
        min_crawl_speed_multiplier=0.15,
    ),
    ApparatusType.LADDER_TRUCK: ApparatusGradeLimits(
        max_climb_grade_percent=14.0,  # 60,000+ lb aerial ladder severe climb constraint
        max_descent_grade_percent=16.0,
        climb_decay_rate=0.075,
        min_crawl_speed_multiplier=0.10,
    ),
    ApparatusType.HEAVY_RESCUE: ApparatusGradeLimits(
        max_climb_grade_percent=16.0,
        max_descent_grade_percent=18.0,
        climb_decay_rate=0.060,
        min_crawl_speed_multiplier=0.12,
    ),
    ApparatusType.HAZMAT_UNIT: ApparatusGradeLimits(
        max_climb_grade_percent=16.0,
        max_descent_grade_percent=18.0,
        climb_decay_rate=0.060,
        min_crawl_speed_multiplier=0.12,
    ),
    ApparatusType.BATTALION_CHIEF: ApparatusGradeLimits(
        max_climb_grade_percent=30.0,  # 4WD SUV fly-car
        max_descent_grade_percent=32.0,
        climb_decay_rate=0.025,
        min_crawl_speed_multiplier=0.35,
    ),
}


def get_grade_speed_multiplier(
    apparatus_type: ApparatusType,
    grade_percent: float,
) -> float:
    """Compute the velocity multiplier for an apparatus traveling on a given slope grade.

    Parameters
    ----------
    apparatus_type : ApparatusType
        The vehicle type to evaluate.
    grade_percent : float
        The slope gradient percentage (+ uphill, - downhill).

    Returns
    -------
    float
        Velocity multiplier in range [0.0, 1.0].
        Returns 0.0 if the incline is impassable or prohibited for this apparatus.
    """
    profile = APPARATUS_GRADE_PROFILES.get(
        apparatus_type,
        APPARATUS_GRADE_PROFILES[ApparatusType.FIRE_ENGINE],
    )

    # Flat terrain tolerance (|grade| <= 1.0%)
    if abs(grade_percent) <= 1.0:
        return 1.0

    # Uphill climb (grade > 1.0%)
    if grade_percent > 0.0:
        if grade_percent > profile.max_climb_grade_percent:
            return 0.0  # Physically impassable for apparatus powertrain

        # Smooth exponential/linear decay as grade increases
        excess_grade = grade_percent - 1.0
        decay = math.exp(-profile.climb_decay_rate * excess_grade)
        return max(profile.min_crawl_speed_multiplier, decay)

    # Downhill descent (grade < -1.0%)
    abs_grade = abs(grade_percent)
    if abs_grade > profile.max_descent_grade_percent:
        return 0.0  # Impassable / runaway hazard

    # Moderate descent (down to -6%): minimal braking required
    if abs_grade <= 6.0:
        return 1.0 - (0.015 * (abs_grade - 1.0))

    # Steep descent: heavy apparatus requires low gearing and engine retarder
    excess_descent = abs_grade - 6.0
    descent_factor = 0.925 - (0.045 * excess_descent)
    return max(0.35, descent_factor)


# ---------------------------------------------------------------------------
# Graph Elevation Enrichment & Dynamic Incline Routing
# ---------------------------------------------------------------------------


@dataclass
class ElevationEnrichmentSummary:
    """Summary metrics of graph elevation enrichment."""

    nodes_enriched: int
    edges_enriched: int
    min_elevation_m: float
    max_elevation_m: float
    max_uphill_grade_percent: float
    max_downhill_grade_percent: float
    node_elevations: Dict[str, float] = field(default_factory=dict)


def enrich_graph_with_elevation(
    graph: Graph,
    elevation_provider: ElevationProvider,
    default_elevation: float = 0.0,
) -> ElevationEnrichmentSummary:
    """Enrich all nodes and edges in a road Graph with 3D elevation and slope metrics.

    Annotates edges with:
        - 'elevation_source': float (m)
        - 'elevation_destination': float (m)
        - 'elevation_delta_m': float (m)
        - 'grade_percent': float (%)
        - 'distance_3d_m': float (m)

    Parameters
    ----------
    graph : Graph
        Directed road network graph.
    elevation_provider : ElevationProvider
        Provider supplying digital elevation data.
    default_elevation : float
        Fallback elevation if coordinates are missing or void.

    Returns
    -------
    ElevationEnrichmentSummary
        Quantitative enrichment summary.
    """
    node_elevs: Dict[str, float] = {}
    min_elev = float("inf")
    max_elev = float("-inf")

    # Step 1: Query node elevations
    for node_id in graph.node_ids():
        node = graph.get_node(node_id)
        if node.coordinates is not None:
            lon, lat = node.coordinates
            elev = elevation_provider.get_elevation_or_default(lat, lon)
        else:
            elev = default_elevation

        node_elevs[node_id] = elev
        min_elev = min(min_elev, elev)
        max_elev = max(max_elev, elev)

    if not node_elevs:
        min_elev = default_elevation
        max_elev = default_elevation

    # Step 2: Annotate edges with 3D slopes
    edges_count = 0
    max_uphill = 0.0
    max_downhill = 0.0

    for source_id in graph.node_ids():
        for edge in graph.get_neighbors(source_id):
            u_node = graph.get_node(source_id)
            v_node = graph.get_node(edge.destination_id)

            u_elev = node_elevs.get(source_id, default_elevation)
            v_elev = node_elevs.get(edge.destination_id, default_elevation)

            if u_node.coordinates is not None and v_node.coordinates is not None:
                metrics = calculate_slope_metrics(
                    u_node.coordinates, u_elev, v_node.coordinates, v_elev
                )
            else:
                d_2d = edge.attributes.get("distance_m", edge.cost)
                v_delta = v_elev - u_elev
                d_3d = math.hypot(d_2d, v_delta)
                grade_pct = (v_delta / d_2d * 100.0) if d_2d >= 0.001 else 0.0
                angle_deg = math.degrees(math.atan2(v_delta, d_2d)) if d_2d >= 0.001 else 0.0
                metrics = SlopeMetrics(
                    horizontal_distance_m=d_2d,
                    vertical_delta_m=v_delta,
                    distance_3d_m=d_3d,
                    grade_percent=grade_pct,
                    slope_angle_deg=angle_deg,
                )

            edge.attributes["elevation_source"] = u_elev
            edge.attributes["elevation_destination"] = v_elev
            edge.attributes["elevation_delta_m"] = metrics.vertical_delta_m
            edge.attributes["grade_percent"] = metrics.grade_percent
            edge.attributes["distance_3d_m"] = metrics.distance_3d_m

            if metrics.grade_percent > max_uphill:
                max_uphill = metrics.grade_percent
            if metrics.grade_percent < max_downhill:
                max_downhill = metrics.grade_percent

            edges_count += 1

    return ElevationEnrichmentSummary(
        nodes_enriched=len(node_elevs),
        edges_enriched=edges_count,
        min_elevation_m=min_elev if math.isfinite(min_elev) else default_elevation,
        max_elevation_m=max_elev if math.isfinite(max_elev) else default_elevation,
        max_uphill_grade_percent=max_uphill,
        max_downhill_grade_percent=max_downhill,
        node_elevations=node_elevs,
    )


class ElevationGraphView:
    """Apparatus-specific dynamic view over an elevation-enriched road graph.

    Adjusts edge traversal costs dynamically using apparatus powertrain grade
    multipliers. Completely prunes impassable edges (grades exceeding the
    apparatus limit) from graph neighbor traversal.
    """

    def __init__(
        self,
        base_graph: Any,
        apparatus_type: ApparatusType = ApparatusType.FIRE_ENGINE,
        use_3d_distance: bool = True,
    ) -> None:
        self._base_graph = base_graph
        self.apparatus_type = apparatus_type
        self.use_3d_distance = use_3d_distance

    def _find_base_edge(self, source_id: str, destination_id: str) -> Optional[Edge]:
        """Retrieve edge from base graph using get_edge or neighbors lookup."""
        if hasattr(self._base_graph, "get_edge"):
            return self._base_graph.get_edge(source_id, destination_id)
        for edge in self._base_graph.get_neighbors(source_id):
            if edge.destination_id == destination_id:
                return edge
        return None

    def has_node(self, node_id: str) -> bool:
        return self._base_graph.has_node(node_id)

    def has_edge(self, source_id: str, destination_id: str) -> bool:
        if not self._base_graph.has_edge(source_id, destination_id):
            return False
        # Verify passable for this apparatus
        edge = self._find_base_edge(source_id, destination_id)
        if edge is None:
            return False
        grade = edge.attributes.get("grade_percent", 0.0)
        multiplier = get_grade_speed_multiplier(self.apparatus_type, grade)
        return multiplier > 0.0

    def get_node(self, node_id: str) -> Node:
        return self._base_graph.get_node(node_id)

    def node_ids(self) -> List[str]:
        return self._base_graph.node_ids()

    def node_count(self) -> int:
        return self._base_graph.node_count()

    def edge_count(self) -> int:
        count = 0
        for node_id in self.node_ids():
            count += len(self.get_neighbors(node_id))
        return count

    def get_edge(self, source_id: str, destination_id: str) -> Optional[Edge]:
        edge = self._find_base_edge(source_id, destination_id)
        if edge is None:
            return None
        grade = edge.attributes.get("grade_percent", 0.0)
        multiplier = get_grade_speed_multiplier(self.apparatus_type, grade)
        if multiplier <= 0.0:
            return None

        # Adjusted cost
        base_cost = edge.cost
        if self.use_3d_distance and "distance_3d_m" in edge.attributes:
            d_2d = edge.attributes.get("distance_m", edge.cost)
            if d_2d > 0.0:
                d_3d = edge.attributes["distance_3d_m"]
                base_cost = base_cost * (d_3d / d_2d)

        effective_cost = base_cost / multiplier
        new_attrs = dict(edge.attributes)
        new_attrs["effective_grade_multiplier"] = multiplier
        new_attrs["apparatus_type"] = self.apparatus_type.value

        return Edge(
            source_id=edge.source_id,
            destination_id=edge.destination_id,
            cost=effective_cost,
            attributes=new_attrs,
        )

    def get_neighbors(self, node_id: str) -> List[Edge]:
        """Return passable outgoing edges with grade-adjusted traversal costs."""
        neighbors: List[Edge] = []
        for edge in self._base_graph.get_neighbors(node_id):
            grade = edge.attributes.get("grade_percent", 0.0)
            multiplier = get_grade_speed_multiplier(self.apparatus_type, grade)
            if multiplier <= 0.0:
                continue  # Impassable for this apparatus

            base_cost = edge.cost
            if self.use_3d_distance and "distance_3d_m" in edge.attributes:
                d_2d = edge.attributes.get("distance_m", edge.cost)
                if d_2d > 0.0:
                    d_3d = edge.attributes["distance_3d_m"]
                    base_cost = base_cost * (d_3d / d_2d)

            effective_cost = base_cost / multiplier
            new_attrs = dict(edge.attributes)
            new_attrs["effective_grade_multiplier"] = multiplier
            new_attrs["apparatus_type"] = self.apparatus_type.value

            neighbors.append(
                Edge(
                    source_id=edge.source_id,
                    destination_id=edge.destination_id,
                    cost=effective_cost,
                    attributes=new_attrs,
                )
            )

        return neighbors
