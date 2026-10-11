"""
Emergency Intelligence AI — Intelligence & Natural-Language Interpretation Layer.
================================================================================
Defines domain contracts, boundary validation, and orchestration interfaces
governing the translation of unstructured emergency reports into deterministic
routing and fleet allocation directives.

Milestone 5.1: AI boundary and structured domain contracts.
Milestone 5.2: Deterministic emergency policy engine.
Milestone 5.3: Natural-language interpretation interface.
Milestone 5.4: Model adapter and end-to-end orchestration.
"""

from emergency_intelligence.intelligence.adapter import (
    EMERGENCY_PROPOSAL_JSON_SCHEMA,
    FakeModelProvider,
    ModelProvider,
    ProviderAuthenticationError,
    ProviderError,
    ProviderMalformedOutputError,
    ProviderNetworkError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    RetryPolicy,
    StructuredModelAdapter,
    extract_json_payload,
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
from emergency_intelligence.intelligence.orchestrator import (
    DispatchedRouteSummary,
    EmergencyIntelligenceOrchestrator,
    OrchestrationResult,
    OrchestrationStatus,
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
    "DispatchedRouteSummary",
    "EMERGENCY_PROPOSAL_JSON_SCHEMA",
    "EmergencyIntelligenceOrchestrator",
    "EmergencyInterpreter",
    "EmergencyPolicyEngine",
    "FakeModelProvider",
    "FixtureEmergencyInterpreter",
    "HazardMention",
    "InterpretationRequest",
    "InterpretationResult",
    "InterpreterErrorCode",
    "LocationProvenance",
    "LocationProvenanceType",
    "ModelProvider",
    "OperationalPolicyDirective",
    "OrchestrationResult",
    "OrchestrationStatus",
    "ProposedIncidentInterpretation",
    "ProviderAuthenticationError",
    "ProviderError",
    "ProviderMalformedOutputError",
    "ProviderNetworkError",
    "ProviderRateLimitError",
    "ProviderTimeoutError",
    "RetryPolicy",
    "RoutingConstraint",
    "RoutingObjective",
    "StructuredModelAdapter",
    "ValidatedIncidentContract",
    "ValidationCode",
    "ValidationIssue",
    "ValidationSeverity",
    "ValidationStatus",
    "detect_adversarial_patterns",
    "extract_json_payload",
    "mask_sensitive_telemetry",
    "sanitize_emergency_text",
    "validate_incident_proposal",
]
