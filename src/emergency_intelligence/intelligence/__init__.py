"""
Emergency Intelligence AI — Intelligence & Natural-Language Interpretation Layer.
================================================================================
Defines domain contracts, boundary validation, and orchestration interfaces
governing the translation of unstructured emergency reports into deterministic
routing and fleet allocation directives.

Milestone 5.1: AI boundary and structured domain contracts.
Milestone 5.2: Deterministic emergency policy engine.
Milestone 5.3: Natural-language interpretation interface.
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
from emergency_intelligence.intelligence.interpreter import (
    AmbiguityType,
    EmergencyInterpreter,
    FixtureEmergencyInterpreter,
    InterpretationRequest,
    InterpretationResult,
    InterpreterErrorCode,
    detect_adversarial_patterns,
    mask_sensitive_telemetry,
    sanitize_emergency_text,
)
from emergency_intelligence.intelligence.policy import (
    ApparatusRequirement,
    EmergencyPolicyEngine,
    OperationalPolicyDirective,
    RoutingConstraint,
    RoutingObjective,
)

__all__ = [
    "AmbiguityType",
    "ApparatusRequirement",
    "EmergencyInterpreter",
    "EmergencyPolicyEngine",
    "FixtureEmergencyInterpreter",
    "HazardMention",
    "InterpretationRequest",
    "InterpretationResult",
    "InterpreterErrorCode",
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
    "detect_adversarial_patterns",
    "mask_sensitive_telemetry",
    "sanitize_emergency_text",
    "validate_incident_proposal",
]
