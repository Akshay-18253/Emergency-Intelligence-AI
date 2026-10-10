"""
Unit Tests for AI Boundary and Structured Domain Contracts (Milestone 5.1).
===========================================================================
Verifies that untrusted natural language proposals are strictly separated from
authoritative operational contracts, and tests:
- Valid structured incident inputs
- Missing required vs optional fields
- Invalid field types, enum values, and out-of-bounds coordinates
- Contradictory triage and apparatus mismatch detection
- Rejection of unvalidated proposals as operational Incident models
- Full compatibility with existing Incident domain models
"""

import pytest

from emergency_intelligence.events.hazards import HazardSeverity, HazardType
from emergency_intelligence.events.incidents import (
    ApparatusType,
    EmergencyType,
    Incident,
    UrgencyLevel,
)
from emergency_intelligence.intelligence.contracts import (
    HazardMention,
    LocationProvenance,
    LocationProvenanceType,
    ProposedIncidentInterpretation,
    ValidatedIncidentContract,
    ValidationCode,
    ValidationIssue,
    ValidationSeverity,
    ValidationStatus,
    validate_incident_proposal,
)


class TestLocationProvenance:
    """Tests for the LocationProvenance value object."""

    def test_valid_location_provenance_creation(self) -> None:
        loc = LocationProvenance(
            raw_text="Market & 10th St",
            coordinates=(-122.4194, 37.7749),
            node_id="1002",
            provenance_type=LocationProvenanceType.VERIFIED_COORDINATES,
            confidence=0.95,
            is_verified=True,
        )
        assert loc.has_coordinates is True
        assert loc.longitude == -122.4194
        assert loc.latitude == 37.7749
        assert loc.provenance_type == LocationProvenanceType.VERIFIED_COORDINATES
        assert loc.is_verified is True

    def test_missing_coordinates_remains_none(self) -> None:
        loc = LocationProvenance(
            raw_text="Near the downtown fountain",
            coordinates=None,
            provenance_type=LocationProvenanceType.CALLER_DESCRIPTION,
            confidence=0.4,
        )
        assert loc.has_coordinates is False
        assert loc.coordinates is None
        assert loc.longitude is None
        assert loc.latitude is None

    def test_non_numeric_coordinates_raises(self) -> None:
        with pytest.raises(ValueError, match="valid numeric floats"):
            LocationProvenance(coordinates=("abc", "def"))  # type: ignore

    def test_coordinate_convenience_properties_none(self) -> None:
        loc = LocationProvenance(coordinates=None)
        assert loc.longitude is None
        assert loc.latitude is None

    def test_out_of_bounds_coordinates_raise(self) -> None:
        with pytest.raises(ValueError, match="Longitude"):
            LocationProvenance(coordinates=(-185.0, 37.0))

        with pytest.raises(ValueError, match="Latitude"):
            LocationProvenance(coordinates=(-122.0, 95.0))

    def test_invalid_coordinate_shape_raises(self) -> None:
        with pytest.raises(ValueError, match="2-element"):
            LocationProvenance(coordinates=(-122.0,))  # type: ignore

    def test_invalid_confidence_range_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            LocationProvenance(confidence=1.5)

        with pytest.raises(ValueError, match="confidence"):
            LocationProvenance(confidence=-0.1)


class TestHazardMention:
    """Tests for the HazardMention value object."""

    def test_hazard_mention_normalization(self) -> None:
        hm = HazardMention(
            hazard_type="flash_flood",  # string automatically normalized to HazardType enum
            description="Deep standing water across roadway",
            location_text="9th St underpass",
            severity="severe",
            confidence=0.85,
        )
        assert hm.hazard_type == HazardType.FLASH_FLOOD
        assert hm.severity == HazardSeverity.SEVERE
        assert hm.confidence == 0.85

    def test_invalid_hazard_type_raises(self) -> None:
        with pytest.raises((ValueError, TypeError)):
            HazardMention(hazard_type=123, description="Invalid")  # type: ignore

    def test_invalid_hazard_severity_type_raises(self) -> None:
        with pytest.raises(TypeError, match="HazardSeverity"):
            HazardMention(hazard_type=HazardType.FLASH_FLOOD, description="Flood", severity=999)  # type: ignore

    def test_invalid_confidence_raises(self) -> None:
        with pytest.raises(ValueError, match="confidence"):
            HazardMention(hazard_type=HazardType.ROAD_COLLAPSE, description="Sinkhole", confidence=1.2)


