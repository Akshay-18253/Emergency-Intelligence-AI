"""
Unit Tests for Deterministic Emergency Policy Engine (Milestone 5.2).
=====================================================================
Verifies statutory dispatch rules, apparatus allocation mandates, routing
constraint selection, hazard-driven bypass policies, and reconciliation of
untrusted model suggestions with authoritative SOPs.
"""

from datetime import datetime, timezone
import pytest

from emergency_intelligence.data.osm import WeightingProfile
from emergency_intelligence.events.hazards import HazardSeverity, HazardType
from emergency_intelligence.events.incidents import (
    ApparatusType,
    EmergencyType,
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
from emergency_intelligence.intelligence.policy import (
    ApparatusRequirement,
    EmergencyPolicyEngine,
    OperationalPolicyDirective,
    RoutingConstraint,
    RoutingObjective,
)


@pytest.fixture
def policy_engine() -> EmergencyPolicyEngine:
    return EmergencyPolicyEngine(jurisdiction="metro_dispatch_test")


class TestApparatusRequirementModel:
    """Tests for the ApparatusRequirement value object."""

    def test_valid_apparatus_requirement_creation(self) -> None:
        req = ApparatusRequirement(
            apparatus_type=ApparatusType.FIRE_ENGINE,
            quantity=2,
            is_mandatory=True,
            rationale="Initial structural attack",
        )
        assert req.apparatus_type == ApparatusType.FIRE_ENGINE
        assert req.quantity == 2
        assert req.is_mandatory is True
        assert req.source == "statutory_policy"

    def test_apparatus_string_normalization(self) -> None:
        req = ApparatusRequirement(apparatus_type="ladder_truck", quantity=1)  # type: ignore
        assert req.apparatus_type == ApparatusType.LADDER_TRUCK

    def test_invalid_apparatus_type_raises(self) -> None:
        with pytest.raises(TypeError, match="ApparatusType"):
            ApparatusRequirement(apparatus_type=123, quantity=1)  # type: ignore

    def test_non_positive_quantity_raises(self) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            ApparatusRequirement(apparatus_type=ApparatusType.FIRE_ENGINE, quantity=0)

        with pytest.raises(ValueError, match="positive integer"):
            ApparatusRequirement(apparatus_type=ApparatusType.FIRE_ENGINE, quantity=-1)


class TestStatutoryPolicyRules:
    """Tests evaluating statutory dispatch baselines across emergency categories."""

    def test_structure_fire_statutory_baseline(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Working structure fire in commercial building, flames from roof.",
            "emergency_type": "structure_fire",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
        })

        directive = policy_engine.evaluate(contract)
        assert directive.is_dispatchable is True
        assert directive.effective_urgency == UrgencyLevel.PRIORITY_1_ECHO
        assert directive.effective_emergency_type == EmergencyType.STRUCTURE_FIRE
        assert directive.weighting_profile == WeightingProfile.EMERGENCY_TIME
        assert directive.routing_objective == RoutingObjective.MINIMIZE_RESPONSE_TIME
        assert directive.has_constraint(RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE)
        assert directive.has_constraint(RoutingConstraint.AVOID_ACTIVE_HAZARDS)

        # NFPA 1710 full alarm assignment
        app_types = directive.to_apparatus_type_list()
        assert app_types.count(ApparatusType.FIRE_ENGINE) == 2
        assert app_types.count(ApparatusType.LADDER_TRUCK) == 1
        assert app_types.count(ApparatusType.BATTALION_CHIEF) == 1
        assert app_types.count(ApparatusType.AMBULANCE_ALS) == 1
        assert directive.total_apparatus_count == 5
        assert "RULE_FIRE_STRUCTURE_FULL_ALARM" in directive.policy_rules_applied

    def test_structure_fire_urgency_escalation(self, policy_engine: EmergencyPolicyEngine) -> None:
        """If caller/model proposed lower urgency for structure fire, policy escalates to Priority 1 Echo."""
        contract = validate_incident_proposal({
            "raw_report": "Structure fire on Pine St, building evacuated.",
            "emergency_type": "structure_fire",
            "urgency": "priority_2_delta",  # lower urgency proposed
            "suggested_coordinates": [-122.41, 37.77],
        })

        directive = policy_engine.evaluate(contract)
        assert directive.effective_urgency == UrgencyLevel.PRIORITY_1_ECHO
        assert "RULE_FIRE_URGENCY_ESCALATION" in directive.policy_rules_applied
        assert any("Escalated" in w for w in directive.policy_warnings)

    def test_cardiac_arrest_dual_response_rule(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Elderly male collapsed, CPR in progress.",
            "emergency_type": "cardiac_arrest",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
        })

        directive = policy_engine.evaluate(contract)
        assert directive.effective_urgency == UrgencyLevel.PRIORITY_1_ECHO
        app_types = directive.to_apparatus_type_list()
        assert ApparatusType.AMBULANCE_ALS in app_types
        assert ApparatusType.FIRE_ENGINE in app_types  # dual response CPR
        assert "RULE_CARDIAC_DUAL_RESPONSE_MANDATE" in directive.policy_rules_applied

    def test_hazmat_spill_tunnel_ban_and_standoff(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Chemical tanker overturned leaking corrosive vapors.",
            "emergency_type": "hazmat_spill",
            "urgency": "priority_2_delta",
            "suggested_coordinates": [-122.41, 37.77],
        })

        directive = policy_engine.evaluate(contract)
        assert directive.routing_objective == RoutingObjective.MAXIMIZE_CREW_SAFETY
        assert directive.has_constraint(RoutingConstraint.AVOID_BRIDGES_TUNNELS)
        assert directive.has_constraint(RoutingConstraint.AVOID_ACTIVE_HAZARDS)
        app_types = directive.to_apparatus_type_list()
        assert ApparatusType.HAZMAT_UNIT in app_types
        assert ApparatusType.FIRE_ENGINE in app_types
        assert ApparatusType.AMBULANCE_ALS in app_types
        assert "RULE_HAZMAT_CONTAINMENT_AND_TUNNEL_BAN" in directive.policy_rules_applied

    def test_flash_flood_swift_water_rescue(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Vehicle trapped in rising floodwaters near creek.",
            "emergency_type": "flash_flood",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
        })

        directive = policy_engine.evaluate(contract)
        assert directive.has_constraint(RoutingConstraint.AVOID_FLOOD_ZONES)
        assert directive.has_constraint(RoutingConstraint.AVOID_ACTIVE_HAZARDS)
        app_types = directive.to_apparatus_type_list()
        assert ApparatusType.HEAVY_RESCUE in app_types
        assert "RULE_SWIFT_WATER_RESCUE_FLOOD_AVOIDANCE" in directive.policy_rules_applied

    def test_structural_collapse_usar_response(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Balcony collapse with multiple victims pinned.",
            "emergency_type": "structural_collapse",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
        })

        directive = policy_engine.evaluate(contract)
        app_types = directive.to_apparatus_type_list()
        assert ApparatusType.HEAVY_RESCUE in app_types
        assert ApparatusType.LADDER_TRUCK in app_types
        assert ApparatusType.FIRE_ENGINE in app_types
        assert ApparatusType.AMBULANCE_ALS in app_types
        assert "RULE_COLLAPSE_USAR_RESPONSE" in directive.policy_rules_applied

    def test_road_traffic_collision_acute_vs_minor(self, policy_engine: EmergencyPolicyEngine) -> None:
        # Acute MVA
        contract_acute = validate_incident_proposal({
            "raw_report": "Head-on collision, driver pinned behind steering column.",
            "emergency_type": "road_traffic_collision",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
        })
        dir_acute = policy_engine.evaluate(contract_acute)
        assert ApparatusType.FIRE_ENGINE in dir_acute.to_apparatus_type_list()
        assert ApparatusType.AMBULANCE_ALS in dir_acute.to_apparatus_type_list()
        assert dir_acute.weighting_profile == WeightingProfile.EMERGENCY_TIME

        # Minor MVA (routine civilian speed)
        contract_minor = validate_incident_proposal({
            "raw_report": "Minor traffic collision, driver requests evaluation.",
            "emergency_type": "road_traffic_collision",
            "urgency": "priority_3_bravo",
            "suggested_coordinates": [-122.41, 37.77],
        })
        dir_minor = policy_engine.evaluate(contract_minor)
        assert ApparatusType.AMBULANCE_BLS in dir_minor.to_apparatus_type_list()
        assert dir_minor.weighting_profile == WeightingProfile.TRAVEL_TIME
        assert dir_minor.has_constraint(RoutingConstraint.STANDARD_CIVILIAN_SPEEDS)

    def test_general_medical_triage_tiers(self, policy_engine: EmergencyPolicyEngine) -> None:
        # Priority 1 Echo Medical
        c_echo = validate_incident_proposal({
            "raw_report": "Severe allergic anaphylaxis with airway swelling.",
            "emergency_type": "medical_general",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
        })
        d_echo = policy_engine.evaluate(c_echo)
        assert ApparatusType.AMBULANCE_ALS in d_echo.to_apparatus_type_list()
        assert d_echo.weighting_profile == WeightingProfile.EMERGENCY_TIME

        # Priority 4 Alpha Routine Medical
        c_alpha = validate_incident_proposal({
            "raw_report": "Chronic back ache for 3 weeks.",
            "emergency_type": "medical_general",
            "urgency": "priority_4_alpha",
            "suggested_coordinates": [-122.41, 37.77],
        })
        d_alpha = policy_engine.evaluate(c_alpha)
        assert ApparatusType.AMBULANCE_BLS in d_alpha.to_apparatus_type_list()
        assert d_alpha.weighting_profile == WeightingProfile.DISTANCE
        assert d_alpha.routing_objective == RoutingObjective.MINIMIZE_DISTANCE


