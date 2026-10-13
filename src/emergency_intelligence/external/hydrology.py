"""
Real-Time Hydrological & Environmental Hazard Ingestion (USGS & Open-Meteo).
=============================================================================
Provides zero-dependency standard-library integration with:
- USGS NWIS Water Services instantaneous river gauge telemetry (gage height, discharge)
- National Weather Service (NWS) flood stage threshold classification (Action, Minor, Moderate, Major)
- Automated dynamic river inundation catchment polygon generation (HazardPolygon)
- Open-Meteo real-time severe weather telemetry (WMO storm codes, high winds, precipitation)
- Dynamic environmental graph closures & speed degradation via DynamicGraphView

Strict zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import urllib.parse
import urllib.request

from emergency_intelligence.events.hazards import (
    HazardPolygon,
    HazardSeverity,
    HazardType,
    find_edges_intersecting_hazard,
)
from emergency_intelligence.events.mutations import DynamicGraphView, MutationType
from emergency_intelligence.graph.models import Edge, Graph

# Mean Earth radius for metric-to-degree spatial buffer projection
EARTH_RADIUS_METERS: float = 6_371_000.0


class FloodStage(str, Enum):
    """NOAA / NWS standard river flood categories."""

    NORMAL = "normal"          # Below Action Stage: water within normal riverbanks
    ACTION = "action"          # Action Stage: water approaching banks, public awareness
    MINOR = "minor"            # Minor Flood: low-lying road inundation, river overflow
    MODERATE = "moderate"      # Moderate Flood: substantial secondary road closures, structural threats
    MAJOR = "major"            # Major Flood: critical road severances, widespread structural flooding


class WeatherAlertLevel(str, Enum):
    """Meteorological hazard warning tiers."""

    NONE = "none"              # Normal weather
    ADVISORY = "advisory"      # Weather conditions cause significant inconvenience
    WATCH = "watch"            # Favorable conditions for a severe environmental hazard
    WARNING = "warning"        # Imminent or occurring life-threatening severe weather event


@dataclass(frozen=True)
class USGSGaugeThresholds:
    """Site-specific NWS river flood stage thresholds in feet."""

    action_stage_ft: float
    minor_stage_ft: float
    moderate_stage_ft: float
    major_stage_ft: float

    def classify_stage(self, gage_height_ft: float) -> FloodStage:
        """Classify gauge height into standard flood category."""
        if gage_height_ft >= self.major_stage_ft:
            return FloodStage.MAJOR
        if gage_height_ft >= self.moderate_stage_ft:
            return FloodStage.MODERATE
        if gage_height_ft >= self.minor_stage_ft:
            return FloodStage.MINOR
        if gage_height_ft >= self.action_stage_ft:
            return FloodStage.ACTION
        return FloodStage.NORMAL


# Default heuristic flood thresholds when USGS site metadata lacks explicit NWS definitions
DEFAULT_GAUGE_THRESHOLDS = USGSGaugeThresholds(
    action_stage_ft=10.0,
    minor_stage_ft=12.0,
    moderate_stage_ft=16.0,
    major_stage_ft=20.0,
)


@dataclass
class USGSGaugeReading:
    """Individual real-time river gauge observation from USGS Water Services."""

    site_id: str
    site_name: str
    latitude: float
    longitude: float
    timestamp: datetime
    gage_height_ft: float
    streamflow_cfs: Optional[float] = None
    flood_stage: FloodStage = FloodStage.NORMAL
    thresholds: USGSGaugeThresholds = DEFAULT_GAUGE_THRESHOLDS
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not (math.isfinite(self.latitude) and math.isfinite(self.longitude)):
            raise ValueError("USGS gauge coordinates must be finite floats.")
        if not (-90.0 <= self.latitude <= 90.0 and -180.0 <= self.longitude <= 180.0):
            raise ValueError(f"USGS gauge coordinates ({self.latitude}, {self.longitude}) out of geographic range.")
        if not math.isfinite(self.gage_height_ft):
            raise ValueError("Gage height must be a finite float.")

    @property
    def gage_height_m(self) -> float:
        """Elevation/gage height in metric meters."""
        return self.gage_height_ft * 0.3048

    def is_flooding(self) -> bool:
        """Returns True if gauge has breached minor, moderate, or major flood stage."""
        return self.flood_stage in (FloodStage.MINOR, FloodStage.MODERATE, FloodStage.MAJOR)


@dataclass
class WeatherConditions:
    """Real-time surface weather observation from Open-Meteo."""

    latitude: float
    longitude: float
    timestamp: datetime
    weather_code: int
    temperature_c: float
    wind_speed_kmh: float
    precipitation_mm: float
    visibility_m: float = 10000.0
    alert_level: WeatherAlertLevel = WeatherAlertLevel.NONE
    summary: str = ""

    def __post_init__(self) -> None:
        if not (math.isfinite(self.latitude) and math.isfinite(self.longitude)):
            raise ValueError("Weather observation coordinates must be finite floats.")


# ---------------------------------------------------------------------------
# USGS JSON Response Parser & Query URL Builder
# ---------------------------------------------------------------------------


def build_usgs_water_query_url(
    site_ids: Sequence[str],
    parameters: Sequence[str] = ("00065", "00060"),
) -> str:
    """Construct an official USGS NWIS Instantaneous Values REST API URL.

    Parameters
    ----------
    site_ids : Sequence[str]
        List of 8-to-15 digit USGS station numbers (e.g. ['12119000', '12113000']).
    parameters : Sequence[str]
        USGS parameter codes: '00065' = Gage height (ft), '00060' = Streamflow (cfs).

    Returns
    -------
    str
        Full HTTPS query URL.
    """
    clean_sites = ",".join(s.strip() for s in site_ids if s.strip())
    clean_params = ",".join(p.strip() for p in parameters if p.strip())
    query_params = {
        "format": "json",
        "sites": clean_sites,
        "parameterCd": clean_params,
        "siteStatus": "all",
    }
    base = "https://waterservices.usgs.gov/nwis/iv/"
    return f"{base}?{urllib.parse.urlencode(query_params)}"


def parse_usgs_water_response(
    payload: Dict[str, Any],
    custom_thresholds: Optional[Dict[str, USGSGaugeThresholds]] = None,
) -> List[USGSGaugeReading]:
    """Parse raw USGS Water Services JSON payload into structured gauge readings.

    Parameters
    ----------
    payload : Dict[str, Any]
        Decoded JSON dictionary from USGS REST endpoint.
    custom_thresholds : Optional[Dict[str, USGSGaugeThresholds]]
        Optional site-specific flood stage thresholds mapped by site_id.

    Returns
    -------
    List[USGSGaugeReading]
        Parsed, stage-classified river observations.
    """
    thresholds_map = custom_thresholds or {}
    readings_by_site: Dict[str, Dict[str, Any]] = {}

    time_series_list = payload.get("value", {}).get("timeSeries", [])
    if not isinstance(time_series_list, list):
        return []

    for series in time_series_list:
        if not isinstance(series, dict):
            continue
        source_info = series.get("sourceInfo", {})
        site_codes = source_info.get("siteCode", [])
        if not isinstance(site_codes, list) or not site_codes:
            continue
        site_id = str(site_codes[0].get("value", "")).strip()
        if not site_id:
            continue

        site_name = str(source_info.get("siteName", f"USGS-{site_id}")).strip()
        geo = source_info.get("geoLocation", {}).get("geogLocation", {})
        try:
            lat = float(geo.get("latitude", 0.0))
            lon = float(geo.get("longitude", 0.0))
        except (ValueError, TypeError):
            continue

        # Parameter classification (00065 = height, 00060 = discharge)
        var_codes = series.get("variable", {}).get("variableCode", [])
        var_code = str(var_codes[0].get("value", "")) if (isinstance(var_codes, list) and var_codes) else ""

        values_arr = series.get("values", [])
        values_list = (
            values_arr[0].get("value", [])
            if (isinstance(values_arr, list) and values_arr and isinstance(values_arr[0], dict))
            else []
        )
        if not isinstance(values_list, list) or not values_list:
            continue

        # Get latest observation
        latest_val = values_list[-1]
        raw_val_str = latest_val.get("value")
        date_str = latest_val.get("dateTime", "")

        try:
            numeric_val = float(raw_val_str)
        except (ValueError, TypeError):
            continue

        try:
            # Parse ISO-8601 timestamp with timezone
            obs_time = datetime.fromisoformat(date_str)
        except (ValueError, TypeError):
            obs_time = datetime.now(timezone.utc)

        if site_id not in readings_by_site:
            readings_by_site[site_id] = {
                "site_id": site_id,
                "site_name": site_name,
                "latitude": lat,
                "longitude": lon,
                "timestamp": obs_time,
                "gage_height_ft": None,
                "streamflow_cfs": None,
            }

        if var_code == "00065":
            readings_by_site[site_id]["gage_height_ft"] = numeric_val
        elif var_code == "00060":
            readings_by_site[site_id]["streamflow_cfs"] = numeric_val

    results: List[USGSGaugeReading] = []
    for site_id, data in readings_by_site.items():
        height = data["gage_height_ft"]
        if height is None:
            continue  # Must have height to evaluate flood category

        thresh = thresholds_map.get(site_id, DEFAULT_GAUGE_THRESHOLDS)
        stage = thresh.classify_stage(height)

        reading = USGSGaugeReading(
            site_id=site_id,
            site_name=data["site_name"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            timestamp=data["timestamp"],
            gage_height_ft=height,
            streamflow_cfs=data["streamflow_cfs"],
            flood_stage=stage,
            thresholds=thresh,
        )
        results.append(reading)

    return results


# ---------------------------------------------------------------------------
# Open-Meteo Weather Parser
# ---------------------------------------------------------------------------


def classify_wmo_weather_code(code: int) -> Tuple[str, WeatherAlertLevel]:
    """Translate standard WMO weather interpretation code into emergency alert tier.

    WMO Codes:
        - 95, 96, 99: Thunderstorm, severe hail -> WARNING
        - 71, 73, 75, 85, 86: Heavy Snow / Blizzard -> WATCH or WARNING
        - 65, 82: Heavy / Violent Rain -> WATCH
        - 45, 48: Dense Fog -> ADVISORY
    """
    if code in (95, 96, 99):
        return "Severe Thunderstorm with Hail", WeatherAlertLevel.WARNING
    if code in (75, 86):
        return "Heavy Blizzard & Snowfall", WeatherAlertLevel.WARNING
    if code in (71, 73, 85):
        return "Moderate Snowfall", WeatherAlertLevel.WATCH
    if code in (65, 82):
        return "Torrential Rain / Flash Flood Hazard", WeatherAlertLevel.WATCH
    if code in (61, 63, 80, 81):
        return "Moderate Rain", WeatherAlertLevel.ADVISORY
    if code in (45, 48):
        return "Dense Fog & Restricted Visibility", WeatherAlertLevel.ADVISORY
    return "Normal Weather Conditions", WeatherAlertLevel.NONE


def parse_open_meteo_response(payload: Dict[str, Any]) -> WeatherConditions:
    """Parse an Open-Meteo forecast API JSON response into a WeatherConditions entity."""
    lat = float(payload.get("latitude", 0.0))
    lon = float(payload.get("longitude", 0.0))

    current = payload.get("current", {})
    weather_code = int(current.get("weather_code", 0))
    temp_c = float(current.get("temperature_2m", 20.0))
    wind_kmh = float(current.get("wind_speed_10m", 0.0))
    precip_mm = float(current.get("precipitation", 0.0))

    time_str = current.get("time", "")
    try:
        timestamp = datetime.fromisoformat(time_str)
    except (ValueError, TypeError):
        timestamp = datetime.now(timezone.utc)

    summary, alert_level = classify_wmo_weather_code(weather_code)

    # Wind speed overrides
    if wind_kmh >= 75.0:
        alert_level = WeatherAlertLevel.WARNING
        summary = f"Dangerous High Winds ({wind_kmh:.1f} km/h)"
    elif wind_kmh >= 50.0 and alert_level == WeatherAlertLevel.NONE:
        alert_level = WeatherAlertLevel.ADVISORY
        summary = f"Brisk Gusts ({wind_kmh:.1f} km/h)"

    # Precipitation intensity overrides
    if precip_mm >= 25.0:
        alert_level = WeatherAlertLevel.WARNING
        summary = f"Extreme Precipitation ({precip_mm:.1f} mm/hr)"

    return WeatherConditions(
        latitude=lat,
        longitude=lon,
        timestamp=timestamp,
        weather_code=weather_code,
        temperature_c=temp_c,
        wind_speed_kmh=wind_kmh,
        precipitation_mm=precip_mm,
        alert_level=alert_level,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Automated Dynamic Hazard Polygon Generators
# ---------------------------------------------------------------------------


def create_flood_inundation_polygon(
    gauge: USGSGaugeReading,
    buffer_radius_m: Optional[float] = None,
    num_vertices: int = 12,
) -> HazardPolygon:
    """Generate an environmental 2D polygon representing river inundation around a gauge.

    Buffer radius scales dynamically with flood category:
        - MINOR: ~250m radius (Severity: MODERATE, speed factor: 0.50)
        - MODERATE: ~500m radius (Severity: SEVERE, speed factor: 0.20)
        - MAJOR: ~1000m radius (Severity: CRITICAL_BLOCKED, severed road)
    """
    if buffer_radius_m is None:
        if gauge.flood_stage == FloodStage.MAJOR:
            radius = 1000.0
            severity = HazardSeverity.CRITICAL_BLOCKED
            speed_mult = 0.0
        elif gauge.flood_stage == FloodStage.MODERATE:
            radius = 500.0
            severity = HazardSeverity.SEVERE
            speed_mult = 0.20
        elif gauge.flood_stage == FloodStage.MINOR:
            radius = 250.0
            severity = HazardSeverity.MODERATE
            speed_mult = 0.50
        else:
            radius = 100.0
            severity = HazardSeverity.LOW
            speed_mult = 0.75
    else:
        radius = float(buffer_radius_m)
        severity = HazardSeverity.CRITICAL_BLOCKED if gauge.flood_stage == FloodStage.MAJOR else HazardSeverity.SEVERE
        speed_mult = 0.0 if severity == HazardSeverity.CRITICAL_BLOCKED else 0.25

    # Compute regular circular polygon boundary in degrees
    d_lat = (radius / EARTH_RADIUS_METERS) * (180.0 / math.pi)
    cos_lat = math.cos(math.radians(gauge.latitude))
    d_lon = d_lat / max(0.01, cos_lat)

    coords: List[Tuple[float, float]] = []
    for i in range(num_vertices):
        angle = (2.0 * math.pi * i) / num_vertices
        lon = gauge.longitude + (d_lon * math.cos(angle))
        lat = gauge.latitude + (d_lat * math.sin(angle))
        coords.append((lon, lat))

    # Close the ring
    coords.append(coords[0])

    return HazardPolygon(
        hazard_id=f"flood_{gauge.site_id}_{gauge.flood_stage.value}",
        hazard_type=HazardType.FLOOD_INUNDATION,
        severity=severity,
        boundary_coordinates=coords,
        speed_multiplier=speed_mult,
        description=f"USGS Flood Inundation at {gauge.site_name} (Stage: {gauge.flood_stage.value.upper()}, Height: {gauge.gage_height_ft:.1f}ft)",
    )


def create_weather_hazard_polygon(
    weather: WeatherConditions,
    buffer_radius_m: float = 2000.0,
    num_vertices: int = 12,
) -> Optional[HazardPolygon]:
    """Generate a geographic hazard zone for extreme weather alerts."""
    if weather.alert_level not in (WeatherAlertLevel.WATCH, WeatherAlertLevel.WARNING):
        return None

    severity = (
        HazardSeverity.CRITICAL_BLOCKED
        if weather.alert_level == WeatherAlertLevel.WARNING and weather.wind_speed_kmh >= 85.0
        else HazardSeverity.SEVERE
    )
    speed_mult = 0.0 if severity == HazardSeverity.CRITICAL_BLOCKED else 0.35

    d_lat = (buffer_radius_m / EARTH_RADIUS_METERS) * (180.0 / math.pi)
    cos_lat = math.cos(math.radians(weather.latitude))
    d_lon = d_lat / max(0.01, cos_lat)

    coords: List[Tuple[float, float]] = []
    for i in range(num_vertices):
        angle = (2.0 * math.pi * i) / num_vertices
        lon = weather.longitude + (d_lon * math.cos(angle))
        lat = weather.latitude + (d_lat * math.sin(angle))
        coords.append((lon, lat))
    coords.append(coords[0])

    hazard_type = HazardType.WILDFIRE_PERIMETER if weather.temperature_c > 38.0 else HazardType.FLASH_FLOOD

    return HazardPolygon(
        hazard_id=f"weather_{weather.alert_level.value}_{int(weather.latitude*100)}_{int(weather.longitude*100)}",
        hazard_type=hazard_type,
        severity=severity,
        boundary_coordinates=coords,
        speed_multiplier=speed_mult,
        description=f"Severe Weather Hazard: {weather.summary} (Alert: {weather.alert_level.value.upper()})",
    )


# ---------------------------------------------------------------------------
# Automated Graph Environmental Mutation Manager
# ---------------------------------------------------------------------------


@dataclass
class EnvironmentalMutationSummary:
    """Summary metrics of environmental mutations enacted onto a road network."""

    floods_detected: int
    weather_hazards_detected: int
    edges_closed: int
    edges_speed_penalized: int
    active_hazard_polygons: List[HazardPolygon] = field(default_factory=list)


def apply_environmental_hazards_to_graph(
    graph: Graph,
    dynamic_view: DynamicGraphView,
    gauges: Sequence[USGSGaugeReading],
    weather_reports: Sequence[WeatherConditions] = (),
) -> EnvironmentalMutationSummary:
    """Evaluate real-time hydrological and meteorological telemetry and enact graph closures.

    Parameters
    ----------
    graph : Graph
        Base road network graph.
    dynamic_view : DynamicGraphView
        Active dynamic graph mutation view.
    gauges : Sequence[USGSGaugeReading]
        Collection of river gauge observations.
    weather_reports : Sequence[WeatherConditions]
        Collection of surface weather observations.

    Returns
    -------
    EnvironmentalMutationSummary
        Quantitative metrics of applied mutations.
    """
    hazard_polygons: List[HazardPolygon] = []

    # 1. Evaluate Floods
    floods_count = 0
    for gauge in gauges:
        if gauge.is_flooding():
            poly = create_flood_inundation_polygon(gauge)
            hazard_polygons.append(poly)
            floods_count += 1

    # 2. Evaluate Weather
    weather_count = 0
    for weather in weather_reports:
        poly = create_weather_hazard_polygon(weather)
        if poly is not None:
            hazard_polygons.append(poly)
            weather_count += 1

    # 3. Apply to DynamicGraphView
    closed_edges = 0
    penalized_edges = 0

    dynamic_view.begin_transaction()

    for hazard in hazard_polygons:
        mutations = dynamic_view.apply_hazard(hazard, bidirectional=True)
        for mut in mutations:
            if mut.blocked:
                closed_edges += 1
            else:
                penalized_edges += 1

    dynamic_view.commit_transaction()

    return EnvironmentalMutationSummary(
        floods_detected=floods_count,
        weather_hazards_detected=weather_count,
        edges_closed=closed_edges,
        edges_speed_penalized=penalized_edges,
        active_hazard_polygons=hazard_polygons,
    )
