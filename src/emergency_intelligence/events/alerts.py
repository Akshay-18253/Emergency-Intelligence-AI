"""
OASIS Common Alerting Protocol (CAP v1.2) & Dynamic Alert Ingestor.
===================================================================
Implements an RFC-compliant parser for OASIS CAP v1.2 (ITU-T X.1303) XML emergency
alert documents and GeoJSON alert feeds. Converts external civil protection,
FEMA/IPAWS, and meteorological alerts directly into active `HazardPolygon`
and `EdgeMutation` instances.

Adheres strictly to zero external runtime dependencies (using Python standard
library `xml.etree.ElementTree` and `json`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from typing import Any, Dict, List, Optional, Tuple, Union
import xml.etree.ElementTree as ET

from emergency_intelligence.events.hazards import (
    HazardPolygon,
    HazardSeverity,
    HazardType,
)


class CAPMsgType(str, Enum):
    """OASIS CAP message type classification."""

    ALERT = "Alert"
    UPDATE = "Update"
    CANCEL = "Cancel"
    ACK = "Ack"
    ERROR = "Error"


class CAPUrgency(str, Enum):
    """OASIS CAP urgency classification."""

    IMMEDIATE = "Immediate"
    EXPECTED = "Expected"
    FUTURE = "Future"
    PAST = "Past"
    UNKNOWN = "Unknown"


class CAPSeverity(str, Enum):
    """OASIS CAP severity classification."""

    EXTREME = "Extreme"
    SEVERE = "Severe"
    MODERATE = "Moderate"
    MINOR = "Minor"
    UNKNOWN = "Unknown"


class CAPCertainty(str, Enum):
    """OASIS CAP certainty classification."""

    OBSERVED = "Observed"
    LIKELY = "Likely"
    POSSIBLE = "Possible"
    UNLIKELY = "Unlikely"
    UNKNOWN = "Unknown"


# Mapping from OASIS CAP severity to our internal HazardSeverity
_SEVERITY_MAP: Dict[str, HazardSeverity] = {
    CAPSeverity.EXTREME.value: HazardSeverity.CRITICAL_BLOCKED,
    CAPSeverity.SEVERE.value: HazardSeverity.SEVERE,
    CAPSeverity.MODERATE.value: HazardSeverity.MODERATE,
    CAPSeverity.MINOR.value: HazardSeverity.LOW,
    CAPSeverity.UNKNOWN.value: HazardSeverity.MODERATE,
}


@dataclass
class CAPAlert:
    """Parsed representation of an OASIS CAP v1.2 emergency alert document.

    Attributes
    ----------
    identifier : str
        Globally unique alert message ID.
    sender : str
        Agency / authority issuing the alert (e.g. 'NWS-SF-BAY', 'FEMA-IPAWS').
    sent_at : datetime
        Timestamp when the alert was published in UTC.
    msg_type : CAPMsgType
        Alert action type (Alert, Update, Cancel).
    event : str
        Human-readable disaster event name (e.g. 'Flash Flood Warning', 'Toxic Smoke Plume').
    urgency : CAPUrgency
        Response urgency.
    severity : CAPSeverity
        Hazard severity.
    certainty : CAPCertainty
        Event confidence.
    description : str
        Detailed textual hazard advisory.
    polygons : List[List[Tuple[float, float]]]
        List of closed 2D spatial coordinate boundaries in [longitude, latitude] order.
    expires_at : Optional[datetime]
        Expiration timestamp in UTC.
    metadata : Dict[str, Any]
        Raw parameters and event tags.
    """

    identifier: str
    sender: str
    sent_at: datetime
    msg_type: CAPMsgType
    event: str
    urgency: CAPUrgency
    severity: CAPSeverity
    certainty: CAPCertainty
    description: str = ""
    polygons: List[List[Tuple[float, float]]] = field(default_factory=list)
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_hazard_polygons(self) -> List[HazardPolygon]:
        """Converts the parsed CAP alert into internal HazardPolygon instances."""
        hazards: List[HazardPolygon] = []
        internal_severity = _SEVERITY_MAP.get(self.severity.value, HazardSeverity.SEVERE)

        # Infer hazard type from event title
        evt_lower = self.event.lower()
        if "flash" in evt_lower:
            h_type = HazardType.FLASH_FLOOD
            speed_mult = 0.0 if self.severity in (CAPSeverity.EXTREME, CAPSeverity.SEVERE) else 0.3
        elif "flood" in evt_lower:
            h_type = HazardType.FLOOD_INUNDATION
            speed_mult = 0.0 if self.severity in (CAPSeverity.EXTREME, CAPSeverity.SEVERE) else 0.3
        elif "fire" in evt_lower or "wildfire" in evt_lower:
            h_type = HazardType.WILDFIRE_PERIMETER
            speed_mult = 0.0
        elif "smoke" in evt_lower or "gas" in evt_lower or "chemical" in evt_lower or "hazmat" in evt_lower:
            h_type = HazardType.TOXIC_GAS_PLUME
            speed_mult = 0.4
        elif "collapse" in evt_lower or "quake" in evt_lower or "earthquake" in evt_lower:
            h_type = HazardType.ROAD_COLLAPSE
            speed_mult = 0.0
        elif "debris" in evt_lower or "downed" in evt_lower:
            h_type = HazardType.STRUCTURAL_DEBRIS
            speed_mult = 0.2
        elif "unrest" in evt_lower:
            h_type = HazardType.CIVIL_UNREST
            speed_mult = 0.3
        else:
            h_type = HazardType.FLOOD_INUNDATION
            speed_mult = 0.0 if self.severity == CAPSeverity.EXTREME else 0.5

        for idx, poly_coords in enumerate(self.polygons):
            h_id = f"cap_{self.identifier}_{idx + 1}"
            hazards.append(
                HazardPolygon(
                    hazard_id=h_id,
                    hazard_type=h_type,
                    severity=internal_severity,
                    boundary_coordinates=poly_coords,
                    speed_multiplier=speed_mult,
                    description=f"{self.event}: {self.description[:120]}",
                    expires_at=self.expires_at,
                    metadata={
                        "cap_identifier": self.identifier,
                        "sender": self.sender,
                        "urgency": self.urgency.value,
                        "severity": self.severity.value,
                        "certainty": self.certainty.value,
                    },
                )
            )

        return hazards

    def to_dict(self) -> Dict[str, Any]:
        """Serializes alert to dictionary."""
        return {
            "identifier": self.identifier,
            "sender": self.sender,
            "sent_at": self.sent_at.isoformat(),
            "msg_type": self.msg_type.value,
            "event": self.event,
            "urgency": self.urgency.value,
            "severity": self.severity.value,
            "certainty": self.certainty.value,
            "description": self.description,
            "polygons": [[[p[0], p[1]] for p in poly] for poly in self.polygons],
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": dict(self.metadata),
        }


def parse_cap_xml(xml_content: str) -> CAPAlert:
    """Parses an OASIS CAP v1.2 XML document string into a `CAPAlert`.

    Handles XML namespaces (e.g. `urn:oasis:names:tc:emergency:cap:1.2`)
    transparently.

    Parameters
    ----------
    xml_content : str
        The raw XML payload of the CAP alert.

    Returns
    -------
    CAPAlert
        Parsed alert domain model.
    """
    try:
        root = ET.fromstring(xml_content)
    except Exception as exc:
        raise ValueError(f"Failed to parse CAP XML: {exc}") from exc

    # Helper to strip namespace from tags
    def find_elem(parent: ET.Element, tag_name: str) -> Optional[ET.Element]:
        for child in parent:
            # Strip {namespace}
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child_tag == tag_name:
                return child
        return None

    def find_all_elems(parent: ET.Element, tag_name: str) -> List[ET.Element]:
        matches: List[ET.Element] = []
        for child in parent:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if child_tag == tag_name:
                matches.append(child)
        return matches

    def get_text(parent: ET.Element, tag_name: str, default: str = "") -> str:
        el = find_elem(parent, tag_name)
        return (el.text or "").strip() if el is not None else default

    identifier = get_text(root, "identifier", "ALERT-UNKNOWN")
    sender = get_text(root, "sender", "UNKNOWN_AGENCY")
    msg_type_str = get_text(root, "msgType", CAPMsgType.ALERT.value)

    sent_str = get_text(root, "sent")
    try:
        sent_at = datetime.fromisoformat(sent_str) if sent_str else datetime.now(timezone.utc)
    except Exception:
        sent_at = datetime.now(timezone.utc)

    # Info block
    info_el = find_elem(root, "info")
    if info_el is None:
        return CAPAlert(
            identifier=identifier,
            sender=sender,
            sent_at=sent_at,
            msg_type=CAPMsgType(msg_type_str) if msg_type_str in [m.value for m in CAPMsgType] else CAPMsgType.ALERT,
            event="General Emergency",
            urgency=CAPUrgency.IMMEDIATE,
            severity=CAPSeverity.SEVERE,
            certainty=CAPCertainty.OBSERVED,
        )

    event = get_text(info_el, "event", "Emergency Incident")
    urgency_str = get_text(info_el, "urgency", CAPUrgency.IMMEDIATE.value)
    severity_str = get_text(info_el, "severity", CAPSeverity.SEVERE.value)
    certainty_str = get_text(info_el, "certainty", CAPCertainty.OBSERVED.value)
    description = get_text(info_el, "description", "")

    expires_str = get_text(info_el, "expires")
    expires_at: Optional[datetime] = None
    if expires_str:
        try:
            expires_at = datetime.fromisoformat(expires_str)
        except Exception:
            expires_at = None

    # Parse spatial polygons inside <area> blocks
    polygons: List[List[Tuple[float, float]]] = []
    area_elems = find_all_elems(info_el, "area")

    for area in area_elems:
        poly_elems = find_all_elems(area, "polygon")
        for p_el in poly_elems:
            poly_text = (p_el.text or "").strip()
            if not poly_text:
                continue

            # Standard CAP v1.2 polygon format: space-delimited "lat,lon lat,lon lat,lon"
            points: List[Tuple[float, float]] = []
            for pair in poly_text.split():
                if "," in pair:
                    parts = pair.split(",")
                    try:
                        lat_val = float(parts[0].strip())
                        lon_val = float(parts[1].strip())
                        # Store in standard GIS [longitude, latitude] order
                        points.append((lon_val, lat_val))
                    except ValueError:
                        continue

            if len(points) >= 3:
                # Close polygon if not already closed
                if points[0] != points[-1]:
                    points.append(points[0])
                polygons.append(points)

    return CAPAlert(
        identifier=identifier,
        sender=sender,
        sent_at=sent_at,
        msg_type=CAPMsgType(msg_type_str) if msg_type_str in [m.value for m in CAPMsgType] else CAPMsgType.ALERT,
        event=event,
        urgency=CAPUrgency(urgency_str) if urgency_str in [u.value for u in CAPUrgency] else CAPUrgency.IMMEDIATE,
        severity=CAPSeverity(severity_str) if severity_str in [s.value for s in CAPSeverity] else CAPSeverity.SEVERE,
        certainty=CAPCertainty(certainty_str) if certainty_str in [c.value for c in CAPCertainty] else CAPCertainty.OBSERVED,
        description=description,
        polygons=polygons,
        expires_at=expires_at,
    )


def parse_geojson_alerts(geojson_payload: Union[str, Dict[str, Any]]) -> List[HazardPolygon]:
    """Parses a standard RFC 7946 GeoJSON FeatureCollection into HazardPolygon instances.

    Common format for USGS Earthquake feeds, NWS active alert shapefiles,
    and municipal open data disaster streams.
    """
    if isinstance(geojson_payload, str):
        data = json.loads(geojson_payload)
    else:
        data = geojson_payload

    hazards: List[HazardPolygon] = []
    features = data.get("features", [])

    for idx, feat in enumerate(features):
        geom = feat.get("geometry", {})
        props = feat.get("properties", {})
        g_type = geom.get("type")

        if g_type != "Polygon" or not geom.get("coordinates"):
            continue

        exterior_ring = geom["coordinates"][0]
        pts = [(float(p[0]), float(p[1])) for p in exterior_ring]
        if len(pts) < 3:
            continue

        h_id = str(feat.get("id", props.get("id", f"geojson_alert_{idx + 1}")))
        h_type_str = str(props.get("hazard_type", props.get("event", "flood"))).lower()

        if "fire" in h_type_str:
            h_type = HazardType.WILDFIRE_PERIMETER
        elif "smoke" in h_type_str or "gas" in h_type_str:
            h_type = HazardType.TOXIC_GAS_PLUME
        elif "collapse" in h_type_str:
            h_type = HazardType.ROAD_COLLAPSE
        elif "flash" in h_type_str:
            h_type = HazardType.FLASH_FLOOD
        elif "debris" in h_type_str:
            h_type = HazardType.STRUCTURAL_DEBRIS
        else:
            h_type = HazardType.FLOOD_INUNDATION

        hazards.append(
            HazardPolygon(
                hazard_id=h_id,
                hazard_type=h_type,
                severity=HazardSeverity(props.get("severity", HazardSeverity.SEVERE.value)),
                boundary_coordinates=pts,
                speed_multiplier=float(props.get("speed_multiplier", 0.0)),
                description=str(props.get("description", props.get("event", ""))),
                metadata=dict(props),
            )
        )

    return hazards