class TestProposedIncidentInterpretation:
    """Tests for the ProposedIncidentInterpretation DTO."""

    def test_from_dict_non_dict_raises(self) -> None:
        with pytest.raises(TypeError, match="requires a dict"):
            ProposedIncidentInterpretation.from_dict("not-a-dict")  # type: ignore

    def test_from_dict_malformed_coordinates_fallback(self) -> None:
        dto = ProposedIncidentInterpretation.from_dict({
            "raw_report": "Medical emergency",
            "suggested_coordinates": ["not-a-float", "not-a-float"],
        })
        assert dto.suggested_coordinates is None


class TestValidateIncidentProposalValidCases:
    """Tests validating well-formed proposals."""

    def test_fully_specified_valid_proposal(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Two-alarm structure fire at 500 Market St, smoke showing from 2nd floor.",
            emergency_type=EmergencyType.STRUCTURE_FIRE,
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
            location_text="500 Market St",
            suggested_coordinates=(-122.401, 37.789),
            suggested_node_id="1004",
            suggested_apparatus=[ApparatusType.FIRE_ENGINE, ApparatusType.LADDER_TRUCK],
            hazards_detected=[
                {
                    "hazard_type": "structural_debris",
                    "description": "Falling glass on sidewalk",
                    "severity": "severe",
                    "confidence": 0.8,
                }
            ],
            confidence_score=0.92,
        )

        contract = validate_incident_proposal(proposal, incident_id="INC-2026-001", valid_node_ids={"1004"})

        assert contract.is_valid is True
        assert contract.has_errors is False
        assert contract.validation_status == ValidationStatus.VALID
        assert contract.incident_id == "INC-2026-001"
        assert contract.emergency_type == EmergencyType.STRUCTURE_FIRE
        assert contract.urgency == UrgencyLevel.PRIORITY_1_ECHO
        assert contract.location.coordinates == (-122.401, 37.789)
        assert contract.location.node_id == "1004"
        assert contract.location.provenance_type == LocationProvenanceType.VERIFIED_COORDINATES
        assert len(contract.required_apparatus) == 2
        assert len(contract.identified_hazards) == 1
        assert contract.identified_hazards[0].hazard_type == HazardType.STRUCTURAL_DEBRIS
        assert contract.is_operable_for_routing is True

        # Test operational incident conversion
        op_incident = contract.to_operational_incident()
        assert isinstance(op_incident, Incident)
        assert op_incident.incident_id == "INC-2026-001"
        assert op_incident.emergency_type == EmergencyType.STRUCTURE_FIRE
        assert op_incident.urgency == UrgencyLevel.PRIORITY_1_ECHO
        assert op_incident.coordinates == (-122.401, 37.789)
        assert op_incident.node_id == "1004"
        assert ApparatusType.FIRE_ENGINE in op_incident.required_apparatus

    def test_valid_proposal_from_raw_dictionary(self) -> None:
        payload = {
            "raw_report": "Elderly patient having difficulty breathing at home.",
            "emergency_type": "medical_general",
            "urgency": "priority_2_delta",
            "suggested_coordinates": [-122.415, 37.778],
            "suggested_apparatus": ["ambulance_als"],
            "hazards_detected": [
                {
                    "hazard_type": "flood_inundation",
                    "description": "Water near driveway",
                    "severity": "moderate",
                    "confidence": "0.7",
                },
                {
                    "hazard_type": "unknown_hazard",  # invalid hazard type warning
                    "description": "weird smoke",
                },
                "not-a-dict",  # skipped gracefully
            ],
            "confidence_score": 0.88,
        }

        contract = validate_incident_proposal(payload)
        assert contract.is_valid is True
        assert contract.validation_status == ValidationStatus.VALID_WITH_WARNINGS
        assert contract.emergency_type == EmergencyType.MEDICAL_GENERAL
        assert contract.urgency == UrgencyLevel.PRIORITY_2_DELTA
        assert contract.location.coordinates == (-122.415, 37.778)
        assert contract.required_apparatus == (ApparatusType.AMBULANCE_ALS,)
        assert len(contract.identified_hazards) == 1
        assert contract.identified_hazards[0].hazard_type == HazardType.FLOOD_INUNDATION

    def test_node_id_without_valid_node_ids_filter(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Rescue call",
            emergency_type=EmergencyType.MEDICAL_GENERAL,
            urgency=UrgencyLevel.PRIORITY_2_DELTA,
            suggested_node_id="NODE_RAW_PASS",
        )
        contract = validate_incident_proposal(proposal, valid_node_ids=None)
        assert contract.location.node_id == "NODE_RAW_PASS"


