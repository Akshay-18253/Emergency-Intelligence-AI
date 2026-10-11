"""
Emergency Intelligence AI — Intelligence & Natural-Language Interpretation Layer.
================================================================================
Defines domain contracts, boundary validation, and orchestration interfaces
governing the translation of unstructured emergency reports into deterministic
routing and fleet allocation directives.

Milestone 5.1: AI boundary and structured domain contracts.
Milestone 5.2: Deterministic emergency policy engine.
"""

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

__all__ = [
    "ApparatusRequirement",
    "EmergencyPolicyEngine",
    "HazardMention",
    "LocationProvenance",
    "LocationProvenanceType",
    "OperationalPolicyDirective",
    "ProposedIncidentInterpretation",
    "RoutingConstraint",
    "RoutingObjective",
    "ValidatedIncidentContract",
    "ValidationCode",
    "ValidationIssue",
    "ValidationSeverity",
    "ValidationStatus",
    "validate_incident_proposal",
]
