"""
Emergency Intelligence AI — Intelligence & Natural-Language Interpretation Layer.
================================================================================
Defines domain contracts, boundary validation, and orchestration interfaces
governing the translation of unstructured emergency reports into deterministic
routing and fleet allocation directives.

Milestone 5.1: AI boundary and structured domain contracts.
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

__all__ = [
    "HazardMention",
    "LocationProvenance",
    "LocationProvenanceType",
    "ProposedIncidentInterpretation",
    "ValidatedIncidentContract",
    "ValidationCode",
    "ValidationIssue",
    "ValidationSeverity",
    "ValidationStatus",
    "validate_incident_proposal",
]
