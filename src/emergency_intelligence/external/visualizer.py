"""
Web Mercator Slippy Map Tile Mathematics & Zero-Dependency Leaflet GIS Visualizer.
===================================================================================
Provides pure-Python standard-library implementations of:
1. Web Mercator (EPSG:3857) Slippy Map Tile Mathematics:
   - (lat, lon) <-> (x, y, zoom) forward and inverse tile transformations
   - Tile bounding box geographic coordinates (WGS84 EPSG:4326)
   - Bounding box tile range discovery at arbitrary zoom levels
   - Meters per pixel resolution at specified latitude and zoom
   - TMS (Tile Map Service) vs Slippy OSM Y-coordinate conversions
2. Zero-Dependency Standalone Interactive Leaflet GIS HTML/JS Visualizer:
   - Standalone single-file HTML5 rendering with CDN-linked Leaflet GIS
   - Multi-layer switching (OpenStreetMap Standard, CartoDB Dark Matter, Topo)
   - Dynamic road network styling by highway classification & slope grades
   - Specialized Emergency POI markers with rich clinical/apparatus popups
   - Real-time USGS river gauge water-level badges and flood stage icons
   - 2D Environmental hazard polygons (floods, wildfires, storms)
   - Voronoi response catchments and NFPA 1710 turnout isochrones
   - Interactive Route Playback Scrubber with animated vehicle progression HUD

Strict zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from emergency_intelligence.events.hazards import HazardPolygon
from emergency_intelligence.external.binding import ExtractedEmergencyPOI
from emergency_intelligence.external.hydrology import FloodStage, USGSGaugeReading
from emergency_intelligence.graph.models import Edge, Graph, Node

# Web Mercator projection bounds
MAX_LATITUDE: float = 85.0511287798066
MIN_LATITUDE: float = -85.0511287798066
EARTH_EQUATORIAL_CIRCUMFERENCE_M: float = 40_075_016.686


# ---------------------------------------------------------------------------
# 1. Web Mercator Slippy Map Tile Arithmetic
# ---------------------------------------------------------------------------


def clamp_latitude(lat: float) -> float:
    """Clamp latitude to the valid Web Mercator conformal limits."""
    return max(MIN_LATITUDE, min(MAX_LATITUDE, float(lat)))


def normalize_longitude(lon: float) -> float:
    """Normalize longitude to the standard [-180.0, 180.0) range."""
    lon = float(lon)
    return (lon + 180.0) % 360.0 - 180.0


def lat_lon_to_tile_xy(lat: float, lon: float, zoom: int) -> Tuple[int, int]:
    """Convert geographic WGS84 (latitude, longitude) to discrete Slippy tile (x, y).

    Parameters
    ----------
    lat : float
        Latitude in decimal degrees (-85.0511 to 85.0511).
    lon : float
        Longitude in decimal degrees (-180.0 to 180.0).
    zoom : int
        Zoom level (0 to 30).

    Returns
    -------
    Tuple[int, int]
        Discrete integer tile indices (tile_x, tile_y).
    """
    if zoom < 0:
        raise ValueError(f"Zoom level must be non-negative, got {zoom}.")

    clamped_lat = clamp_latitude(lat)
    norm_lon = normalize_longitude(lon)

    lat_rad = math.radians(clamped_lat)
    n = 1 << zoom  # 2^zoom

    tile_x = int(math.floor((norm_lon + 180.0) / 360.0 * n))
    tile_y = int(
        math.floor(
            (1.0 - math.log(math.tan(lat_rad) + (1.0 / math.cos(lat_rad))) / math.pi)
            / 2.0
            * n
        )
    )

    # Clamp tile coordinates within [0, n - 1]
    tile_x = max(0, min(n - 1, tile_x))
    tile_y = max(0, min(n - 1, tile_y))

    return tile_x, tile_y


def tile_xy_to_lat_lon(tile_x: int, tile_y: int, zoom: int) -> Tuple[float, float]:
    """Convert discrete Slippy tile (x, y) to the NW corner (latitude, longitude).

    Parameters
    ----------
    tile_x : int
        Discrete column index.
    tile_y : int
        Discrete row index.
    zoom : int
        Zoom level (0 to 30).

    Returns
    -------
    Tuple[float, float]
        Northwest corner coordinates (latitude, longitude).
    """
    if zoom < 0:
        raise ValueError(f"Zoom level must be non-negative, got {zoom}.")

    n = 1 << zoom
    lon = (float(tile_x) / n) * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1.0 - 2.0 * float(tile_y) / n)))
    lat = math.degrees(lat_rad)

    return lat, lon


@dataclass(frozen=True)
class TileBoundingBox:
    """Geographic bounding box for a Slippy map tile."""

    tile_x: int
    tile_y: int
    zoom: int
    min_lat: float
    min_lon: float
    max_lat: float
    max_lon: float

    @property
    def center_lat(self) -> float:
        return (self.min_lat + self.max_lat) / 2.0

    @property
    def center_lon(self) -> float:
        return (self.min_lon + self.max_lon) / 2.0


def tile_bounding_box(tile_x: int, tile_y: int, zoom: int) -> TileBoundingBox:
    """Compute the geographic boundary box (min_lat, min_lon, max_lat, max_lon) of a tile."""
    # Top-left (NW)
    max_lat, min_lon = tile_xy_to_lat_lon(tile_x, tile_y, zoom)
    # Bottom-right (SE)
    min_lat, max_lon = tile_xy_to_lat_lon(tile_x + 1, tile_y + 1, zoom)

    return TileBoundingBox(
        tile_x=tile_x,
        tile_y=tile_y,
        zoom=zoom,
        min_lat=min_lat,
        min_lon=min_lon,
        max_lat=max_lat,
        max_lon=max_lon,
    )


def get_tiles_for_bounding_box(
    min_lat: float,
    min_lon: float,
    max_lat: float,
    max_lon: float,
    zoom: int,
) -> List[Tuple[int, int]]:
    """Discover all Slippy tile coordinates covering a geographic bounding box."""
    if zoom < 0:
        raise ValueError(f"Zoom level must be non-negative, got {zoom}.")
    if min_lat > max_lat:
        min_lat, max_lat = max_lat, min_lat
    if min_lon > max_lon:
        min_lon, max_lon = max_lon, min_lon

    x_min, y_min = lat_lon_to_tile_xy(max_lat, min_lon, zoom)
    x_max, y_max = lat_lon_to_tile_xy(min_lat, max_lon, zoom)

    tiles: List[Tuple[int, int]] = []
    for x in range(min(x_min, x_max), max(x_min, x_max) + 1):
        for y in range(min(y_min, y_max), max(y_min, y_max) + 1):
            tiles.append((x, y))

    return tiles


def resolution_meters_per_pixel(lat: float, zoom: int, tile_size_pixels: int = 256) -> float:
    """Calculate physical ground resolution (meters per pixel) at latitude and zoom level."""
    clamped_lat = clamp_latitude(lat)
    lat_rad = math.radians(clamped_lat)
    n = 1 << zoom
    return (EARTH_EQUATORIAL_CIRCUMFERENCE_M * math.cos(lat_rad)) / (n * tile_size_pixels)


def slippy_to_tms_y(tile_y: int, zoom: int) -> int:
    """Convert standard Slippy OSM Y-coordinate to OSGeo TMS (Tile Map Service) flipped Y."""
    n = 1 << zoom
    return (n - 1) - tile_y


def tms_to_slippy_y(tms_y: int, zoom: int) -> int:
    """Convert OSGeo TMS Y-coordinate to standard Slippy OSM Y."""
    return slippy_to_tms_y(tms_y, zoom)


def format_tile_url(
    tile_x: int,
    tile_y: int,
    zoom: int,
    template: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
) -> str:
    """Format standard XYZ tile server URL."""
    return template.replace("{z}", str(zoom)).replace("{x}", str(tile_x)).replace("{y}", str(tile_y))


# ---------------------------------------------------------------------------
# 2. Standalone Zero-Dependency Interactive Leaflet Visualizer
# ---------------------------------------------------------------------------


@dataclass
class MapRouteOverlay:
    """Visual overlay for planned or dispatched vehicle routes."""

    route_id: str
    label: str
    path_nodes: Sequence[str]
    color: str = "#2563EB"  # Primary blue
    weight: int = 5
    opacity: float = 0.85
    dash_array: Optional[str] = None
    total_cost: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MapIsochroneOverlay:
    """Travel-time frontier polygon overlay (e.g. NFPA 1710 240s/480s isochrones)."""

    isochrone_id: str
    label: str
    threshold_seconds: float
    boundary_coordinates: Sequence[Tuple[float, float]]  # [(lon, lat), ...]
    color: str = "#10B981"  # Emerald green
    fill_opacity: float = 0.20


def render_interactive_map_html(
    center_lat: float,
    center_lon: float,
    zoom: int = 13,
    title: str = "Emergency Intelligence AI — Tactical GIS Visualizer",
    graph: Optional[Graph] = None,
    pois: Sequence[ExtractedEmergencyPOI] = (),
    gauges: Sequence[USGSGaugeReading] = (),
    hazards: Sequence[HazardPolygon] = (),
    routes: Sequence[MapRouteOverlay] = (),
    isochrones: Sequence[MapIsochroneOverlay] = (),
    show_playback_hud: bool = True,
) -> str:
    """Generate a self-contained, standalone single-file HTML/JS GIS map using Leaflet.

    Parameters
    ----------
    center_lat : float
        Initial map center latitude.
    center_lon : float
        Initial map center longitude.
    zoom : int
        Initial map zoom level (default 13).
    title : str
        Document and HUD title banner.
    graph : Optional[Graph]
        Optional road network graph to render as interactive polylines.
    pois : Sequence[ExtractedEmergencyPOI]
        Optional emergency stations, hospitals, clinics, and helipads.
    gauges : Sequence[USGSGaugeReading]
        Optional USGS river gauges with real-time flood stages.
    hazards : Sequence[HazardPolygon]
        Optional environmental disaster polygons (floods, fires, plumes).
    routes : Sequence[MapRouteOverlay]
        Optional vehicle routes (baseline dispatch, dynamic detours).
    isochrones : Sequence[MapIsochroneOverlay]
        Optional NFPA 1710 response boundary catchment rings.
    show_playback_hud : bool
        If True, renders the interactive vehicle trajectory playback scrubber.

    Returns
    -------
    str
        Complete, valid HTML5 document ready for browser display or file saving.
    """
    # 1. Format GeoJSON / JSON structures for map layers
    nodes_map: Dict[str, Tuple[float, float]] = {}
    graph_edges_data: List[Dict[str, Any]] = []

    if graph is not None:
        for node_id in graph.node_ids():
            n = graph.get_node(node_id)
            if n is not None and n.lat is not None and n.lon is not None:
                nodes_map[node_id] = (float(n.lat), float(n.lon))

        # Build edge segments
        for src_id in graph.node_ids():
            src_coord = nodes_map.get(src_id)
            if not src_coord:
                continue
            for edge in graph.get_neighbors(src_id):
                dst_coord = nodes_map.get(edge.destination_id)
                if not dst_coord:
                    continue

                # Intermediate geometry if present
                geom = edge.attributes.get("geometry")
                if geom and isinstance(geom, list) and len(geom) >= 2:
                    coords = [[float(pt[1]), float(pt[0])] for pt in geom]  # Leaflet uses [lat, lon]
                else:
                    coords = [list(src_coord), list(dst_coord)]

                grade = edge.attributes.get("grade_percent", 0.0)
                edge_cost = edge.cost

                graph_edges_data.append({
                    "src": src_id,
                    "dst": edge.destination_id,
                    "coords": coords,
                    "cost": edge_cost,
                    "grade": grade,
                    "highway": edge.attributes.get("highway", "residential"),
                })

    # POI Markers
    pois_data: List[Dict[str, Any]] = []
    for poi in pois:
        poi_type_val = poi.poi_type.value if hasattr(poi.poi_type, "value") else str(poi.poi_type)
        badge_color = "#DC2626" if poi_type_val in ("hospital", "clinic") else "#2563EB"

        trauma_val = getattr(poi, "trauma_level", None)
        trauma_str = f"Trauma Level {trauma_val}" if trauma_val is not None else "General Care"

        caps = getattr(poi, "capabilities", None) or getattr(poi, "specialties", None) or []
        cap_names = [getattr(c, "value", str(c)) for c in caps]

        poi_id_val = getattr(poi, "poi_id", getattr(poi, "osm_id", "poi"))
        phone_val = getattr(poi, "phone", None) or getattr(poi, "emergency_phone", "N/A")

        pois_data.append({
            "id": str(poi_id_val),
            "name": poi.name or f"{poi_type_val.capitalize()} #{poi_id_val}",
            "type": poi_type_val,
            "lat": float(poi.latitude),
            "lon": float(poi.longitude),
            "color": badge_color,
            "trauma": trauma_str,
            "specialties": cap_names,
            "bays": getattr(poi, "apparatus_bays", None),
            "phone": str(phone_val),
        })

    # River Gauges
    gauges_data: List[Dict[str, Any]] = []
    for g in gauges:
        stage_colors = {
            FloodStage.NORMAL: "#10B981",    # Emerald
            FloodStage.ACTION: "#F59E0B",    # Amber
            FloodStage.MINOR: "#EF4444",     # Red
            FloodStage.MODERATE: "#DC2626",  # Dark Red
            FloodStage.MAJOR: "#7F1D1D",     # Maroon
        }
        color = stage_colors.get(g.flood_stage, "#6B7280")
        gauges_data.append({
            "site_id": g.site_id,
            "name": g.site_name,
            "lat": g.latitude,
            "lon": g.longitude,
            "stage": g.flood_stage.value.upper(),
            "color": color,
            "height_ft": round(g.gage_height_ft, 2),
            "height_m": round(g.gage_height_m, 2),
            "flow_cfs": round(g.streamflow_cfs, 1) if g.streamflow_cfs else "N/A",
            "is_flooding": g.is_flooding(),
        })

    # Hazards
    hazards_data: List[Dict[str, Any]] = []
    for h in hazards:
        # Convert boundary (lon, lat) to Leaflet (lat, lon)
        poly_coords = [[float(pt[1]), float(pt[0])] for pt in h.boundary_coordinates]
        is_blocked = h.is_blocking()
        color = "#DC2626" if is_blocked else "#D97706"

        hazards_data.append({
            "id": h.hazard_id,
            "type": h.hazard_type.value,
            "severity": h.severity.value,
            "description": h.description,
            "speed_mult": h.speed_multiplier or 0.0,
            "coords": poly_coords,
            "color": color,
            "fillColor": "#EF4444" if is_blocked else "#F59E0B",
            "is_blocked": is_blocked,
        })

    # Routes & Playback Waypoints
    routes_data: List[Dict[str, Any]] = []
    primary_playback_route_coords: List[List[float]] = []

    for r in routes:
        r_coords: List[List[float]] = []
        for nid in r.path_nodes:
            coord = nodes_map.get(nid)
            if coord:
                r_coords.append([coord[0], coord[1]])

        if r_coords and not primary_playback_route_coords:
            primary_playback_route_coords = r_coords

        routes_data.append({
            "id": r.route_id,
            "label": r.label,
            "coords": r_coords,
            "color": r.color,
            "weight": r.weight,
            "opacity": r.opacity,
            "dashArray": r.dash_array or "",
            "cost": r.total_cost or 0.0,
            "nodes": list(r.path_nodes),
        })

    # Isochrones
    isochrones_data: List[Dict[str, Any]] = []
    for iso in isochrones:
        coords = [[float(pt[1]), float(pt[0])] for pt in iso.boundary_coordinates]
        isochrones_data.append({
            "id": iso.isochrone_id,
            "label": iso.label,
            "seconds": iso.threshold_seconds,
            "coords": coords,
            "color": iso.color,
            "fillOpacity": iso.fill_opacity,
        })

    # Convert to JSON strings for embedded script
    json_edges = json.dumps(graph_edges_data)
    json_pois = json.dumps(pois_data)
    json_gauges = json.dumps(gauges_data)
    json_hazards = json.dumps(hazards_data)
    json_routes = json.dumps(routes_data)
    json_isochrones = json.dumps(isochrones_data)
    json_playback = json.dumps(primary_playback_route_coords)

    # Standalone HTML Template with embedded styles and Leaflet bindings
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>

  <!-- Leaflet 1.9.4 CSS & JS (Zero local dependencies) -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>

  <style>
    :root {{
      --bg-dark: #0f172a;
      --panel-bg: rgba(30, 41, 59, 0.92);
      --border-color: rgba(255, 255, 255, 0.12);
      --accent-blue: #3b82f6;
      --accent-emerald: #10b981;
      --accent-rose: #f43f5e;
      --accent-amber: #f59e0b;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg-dark);
      color: var(--text-main);
      overflow: hidden;
      height: 100vh;
      width: 100vw;
    }}
    #map {{
      height: 100vh;
      width: 100vw;
      background: #020617;
    }}

    /* Floating Header HUD */
    .header-hud {{
      position: absolute;
      top: 16px;
      left: 16px;
      z-index: 1000;
      background: var(--panel-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 14px 20px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
      max-width: 440px;
      pointer-events: auto;
    }}
    .header-title {{
      font-size: 16px;
      font-weight: 700;
      letter-spacing: -0.02em;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .header-subtitle {{
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
      line-height: 1.4;
    }}
    .badge-status {{
      display: inline-block;
      padding: 2px 8px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      border-radius: 9999px;
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }}

    /* Playback & Telemetry Scrubber Bar */
    .playback-hud {{
      position: absolute;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 1000;
      background: var(--panel-bg);
      backdrop-filter: blur(12px);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 12px 20px;
      display: {"flex" if show_playback_hud else "none"};
      align-items: center;
      gap: 16px;
      box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.6);
      width: min(90vw, 680px);
      pointer-events: auto;
    }}
    .btn-play {{
      background: var(--accent-blue);
      color: #ffffff;
      border: none;
      border-radius: 8px;
      padding: 8px 16px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 6px;
      transition: background 0.2s;
    }}
    .btn-play:hover {{ background: #2563eb; }}
    .scrubber-slider {{
      flex: 1;
      accent-color: var(--accent-blue);
      cursor: pointer;
    }}
    .telemetry-chip {{
      font-size: 12px;
      font-family: monospace;
      color: var(--text-muted);
      white-space: nowrap;
    }}

    /* Custom Leaflet Popups */
    .leaflet-popup-content-wrapper {{
      background: var(--panel-bg) !important;
      color: var(--text-main) !important;
      border-radius: 10px !important;
      border: 1px solid var(--border-color) !important;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5) !important;
    }}
    .leaflet-popup-tip {{
      background: var(--panel-bg) !important;
    }}
    .popup-title {{
      font-weight: 700;
      font-size: 14px;
      margin-bottom: 6px;
      color: var(--accent-blue);
    }}
    .popup-row {{
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 3px;
    }}
    .popup-row strong {{ color: var(--text-main); }}
  </style>
</head>
<body>

  <!-- Floating Header HUD -->
  <div class="header-hud">
    <div class="header-title">
      <span>{title}</span>
      <span class="badge-status">LIVE GIS</span>
    </div>
    <div class="header-subtitle">
      Deterministic Multi-Modal Routing • USGS Hydrological Telemetry • Dynamic Hazard Boundaries
    </div>
  </div>

  <!-- Interactive Map Canvas -->
  <div id="map"></div>

  <!-- Route Playback HUD -->
  <div class="playback-hud" id="playbackHud">
    <button class="btn-play" id="btnPlay" onclick="togglePlayback()">▶ Play</button>
    <input type="range" min="0" max="100" value="0" class="scrubber-slider" id="playbackSlider" oninput="onSliderChange(this.value)">
    <div class="telemetry-chip" id="telemetryDisplay">Step 0 / 0</div>
  </div>

  <script>
    // -------------------------------------------------------------------------
    // 1. Initialize Map & Base Tile Layers
    // -------------------------------------------------------------------------
    const map = L.map('map', {{
      center: [{center_lat}, {center_lon}],
      zoom: {zoom},
      zoomControl: true
    }});

    const osmStandard = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: '© OpenStreetMap contributors'
    }});

    const cartoDark = L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
      maxZoom: 19,
      attribution: '© OpenStreetMap, © CARTO',
      subdomains: 'abcd'
    }}).addTo(map);

    const baseMaps = {{
      "CartoDB Dark": cartoDark,
      "OpenStreetMap": osmStandard
    }};

    // Layer groups for toggle control
    const roadLayer = L.layerGroup().addTo(map);
    const poiLayer = L.layerGroup().addTo(map);
    const gaugeLayer = L.layerGroup().addTo(map);
    const hazardLayer = L.layerGroup().addTo(map);
    const routeLayer = L.layerGroup().addTo(map);
    const isochroneLayer = L.layerGroup().addTo(map);

    const overlayMaps = {{
      "Road Network": roadLayer,
      "Emergency POIs": poiLayer,
      "USGS Gauges": gaugeLayer,
      "Hazard Zones": hazardLayer,
      "Dispatched Routes": routeLayer,
      "Isochrones": isochroneLayer
    }};

    L.control.layers(baseMaps, overlayMaps, {{ position: 'topright' }}).addTo(map);

    // -------------------------------------------------------------------------
    // 2. Render Road Network Edges
    // -------------------------------------------------------------------------
    const edgesData = {json_edges};
    edgesData.forEach(edge => {{
      let color = '#475569';
      let weight = 2;
      if (edge.grade >= 10.0) {{ color = '#e11d48'; weight = 3; }}
      else if (edge.grade >= 6.0) {{ color = '#f59e0b'; weight = 2.5; }}

      const polyline = L.polyline(edge.coords, {{
        color: color,
        weight: weight,
        opacity: 0.7
      }}).addTo(roadLayer);

      polyline.bindPopup(
        `<div class="popup-title">Edge: ${{edge.src}} ➔ ${{edge.dst}}</div>` +
        `<div class="popup-row">Cost: <strong>${{edge.cost.toFixed(1)}} m</strong></div>` +
        `<div class="popup-row">Grade: <strong>${{edge.grade.toFixed(1)}}%</strong></div>` +
        `<div class="popup-row">Type: <strong>${{edge.highway}}</strong></div>`
      );
    }});

    // -------------------------------------------------------------------------
    // 3. Render Emergency POIs
    // -------------------------------------------------------------------------
    const poisData = {json_pois};
    poisData.forEach(poi => {{
      const marker = L.circleMarker([poi.lat, poi.lon], {{
        radius: 8,
        fillColor: poi.color,
        color: '#ffffff',
        weight: 2,
        opacity: 1,
        fillOpacity: 0.9
      }}).addTo(poiLayer);

      let specHtml = poi.specialties.length > 0 ? poi.specialties.join(', ') : 'Standard';
      marker.bindPopup(
        `<div class="popup-title">${{poi.name}}</div>` +
        `<div class="popup-row">Category: <strong>${{poi.type.toUpperCase()}}</strong></div>` +
        `<div class="popup-row">Level: <strong>${{poi.trauma}}</strong></div>` +
        `<div class="popup-row">Capabilities: <strong>${{specHtml}}</strong></div>` +
        `<div class="popup-row">Bays: <strong>${{poi.bays || 'N/A'}}</strong></div>` +
        `<div class="popup-row">Dispatch Phone: <strong>${{poi.phone}}</strong></div>`
      );
    }});

    // -------------------------------------------------------------------------
    // 4. Render USGS River Gauges
    // -------------------------------------------------------------------------
    const gaugesData = {json_gauges};
    gaugesData.forEach(g => {{
      const gaugeMarker = L.circleMarker([g.lat, g.lon], {{
        radius: 10,
        fillColor: g.color,
        color: '#ffffff',
        weight: 2.5,
        opacity: 1,
        fillOpacity: 0.95
      }}).addTo(gaugeLayer);

      gaugeMarker.bindPopup(
        `<div class="popup-title">USGS Gauge: ${{g.site_id}}</div>` +
        `<div class="popup-row">${{g.name}}</div>` +
        `<div class="popup-row">Flood Stage: <strong style="color:${{g.color}}">${{g.stage}}</strong></div>` +
        `<div class="popup-row">Gage Height: <strong>${{g.height_ft}} ft (${{g.height_m}} m)</strong></div>` +
        `<div class="popup-row">Streamflow: <strong>${{g.flow_cfs}} cfs</strong></div>`
      );
    }});

    // -------------------------------------------------------------------------
    // 5. Render Environmental Hazards
    // -------------------------------------------------------------------------
    const hazardsData = {json_hazards};
    hazardsData.forEach(h => {{
      const poly = L.polygon(h.coords, {{
        color: h.color,
        fillColor: h.fillColor,
        fillOpacity: 0.35,
        weight: 2
      }}).addTo(hazardLayer);

      poly.bindPopup(
        `<div class="popup-title">${{h.description}}</div>` +
        `<div class="popup-row">Type: <strong>${{h.type}}</strong></div>` +
        `<div class="popup-row">Severity: <strong>${{h.severity.toUpperCase()}}</strong></div>` +
        `<div class="popup-row">Status: <strong>${{h.is_blocked ? 'ROAD CLOSURE / SEVERED' : 'SPEED PENALTY'}}</strong></div>` +
        `<div class="popup-row">Speed Factor: <strong>${{(h.speed_mult * 100).toFixed(0)}}%</strong></div>`
      );
    }});

    // -------------------------------------------------------------------------
    // 6. Render Dispatched Routes & Isochrones
    // -------------------------------------------------------------------------
    const routesData = {json_routes};
    routesData.forEach(r => {{
      if (r.coords.length > 0) {{
        const polyline = L.polyline(r.coords, {{
          color: r.color,
          weight: r.weight,
          opacity: r.opacity,
          dashArray: r.dashArray || null
        }}).addTo(routeLayer);

        polyline.bindPopup(
          `<div class="popup-title">${{r.label}}</div>` +
          `<div class="popup-row">Cost: <strong>${{r.cost.toFixed(1)}} m</strong></div>` +
          `<div class="popup-row">Waypoints: <strong>${{r.nodes.length}} nodes</strong></div>`
        );
      }}
    }});

    const isochronesData = {json_isochrones};
    isochronesData.forEach(iso => {{
      L.polygon(iso.coords, {{
        color: iso.color,
        fillColor: iso.color,
        fillOpacity: iso.fillOpacity,
        weight: 2,
        dashArray: '4, 4'
      }}).addTo(isochroneLayer).bindPopup(
        `<div class="popup-title">${{iso.label}}</div>` +
        `<div class="popup-row">Threshold: <strong>${{iso.seconds}} seconds</strong></div>`
      );
    }});

    // -------------------------------------------------------------------------
    // 7. Interactive Playback Scrubber Animation
    // -------------------------------------------------------------------------
    const playbackCoords = {json_playback};
    let playbackMarker = null;
    let playbackIndex = 0;
    let isPlaying = false;
    let playbackTimer = null;

    if (playbackCoords.length > 0) {{
      playbackMarker = L.circleMarker(playbackCoords[0], {{
        radius: 7,
        fillColor: '#38bdf8',
        color: '#ffffff',
        weight: 3,
        opacity: 1,
        fillOpacity: 1
      }}).addTo(map);

      document.getElementById('playbackSlider').max = playbackCoords.length - 1;
      updateTelemetry();
    }}

    function updateTelemetry() {{
      if (playbackCoords.length === 0) return;
      const pt = playbackCoords[playbackIndex];
      playbackMarker.setLatLng(pt);
      document.getElementById('playbackSlider').value = playbackIndex;
      document.getElementById('telemetryDisplay').innerText =
        `Step ${{playbackIndex + 1}} / ${{playbackCoords.length}} | (${{pt[0].toFixed(4)}}, ${{pt[1].toFixed(4)}})`;
    }}

    function onSliderChange(val) {{
      playbackIndex = parseInt(val);
      updateTelemetry();
    }}

    function togglePlayback() {{
      const btn = document.getElementById('btnPlay');
      if (isPlaying) {{
        clearInterval(playbackTimer);
        isPlaying = false;
        btn.innerText = '▶ Play';
      }} else {{
        isPlaying = true;
        btn.innerText = '⏸ Pause';
        playbackTimer = setInterval(() => {{
          playbackIndex++;
          if (playbackIndex >= playbackCoords.length) {{
            playbackIndex = 0;
          }}
          updateTelemetry();
        }}, 400);
      }}
    }}
  </script>
</body>
</html>
"""
    return html


def save_interactive_map_html(
    html_content: str,
    output_path: Union[str, Path],
) -> Path:
    """Save generated interactive Leaflet HTML visualizer to disk.

    Parameters
    ----------
    html_content : str
        Rendered HTML document string.
    output_path : Union[str, Path]
        Target destination file path.

    Returns
    -------
    Path
        Absolute path to the created HTML document.
    """
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html_content, encoding="utf-8")
    return path