class TestModelReconciliationAndAugmentation:
    """Tests how the policy engine handles model proposals vs statutory rules."""

    def test_compatible_model_apparatus_augmentation_accepted(self, policy_engine: EmergencyPolicyEngine) -> None:
        """Model proposed HEAVY_RESCUE for structure fire based on trapped victim context."""
        contract = validate_incident_proposal({
            "raw_report": "Fire in apartment building, caller says occupant trapped in bedroom.",
            "emergency_type": "structure_fire",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
            "suggested_apparatus": ["heavy_rescue"],  # model suggestion
        })

        directive = policy_engine.evaluate(contract, allow_model_augmentation=True)
        app_types = directive.to_apparatus_type_list()
        # Statutory 5 units + 1 model augmented unit = 6 units
        assert directive.total_apparatus_count == 6
        assert ApparatusType.HEAVY_RESCUE in app_types
        # Verify source tagging
        rescue_req = next(r for r in directive.required_apparatus if r.apparatus_type == ApparatusType.HEAVY_RESCUE)
        assert rescue_req.source == "model_augmented"
        assert rescue_req.is_mandatory is False
        assert "RULE_AUGMENT_TYPE_HEAVY_RESCUE" in directive.policy_rules_applied

    def test_model_quantity_augmentation_accepted(self, policy_engine: EmergencyPolicyEngine) -> None:
        """Model proposed 3 engines instead of baseline 2."""
        contract = validate_incident_proposal({
            "raw_report": "Large warehouse blaze spreading quickly.",
            "emergency_type": "structure_fire",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
            "suggested_apparatus": ["fire_engine", "fire_engine", "fire_engine"],
        })

        directive = policy_engine.evaluate(contract, allow_model_augmentation=True)
        engine_req = next(r for r in directive.required_apparatus if r.apparatus_type == ApparatusType.FIRE_ENGINE)
        assert engine_req.quantity == 3
        assert "RULE_AUGMENT_QUANTITY_FIRE_ENGINE" in directive.policy_rules_applied

    def test_incompatible_model_apparatus_rejected_with_warning(self, policy_engine: EmergencyPolicyEngine) -> None:
        """Model suggested HAZMAT_UNIT for routine back ache call."""
        contract = validate_incident_proposal({
            "raw_report": "Patient has mild flu symptoms.",
            "emergency_type": "medical_general",
            "urgency": "priority_3_bravo",
            "suggested_coordinates": [-122.41, 37.77],
            "suggested_apparatus": ["hazmat_unit"],  # bizarre model hallucination
        })

        directive = policy_engine.evaluate(contract, allow_model_augmentation=True)
        app_types = directive.to_apparatus_type_list()
        assert ApparatusType.HAZMAT_UNIT not in app_types
        assert any("rejected" in w for w in directive.policy_warnings)
        assert "RULE_REJECT_INCOMPATIBLE_HAZMAT_UNIT" in directive.policy_rules_applied

    def test_model_augmentation_disabled(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Fire call.",
            "emergency_type": "structure_fire",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
            "suggested_apparatus": ["heavy_rescue"],
        })

        directive = policy_engine.evaluate(contract, allow_model_augmentation=False)
        assert ApparatusType.HEAVY_RESCUE not in directive.to_apparatus_type_list()
        assert directive.total_apparatus_count == 5  # strictly baseline


