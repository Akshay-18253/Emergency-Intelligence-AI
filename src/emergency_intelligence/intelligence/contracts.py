"""
AI Boundary & Structured Domain Contracts (Milestone 5.1).
===========================================================
Defines the authoritative boundary between untrusted natural-language
interpretations and deterministic emergency routing/dispatch processing.

Architectural Invariant:
------------------------
The AI interprets the emergency. The deterministic engine calculates the route.
Untrusted model proposals (ProposedIncidentInterpretation) must NEVER be treated
as authoritative operational data. They must pass through deterministic domain
validation into an immutable ValidatedIncidentContract before being consumed
by downstream emergency routing, policy, or fleet allocation engines.

Adheres strictly to zero external runtime dependencies (100% Python standard library).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid

from emergency_intelligence.events.hazards import HazardSeverity, HazardType
from emergency_intelligence.events.incidents import (
    ApparatusType,
    EmergencyType,
    Incident,
    UrgencyLevel,
)


class LocationProvenanceType(str, Enum):
    """Origin and verification lineage of location information."""

    VERIFIED_COORDINATES = "verified_coordinates"  # CAD / GPS hardware telemetry
    GEOCODED_ADDRESS = "geocoded_address"          # Authoritatively resolved geocode
    NETWORK_NODE_SNAPPED = "network_node_snapped"  # Snapped directly to known graph junction
    CALLER_DESCRIPTION = "caller_description"      # Natural-language text only (unresolved)
    UNKNOWN = "unknown"                            # Location entirely absent or unidentified


@dataclass(frozen=True)
class LocationProvenance:
    """Represents location information alongside its verification lineage and certainty.

    Attributes:
        raw_text: Original place name or address description from the report.
        coordinates: (longitude, latitude) tuple in WGS 84 format, or None if unresolved.
        node_id: Road network graph junction ID, if resolved.
        provenance_type: Lineage indicating how the location was derived.
        confidence: Normalized confidence score in [0.0, 1.0].
        is_verified: True if location has been validated against authoritative GIS / CAD.
    """

    raw_text: Optional[str] = None
    coordinates: Optional[Tuple[float, float]] = None
    node_id: Optional[str] = None
    provenance_type: LocationProvenanceType = LocationProvenanceType.UNKNOWN
    confidence: float = 0.0
    is_verified: bool = False

    def __post_init__(self) -> None:
        if self.coordinates is not None:
            if not isinstance(self.coordinates, (tuple, list)) or len(self.coordinates) != 2:
                raise ValueError("LocationProvenance.coordinates must be a 2-element (longitude, latitude) tuple or None.")
            try:
                lon = float(self.coordinates[0])
                lat = float(self.coordinates[1])
            except (ValueError, TypeError) as err:
                raise ValueError(f"LocationProvenance coordinates must contain valid numeric floats: {err}") from err

            if not (-180.0 <= lon <= 180.0):
                raise ValueError(f"Longitude {lon} out of valid WGS 84 range [-180.0, 180.0].")
            if not (-90.0 <= lat <= 90.0):
                raise ValueError(f"Latitude {lat} out of valid WGS 84 range [-90.0, 90.0].")

            object.__setattr__(self, "coordinates", (lon, lat))

        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(f"LocationProvenance.confidence must be in range [0.0, 1.0], got {self.confidence}.")

    @property
    def has_coordinates(self) -> bool:
        """Returns True if physical spatial coordinates are available."""
        return self.coordinates is not None

    @property
    def longitude(self) -> Optional[float]:
        """Convenience property for longitude."""
        return self.coordinates[0] if self.coordinates is not None else None

    @property
    def latitude(self) -> Optional[float]:
        """Convenience property for latitude."""
        return self.coordinates[1] if self.coordinates is not None else None


@dataclass(frozen=True)
class HazardMention:
    """A disaster hazard explicitly mentioned in or inferred from an emergency report.

    Attributes:
        hazard_type: Standardized category of environmental/physical disaster hazard.
        description: Natural-language synopsis or caller quote.
        location_text: Spatial description of where the hazard is situated.
        severity: Assessed severity level, if discernable.
        confidence: Assessment confidence score in [0.0, 1.0].
    """

    hazard_type: HazardType
    description: str
    location_text: Optional[str] = None
    severity: Optional[HazardSeverity] = None
    confidence: float = 0.5

    def __post_init__(self) -> None:
        if not isinstance(self.hazard_type, HazardType):
            if isinstance(self.hazard_type, str):
                object.__setattr__(self, "hazard_type", HazardType(self.hazard_type))
            else:
                raise TypeError(f"HazardMention.hazard_type must be a HazardType enum, got {type(self.hazard_type)}.")

        if self.severity is not None and not isinstance(self.severity, HazardSeverity):
            if isinstance(self.severity, str):
                object.__setattr__(self, "severity", HazardSeverity(self.severity))
            else:
                raise TypeError(f"HazardMention.severity must be a HazardSeverity enum, got {type(self.severity)}.")

        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(f"HazardMention.confidence must be in range [0.0, 1.0], got {self.confidence}.")


class ValidationSeverity(str, Enum):
    """Severity classification of validation findings."""

    ERROR = "error"      # Fatal validation barrier; blocks conversion to operational dispatch
    WARNING = "warning"  # Non-fatal ambiguity or missing non-essential data
    INFO = "info"        # Informational advisory or provenance notice


class ValidationCode(str, Enum):
    """Standardized machine-readable validation finding codes."""

    EMPTY_REPORT = "empty_report"
    MISSING_EMERGENCY_TYPE = "missing_emergency_type"
    INVALID_EMERGENCY_TYPE = "invalid_emergency_type"
    MISSING_URGENCY = "missing_urgency"
    INVALID_URGENCY = "invalid_urgency"
    MISSING_LOCATION = "missing_location"
    INVALID_COORDINATES = "invalid_coordinates"
    UNKNOWN_GRAPH_NODE = "unknown_graph_node"
    INVALID_APPARATUS_TYPE = "invalid_apparatus_type"
    INVALID_HAZARD_TYPE = "invalid_hazard_type"
    CONTRADICTORY_URGENCY_UNDER_TRIAGE = "contradictory_urgency_under_triage"
    CONTRADICTORY_URGENCY_OVER_TRIAGE = "contradictory_urgency_over_triage"
    CONTRADICTORY_APPARATUS_MISMATCH = "contradictory_apparatus_mismatch"
    MALFORMED_DATA_STRUCTURE = "malformed_data_structure"
    UNVALIDATED_PROPOSAL_REJECTED = "unvalidated_proposal_rejected"


@dataclass(frozen=True)
class ValidationIssue:
    """A discrete validation finding generated during domain contract verification.

    Attributes:
        code: Machine-readable validation code.
        message: Human-readable explanation of the validation issue.
        field: Specific attribute or domain dimension exhibiting the issue.
        severity: Criticality of the finding (ERROR, WARNING, INFO).
    """

    code: ValidationCode
    message: str
    field: str
    severity: ValidationSeverity = ValidationSeverity.ERROR


class ValidationStatus(str, Enum):
    """Overall validation health of an interpreted emergency report."""

    VALID = "valid"                                     # Fully validated; ready for deterministic processing
    VALID_WITH_WARNINGS = "valid_with_warnings"         # Valid operational data, but carries non-fatal caveats
    INVALID_INSUFFICIENT_DATA = "invalid_insufficient" # Missing core required parameters (type, urgency, text)
    INVALID_CONTRADICTORY = "invalid_contradictory"     # Severe internal contradictions detected
    REJECTED = "rejected"                               # Unparseable, corrupted, or malicious payload


@dataclass
class ProposedIncidentInterpretation:
    """Untrusted raw candidate interpretation emitted by an AI model or parser.

    This is an unvalidated Data Transfer Object (DTO). It MUST NEVER be passed directly
    to routing engines or fleet allocators without validation via `validate_incident_proposal()`.

    Attributes:
        raw_report: Original verbatim text received from the caller / CAD.
        emergency_type: Candidate emergency type (string or enum).
        urgency: Candidate triage priority (string or enum).
        location_text: Candidate extracted address or landmark mention.
        suggested_coordinates: Candidate (lon, lat) tuple proposed by model.
        suggested_node_id: Candidate network node proposed by model.
        suggested_apparatus: Candidate list of apparatus types proposed by model.
        hazards_detected: Raw list of hazard dictionaries or descriptions.
        confidence_score: Self-reported model confidence in [0.0, 1.0].
        uncertainty_notes: Explanations of ambiguous or unconfirmed information.
        model_metadata: Auxiliary telemetry (model name, prompt tokens, latency).
    """

    raw_report: str
    emergency_type: Optional[Union[EmergencyType, str]] = None
    urgency: Optional[Union[UrgencyLevel, str]] = None
    location_text: Optional[str] = None
    suggested_coordinates: Optional[Tuple[float, float]] = None
    suggested_node_id: Optional[str] = None
    suggested_apparatus: List[Union[ApparatusType, str]] = field(default_factory=list)
    hazards_detected: List[Dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    uncertainty_notes: List[str] = field(default_factory=list)
    model_metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProposedIncidentInterpretation:
        """Constructs a proposal instance from an unstructured dictionary."""
        if not isinstance(data, dict):
            raise TypeError(f"ProposedIncidentInterpretation.from_dict requires a dict, got {type(data)}.")

        coords_raw = data.get("suggested_coordinates")
        coords: Optional[Tuple[float, float]] = None
        if coords_raw is not None and isinstance(coords_raw, (list, tuple)) and len(coords_raw) == 2:
            try:
                coords = (float(coords_raw[0]), float(coords_raw[1]))
            except (ValueError, TypeError):
                coords = None

        return cls(
            raw_report=str(data.get("raw_report", "")),
            emergency_type=data.get("emergency_type"),
            urgency=data.get("urgency"),
            location_text=data.get("location_text"),
            suggested_coordinates=coords,
            suggested_node_id=str(data["suggested_node_id"]) if data.get("suggested_node_id") is not None else None,
            suggested_apparatus=list(data.get("suggested_apparatus", [])),
            hazards_detected=list(data.get("hazards_detected", [])),
            confidence_score=float(data.get("confidence_score", 0.0)),
            uncertainty_notes=list(data.get("uncertainty_notes", [])),
            model_metadata=dict(data.get("model_metadata", {})),
        )


@dataclass(frozen=True)
class ValidatedIncidentContract:
    """Authoritative, immutable domain contract representing a validated emergency report.

    Produced exclusively by `validate_incident_proposal()`. Serves as the verified interface
    passed to deterministic emergency policy engines, fleet allocators, and routing algorithms.

    Attributes:
        incident_id: Unique string identifier for this incident.
        raw_report: Original verbatim emergency text (preserved for audit trail).
        emergency_type: Validated incident category, or None if under-specified.
        urgency: Validated triage priority, or None if under-specified.
        location: Validated location provenance record.
        required_apparatus: Validated tuple of required apparatus types.
        identified_hazards: Validated tuple of identified disaster hazards.
        validation_status: Overall validation health status.
        validation_issues: Tuple of all recorded validation issues (errors, warnings, info).
        uncertainty_flags: Tuple of strings documenting unresolved aspects of the call.
        validated_at: UTC timestamp of validation execution.
        model_confidence: Self-reported model confidence score (for telemetry only).
    """

    incident_id: str
    raw_report: str
    emergency_type: Optional[EmergencyType]
    urgency: Optional[UrgencyLevel]
    location: LocationProvenance
    required_apparatus: Tuple[ApparatusType, ...]
    identified_hazards: Tuple[HazardMention, ...]
    validation_status: ValidationStatus
    validation_issues: Tuple[ValidationIssue, ...]
    uncertainty_flags: Tuple[str, ...]
    validated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    model_confidence: float = 0.0

    @property
    def is_valid(self) -> bool:
        """Returns True if the contract is accepted without fatal validation errors."""
        return self.validation_status in (ValidationStatus.VALID, ValidationStatus.VALID_WITH_WARNINGS)

    @property
    def has_errors(self) -> bool:
        """Returns True if any fatal validation issues exist."""
        return any(issue.severity == ValidationSeverity.ERROR for issue in self.validation_issues)

    @property
    def is_operable_for_routing(self) -> bool:
        """Returns True if the contract possesses verified coordinates or node ID required for routing."""
        return (
            self.is_valid
            and (self.location.coordinates is not None or self.location.node_id is not None)
            and self.emergency_type is not None
            and self.urgency is not None
        )

    def to_operational_incident(self) -> Incident:
        """Converts this contract to an operational `Incident` domain model.

        Raises:
            ValueError: If the contract is not valid, lacks coordinates, or lacks triage.
        """
        if not self.is_operable_for_routing:
            error_msgs = [f"[{i.code.value}] {i.message}" for i in self.validation_issues if i.severity == ValidationSeverity.ERROR]
            raise ValueError(
                f"Cannot convert ValidatedIncidentContract to operational Incident: contract is not operable for routing. "
                f"Status='{self.validation_status.value}'. Errors: {error_msgs or 'Missing required coordinates or triage.'}"
            )

        assert self.emergency_type is not None
        assert self.urgency is not None

        coords = self.location.coordinates
        if coords is None:
            raise ValueError("Operational Incident requires physical (longitude, latitude) coordinates.")

        return Incident(
            incident_id=self.incident_id,
            emergency_type=self.emergency_type,
            urgency=self.urgency,
            coordinates=coords,
            node_id=self.location.node_id,
            required_apparatus=list(self.required_apparatus),
            description=self.raw_report,
            metadata={
                "validation_status": self.validation_status.value,
                "location_provenance": self.location.provenance_type.value,
                "location_confidence": self.location.confidence,
                "uncertainty_flags": list(self.uncertainty_flags),
                "model_confidence": self.model_confidence,
            },
        )


# Keywords used for heuristic sanity and under-triage contradiction detection
_CRITICAL_LIFE_THREAT_PATTERNS = [
    r"\b(unconscious|unresponsive)\b",
    r"\b(cardiac\s+arrest|heart\s+attack)\b",
    r"\b(not\s+breathing|stopped\s+breathing|respiratory\s+arrest)\b",
    r"\b(severe\s+bleeding|bleeding\s+heavily|arterial\s+bleed|hemorrhag\w*)\b",
    r"\b(trapped\s+in\s+fire|building\s+collapse|crushed)\b",
    r"\b(gunshot|stabbing|penetrating\s+wound)\b",
]

_NON_EMERGENCY_PATTERNS = [
    r"\b(minor\s+scratch|fender\s+bender|no\s+injur\w*|non[\s-]emergency)\b",
    r"\b(routine\s+transfer|cold\s+symptoms|minor\s+cut)\b",
]


def validate_incident_proposal(
    proposal: Union[ProposedIncidentInterpretation, Dict[str, Any]],
    incident_id: Optional[str] = None,
    valid_node_ids: Optional[Set[str]] = None,
) -> ValidatedIncidentContract:
    """Deterministically validates an untrusted incident proposal into an authoritative contract.

    Parameters:
        proposal: The raw untrusted interpretation (DTO or dictionary).
        incident_id: Optional unique incident identifier (generated if omitted).
        valid_node_ids: Optional set of recognized topological graph node IDs.

    Returns:
        ValidatedIncidentContract: An immutable contract containing validated fields,
        explicit uncertainty flags, and structured validation issues.
    """
    if isinstance(proposal, dict):
        try:
            prop = ProposedIncidentInterpretation.from_dict(proposal)
        except Exception as err:
            return ValidatedIncidentContract(
                incident_id=incident_id or f"INC-{uuid.uuid4().hex[:8].upper()}",
                raw_report="",
                emergency_type=None,
                urgency=None,
                location=LocationProvenance(),
                required_apparatus=(),
                identified_hazards=(),
                validation_status=ValidationStatus.REJECTED,
                validation_issues=(
                    ValidationIssue(
                        code=ValidationCode.MALFORMED_DATA_STRUCTURE,
                        message=f"Failed to parse raw proposal dictionary: {err}",
                        field="payload",
                        severity=ValidationSeverity.ERROR,
                    ),
                ),
                uncertainty_flags=("unparseable_proposal",),
            )
    elif isinstance(proposal, ProposedIncidentInterpretation):
        prop = proposal
    else:
        return ValidatedIncidentContract(
            incident_id=incident_id or f"INC-{uuid.uuid4().hex[:8].upper()}",
            raw_report="",
            emergency_type=None,
            urgency=None,
            location=LocationProvenance(),
            required_apparatus=(),
            identified_hazards=(),
            validation_status=ValidationStatus.REJECTED,
            validation_issues=(
                ValidationIssue(
                    code=ValidationCode.MALFORMED_DATA_STRUCTURE,
                    message=f"Expected ProposedIncidentInterpretation or dict, got {type(proposal)}.",
                    field="proposal",
                    severity=ValidationSeverity.ERROR,
                ),
            ),
            uncertainty_flags=("unsupported_input_type",),
        )

    active_id = incident_id or f"INC-{uuid.uuid4().hex[:8].upper()}"
    issues: List[ValidationIssue] = []
    uncertainty_flags: List[str] = list(prop.uncertainty_notes)

    # 1. Report Text Validation
    raw_text = prop.raw_report.strip() if prop.raw_report else ""
    if not raw_text:
        issues.append(
            ValidationIssue(
                code=ValidationCode.EMPTY_REPORT,
                message="Emergency report text is empty or missing.",
                field="raw_report",
                severity=ValidationSeverity.ERROR,
            )
        )
        uncertainty_flags.append("empty_caller_transcript")

    # 2. Emergency Type Validation
    validated_type: Optional[EmergencyType] = None
    if prop.emergency_type is None:
        issues.append(
            ValidationIssue(
                code=ValidationCode.MISSING_EMERGENCY_TYPE,
                message="No emergency incident type specified in proposal.",
                field="emergency_type",
                severity=ValidationSeverity.ERROR,
            )
        )
        uncertainty_flags.append("unspecified_emergency_type")
    elif isinstance(prop.emergency_type, EmergencyType):
        validated_type = prop.emergency_type
    elif isinstance(prop.emergency_type, str):
        try:
            validated_type = EmergencyType(prop.emergency_type.strip().lower())
        except ValueError:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_EMERGENCY_TYPE,
                    message=f"Unrecognized emergency type value: '{prop.emergency_type}'.",
                    field="emergency_type",
                    severity=ValidationSeverity.ERROR,
                )
            )
            uncertainty_flags.append("unrecognized_emergency_type")
    else:
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_EMERGENCY_TYPE,
                message=f"Invalid type for emergency_type: {type(prop.emergency_type)}.",
                field="emergency_type",
                severity=ValidationSeverity.ERROR,
            )
        )

    # 3. Urgency Level Validation
    validated_urgency: Optional[UrgencyLevel] = None
    if prop.urgency is None:
        issues.append(
            ValidationIssue(
                code=ValidationCode.MISSING_URGENCY,
                message="No triage urgency level specified in proposal.",
                field="urgency",
                severity=ValidationSeverity.ERROR,
            )
        )
        uncertainty_flags.append("unspecified_urgency")
    elif isinstance(prop.urgency, UrgencyLevel):
        validated_urgency = prop.urgency
    elif isinstance(prop.urgency, str):
        try:
            validated_urgency = UrgencyLevel(prop.urgency.strip().lower())
        except ValueError:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_URGENCY,
                    message=f"Unrecognized urgency level value: '{prop.urgency}'.",
                    field="urgency",
                    severity=ValidationSeverity.ERROR,
                )
            )
            uncertainty_flags.append("unrecognized_urgency")
    else:
        issues.append(
            ValidationIssue(
                code=ValidationCode.INVALID_URGENCY,
                message=f"Invalid type for urgency: {type(prop.urgency)}.",
                field="urgency",
                severity=ValidationSeverity.ERROR,
            )
        )

    # 4. Location & Provenance Validation
    loc_coords: Optional[Tuple[float, float]] = None
    loc_node: Optional[str] = None
    loc_prov_type = LocationProvenanceType.UNKNOWN
    loc_conf = 0.0
    loc_verified = False

    if prop.suggested_coordinates is not None:
        try:
            lon = float(prop.suggested_coordinates[0])
            lat = float(prop.suggested_coordinates[1])
            if (-180.0 <= lon <= 180.0) and (-90.0 <= lat <= 90.0):
                loc_coords = (lon, lat)
                loc_prov_type = LocationProvenanceType.VERIFIED_COORDINATES
                loc_conf = max(0.5, min(1.0, prop.confidence_score or 0.8))
                loc_verified = True
            else:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_COORDINATES,
                        message=f"Suggested coordinates ({lon}, {lat}) outside valid WGS 84 bounds.",
                        field="suggested_coordinates",
                        severity=ValidationSeverity.ERROR,
                    )
                )
                uncertainty_flags.append("out_of_bounds_coordinates")
        except (ValueError, TypeError, IndexError) as err:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_COORDINATES,
                    message=f"Malformed suggested coordinates: {err}",
                    field="suggested_coordinates",
                    severity=ValidationSeverity.ERROR,
                )
            )
            uncertainty_flags.append("malformed_coordinates")

    if prop.suggested_node_id is not None:
        raw_node = str(prop.suggested_node_id).strip()
        if valid_node_ids is not None:
            if raw_node in valid_node_ids:
                loc_node = raw_node
                if loc_prov_type == LocationProvenanceType.UNKNOWN:
                    loc_prov_type = LocationProvenanceType.NETWORK_NODE_SNAPPED
                    loc_conf = max(0.6, min(1.0, prop.confidence_score or 0.8))
                    loc_verified = True
            else:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.UNKNOWN_GRAPH_NODE,
                        message=f"Suggested node ID '{raw_node}' does not exist in target road network graph.",
                        field="suggested_node_id",
                        severity=ValidationSeverity.WARNING,
                    )
                )
                uncertainty_flags.append("unverified_node_id")
        else:
            loc_node = raw_node

    if loc_coords is None and loc_node is None:
        if prop.location_text and prop.location_text.strip():
            loc_prov_type = LocationProvenanceType.CALLER_DESCRIPTION
            loc_conf = max(0.2, min(0.6, prop.confidence_score or 0.4))
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_LOCATION,
                    message=f"Incident location specified as un-geocoded descriptive text only: '{prop.location_text.strip()}'.",
                    field="location",
                    severity=ValidationSeverity.WARNING,
                )
            )
            uncertainty_flags.append("unresolved_coordinates_text_only")
        else:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.MISSING_LOCATION,
                    message="No location text, coordinates, or node ID provided.",
                    field="location",
                    severity=ValidationSeverity.WARNING,
                )
            )
            uncertainty_flags.append("missing_location")

    location_record = LocationProvenance(
        raw_text=prop.location_text.strip() if prop.location_text else None,
        coordinates=loc_coords,
        node_id=loc_node,
        provenance_type=loc_prov_type,
        confidence=loc_conf,
        is_verified=loc_verified,
    )

    # 5. Required Apparatus Validation
    validated_apparatus: List[ApparatusType] = []
    seen_app: Set[ApparatusType] = set()
    for raw_app in prop.suggested_apparatus:
        if isinstance(raw_app, ApparatusType):
            if raw_app not in seen_app:
                seen_app.add(raw_app)
                validated_apparatus.append(raw_app)
        elif isinstance(raw_app, str):
            try:
                parsed_app = ApparatusType(raw_app.strip().lower())
                if parsed_app not in seen_app:
                    seen_app.add(parsed_app)
                    validated_apparatus.append(parsed_app)
            except ValueError:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_APPARATUS_TYPE,
                        message=f"Unrecognized apparatus requirement: '{raw_app}'.",
                        field="suggested_apparatus",
                        severity=ValidationSeverity.ERROR,
                    )
                )
                uncertainty_flags.append(f"unrecognized_apparatus_{raw_app}")
        else:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.INVALID_APPARATUS_TYPE,
                    message=f"Invalid type for apparatus item: {type(raw_app)}.",
                    field="suggested_apparatus",
                    severity=ValidationSeverity.ERROR,
                )
            )

    # 6. Hazards Mentioned Validation
    validated_hazards: List[HazardMention] = []
    for h_dict in prop.hazards_detected:
        if not isinstance(h_dict, dict):
            continue
        h_type_raw = h_dict.get("hazard_type")
        h_type: Optional[HazardType] = None
        if isinstance(h_type_raw, HazardType):
            h_type = h_type_raw
        elif isinstance(h_type_raw, str):
            try:
                h_type = HazardType(h_type_raw.strip().lower())
            except ValueError:
                issues.append(
                    ValidationIssue(
                        code=ValidationCode.INVALID_HAZARD_TYPE,
                        message=f"Unrecognized hazard type: '{h_type_raw}'.",
                        field="hazards_detected",
                        severity=ValidationSeverity.WARNING,
                    )
                )
                uncertainty_flags.append(f"unrecognized_hazard_{h_type_raw}")

        if h_type is not None:
            sev_raw = h_dict.get("severity")
            sev: Optional[HazardSeverity] = None
            if isinstance(sev_raw, HazardSeverity):
                sev = sev_raw
            elif isinstance(sev_raw, str):
                try:
                    sev = HazardSeverity(sev_raw.strip().lower())
                except ValueError:
                    sev = None

            conf_raw = h_dict.get("confidence", 0.5)
            try:
                h_conf = max(0.0, min(1.0, float(conf_raw)))
            except (ValueError, TypeError):
                h_conf = 0.5

            validated_hazards.append(
                HazardMention(
                    hazard_type=h_type,
                    description=str(h_dict.get("description", "")),
                    location_text=str(h_dict.get("location_text", "")) if h_dict.get("location_text") else None,
                    severity=sev,
                    confidence=h_conf,
                )
            )

    # 7. Contradiction & Under/Over-Triage Detection
    lower_report = raw_text.lower()
    has_life_threat_mention = any(re.search(pat, lower_report) for pat in _CRITICAL_LIFE_THREAT_PATTERNS)
    has_non_emergency_mention = any(re.search(pat, lower_report) for pat in _NON_EMERGENCY_PATTERNS)

    if has_life_threat_mention and validated_urgency in (UrgencyLevel.PRIORITY_4_ALPHA, UrgencyLevel.PRIORITY_3_BRAVO):
        issues.append(
            ValidationIssue(
                code=ValidationCode.CONTRADICTORY_URGENCY_UNDER_TRIAGE,
                message=(
                    f"Report describes critical life threat or acute trauma, but proposed urgency is "
                    f"under-triaged at '{validated_urgency.value}'."
                ),
                field="urgency",
                severity=ValidationSeverity.ERROR,
            )
        )
        uncertainty_flags.append("under_triage_detected")

    if has_non_emergency_mention and validated_urgency == UrgencyLevel.PRIORITY_1_ECHO:
        issues.append(
            ValidationIssue(
                code=ValidationCode.CONTRADICTORY_URGENCY_OVER_TRIAGE,
                message=(
                    "Report describes minor/non-emergency incident, but proposed urgency is "
                    "over-triaged at Priority 1 Echo."
                ),
                field="urgency",
                severity=ValidationSeverity.WARNING,
            )
        )
        uncertainty_flags.append("possible_over_triage")

    # Apparatus Plausibility Check
    if validated_type in (EmergencyType.CARDIAC_ARREST, EmergencyType.TRAUMA_MAJOR) and validated_apparatus:
        has_medical = any(app in (ApparatusType.AMBULANCE_ALS, ApparatusType.AMBULANCE_BLS) for app in validated_apparatus)
        if not has_medical:
            issues.append(
                ValidationIssue(
                    code=ValidationCode.CONTRADICTORY_APPARATUS_MISMATCH,
                    message=(
                        f"Incident is classified as {validated_type.value}, but no medical transport unit "
                        f"(ALS/BLS Ambulance) was requested."
                    ),
                    field="required_apparatus",
                    severity=ValidationSeverity.WARNING,
                )
            )
            uncertainty_flags.append("missing_medical_transport_unit")

    # 8. Determine Overall Validation Status
    has_fatal_error = any(i.severity == ValidationSeverity.ERROR for i in issues)
    has_contradiction = any(i.code == ValidationCode.CONTRADICTORY_URGENCY_UNDER_TRIAGE for i in issues)
    has_warnings = any(i.severity == ValidationSeverity.WARNING for i in issues)

    if has_contradiction:
        status = ValidationStatus.INVALID_CONTRADICTORY
    elif has_fatal_error:
        status = ValidationStatus.INVALID_INSUFFICIENT_DATA
    elif has_warnings:
        status = ValidationStatus.VALID_WITH_WARNINGS
    else:
        status = ValidationStatus.VALID

    return ValidatedIncidentContract(
        incident_id=active_id,
        raw_report=raw_text,
        emergency_type=validated_type,
        urgency=validated_urgency,
        location=location_record,
        required_apparatus=tuple(validated_apparatus),
        identified_hazards=tuple(validated_hazards),
        validation_status=status,
        validation_issues=tuple(issues),
        uncertainty_flags=tuple(sorted(set(uncertainty_flags))),
        model_confidence=max(0.0, min(1.0, prop.confidence_score or 0.0)),
    )
