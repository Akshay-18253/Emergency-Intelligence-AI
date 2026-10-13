"""
OpenStreetMap Overpass API Client & Emergency Facility Extractor.
=================================================================
Provides standard-library-compliant query construction, API ingestion, and
clinical capability parsing for municipal emergency infrastructure:
- Overpass QL query builder for geographic bounding boxes and municipal areas
- Emergency amenity classification (Hospitals, Fire Stations, Helipads, Police)
- Clinical capability extractor (Trauma Levels 1-4, Cardiac Care, Burn Centers)
- Safe offline caching and error-isolated HTTP client

Adheres strictly to zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import urllib.error
import urllib.parse
import urllib.request


class OverpassParseError(ValueError):
    """Raised when an Overpass JSON response cannot be parsed or is malformed."""


class OverpassNetworkError(RuntimeError):
    """Raised when an HTTP or network error occurs communicating with Overpass."""


class EmergencyPOIType(Enum):
    """Standardized classification of emergency points of interest."""

    HOSPITAL = "hospital"
    FIRE_STATION = "fire_station"
    AMBULANCE_STATION = "ambulance_station"
    POLICE = "police"
    HELIPAD = "helipad"
    DISPATCH_CENTER = "dispatch_center"
    URGENT_CARE = "urgent_care"


class ClinicalCapability(Enum):
    """Specialized clinical and operational capabilities for emergency facilities."""

    TRAUMA_LEVEL_1 = "trauma_level_1"
    TRAUMA_LEVEL_2 = "trauma_level_2"
    TRAUMA_LEVEL_3 = "trauma_level_3"
    TRAUMA_LEVEL_4 = "trauma_level_4"
    CARDIAC_CARE = "cardiac_care"
    BURN_CENTER = "burn_center"
    PEDIATRIC_CARE = "pediatric_care"
    STROKE_CENTER = "stroke_center"
    HELIPAD = "helipad"
    HAZMAT_DECON = "hazmat_decon"


@dataclass
class ExtractedEmergencyPOI:
    """A verified emergency facility extracted from OpenStreetMap.

    Attributes
    ----------
    osm_id : int
        The unique OpenStreetMap identifier.
    osm_type : str
        The OSM primitive element type ('node', 'way', 'relation').
    poi_type : EmergencyPOIType
        The standardized classification of the emergency amenity.
    name : str
        Human-readable facility name.
    latitude : float
        Geographic latitude in decimal degrees.
    longitude : float
        Geographic longitude in decimal degrees.
    capabilities : Set[ClinicalCapability]
        Set of specialized clinical or operational certifications.
    trauma_level : Optional[int]
        Designated trauma care level (1 = highest tertiary, 4 = basic).
    apparatus_bays : Optional[int]
        Number of vehicular apparatus bays (for fire/ambulance stations).
    operator : Optional[str]
        Managing municipal or healthcare authority.
    phone : Optional[str]
        Emergency contact or dispatch telephone number.
    address : Optional[str]
        Street address if cataloged in OSM tags.
    raw_tags : Dict[str, str]
        Original unparsed OSM key-value attributes.
    """

    osm_id: int
    osm_type: str
    poi_type: EmergencyPOIType
    name: str
    latitude: float
    longitude: float
    capabilities: Set[ClinicalCapability] = field(default_factory=set)
    trauma_level: Optional[int] = None
    apparatus_bays: Optional[int] = None
    operator: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    raw_tags: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not math.isfinite(self.latitude) or not math.isfinite(self.longitude):
            raise ValueError("Coordinates must be finite numbers.")
        if not (-90.0 <= self.latitude <= 90.0):
            raise ValueError(f"Invalid latitude: {self.latitude}. Must be in [-90, 90].")
        if not (-180.0 <= self.longitude <= 180.0):
            raise ValueError(f"Invalid longitude: {self.longitude}. Must be in [-180, 180].")
        if not isinstance(self.poi_type, EmergencyPOIType):
            if isinstance(self.poi_type, str):
                self.poi_type = EmergencyPOIType(self.poi_type)
            else:
                raise TypeError(f"Invalid poi_type: {self.poi_type}")

    def has_capability(self, capability: Union[ClinicalCapability, str]) -> bool:
        """Returns True if the facility holds the specified clinical capability."""
        if isinstance(capability, str):
            try:
                capability = ClinicalCapability(capability)
            except ValueError:
                return False
        return capability in self.capabilities

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the extracted POI to a JSON-compatible dictionary."""
        return {
            "osm_id": self.osm_id,
            "osm_type": self.osm_type,
            "poi_type": self.poi_type.value,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "capabilities": sorted([c.value for c in self.capabilities]),
            "trauma_level": self.trauma_level,
            "apparatus_bays": self.apparatus_bays,
            "operator": self.operator,
            "phone": self.phone,
            "address": self.address,
            "raw_tags": dict(self.raw_tags),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractedEmergencyPOI:
        """Constructs an ExtractedEmergencyPOI from a dictionary representation."""
        caps = {ClinicalCapability(c) for c in data.get("capabilities", [])}
        return cls(
            osm_id=int(data["osm_id"]),
            osm_type=str(data.get("osm_type", "node")),
            poi_type=EmergencyPOIType(data["poi_type"]),
            name=str(data["name"]),
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            capabilities=caps,
            trauma_level=int(data["trauma_level"]) if data.get("trauma_level") is not None else None,
            apparatus_bays=int(data["apparatus_bays"]) if data.get("apparatus_bays") is not None else None,
            operator=data.get("operator"),
            phone=data.get("phone"),
            address=data.get("address"),
            raw_tags=dict(data.get("raw_tags", {})),
        )


def build_emergency_poi_query(
    bbox: Optional[Tuple[float, float, float, float]] = None,
    area_name: Optional[str] = None,
    poi_types: Optional[List[EmergencyPOIType]] = None,
    timeout_seconds: int = 25,
) -> str:
    """Constructs a valid Overpass QL query string for emergency facilities.

    Parameters
    ----------
    bbox : Optional[Tuple[float, float, float, float]]
        Geographic bounding box as (min_lat, min_lon, max_lat, max_lon).
    area_name : Optional[str]
        Named municipal area (e.g. 'Seattle', 'Pittsburgh').
    poi_types : Optional[List[EmergencyPOIType]]
        Subset of emergency POI types to query. Defaults to all types.
    timeout_seconds : int
        Overpass server query timeout in seconds (default 25s).

    Returns
    -------
    str
        Syntactically valid Overpass QL query text.
    """
    if bbox is None and area_name is None:
        raise ValueError("Either bbox or area_name must be specified.")

    if bbox is not None:
        min_lat, min_lon, max_lat, max_lon = bbox
        if not (-90.0 <= min_lat <= max_lat <= 90.0):
            raise ValueError(f"Invalid latitude bounds: ({min_lat}, {max_lat})")
        if not (-180.0 <= min_lon <= max_lon <= 180.0):
            raise ValueError(f"Invalid longitude bounds: ({min_lon}, {max_lon})")
        filter_scope = f"({min_lat},{min_lon},{max_lat},{max_lon})"
    else:
        escaped_area = area_name.replace('"', '\\"')  # type: ignore[union-attr]
        filter_scope = f"(area.searchArea)"

    if poi_types is None:
        selected_types = list(EmergencyPOIType)
    else:
        selected_types = list(poi_types)

    tag_selectors: List[Tuple[str, str]] = []
    for ptype in selected_types:
        if ptype == EmergencyPOIType.HOSPITAL:
            tag_selectors.extend([("amenity", "hospital"), ("healthcare", "hospital")])
        elif ptype == EmergencyPOIType.FIRE_STATION:
            tag_selectors.extend([("amenity", "fire_station"), ("emergency", "fire_station")])
        elif ptype == EmergencyPOIType.AMBULANCE_STATION:
            tag_selectors.append(("emergency", "ambulance_station"))
        elif ptype == EmergencyPOIType.POLICE:
            tag_selectors.append(("amenity", "police"))
        elif ptype == EmergencyPOIType.HELIPAD:
            tag_selectors.extend([("aeroway", "helipad"), ("emergency", "helipad")])
        elif ptype == EmergencyPOIType.DISPATCH_CENTER:
            tag_selectors.append(("emergency", "control_centre"))
        elif ptype == EmergencyPOIType.URGENT_CARE:
            tag_selectors.extend([("amenity", "clinic"), ("healthcare", "centre")])

    # De-duplicate tag selectors
    unique_selectors = sorted(list(set(tag_selectors)))

    lines = [f"[out:json][timeout:{int(timeout_seconds)}];"]
    if area_name is not None and bbox is None:
        lines.append(f'area["name"="{escaped_area}"]->.searchArea;')

    lines.append("(")
    for k, v in unique_selectors:
        for geom in ("node", "way", "relation"):
            lines.append(f'  {geom}["{k}"="{v}"]{filter_scope};')
    lines.append(");")
    lines.append("out center tags;")

    return "\n".join(lines)


def _parse_capabilities(tags: Dict[str, str], poi_type: EmergencyPOIType) -> Tuple[Set[ClinicalCapability], Optional[int]]:
    """Infers clinical capabilities and trauma tiers from raw OSM tags."""
    capabilities: Set[ClinicalCapability] = set()
    trauma_level: Optional[int] = None

    # 1. Trauma Level tags
    trauma_tag = tags.get("emergency:trauma_level") or tags.get("trauma_level")
    if trauma_tag:
        try:
            level_num = int(trauma_tag.strip())
            if level_num in (1, 2, 3, 4):
                trauma_level = level_num
                if level_num == 1:
                    capabilities.add(ClinicalCapability.TRAUMA_LEVEL_1)
                elif level_num == 2:
                    capabilities.add(ClinicalCapability.TRAUMA_LEVEL_2)
                elif level_num == 3:
                    capabilities.add(ClinicalCapability.TRAUMA_LEVEL_3)
                elif level_num == 4:
                    capabilities.add(ClinicalCapability.TRAUMA_LEVEL_4)
        except ValueError:
            pass

    # 2. Healthcare speciality tags
    specialities = tags.get("healthcare:speciality", "").lower()
    designations = tags.get("designation", "").lower()
    description = tags.get("description", "").lower()
    combined_text = f"{specialities} {designations} {description} {tags.get('name', '').lower()}"

    if "cardiac" in combined_text or "cardiology" in combined_text or "heart" in combined_text:
        capabilities.add(ClinicalCapability.CARDIAC_CARE)

    if "burn" in combined_text:
        capabilities.add(ClinicalCapability.BURN_CENTER)

    if "pediatric" in combined_text or "children" in combined_text:
        capabilities.add(ClinicalCapability.PEDIATRIC_CARE)

    if "stroke" in combined_text or "neuro" in combined_text:
        capabilities.add(ClinicalCapability.STROKE_CENTER)

    if (
        tags.get("emergency:helipad") == "yes"
        or tags.get("helipad") == "yes"
        or tags.get("aeroway") == "helipad"
        or "helipad" in combined_text
    ):
        capabilities.add(ClinicalCapability.HELIPAD)

    if (
        tags.get("emergency:decontamination") == "yes"
        or tags.get("hazmat") == "yes"
        or "hazmat" in combined_text
    ):
        capabilities.add(ClinicalCapability.HAZMAT_DECON)

    return capabilities, trauma_level


def _parse_apparatus_bays(tags: Dict[str, str]) -> Optional[int]:
    """Infers vehicle capacity from fire station or ambulance depot tags."""
    for key in ("fire_station:engine_bays", "fire_station:bays", "bays", "capacity"):
        val = tags.get(key)
        if val:
            try:
                bays = int(val.strip())
                if bays > 0:
                    return bays
            except ValueError:
                pass
    return None


def parse_overpass_response(payload: Union[Dict[str, Any], str]) -> List[ExtractedEmergencyPOI]:
    """Parses raw Overpass JSON response payload into structured ExtractedEmergencyPOI objects.

    Parameters
    ----------
    payload : Union[Dict[str, Any], str]
        Parsed JSON dictionary or raw JSON string received from Overpass.

    Returns
    -------
    List[ExtractedEmergencyPOI]
        List of successfully parsed and verified emergency facilities.
    """
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as err:
            raise OverpassParseError(f"Failed to parse Overpass response as JSON: {err}") from err
    elif isinstance(payload, dict):
        data = payload
    else:
        raise OverpassParseError(f"Expected dict or str payload, got {type(payload)}")

    if not isinstance(data, dict) or "elements" not in data:
        raise OverpassParseError("Overpass response missing mandatory 'elements' array.")

    results: List[ExtractedEmergencyPOI] = []
    elements = data.get("elements", [])

    for el in elements:
        if not isinstance(el, dict):
            continue

        osm_id = el.get("id")
        osm_type = el.get("type", "node")
        tags = el.get("tags", {})
        if not isinstance(tags, dict) or osm_id is None:
            continue

        # Coordinate extraction (node lat/lon vs way/relation center)
        lat = el.get("lat")
        lon = el.get("lon")
        if (lat is None or lon is None) and "center" in el:
            center = el.get("center", {})
            lat = center.get("lat")
            lon = center.get("lon")

        if lat is None or lon is None:
            continue

        try:
            f_lat = float(lat)
            f_lon = float(lon)
            if not (-90.0 <= f_lat <= 90.0 and -180.0 <= f_lon <= 180.0):
                continue
            if not (math.isfinite(f_lat) and math.isfinite(f_lon)):
                continue
        except (ValueError, TypeError):
            continue

        # Classify POI Type
        amenity = tags.get("amenity", "")
        emergency_tag = tags.get("emergency", "")
        aeroway = tags.get("aeroway", "")
        healthcare = tags.get("healthcare", "")

        poi_type: Optional[EmergencyPOIType] = None
        if amenity == "hospital" or healthcare == "hospital":
            poi_type = EmergencyPOIType.HOSPITAL
        elif amenity == "fire_station" or emergency_tag == "fire_station":
            poi_type = EmergencyPOIType.FIRE_STATION
        elif emergency_tag == "ambulance_station":
            poi_type = EmergencyPOIType.AMBULANCE_STATION
        elif amenity == "police":
            poi_type = EmergencyPOIType.POLICE
        elif aeroway == "helipad" or emergency_tag == "helipad":
            poi_type = EmergencyPOIType.HELIPAD
        elif emergency_tag == "control_centre":
            poi_type = EmergencyPOIType.DISPATCH_CENTER
        elif amenity == "clinic" or healthcare in ("centre", "clinic"):
            poi_type = EmergencyPOIType.URGENT_CARE

        if poi_type is None:
            continue

        # Name fallback
        raw_name = tags.get("name", "").strip()
        if not raw_name:
            type_label = poi_type.value.replace("_", " ").title()
            name = f"Unnamed {type_label} (OSM:{osm_id})"
        else:
            name = raw_name

        capabilities, trauma_level = _parse_capabilities(tags, poi_type)
        apparatus_bays = _parse_apparatus_bays(tags)

        # Address construction
        street = tags.get("addr:street")
        housenumber = tags.get("addr:housenumber")
        city = tags.get("addr:city")
        address_parts = [p for p in (housenumber, street, city) if p]
        address = ", ".join(address_parts) if address_parts else None

        operator = tags.get("operator")
        phone = tags.get("phone") or tags.get("contact:phone")

        poi = ExtractedEmergencyPOI(
            osm_id=int(osm_id),
            osm_type=str(osm_type),
            poi_type=poi_type,
            name=name,
            latitude=f_lat,
            longitude=f_lon,
            capabilities=capabilities,
            trauma_level=trauma_level,
            apparatus_bays=apparatus_bays,
            operator=operator,
            phone=phone,
            address=address,
            raw_tags={str(k): str(v) for k, v in tags.items()},
        )
        results.append(poi)

    return results


def fetch_or_load_overpass_pois(
    query: str,
    endpoint: str = "https://overpass-api.de/api/interpreter",
    timeout: float = 10.0,
    cache_path: Optional[Union[Path, str]] = None,
    force_refresh: bool = False,
) -> List[ExtractedEmergencyPOI]:
    """Fetches emergency facilities from an Overpass endpoint or loads from local cache.

    Guarantees deterministic offline execution when cache_path exists and force_refresh is False.

    Parameters
    ----------
    query : str
        Overpass QL query text.
    endpoint : str
        Overpass interpreter URL (default public main instance).
    timeout : float
        HTTP timeout in seconds (default 10s).
    cache_path : Optional[Union[Path, str]]
        Local file path to read/write cached JSON responses.
    force_refresh : bool
        If True, ignores existing cache and queries the network endpoint.

    Returns
    -------
    List[ExtractedEmergencyPOI]
        List of parsed emergency infrastructure facilities.

    Raises
    ------
    OverpassNetworkError
        If network communication fails or times out.
    OverpassParseError
        If response payload cannot be decoded.
    """
    path_obj = Path(cache_path) if cache_path is not None else None

    # 1. Attempt cache load
    if path_obj is not None and path_obj.is_file() and not force_refresh:
        try:
            cached_text = path_obj.read_text(encoding="utf-8")
            return parse_overpass_response(cached_text)
        except Exception as err:
            if force_refresh:
                pass
            else:
                raise OverpassParseError(f"Failed to read cached Overpass data at '{path_obj}': {err}") from err

    # 2. Network query
    post_data = query.encode("utf-8")
    req = urllib.request.Request(
        url=endpoint,
        data=post_data,
        headers={
            "User-Agent": "EmergencyIntelligenceAI/0.7.0 (GSOC-Research; OpenGeospatial)",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            status = response.status
            if status != 200:
                raise OverpassNetworkError(f"Overpass endpoint returned HTTP {status}")
            raw_bytes = response.read()
            raw_text = raw_bytes.decode("utf-8")
    except urllib.error.HTTPError as err:
        raise OverpassNetworkError(f"Overpass HTTP Error {err.code}: {err.reason}") from err
    except urllib.error.URLError as err:
        raise OverpassNetworkError(f"Overpass URL/Connection Error: {err.reason}") from err
    except Exception as err:
        raise OverpassNetworkError(f"Overpass network request failed: {err}") from err

    # 3. Save cache if path supplied
    if path_obj is not None:
        try:
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            path_obj.write_text(raw_text, encoding="utf-8")
        except OSError:
            pass

    return parse_overpass_response(raw_text)