class TestHazardDrivenRoutingPolicies:
    """Tests evaluating routing constraints when hazards are active."""

    def test_active_hazards_enforce_avoidance_threshold(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Tree fell on electrical lines causing fire on roadway.",
            "emergency_type": "structure_fire",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
            "hazards_detected": [
                {
                    "hazard_type": "structural_debris",
                    "description": "Downed high-voltage line",
                    "severity": "severe",
                }
            ],
        })

        directive = policy_engine.evaluate(contract)
        assert directive.has_constraint(RoutingConstraint.AVOID_ACTIVE_HAZARDS)
        assert directive.hazard_avoidance_threshold == HazardSeverity.MODERATE
        assert "RULE_ENFORCE_HAZARD_AVOIDANCE" in directive.policy_rules_applied

    def test_flood_hazard_enforces_flood_zone_bypass(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Medical assistance needed, road has high water.",
            "emergency_type": "medical_general",
            "urgency": "priority_1_echo",
            "suggested_coordinates": [-122.41, 37.77],
            "hazards_detected": [
                {
                    "hazard_type": "flash_flood",
                    "description": "Standing water 2 feet deep",
                }
            ],
        })

        directive = policy_engine.evaluate(contract)
        assert directive.has_constraint(RoutingConstraint.AVOID_FLOOD_ZONES)
        assert "RULE_ENFORCE_FLOOD_ZONE_BYPASS" in directive.policy_rules_applied