class TestValidateIncidentProposalMissingInformation:
    """Tests handling of missing required vs optional information."""

    def test_missing_report_text_is_rejected_as_insufficient(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="",
            emergency_type=EmergencyType.MEDICAL_GENERAL,
            urgency=UrgencyLevel.PRIORITY_2_DELTA,
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert contract.validation_status == ValidationStatus.INVALID_INSUFFICIENT_DATA
        assert any(i.code == ValidationCode.EMPTY_REPORT for i in contract.validation_issues)

    def test_missing_emergency_type_is_fatal(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Something bad happened here, send help!",
            emergency_type=None,
            urgency=UrgencyLevel.PRIORITY_2_DELTA,
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert contract.validation_status == ValidationStatus.INVALID_INSUFFICIENT_DATA
        assert any(i.code == ValidationCode.MISSING_EMERGENCY_TYPE for i in contract.validation_issues)

    def test_missing_urgency_is_fatal(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="House fire on Maple Avenue.",
            emergency_type=EmergencyType.STRUCTURE_FIRE,
            urgency=None,
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert contract.validation_status == ValidationStatus.INVALID_INSUFFICIENT_DATA
        assert any(i.code == ValidationCode.MISSING_URGENCY for i in contract.validation_issues)

    def test_missing_coordinates_remains_none_and_not_invented(self) -> None:
        """Unknown values must remain unknown. Do not silently substitute invented coordinates."""
        proposal = ProposedIncidentInterpretation(
            raw_report="Car crash near the post office, two people injured.",
            emergency_type=EmergencyType.ROAD_TRAFFIC_COLLISION,
            urgency=UrgencyLevel.PRIORITY_2_DELTA,
            location_text="Near the post office",
            suggested_coordinates=None,  # No coordinates available!
            suggested_apparatus=[ApparatusType.AMBULANCE_ALS],
        )

        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is True  # Valid with warning because text location is known
        assert contract.validation_status == ValidationStatus.VALID_WITH_WARNINGS
        assert contract.location.coordinates is None
        assert contract.location.provenance_type == LocationProvenanceType.CALLER_DESCRIPTION
        assert "unresolved_coordinates_text_only" in contract.uncertainty_flags
        assert any(i.code == ValidationCode.MISSING_LOCATION for i in contract.validation_issues)

        # Operable for routing MUST be False when coordinates are missing
        assert contract.is_operable_for_routing is False
        with pytest.raises(ValueError, match="not operable for routing"):
            contract.to_operational_incident()

    def test_completely_missing_location(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="General distress call, caller hung up immediately.",
            emergency_type=EmergencyType.MEDICAL_GENERAL,
            urgency=UrgencyLevel.PRIORITY_3_BRAVO,
            location_text=None,
            suggested_coordinates=None,
        )
        contract = validate_incident_proposal(proposal)
        assert contract.location.provenance_type == LocationProvenanceType.UNKNOWN
        assert "missing_location" in contract.uncertainty_flags


class TestValidateIncidentProposalInvalidValues:
    """Tests handling of invalid types, enums, and malformed inputs."""

    def test_invalid_emergency_type_string_recorded_as_error(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Alien invasion in the park.",
            emergency_type="alien_abduction",  # invalid enum string
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert any(i.code == ValidationCode.INVALID_EMERGENCY_TYPE for i in contract.validation_issues)

    def test_invalid_emergency_type_non_string_non_enum_recorded_as_error(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Test report",
            emergency_type=999,  # type: ignore
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert any(i.code == ValidationCode.INVALID_EMERGENCY_TYPE for i in contract.validation_issues)

    def test_invalid_urgency_string_recorded_as_error(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Kitchen fire.",
            emergency_type=EmergencyType.STRUCTURE_FIRE,
            urgency="super_urgent_now",  # invalid enum string
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert any(i.code == ValidationCode.INVALID_URGENCY for i in contract.validation_issues)

    def test_invalid_urgency_non_string_non_enum_recorded_as_error(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Test report",
            emergency_type=EmergencyType.STRUCTURE_FIRE,
            urgency=999,  # type: ignore
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert any(i.code == ValidationCode.INVALID_URGENCY for i in contract.validation_issues)

    def test_invalid_out_of_bounds_coordinates_recorded_as_error(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Medical call.",
            emergency_type=EmergencyType.MEDICAL_GENERAL,
            urgency=UrgencyLevel.PRIORITY_3_BRAVO,
            suggested_coordinates=(-250.0, 45.0),  # Longitude -250 is invalid
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert any(i.code == ValidationCode.INVALID_COORDINATES for i in contract.validation_issues)

    def test_invalid_apparatus_string_recorded_as_error(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Rescue needed.",
            emergency_type=EmergencyType.STRUCTURAL_COLLAPSE,
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
            suggested_apparatus=["flying_carpet", "fire_engine"],  # invalid apparatus
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert any(i.code == ValidationCode.INVALID_APPARATUS_TYPE for i in contract.validation_issues)

    def test_invalid_apparatus_non_string_recorded_as_error(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Rescue needed.",
            emergency_type=EmergencyType.STRUCTURAL_COLLAPSE,
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
            suggested_apparatus=[12345],  # type: ignore
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert any(i.code == ValidationCode.INVALID_APPARATUS_TYPE for i in contract.validation_issues)

    def test_unknown_graph_node_recorded_as_warning(self) -> None:
        proposal = ProposedIncidentInterpretation(
            raw_report="Structure fire.",
            emergency_type=EmergencyType.STRUCTURE_FIRE,
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
            suggested_coordinates=(-122.41, 37.77),
            suggested_node_id="NODE_DOES_NOT_EXIST",
        )
        contract = validate_incident_proposal(proposal, valid_node_ids={"1001", "1002"})
        assert any(i.code == ValidationCode.UNKNOWN_GRAPH_NODE for i in contract.validation_issues)
        assert "unverified_node_id" in contract.uncertainty_flags


class TestValidateIncidentProposalContradictions:
    """Tests detecting under-triage, over-triage, and apparatus mismatches."""

    def test_under_triage_life_threat_contradiction(self) -> None:
        """Report describes cardiac arrest, but model proposed Priority 4 Alpha."""
        proposal = ProposedIncidentInterpretation(
            raw_report="Patient is unconscious and not breathing on the floor!",
            emergency_type=EmergencyType.CARDIAC_ARREST,
            urgency=UrgencyLevel.PRIORITY_4_ALPHA,  # Extreme under-triage!
            suggested_coordinates=(-122.41, 37.77),
        )
        contract = validate_incident_proposal(proposal)
        assert contract.is_valid is False
        assert contract.validation_status == ValidationStatus.INVALID_CONTRADICTORY
        assert any(i.code == ValidationCode.CONTRADICTORY_URGENCY_UNDER_TRIAGE for i in contract.validation_issues)
        assert "under_triage_detected" in contract.uncertainty_flags

    def test_over_triage_fender_bender_generates_warning(self) -> None:
        """Report states minor fender bender with no injuries, but proposed Priority 1 Echo."""
        proposal = ProposedIncidentInterpretation(
            raw_report="Minor fender bender in parking lot, no injuries at all.",
            emergency_type=EmergencyType.ROAD_TRAFFIC_COLLISION,
            urgency=UrgencyLevel.PRIORITY_1_ECHO,  # Over-triage
            suggested_coordinates=(-122.41, 37.77),
        )
        contract = validate_incident_proposal(proposal)
        assert any(i.code == ValidationCode.CONTRADICTORY_URGENCY_OVER_TRIAGE for i in contract.validation_issues)
        assert "possible_over_triage" in contract.uncertainty_flags

    def test_cardiac_arrest_without_medical_transport_generates_warning(self) -> None:
        """Cardiac arrest with only a ladder truck requested generates apparatus mismatch warning."""
        proposal = ProposedIncidentInterpretation(
            raw_report="Patient in sudden cardiac arrest.",
            emergency_type=EmergencyType.CARDIAC_ARREST,
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
            suggested_coordinates=(-122.41, 37.77),
            suggested_apparatus=[ApparatusType.LADDER_TRUCK],  # No ambulance!
        )
        contract = validate_incident_proposal(proposal)
        assert any(i.code == ValidationCode.CONTRADICTORY_APPARATUS_MISMATCH for i in contract.validation_issues)
        assert "missing_medical_transport_unit" in contract.uncertainty_flags


class TestAIContractBoundariesAndRejection:
    """Verifies that untrusted AI output cannot bypass validation."""

    def test_untrusted_proposal_is_not_incident(self) -> None:
        """ProposedIncidentInterpretation must not inherit from or duck-type as Incident."""
        proposal = ProposedIncidentInterpretation(
            raw_report="Test report",
            emergency_type=EmergencyType.MEDICAL_GENERAL,
            urgency=UrgencyLevel.PRIORITY_2_DELTA,
        )
        assert not isinstance(proposal, Incident)
        assert not hasattr(proposal, "is_life_threatening")

    def test_malformed_unparseable_input_rejected(self) -> None:
        contract = validate_incident_proposal("Not a dict or proposal object")  # type: ignore
        assert contract.validation_status == ValidationStatus.REJECTED
        assert contract.is_valid is False
        assert any(i.code == ValidationCode.MALFORMED_DATA_STRUCTURE for i in contract.validation_issues)

    def test_contract_immutability(self) -> None:
        """ValidatedIncidentContract is frozen and cannot be mutated by downstream callers."""
        contract = validate_incident_proposal(
            ProposedIncidentInterpretation(
                raw_report="Routine medical call",
                emergency_type=EmergencyType.MEDICAL_GENERAL,
                urgency=UrgencyLevel.PRIORITY_3_BRAVO,
                suggested_coordinates=(-122.4, 37.7),
            )
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            contract.raw_report = "Tampered report"  # type: ignore

