"""
Deterministic Emergency Policy Engine (Milestone 5.2).
========================================================
Translates validated incident domain contracts into authoritative, statutory
operational directives, apparatus selection requirements, and routing constraints.

Architectural Invariant:
------------------------
The AI proposes structured emergency interpretations; the deterministic policy
engine dictates authoritative dispatch and routing decisions. Model suggestions
can inform policy augmentation, but CANNOT override statutory safety minimums,
downgrade life-threat urgency, or bypass physical road restrictions.

Adheres strictly to zero external runtime dependencies (100% Python standard library).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from emergency_intelligence.data.osm import WeightingProfile
from emergency_intelligence.events.hazards import HazardSeverity, HazardType
from emergency_intelligence.events.incidents import (
    ApparatusType,
    EmergencyType,
    UrgencyLevel,
)
from emergency_intelligence.intelligence.contracts import (
    ValidatedIncidentContract,
    ValidationStatus,
)


class RoutingObjective(str, Enum):
    """High-level navigational optimization objective for emergency apparatus."""

    MINIMIZE_RESPONSE_TIME = "minimize_response_time"  # Siren-authorized rapid arrival (Echo/Delta)
    MINIMIZE_DISTANCE = "minimize_distance"            # Non-emergency relocation / staging (Alpha)
    MAXIMIZE_CREW_SAFETY = "maximize_crew_safety"      # Standoff routing avoiding plumes / collapses
    BALANCED_TRAVEL = "balanced_travel"                # Standard urban navigation for routine calls (Bravo)


class RoutingConstraint(str, Enum):
    """Deterministic routing constraints enforced on downstream path calculation."""

    EMERGENCY_SIREN_PRIVILEGE = "emergency_siren_privilege"  # Authorize emergency speed factor & bypass access=no
    AVOID_ACTIVE_HAZARDS = "avoid_active_hazards"            # Strictly avoid edges penetrating active hazard zones
    AVOID_FLOOD_ZONES = "avoid_flood_zones"                  # Specific avoidance of standing water and flash floods
    AVOID_BRIDGES_TUNNELS = "avoid_bridges_tunnels"          # Avoid confined tunnels (Hazmat or structural collapse)
    STANDARD_CIVILIAN_SPEEDS = "standard_civilian_speeds"    # Enforce standard speed limits (no emergency sirens)


@dataclass(frozen=True)
class ApparatusRequirement:
    """An individual apparatus requirement mandated or augmented by emergency policy.

    Attributes:
        apparatus_type: Standardized apparatus classification.
        quantity: Number of apparatus units required.
        is_mandatory: True if mandated by statutory dispatch policy (cannot be waived).
        rationale: Operational justification explaining why this apparatus is required.
        source: Provenance of requirement ('statutory_policy' or 'model_augmented').
    """

    apparatus_type: ApparatusType
    quantity: int = 1
    is_mandatory: bool = True
    rationale: str = ""
    source: str = "statutory_policy"

    def __post_init__(self) -> None:
        if not isinstance(self.apparatus_type, ApparatusType):
            if isinstance(self.apparatus_type, str):
                object.__setattr__(self, "apparatus_type", ApparatusType(self.apparatus_type))
            else:
                raise TypeError(f"ApparatusRequirement.apparatus_type must be an ApparatusType, got {type(self.apparatus_type)}.")

        if int(self.quantity) <= 0:
            raise ValueError(f"ApparatusRequirement.quantity must be a positive integer, got {self.quantity}.")


@dataclass(frozen=True)
class OperationalPolicyDirective:
    """Authoritative operational directive produced by the deterministic policy engine.

    Directs fleet dispatch matching and routing profile selection. Fully auditable,
    recording every rule applied and any reconciliation made with model suggestions.

    Attributes:
        incident_id: Unique incident identifier.
        effective_urgency: Authoritative triage urgency tier determined by policy.
        effective_emergency_type: Authoritative emergency classification.
        required_apparatus: Tuple of mandated and augmented apparatus requirements.
        weighting_profile: Cost calculation profile (from `WeightingProfile`).
        routing_objective: Optimization objective for path planning.
        routing_constraints: Tuple of deterministic routing constraints.
        hazard_avoidance_threshold: Minimum hazard severity to actively bypass.
        policy_rules_applied: Tuple of auditable rule identifiers fired during evaluation.
        policy_warnings: Tuple of warnings regarding contradictions or model overrides.
        audit_timestamp: UTC timestamp when directive was formulated.
        is_dispatchable: True if directive possesses sufficient valid data to dispatch units.
    """

    incident_id: str
    effective_urgency: UrgencyLevel
    effective_emergency_type: EmergencyType
    required_apparatus: Tuple[ApparatusRequirement, ...]
    weighting_profile: str
    routing_objective: RoutingObjective
    routing_constraints: Tuple[RoutingConstraint, ...]
    hazard_avoidance_threshold: Optional[HazardSeverity]
    policy_rules_applied: Tuple[str, ...]
    policy_warnings: Tuple[str, ...]
    audit_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_dispatchable: bool = True

    @property
    def total_apparatus_count(self) -> int:
        """Returns the total number of apparatus units required across all types."""
        return sum(req.quantity for req in self.required_apparatus)

    def has_constraint(self, constraint: RoutingConstraint) -> bool:
        """Returns True if the specified routing constraint is active."""
        return constraint in self.routing_constraints

    def to_apparatus_type_list(self) -> List[ApparatusType]:
        """Flattens requirements into an individual ApparatusType list for FleetManager dispatch."""
        result: List[ApparatusType] = []
        for req in self.required_apparatus:
            result.extend([req.apparatus_type] * req.quantity)
        return result


class EmergencyPolicyEngine:
    """Deterministic policy engine enforcing municipal dispatch standards and routing rules.

    Reconciles model-proposed interpretations with statutory Standard Operating
    Procedures (SOPs), NFPA 1710 alarm standards, and mutual-aid protocols.
    """

    def __init__(self, jurisdiction: str = "default_municipal") -> None:
        self.jurisdiction = str(jurisdiction)

    def evaluate(
        self,
        contract: ValidatedIncidentContract,
        allow_model_augmentation: bool = True,
    ) -> OperationalPolicyDirective:
        """Evaluates a validated incident contract into an authoritative operational directive.

        Parameters:
            contract: The validated domain contract emitted by Milestone 5.1 validation.
            allow_model_augmentation: If True, permits valid model suggestions to augment
                (but never reduce) statutory minimum apparatus requirements.

        Returns:
            OperationalPolicyDirective: Authoritative dispatch and routing instructions.
        """
        rules_applied: List[str] = []
        warnings: List[str] = []

        # 1. Gate Check: Contract Validity
        if not contract.is_valid or contract.emergency_type is None or contract.urgency is None:
            issue_msgs = [f"[{i.code.value}] {i.message}" for i in contract.validation_issues]
            return OperationalPolicyDirective(
                incident_id=contract.incident_id,
                effective_urgency=contract.urgency or UrgencyLevel.PRIORITY_4_ALPHA,
                effective_emergency_type=contract.emergency_type or EmergencyType.MEDICAL_GENERAL,
                required_apparatus=(),
                weighting_profile=WeightingProfile.TRAVEL_TIME,
                routing_objective=RoutingObjective.BALANCED_TRAVEL,
                routing_constraints=(),
                hazard_avoidance_threshold=None,
                policy_rules_applied=("POLICY_REJECT_INVALID_CONTRACT",),
                policy_warnings=tuple(issue_msgs or ["Contract failed validation checks."]),
                is_dispatchable=False,
            )

        e_type = contract.emergency_type
        proposed_urgency = contract.urgency
        effective_urgency = proposed_urgency
        baseline_reqs: Dict[ApparatusType, ApparatusRequirement] = {}
        constraints: Set[RoutingConstraint] = set()

        # 2. Statutory Policy Rules by Emergency Type
        if e_type == EmergencyType.STRUCTURE_FIRE:
            # NFPA 1710 Initial Full Alarm Assignment
            if effective_urgency != UrgencyLevel.PRIORITY_1_ECHO:
                effective_urgency = UrgencyLevel.PRIORITY_1_ECHO
                warnings.append("Escalated structure fire to Priority 1 Echo per statutory SOP.")
                rules_applied.append("RULE_FIRE_URGENCY_ESCALATION")

            baseline_reqs[ApparatusType.FIRE_ENGINE] = ApparatusRequirement(
                ApparatusType.FIRE_ENGINE, quantity=2, is_mandatory=True,
                rationale="NFPA 1710 initial suppression & water supply pumper units."
            )
            baseline_reqs[ApparatusType.LADDER_TRUCK] = ApparatusRequirement(
                ApparatusType.LADDER_TRUCK, quantity=1, is_mandatory=True,
                rationale="Aerial rescue, forcible entry, and roof ventilation."
            )
            baseline_reqs[ApparatusType.BATTALION_CHIEF] = ApparatusRequirement(
                ApparatusType.BATTALION_CHIEF, quantity=1, is_mandatory=True,
                rationale="Incident Command and tactical safety officer."
            )
            baseline_reqs[ApparatusType.AMBULANCE_ALS] = ApparatusRequirement(
                ApparatusType.AMBULANCE_ALS, quantity=1, is_mandatory=True,
                rationale="Rapid Intervention Team (RIT) medical standby and victim transport."
            )
            constraints.add(RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE)
            constraints.add(RoutingConstraint.AVOID_ACTIVE_HAZARDS)
            rules_applied.append("RULE_FIRE_STRUCTURE_FULL_ALARM")

        elif e_type == EmergencyType.WILDLAND_FIRE:
            if effective_urgency not in (UrgencyLevel.PRIORITY_1_ECHO, UrgencyLevel.PRIORITY_2_DELTA):
                effective_urgency = UrgencyLevel.PRIORITY_1_ECHO
                rules_applied.append("RULE_WILDLAND_URGENCY_ESCALATION")

            baseline_reqs[ApparatusType.FIRE_ENGINE] = ApparatusRequirement(
                ApparatusType.FIRE_ENGINE, quantity=2, is_mandatory=True,
                rationale="Wildland-urban interface brush & structural defense."
            )
            baseline_reqs[ApparatusType.BATTALION_CHIEF] = ApparatusRequirement(
                ApparatusType.BATTALION_CHIEF, quantity=1, is_mandatory=True,
                rationale="Wildland sector incident commander."
            )
            constraints.add(RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE)
            constraints.add(RoutingConstraint.AVOID_ACTIVE_HAZARDS)
            rules_applied.append("RULE_WILDLAND_FIRE_ASSIGNMENT")

        elif e_type == EmergencyType.CARDIAC_ARREST:
            effective_urgency = UrgencyLevel.PRIORITY_1_ECHO
            baseline_reqs[ApparatusType.AMBULANCE_ALS] = ApparatusRequirement(
                ApparatusType.AMBULANCE_ALS, quantity=1, is_mandatory=True,
                rationale="Paramedic resuscitation, defibrillation, advanced airway management."
            )
            baseline_reqs[ApparatusType.FIRE_ENGINE] = ApparatusRequirement(
                ApparatusType.FIRE_ENGINE, quantity=1, is_mandatory=True,
                rationale="Dual-response company for high-performance CPR & mechanical chest compression."
            )
            constraints.add(RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE)
            rules_applied.append("RULE_CARDIAC_DUAL_RESPONSE_MANDATE")

        elif e_type == EmergencyType.TRAUMA_MAJOR:
            effective_urgency = UrgencyLevel.PRIORITY_1_ECHO
            baseline_reqs[ApparatusType.AMBULANCE_ALS] = ApparatusRequirement(
                ApparatusType.AMBULANCE_ALS, quantity=1, is_mandatory=True,
                rationale="Immediate advanced trauma life support and regional trauma center transfer."
            )
            constraints.add(RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE)
            rules_applied.append("RULE_TRAUMA_ALS_RAPID_DISPATCH")

        elif e_type == EmergencyType.HAZMAT_SPILL:
            if effective_urgency not in (UrgencyLevel.PRIORITY_1_ECHO, UrgencyLevel.PRIORITY_2_DELTA):
                effective_urgency = UrgencyLevel.PRIORITY_2_DELTA
                rules_applied.append("RULE_HAZMAT_URGENCY_DEFAULT")

            baseline_reqs[ApparatusType.HAZMAT_UNIT] = ApparatusRequirement(
                ApparatusType.HAZMAT_UNIT, quantity=1, is_mandatory=True,
                rationale="Chemical containment, air monitoring, and decontamination corridor."
            )
            baseline_reqs[ApparatusType.FIRE_ENGINE] = ApparatusRequirement(
                ApparatusType.FIRE_ENGINE, quantity=1, is_mandatory=True,
                rationale="Vapor suppression and water curtain protection."
            )
            baseline_reqs[ApparatusType.AMBULANCE_ALS] = ApparatusRequirement(
                ApparatusType.AMBULANCE_ALS, quantity=1, is_mandatory=True,
                rationale="Toxic exposure paramedic triage and antidote administration."
            )
            constraints.add(RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE)
            constraints.add(RoutingConstraint.AVOID_ACTIVE_HAZARDS)
            constraints.add(RoutingConstraint.AVOID_BRIDGES_TUNNELS)
            rules_applied.append("RULE_HAZMAT_CONTAINMENT_AND_TUNNEL_BAN")

        elif e_type == EmergencyType.FLASH_FLOOD:
            effective_urgency = UrgencyLevel.PRIORITY_1_ECHO
            baseline_reqs[ApparatusType.HEAVY_RESCUE] = ApparatusRequirement(
                ApparatusType.HEAVY_RESCUE, quantity=1, is_mandatory=True,
                rationale="Swift-water rescue technicians and inflatable rescue craft."
            )
            baseline_reqs[ApparatusType.FIRE_ENGINE] = ApparatusRequirement(
                ApparatusType.FIRE_ENGINE, quantity=1, is_mandatory=True,
                rationale="Shore-based safety line and winch recovery operations."
            )
            baseline_reqs[ApparatusType.AMBULANCE_ALS] = ApparatusRequirement(
                ApparatusType.AMBULANCE_ALS, quantity=1, is_mandatory=True,
                rationale="Hypothermia and submersion injury resuscitation."
            )
            constraints.add(RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE)
            constraints.add(RoutingConstraint.AVOID_ACTIVE_HAZARDS)
            constraints.add(RoutingConstraint.AVOID_FLOOD_ZONES)
            rules_applied.append("RULE_SWIFT_WATER_RESCUE_FLOOD_AVOIDANCE")

        elif e_type == EmergencyType.STRUCTURAL_COLLAPSE:
            effective_urgency = UrgencyLevel.PRIORITY_1_ECHO
            baseline_reqs[ApparatusType.HEAVY_RESCUE] = ApparatusRequirement(
                ApparatusType.HEAVY_RESCUE, quantity=1, is_mandatory=True,
                rationale="Urban search and rescue (USAR) shoring, listening devices, breaching tools."
            )
            baseline_reqs[ApparatusType.LADDER_TRUCK] = ApparatusRequirement(
                ApparatusType.LADDER_TRUCK, quantity=1, is_mandatory=True,
                rationale="Overhead crane/aerial anchor point and high-angle egress."
            )
            baseline_reqs[ApparatusType.FIRE_ENGINE] = ApparatusRequirement(
                ApparatusType.FIRE_ENGINE, quantity=1, is_mandatory=True,
                rationale="Collapse zone fire watch and utility control."
            )
            baseline_reqs[ApparatusType.AMBULANCE_ALS] = ApparatusRequirement(
                ApparatusType.AMBULANCE_ALS, quantity=1, is_mandatory=True,
                rationale="Confined space extrication trauma triage and crush syndrome treatment."
            )
            constraints.add(RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE)
            constraints.add(RoutingConstraint.AVOID_ACTIVE_HAZARDS)
            rules_applied.append("RULE_COLLAPSE_USAR_RESPONSE")

        elif e_type == EmergencyType.ROAD_TRAFFIC_COLLISION:
            if effective_urgency in (UrgencyLevel.PRIORITY_1_ECHO, UrgencyLevel.PRIORITY_2_DELTA):
                baseline_reqs[ApparatusType.FIRE_ENGINE] = ApparatusRequirement(
                    ApparatusType.FIRE_ENGINE, quantity=1, is_mandatory=True,
                    rationale="Hydraulic extrication tools (Jaws of Life) and hazard control."
                )
                baseline_reqs[ApparatusType.AMBULANCE_ALS] = ApparatusRequirement(
                    ApparatusType.AMBULANCE_ALS, quantity=1, is_mandatory=True,
                    rationale="Advanced trauma care and immobilization."
                )
                constraints.add(RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE)
                rules_applied.append("RULE_MVA_EXTRICATION_RESPONSE")
            else:
                baseline_reqs[ApparatusType.AMBULANCE_BLS] = ApparatusRequirement(
                    ApparatusType.AMBULANCE_BLS, quantity=1, is_mandatory=True,
                    rationale="Basic evaluation and transport for minor collision."
                )
                constraints.add(RoutingConstraint.STANDARD_CIVILIAN_SPEEDS)
                rules_applied.append("RULE_MVA_MINOR_EVALUATION")

        elif e_type == EmergencyType.MEDICAL_GENERAL:
            if effective_urgency in (UrgencyLevel.PRIORITY_1_ECHO, UrgencyLevel.PRIORITY_2_DELTA):
                baseline_reqs[ApparatusType.AMBULANCE_ALS] = ApparatusRequirement(
                    ApparatusType.AMBULANCE_ALS, quantity=1, is_mandatory=True,
                    rationale="Advanced Life Support paramedic evaluation and transport."
                )
                constraints.add(RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE)
                rules_applied.append("RULE_MEDICAL_ACUTE_ALS")
            else:
                baseline_reqs[ApparatusType.AMBULANCE_BLS] = ApparatusRequirement(
                    ApparatusType.AMBULANCE_BLS, quantity=1, is_mandatory=True,
                    rationale="Basic Life Support non-emergent medical transport."
                )
                constraints.add(RoutingConstraint.STANDARD_CIVILIAN_SPEEDS)
                rules_applied.append("RULE_MEDICAL_ROUTINE_BLS")

        # 3. Model Suggestion Reconciliation & Policy Augmentation
        if allow_model_augmentation:
            # Map proposed apparatus quantities
            model_counts: Dict[ApparatusType, int] = {}
            for app in contract.required_apparatus:
                model_counts[app] = model_counts.get(app, 0) + 1

            for model_app, count in model_counts.items():
                if model_app in baseline_reqs:
                    current_req = baseline_reqs[model_app]
                    if count > current_req.quantity:
                        # Model proposed additional units of an authorized type
                        baseline_reqs[model_app] = ApparatusRequirement(
                            apparatus_type=model_app,
                            quantity=count,
                            is_mandatory=current_req.is_mandatory,
                            rationale=f"{current_req.rationale} (Quantity augmented to {count} by model proposal).",
                            source="model_augmented",
                        )
                        rules_applied.append(f"RULE_AUGMENT_QUANTITY_{model_app.value.upper()}")
                else:
                    # Model proposed an extra apparatus type not in the minimum baseline
                    # Verify compatibility with emergency domain
                    is_compatible = self._is_apparatus_compatible(e_type, model_app)
                    if is_compatible:
                        baseline_reqs[model_app] = ApparatusRequirement(
                            apparatus_type=model_app,
                            quantity=count,
                            is_mandatory=False,
                            rationale=f"Model suggested additional {model_app.value} based on caller context.",
                            source="model_augmented",
                        )
                        rules_applied.append(f"RULE_AUGMENT_TYPE_{model_app.value.upper()}")
                    else:
                        warnings.append(
                            f"Model-suggested apparatus '{model_app.value}' rejected as operationally incompatible with {e_type.value}."
                        )
                        rules_applied.append(f"RULE_REJECT_INCOMPATIBLE_{model_app.value.upper()}")

        # 4. Hazard-Driven Constraints
        hazard_threshold: Optional[HazardSeverity] = None
        if contract.identified_hazards:
            constraints.add(RoutingConstraint.AVOID_ACTIVE_HAZARDS)
            hazard_threshold = HazardSeverity.MODERATE
            rules_applied.append("RULE_ENFORCE_HAZARD_AVOIDANCE")
            for h in contract.identified_hazards:
                if h.hazard_type in (HazardType.FLASH_FLOOD, HazardType.FLOOD_INUNDATION):
                    constraints.add(RoutingConstraint.AVOID_FLOOD_ZONES)
                    rules_applied.append("RULE_ENFORCE_FLOOD_ZONE_BYPASS")

        # 5. Routing Profile & Objective Selection
        if RoutingConstraint.EMERGENCY_SIREN_PRIVILEGE in constraints:
            profile = WeightingProfile.EMERGENCY_TIME
            objective = (
                RoutingObjective.MAXIMIZE_CREW_SAFETY
                if e_type in (EmergencyType.HAZMAT_SPILL, EmergencyType.WILDLAND_FIRE)
                else RoutingObjective.MINIMIZE_RESPONSE_TIME
            )
        elif effective_urgency == UrgencyLevel.PRIORITY_3_BRAVO:
            profile = WeightingProfile.TRAVEL_TIME
            objective = RoutingObjective.BALANCED_TRAVEL
        else:
            profile = WeightingProfile.DISTANCE
            objective = RoutingObjective.MINIMIZE_DISTANCE

        # Sort apparatus requirements deterministically: mandatory first, then by apparatus name
        sorted_reqs = tuple(
            sorted(baseline_reqs.values(), key=lambda r: (not r.is_mandatory, r.apparatus_type.value))
        )

        return OperationalPolicyDirective(
            incident_id=contract.incident_id,
            effective_urgency=effective_urgency,
            effective_emergency_type=e_type,
            required_apparatus=sorted_reqs,
            weighting_profile=profile,
            routing_objective=objective,
            routing_constraints=tuple(sorted(constraints, key=lambda c: c.value)),
            hazard_avoidance_threshold=hazard_threshold,
            policy_rules_applied=tuple(rules_applied),
            policy_warnings=tuple(warnings),
            is_dispatchable=True,
        )

    def _is_apparatus_compatible(self, e_type: EmergencyType, app: ApparatusType) -> bool:
        """Determines if an apparatus type is operationally viable for an incident category."""
        # Fire emergencies accept fire, rescue, ladder, chief, and ALS medical
        if e_type in (EmergencyType.STRUCTURE_FIRE, EmergencyType.WILDLAND_FIRE, EmergencyType.STRUCTURAL_COLLAPSE):
            return app in (
                ApparatusType.FIRE_ENGINE,
                ApparatusType.LADDER_TRUCK,
                ApparatusType.HEAVY_RESCUE,
                ApparatusType.BATTALION_CHIEF,
                ApparatusType.AMBULANCE_ALS,
                ApparatusType.AMBULANCE_BLS,
            )
        # Medical calls accept ambulances, engines (CPR/first responder), and heavy rescue (extrication)
        if e_type in (EmergencyType.CARDIAC_ARREST, EmergencyType.TRAUMA_MAJOR, EmergencyType.MEDICAL_GENERAL):
            return app in (
                ApparatusType.AMBULANCE_ALS,
                ApparatusType.AMBULANCE_BLS,
                ApparatusType.FIRE_ENGINE,
                ApparatusType.HEAVY_RESCUE,
            )
        # Road traffic collisions accept engines, rescue, and ambulances
        if e_type == EmergencyType.ROAD_TRAFFIC_COLLISION:
            return app in (
                ApparatusType.FIRE_ENGINE,
                ApparatusType.HEAVY_RESCUE,
                ApparatusType.AMBULANCE_ALS,
                ApparatusType.AMBULANCE_BLS,
            )
        # Hazmat accepts hazmat units, engines, chief, rescue, ambulances
        if e_type == EmergencyType.HAZMAT_SPILL:
            return app in (
                ApparatusType.HAZMAT_UNIT,
                ApparatusType.FIRE_ENGINE,
                ApparatusType.HEAVY_RESCUE,
                ApparatusType.BATTALION_CHIEF,
                ApparatusType.AMBULANCE_ALS,
            )
        # Floods accept rescue, engines, ambulances
        if e_type == EmergencyType.FLASH_FLOOD:
            return app in (
                ApparatusType.HEAVY_RESCUE,
                ApparatusType.FIRE_ENGINE,
                ApparatusType.AMBULANCE_ALS,
            )
        return False
