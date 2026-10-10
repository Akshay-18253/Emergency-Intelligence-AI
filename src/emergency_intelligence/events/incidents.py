"""
Incident and emergency call data models.

Defines the core domain abstractions for dynamic emergency events:
- EmergencyType: Taxonomy of incident categories (fire, medical, hazmat, flood, etc.)
- UrgencyLevel: Triage priority tiers (Echo/Delta to Alpha)
- ApparatusType: Required emergency vehicle types (ALS ambulance, engine, ladder, etc.)
- Incident: Strongly typed incident record with geocoordinates, apparatus requirements,
  timestamps, and status tracking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class EmergencyType(str, Enum):
    """Standardized taxonomy of emergency incident categories."""

    STRUCTURE_FIRE = "structure_fire"
    WILDLAND_FIRE = "wildland_fire"
    CARDIAC_ARREST = "cardiac_arrest"
    TRAUMA_MAJOR = "trauma_major"
    HAZMAT_SPILL = "hazmat_spill"
    FLASH_FLOOD = "flash_flood"
    STRUCTURAL_COLLAPSE = "structural_collapse"
    ROAD_TRAFFIC_COLLISION = "road_traffic_collision"
    MEDICAL_GENERAL = "medical_general"


class UrgencyLevel(str, Enum):
    """Triage urgency tiers following emergency medical dispatch standards.

    Priority 1 (Echo/Delta) represents an immediate life threat requiring maximum
    response velocity, down to Priority 4 (Alpha) for routine non-emergency calls.
    """

    PRIORITY_1_ECHO = "priority_1_echo"
    PRIORITY_2_DELTA = "priority_2_delta"
    PRIORITY_3_BRAVO = "priority_3_bravo"
    PRIORITY_4_ALPHA = "priority_4_alpha"


class ApparatusType(str, Enum):
    """Required emergency vehicle capabilities."""

    AMBULANCE_ALS = "ambulance_als"  # Advanced Life Support (paramedic unit)
    AMBULANCE_BLS = "ambulance_bls"  # Basic Life Support
    FIRE_ENGINE = "fire_engine"      # Pumper with water, hose, pump
    LADDER_TRUCK = "ladder_truck"    # Aerial ladder / tower
    HEAVY_RESCUE = "heavy_rescue"    # Technical extraction & collapse tools
    HAZMAT_UNIT = "hazmat_unit"      # Decontamination & containment
    BATTALION_CHIEF = "battalion_chief"  # Incident command vehicle


@dataclass
class Incident:
    """Represents a discrete emergency call / incident in the field.

    Attributes:
        incident_id: Unique string identifier for this incident.
        emergency_type: Category of the emergency.
        urgency: Triage priority tier.
        coordinates: (longitude, latitude) tuple in WGS 84 format.
        required_apparatus: List of apparatus types required for adequate response.
        description: Free-text synopsis or caller notes.
        reported_at: Timestamp when incident was reported (defaults to UTC now).
        active: True if the incident is currently active and awaiting resolution.
        metadata: Arbitrary additional incident telemetry (e.g. caller ID, floor number).
    """

    incident_id: str
    emergency_type: EmergencyType
    urgency: UrgencyLevel
    coordinates: Tuple[float, float]
    node_id: Optional[str] = None
    required_apparatus: List[ApparatusType] = field(default_factory=list)
    description: str = ""
    reported_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.incident_id or not isinstance(self.incident_id, str):
            raise ValueError("Incident.incident_id must be a non-empty string.")

        if not isinstance(self.emergency_type, EmergencyType):
            if isinstance(self.emergency_type, str):
                self.emergency_type = EmergencyType(self.emergency_type)
            else:
                raise TypeError("Incident.emergency_type must be an EmergencyType enum.")

        if not isinstance(self.urgency, UrgencyLevel):
            if isinstance(self.urgency, str):
                self.urgency = UrgencyLevel(self.urgency)
            else:
                raise TypeError("Incident.urgency must be an UrgencyLevel enum.")

        if not isinstance(self.coordinates, (tuple, list)) or len(self.coordinates) != 2:
            raise ValueError("Incident.coordinates must be a (longitude, latitude) pair.")

        lon, lat = float(self.coordinates[0]), float(self.coordinates[1])
        if not (-180.0 <= lon <= 180.0):
            raise ValueError(f"Longitude {lon} out of valid WGS 84 range [-180, 180].")
        if not (-90.0 <= lat <= 90.0):
            raise ValueError(f"Latitude {lat} out of valid WGS 84 range [-90, 90].")
        self.coordinates = (lon, lat)

        # Standardize apparatus types
        parsed_apparatus: List[ApparatusType] = []
        for app in self.required_apparatus:
            if isinstance(app, ApparatusType):
                parsed_apparatus.append(app)
            elif isinstance(app, str):
                parsed_apparatus.append(ApparatusType(app))
            else:
                raise TypeError(f"Invalid apparatus specification: {app}")
        self.required_apparatus = parsed_apparatus

    @property
    def longitude(self) -> float:
        """Convenience property for longitude."""
        return self.coordinates[0]

    @property
    def latitude(self) -> float:
        """Convenience property for latitude."""
        return self.coordinates[1]

    def is_life_threatening(self) -> bool:
        """Returns True if the incident is designated Priority 1 Echo or Priority 2 Delta."""
        return self.urgency in (UrgencyLevel.PRIORITY_1_ECHO, UrgencyLevel.PRIORITY_2_DELTA)

    def requires_apparatus(self, apparatus: ApparatusType) -> bool:
        """Returns True if the incident explicitly requires the specified apparatus."""
        return apparatus in self.required_apparatus

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the incident to a JSON-compatible dictionary."""
        return {
            "incident_id": self.incident_id,
            "emergency_type": self.emergency_type.value,
            "urgency": self.urgency.value,
            "coordinates": [self.longitude, self.latitude],
            "node_id": self.node_id,
            "required_apparatus": [app.value for app in self.required_apparatus],
            "description": self.description,
            "reported_at": self.reported_at.isoformat(),
            "active": self.active,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Incident:
        """Constructs an Incident instance from a dictionary."""
        reported_at = data.get("reported_at")
        if isinstance(reported_at, str):
            dt = datetime.fromisoformat(reported_at)
        elif isinstance(reported_at, datetime):
            dt = reported_at
        else:
            dt = datetime.now(timezone.utc)

        return cls(
            incident_id=str(data["incident_id"]),
            emergency_type=EmergencyType(data["emergency_type"]),
            urgency=UrgencyLevel(data["urgency"]),
            coordinates=(float(data["coordinates"][0]), float(data["coordinates"][1])),
            node_id=str(data["node_id"]) if data.get("node_id") is not None else None,
            required_apparatus=[ApparatusType(app) for app in data.get("required_apparatus", [])],
            description=str(data.get("description", "")),
            reported_at=dt,
            active=bool(data.get("active", True)),
            metadata=dict(data.get("metadata", {})),
        )