class TestInvalidContractHandling:
    """Tests handling contracts that failed validation or lack essential data."""

    def test_invalid_contract_is_not_dispatchable(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "",  # empty call
            "emergency_type": None,
            "urgency": None,
        })
        assert contract.is_valid is False

        directive = policy_engine.evaluate(contract)
        assert directive.is_dispatchable is False
        assert "POLICY_REJECT_INVALID_CONTRACT" in directive.policy_rules_applied
        assert len(directive.required_apparatus) == 0

    def test_wildland_fire_urgency_escalation(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Brush fire near ridge, moving slowly.",
            "emergency_type": "wildland_fire",
            "urgency": "priority_3_bravo",
            "suggested_coordinates": [-122.41, 37.77],
        })
        directive = policy_engine.evaluate(contract)
        assert directive.effective_urgency == UrgencyLevel.PRIORITY_1_ECHO
        assert "RULE_WILDLAND_URGENCY_ESCALATION" in directive.policy_rules_applied

    def test_hazmat_urgency_escalation(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Small solvent spill in laboratory sink.",
            "emergency_type": "hazmat_spill",
            "urgency": "priority_3_bravo",
            "suggested_coordinates": [-122.41, 37.77],
        })
        directive = policy_engine.evaluate(contract)
        assert directive.effective_urgency == UrgencyLevel.PRIORITY_2_DELTA
        assert "RULE_HAZMAT_URGENCY_DEFAULT" in directive.policy_rules_applied

    def test_apparatus_compatibility_matrix(self, policy_engine: EmergencyPolicyEngine) -> None:
        assert policy_engine._is_apparatus_compatible(EmergencyType.WILDLAND_FIRE, ApparatusType.LADDER_TRUCK) is True
        assert policy_engine._is_apparatus_compatible(EmergencyType.ROAD_TRAFFIC_COLLISION, ApparatusType.HEAVY_RESCUE) is True
        assert policy_engine._is_apparatus_compatible(EmergencyType.HAZMAT_SPILL, ApparatusType.HAZMAT_UNIT) is True
        assert policy_engine._is_apparatus_compatible(EmergencyType.FLASH_FLOOD, ApparatusType.HEAVY_RESCUE) is True
        assert policy_engine._is_apparatus_compatible(EmergencyType.FLASH_FLOOD, ApparatusType.LADDER_TRUCK) is False

    def test_directive_immutability(self, policy_engine: EmergencyPolicyEngine) -> None:
        contract = validate_incident_proposal({
            "raw_report": "Medical call.",
            "emergency_type": "medical_general",
            "urgency": "priority_2_delta",
            "suggested_coordinates": [-122.41, 37.77],
        })
        directive = policy_engine.evaluate(contract)
        with pytest.raises(Exception):  # FrozenInstanceError
            directive.effective_urgency = UrgencyLevel.PRIORITY_4_ALPHA  # type: ignore

