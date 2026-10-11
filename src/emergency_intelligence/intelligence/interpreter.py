"""
Natural-Language Interpretation Interface (Milestone 5.3).
===========================================================
Defines the provider-independent natural-language interpretation interface
that transforms unstructured emergency descriptions into structured, unvalidated
`ProposedIncidentInterpretation` proposals.

Architectural Invariant:
------------------------
1. The AI interprets the emergency; the deterministic engine calculates the route.
2. The interpretation interface emits PROPOSALS (untrusted DTOs), NEVER authoritative
   emergency dispatch, triage, or routing decisions.
3. The interface is strictly decoupled from any external LLM provider, SDK, or network.
4. Ambiguity, uncertainty, missing data, and adversarial attempts are explicitly
   represented and surfaced, never masked by fabricated certainty.
5. All proposals must subsequently pass through deterministic contract validation
   (`validate_incident_proposal`) and the statutory emergency policy engine
   (`EmergencyPolicyEngine`) before any downstream action.

Zero external runtime dependencies: 100% Python standard library.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from emergency_intelligence.events.hazards import HazardSeverity, HazardType
from emergency_intelligence.events.incidents import (
    ApparatusType,
    EmergencyType,
    UrgencyLevel,
)
from emergency_intelligence.intelligence.contracts import (
    ProposedIncidentInterpretation,
    ValidatedIncidentContract,
    validate_incident_proposal,
)


# Default input length constraints (RFC/CAD telecommunications standards)
DEFAULT_MAX_INPUT_LENGTH = 4000
MIN_VALID_INPUT_LENGTH = 3


class InterpreterErrorCode(str, Enum):
    """Standardized error codes for interpretation interface failures."""

    EMPTY_INPUT = "empty_input"
    INPUT_TOO_LONG = "input_too_long"
    MALFORMED_INPUT = "malformed_input"
    UNSUPPORTED_INCIDENT_TYPE = "unsupported_incident_type"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    CONTRADICTORY_INPUT = "contradictory_input"
    ADVERSARIAL_INJECTION_DETECTED = "adversarial_injection_detected"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INTERNAL_INTERPRETATION_ERROR = "internal_interpretation_error"


class AmbiguityType(str, Enum):
    """Categories of ambiguity identified in unstructured reports."""

    MISSING_LOCATION = "missing_location"
    VAGUE_SYMPTOMS = "vague_symptoms"
    UNCERTAIN_SEVERITY = "uncertain_severity"
    MULTIPLE_INCIDENTS = "multiple_incidents"
    CONTRADICTORY_STATEMENTS = "contradictory_statements"
    UNVERIFIED_HAZARDS = "unverified_hazards"


# Patterns indicative of prompt injection, instruction override, or bypass attempts
_ADVERSARIAL_INJECTION_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"\bignore\s+(all\s+)?(previous\s+)?(safety\s+|system\s+|operating\s+|policy\s+)?(rules|instructions|prompts|guidelines)\b", "instruction_override_attempt"),
    (r"\b(override|bypass|disable)\s+(all\s+)?(safety|statutory|speed|road|routing|hazard|policy|tunnel|bridge|traffic)\s*(rules|constraints|restrictions|limits)?\b", "safety_bypass_attempt"),
    (r"\bclassify\s+(this\s+)?(as\s+)?(non-urgent|routine|minor|alpha|bravo|priority\s*4)\b", "under_triage_injection"),
    (r"\bpretend\s+(you\s+are|to\s+be)\b", "persona_manipulation"),
    (r"\b(system\s+prompt|developer\s+mode|jailbreak)\b", "jailbreak_probe"),
    (r"\bdo\s+not\s+(dispatch|send|call)\s+(any\s+|an?\s+)?(ambulance|police|fire|first\s+responders)\b", "dispatch_suppression_attempt"),
    (r"\bignore\s+(the\s+)?road\s+(closure|hazard|block)\b", "routing_override_attempt"),
)


def sanitize_emergency_text(text: str, max_length: int = DEFAULT_MAX_INPUT_LENGTH) -> str:
    """Normalizes and sanitizes raw emergency text input.

    - Strips non-printable control characters (preserving standard newlines/tabs).
    - Collapses excessive whitespace sequences.
    - Enforces length bounds without truncating silent errors.

    Parameters:
        text: Raw caller or CAD description string.
        max_length: Maximum allowed character count.

    Returns:
        Cleaned, normalized string.

    Raises:
        ValueError: If text is empty, whitespace-only, or exceeds max_length.
    """
    if text is None:
        raise ValueError("Emergency text input cannot be None.")

    # Strip control characters except newline and tab
    cleaned = "".join(ch for ch in text if ch.isprintable() or ch in ("\n", "\t"))
    cleaned = cleaned.strip()

    if len(cleaned) < MIN_VALID_INPUT_LENGTH:
        raise ValueError(f"Emergency text input is too short ({len(cleaned)} chars, minimum {MIN_VALID_INPUT_LENGTH}).")

    if len(cleaned) > max_length:
        raise ValueError(
            f"Emergency text input exceeds maximum length limit ({len(cleaned)} > {max_length} chars)."
        )

    return cleaned


def detect_adversarial_patterns(text: str) -> List[str]:
    """Inspects raw text for prompt injection and constraint bypass attempts.

    Parameters:
        text: Raw emergency text.

    Returns:
        List of detected adversarial flag strings.
    """
    flags: List[str] = []
    text_lower = text.lower()
    for pattern, flag_name in _ADVERSARIAL_INJECTION_PATTERNS:
        if re.search(pattern, text_lower):
            flags.append(flag_name)
    return flags


def mask_sensitive_telemetry(text: str) -> str:
    """Redacts potential personal identification data (SSN, credit card, phone).

    Ensures sensitive details are not propagated into auxiliary audit telemetry.
    """
    # Mask SSN patterns (XXX-XX-XXXX)
    redacted = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED-SSN]", text)
    # Mask full payment card sequences (16 digits)
    redacted = re.sub(r"\b(?:\d{4}[ -]?){3}\d{4}\b", "[REDACTED-CARD]", redacted)
    # Mask standard 10-digit phone numbers
    redacted = re.sub(r"(?:(?:\+?1[-.\s]?)?\(?\d{3}\)?|\b\d{3})[-.\s]?\d{3}[-.\s]?\d{4}\b", "[REDACTED-PHONE]", redacted)
    return redacted


@dataclass(frozen=True)
class InterpretationRequest:
    """Encapsulates a request for natural-language emergency interpretation.

    Attributes:
        raw_text: Unstructured text description from caller, 911 operator, or CAD feed.
        request_id: Unique tracking identifier.
        context_metadata: Auxiliary caller or dispatch telemetry (e.g. CAD channel, timestamp).
        max_length: Maximum allowed character length for the report.
    """

    raw_text: str
    request_id: str = field(default_factory=lambda: hashlib.sha256(f"{datetime.now(timezone.utc)}".encode()).hexdigest()[:16])
    context_metadata: Dict[str, Any] = field(default_factory=dict)
    max_length: int = DEFAULT_MAX_INPUT_LENGTH

    def __post_init__(self) -> None:
        if not isinstance(self.raw_text, str):
            raise TypeError(f"InterpretationRequest.raw_text must be str, got {type(self.raw_text)}.")


@dataclass(frozen=True)
class InterpretationResult:
    """Structured response emitted by the interpretation interface.

    Attributes:
        success: True if an interpretation was successfully formulated.
        proposal: The generated `ProposedIncidentInterpretation` DTO (if successful).
        clarification_needed: True if ambiguity requires operator/caller follow-up questions.
        clarification_questions: Recommended questions to resolve missing or ambiguous details.
        reported_symptoms: Specific patient/casualty symptoms extracted from text.
        reported_circumstances: Environmental/physical circumstances extracted from text.
        ambiguities: Identified ambiguity types.
        adversarial_flags: Flags indicating attempted instruction injection or override.
        confidence_score: Self-reported model/interpreter confidence in [0.0, 1.0].
        uncertainty_notes: Explanations of unconfirmed or missing information.
        error_code: Standardized machine-readable error code if processing failed.
        error_message: Human-readable diagnostic description of any failure.
        metadata: Audit metadata (interpreter class, latency, input digest).
    """

    success: bool
    proposal: Optional[ProposedIncidentInterpretation] = None
    clarification_needed: bool = False
    clarification_questions: Tuple[str, ...] = field(default_factory=tuple)
    reported_symptoms: Tuple[str, ...] = field(default_factory=tuple)
    reported_circumstances: Tuple[str, ...] = field(default_factory=tuple)
    ambiguities: Tuple[AmbiguityType, ...] = field(default_factory=tuple)
    adversarial_flags: Tuple[str, ...] = field(default_factory=tuple)
    confidence_score: float = 0.0
    uncertainty_notes: Tuple[str, ...] = field(default_factory=tuple)
    error_code: Optional[InterpreterErrorCode] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_proposal(self) -> bool:
        """Returns True if a candidate proposal is present."""
        return self.proposal is not None

    def validate_contract(self) -> ValidatedIncidentContract:
        """Convenience method to validate the generated proposal into an authoritative contract.

        Raises:
            ValueError: If no candidate proposal exists or interpretation failed.
        """
        if self.proposal is None:
            raise ValueError(
                f"Cannot validate contract: InterpretationResult has no candidate proposal. "
                f"Error: {self.error_code.value if self.error_code else 'unknown'}: {self.error_message}"
            )
        return validate_incident_proposal(self.proposal)


class EmergencyInterpreter(ABC):
    """Abstract provider-independent natural-language interpretation interface.

    Subclasses implement specific interpretation strategies (fixture doubles, rule-based
    parsers, or provider-specific LLM adapters in future milestones).
    """

    @abstractmethod
    def interpret(self, request: InterpretationRequest) -> InterpretationResult:
        """Transforms an emergency request into a structured interpretation result.

        Must adhere to:
        - Never raise unhandled provider exceptions; return controlled InterpretationResult.
        - Surface honest uncertainty rather than fabricating details.
        - Detect and flag adversarial override attempts.
        - Enforce input bounds and data sanitization.
        """
        raise NotImplementedError

    def interpret_text(
        self,
        raw_text: str,
        context_metadata: Optional[Dict[str, Any]] = None,
        max_length: int = DEFAULT_MAX_INPUT_LENGTH,
    ) -> InterpretationResult:
        """Convenience helper to interpret raw text directly."""
        req = InterpretationRequest(
            raw_text=raw_text,
            context_metadata=context_metadata or {},
            max_length=max_length,
        )
        return self.interpret(req)


# ===========================================================================
# Fixture-Based Reference Interpreter (Test Double & Interface Baseline)
# ===========================================================================

@dataclass
class _FixtureRule:
    """Pattern matching rule used by the reference interpreter."""

    pattern: str
    emergency_type: Optional[EmergencyType]
    urgency: Optional[UrgencyLevel]
    apparatus: List[ApparatusType]
    symptoms: List[str]
    circumstances: List[str]
    hazards: List[Dict[str, Any]]
    confidence: float
    requires_location: bool = True


class FixtureEmergencyInterpreter(EmergencyInterpreter):
    """Deterministic, fixture-based reference implementation of `EmergencyInterpreter`.

    IMPORTANT NOTE:
    ----------------
    This is a development, test double, and architectural reference implementation.
    It does NOT connect to live LLM providers, external APIs, or neural networks.
    It provides reproducible, deterministic interpretation of representative emergency
    descriptions, validates interface contracts, and serves as the baseline for
    Milestone 5.4 provider adapters.
    """

    def __init__(self) -> None:
        self._custom_fixtures: Dict[str, InterpretationResult] = {}
        self._rules: List[_FixtureRule] = self._build_default_rules()

    def register_fixture(self, key_or_pattern: str, result: InterpretationResult) -> None:
        """Registers a custom fixture response for explicit unit test scenarios."""
        self._custom_fixtures[key_or_pattern.lower().strip()] = result

    def interpret(self, request: InterpretationRequest) -> InterpretationResult:
        """Processes the request deterministically according to established rules."""
        raw = request.raw_text

        # 1. Input sanitization and bounds check
        try:
            cleaned_text = sanitize_emergency_text(raw, max_length=request.max_length)
        except ValueError as exc:
            err_msg = str(exc)
            if "too short" in err_msg or "cannot be None" in err_msg:
                return InterpretationResult(
                    success=False,
                    error_code=InterpreterErrorCode.EMPTY_INPUT,
                    error_message=err_msg,
                    metadata={"interpreter": "FixtureEmergencyInterpreter", "input_chars": len(raw or "")},
                )
            if "exceeds maximum length" in err_msg:
                return InterpretationResult(
                    success=False,
                    error_code=InterpreterErrorCode.INPUT_TOO_LONG,
                    error_message=err_msg,
                    metadata={"interpreter": "FixtureEmergencyInterpreter", "input_chars": len(raw or "")},
                )
            return InterpretationResult(
                success=False,
                error_code=InterpreterErrorCode.MALFORMED_INPUT,
                error_message=err_msg,
                metadata={"interpreter": "FixtureEmergencyInterpreter"},
            )

        # 2. Check for exact registered custom fixtures
        lower_cleaned = cleaned_text.lower()
        for fixture_key, custom_result in self._custom_fixtures.items():
            if fixture_key in lower_cleaned:
                return custom_result

        # 3. Adversarial / Prompt Injection Analysis
        adv_flags = detect_adversarial_patterns(cleaned_text)

        # 4. Multi-Incident Conflict Check
        # If text explicitly mentions multiple distinct emergencies simultaneously
        type_matches: List[EmergencyType] = self._detect_candidate_types(lower_cleaned)
        if len(type_matches) > 1:
            clarification_q = (
                f"Multiple simultaneous incidents detected ({', '.join(t.value for t in type_matches)}). "
                "Please clarify which is the primary immediate life threat."
            )
            # Create proposal with the highest severity candidate as primary, but document ambiguity
            primary_type = self._pick_highest_priority_type(type_matches)
            proposal = ProposedIncidentInterpretation(
                raw_report=cleaned_text,
                emergency_type=primary_type,
                urgency=UrgencyLevel.PRIORITY_1_ECHO,
                location_text=self._extract_location(cleaned_text),
                confidence_score=0.6,
                uncertainty_notes=[
                    f"multiple_simultaneous_incidents_detected: {[t.value for t in type_matches]}",
                    "requires_incident_command_triage",
                ],
                model_metadata={
                    "interpreter": "FixtureEmergencyInterpreter",
                    "candidate_types": [t.value for t in type_matches],
                    "adversarial_flags": adv_flags,
                },
            )
            return InterpretationResult(
                success=True,
                proposal=proposal,
                clarification_needed=True,
                clarification_questions=(clarification_q,),
                ambiguities=(AmbiguityType.MULTIPLE_INCIDENTS,),
                adversarial_flags=tuple(adv_flags),
                confidence_score=0.6,
                uncertainty_notes=(
                    f"Multiple simultaneous incidents reported: {[t.value for t in type_matches]}",
                ),
                metadata={"interpreter": "FixtureEmergencyInterpreter"},
            )

        # 5. Contradictory Claims Analysis
        # Example: Caller claims "nobody is injured" but also "patient is unresponsive / bleeding heavily"
        has_benign = bool(re.search(r"\b(no\s+injur\w*|nobody\s+(is\s+)?hurt|every(one|thing)\s+(is\s+)?fine|minor|not\s+an\s+emergency)\b", lower_cleaned))
        has_critical = bool(re.search(r"\b(unconscious|unresponsive|cardiac|not\s+breathing|trapped|bleeding\s+heavily)\b", lower_cleaned))
        if has_benign and has_critical:
            clarification_q = (
                "Contradictory claims in report: describes both non-emergency status and critical life threat symptoms. "
                "Please confirm patient consciousness and breathing status immediately."
            )
            proposal = ProposedIncidentInterpretation(
                raw_report=cleaned_text,
                emergency_type=EmergencyType.MEDICAL_GENERAL if not type_matches else type_matches[0],
                urgency=UrgencyLevel.PRIORITY_1_ECHO,  # Fail-safe to high urgency when critical symptoms exist
                location_text=self._extract_location(cleaned_text),
                confidence_score=0.45,
                uncertainty_notes=[
                    "contradictory_caller_statements",
                    "fail_safe_escalated_to_priority_1",
                ],
                model_metadata={
                    "interpreter": "FixtureEmergencyInterpreter",
                    "adversarial_flags": adv_flags,
                },
            )
            return InterpretationResult(
                success=True,
                proposal=proposal,
                clarification_needed=True,
                clarification_questions=(clarification_q,),
                ambiguities=(AmbiguityType.CONTRADICTORY_STATEMENTS, AmbiguityType.UNCERTAIN_SEVERITY),
                adversarial_flags=tuple(adv_flags),
                confidence_score=0.45,
                uncertainty_notes=("Conflicting claims: reported benign status alongside critical life threat symptoms.",),
                metadata={"interpreter": "FixtureEmergencyInterpreter"},
            )

        # 6. Evaluate Default Match Rules
        matched_rule = self._match_rule(lower_cleaned)
        if matched_rule is None:
            # Check for completely unsupported / unrecognized incident description
            if not self._is_emergency_domain(lower_cleaned):
                return InterpretationResult(
                    success=False,
                    error_code=InterpreterErrorCode.UNSUPPORTED_INCIDENT_TYPE,
                    error_message=(
                        "Report does not describe a recognized municipal or emergency services incident category."
                    ),
                    adversarial_flags=tuple(adv_flags),
                    clarification_needed=True,
                    clarification_questions=("Please state the nature of your emergency (police, fire, medical, or rescue).",),
                    metadata={"interpreter": "FixtureEmergencyInterpreter"},
                )

            # Generic fallback with high uncertainty
            loc = self._extract_location(cleaned_text)
            clarifications: List[str] = [
                "Could not determine specific emergency taxonomy. What service is required (EMS, Fire, Hazmat)?"
            ]
            ambs: List[AmbiguityType] = [AmbiguityType.VAGUE_SYMPTOMS]
            uncs: List[str] = ["unrecognized_specific_taxonomy"]
            if not loc:
                clarifications.append("What is the exact location of the incident?")
                ambs.append(AmbiguityType.MISSING_LOCATION)
                uncs.append("missing_location")

            proposal = ProposedIncidentInterpretation(
                raw_report=cleaned_text,
                emergency_type=EmergencyType.MEDICAL_GENERAL,
                urgency=UrgencyLevel.PRIORITY_3_BRAVO,
                location_text=loc,
                confidence_score=0.3,
                uncertainty_notes=uncs,
                model_metadata={"interpreter": "FixtureEmergencyInterpreter", "adversarial_flags": adv_flags},
            )
            return InterpretationResult(
                success=True,
                proposal=proposal,
                clarification_needed=True,
                clarification_questions=tuple(clarifications),
                ambiguities=tuple(ambs),
                adversarial_flags=tuple(adv_flags),
                confidence_score=0.3,
                uncertainty_notes=tuple(uncs),
                metadata={"interpreter": "FixtureEmergencyInterpreter"},
            )

        # 7. Formulate Candidate Proposal from Matched Rule
        location_text = self._extract_location(cleaned_text)
        clarifications = []
        ambiguities = []
        uncertainties = []

        if not location_text and matched_rule.requires_location:
            clarifications.append("What is the exact address or intersection of the incident?")
            ambiguities.append(AmbiguityType.MISSING_LOCATION)
            uncertainties.append("location_unspecified_in_report")

        # If adversarial flags exist, preserve the safety classification and log notes
        if adv_flags:
            uncertainties.append(f"adversarial_instruction_attempts_detected: {adv_flags}")

        proposal = ProposedIncidentInterpretation(
            raw_report=cleaned_text,
            emergency_type=matched_rule.emergency_type,
            urgency=matched_rule.urgency,
            location_text=location_text,
            suggested_apparatus=list(matched_rule.apparatus),
            hazards_detected=list(matched_rule.hazards),
            confidence_score=matched_rule.confidence if location_text else max(0.2, matched_rule.confidence - 0.25),
            uncertainty_notes=uncertainties,
            model_metadata={
                "interpreter": "FixtureEmergencyInterpreter",
                "matched_pattern": matched_rule.pattern,
                "adversarial_flags": adv_flags,
                "digest": hashlib.sha256(cleaned_text.encode()).hexdigest()[:12],
            },
        )

        return InterpretationResult(
            success=True,
            proposal=proposal,
            clarification_needed=bool(clarifications),
            clarification_questions=tuple(clarifications),
            reported_symptoms=tuple(matched_rule.symptoms),
            reported_circumstances=tuple(matched_rule.circumstances),
            ambiguities=tuple(ambiguities),
            adversarial_flags=tuple(adv_flags),
            confidence_score=proposal.confidence_score,
            uncertainty_notes=tuple(uncertainties),
            metadata={
                "interpreter": "FixtureEmergencyInterpreter",
                "sanitized_length": len(cleaned_text),
            },
        )

    # -----------------------------------------------------------------------
    # Helper Rule & Extraction Logic
    # -----------------------------------------------------------------------

    def _build_default_rules(self) -> List[_FixtureRule]:
        return [
            # Traffic collision / Vehicle crash
            _FixtureRule(
                pattern=r"\b(crash|crashed|collided|collision|car\s+accident|hit\s+a\s+barrier|rollover|vehicle\s+wreck)\b",
                emergency_type=EmergencyType.ROAD_TRAFFIC_COLLISION,
                urgency=UrgencyLevel.PRIORITY_1_ECHO,
                apparatus=[ApparatusType.FIRE_ENGINE, ApparatusType.HEAVY_RESCUE, ApparatusType.AMBULANCE_ALS],
                symptoms=["possible_trauma", "potential_loss_of_consciousness"],
                circumstances=["vehicle_impact", "entrapment_risk"],
                hazards=[{"hazard_type": HazardType.STRUCTURAL_DEBRIS, "severity": HazardSeverity.MODERATE, "description": "Vehicle crash debris on roadway"}],
                confidence=0.92,
            ),
            # Cardiac arrest / Heart attack
            _FixtureRule(
                pattern=r"\b(cardiac\s+arrest|heart\s+attack|chest\s+pain|collapsed|not\s+breathing|no\s+pulse)\b",
                emergency_type=EmergencyType.CARDIAC_ARREST,
                urgency=UrgencyLevel.PRIORITY_1_ECHO,
                apparatus=[ApparatusType.AMBULANCE_ALS, ApparatusType.FIRE_ENGINE],
                symptoms=["chest_pain", "unresponsive", "absence_of_pulse"],
                circumstances=["acute_medical_collapse"],
                hazards=[],
                confidence=0.95,
            ),
            # Structure Fire
            _FixtureRule(
                pattern=r"\b(building\s+on\s+fire|structure\s+fire|apartment\s+burning|flames\s+from\s+roof|house\s+fire)\b",
                emergency_type=EmergencyType.STRUCTURE_FIRE,
                urgency=UrgencyLevel.PRIORITY_1_ECHO,
                apparatus=[ApparatusType.FIRE_ENGINE, ApparatusType.LADDER_TRUCK, ApparatusType.HEAVY_RESCUE, ApparatusType.BATTALION_CHIEF],
                symptoms=["smoke_inhalation_risk", "burn_injury_risk"],
                circumstances=["structural_combustion", "thermal_exposure"],
                hazards=[{"hazard_type": HazardType.TOXIC_GAS_PLUME, "severity": HazardSeverity.SEVERE, "description": "Structure fire dense smoke plume"}],
                confidence=0.94,
            ),
            # Wildland Fire
            _FixtureRule(
                pattern=r"\b(brush\s+fire|wildfire|forest\s+fire|grass\s+fire|vegetation\s+fire)\b",
                emergency_type=EmergencyType.WILDLAND_FIRE,
                urgency=UrgencyLevel.PRIORITY_1_ECHO,
                apparatus=[ApparatusType.FIRE_ENGINE, ApparatusType.BATTALION_CHIEF],
                symptoms=["respiratory_distress"],
                circumstances=["wildland_combustion", "rapid_perimeter_expansion"],
                hazards=[{"hazard_type": HazardType.WILDFIRE_PERIMETER, "severity": HazardSeverity.CRITICAL_BLOCKED, "description": "Rapidly moving wildfire front"}],
                confidence=0.91,
            ),
            # Hazmat Spill
            _FixtureRule(
                pattern=r"\b(chemical\s+spill|hazmat|toxic\s+leak|chlorine\s+gas|acid\s+spill|chemical\s+plume)\b",
                emergency_type=EmergencyType.HAZMAT_SPILL,
                urgency=UrgencyLevel.PRIORITY_2_DELTA,
                apparatus=[ApparatusType.HAZMAT_UNIT, ApparatusType.FIRE_ENGINE, ApparatusType.AMBULANCE_ALS],
                symptoms=["chemical_burns", "dyspnea", "eye_irritation"],
                circumstances=["toxic_vapor_release", "environmental_contamination"],
                hazards=[{"hazard_type": HazardType.TOXIC_GAS_PLUME, "severity": HazardSeverity.SEVERE, "description": "Airborne toxic chemical vapor"}],
                confidence=0.90,
            ),
            # Flash Flood
            _FixtureRule(
                pattern=r"\b(flash\s+flood|rising\s+water|submerged\s+car|river\s+overflow|trapped\s+by\s+water)\b",
                emergency_type=EmergencyType.FLASH_FLOOD,
                urgency=UrgencyLevel.PRIORITY_1_ECHO,
                apparatus=[ApparatusType.HEAVY_RESCUE, ApparatusType.FIRE_ENGINE, ApparatusType.AMBULANCE_ALS],
                symptoms=["hypothermia_risk", "submersion_drowning_risk"],
                circumstances=["rapid_water_inundation", "swift_current"],
                hazards=[{"hazard_type": HazardType.FLASH_FLOOD, "severity": HazardSeverity.CRITICAL_BLOCKED, "description": "Impassable flash flood inundation"}],
                confidence=0.93,
            ),
            # Structural Collapse
            _FixtureRule(
                pattern=r"\b(building\s+collapse|roof\s+cave-in|collapsed\s+structure|buried\s+under\s+rubble)\b",
                emergency_type=EmergencyType.STRUCTURAL_COLLAPSE,
                urgency=UrgencyLevel.PRIORITY_1_ECHO,
                apparatus=[ApparatusType.HEAVY_RESCUE, ApparatusType.LADDER_TRUCK, ApparatusType.FIRE_ENGINE, ApparatusType.AMBULANCE_ALS],
                symptoms=["crush_injury", "asphyxiation_risk"],
                circumstances=["mass_structural_failure", "confined_space_rubble"],
                hazards=[{"hazard_type": HazardType.STRUCTURAL_DEBRIS, "severity": HazardSeverity.CRITICAL_BLOCKED, "description": "Collapsed structural concrete rubble"}],
                confidence=0.92,
            ),
            # Major Trauma
            _FixtureRule(
                pattern=r"\b(gunshot|stabbing|severe\s+hemorrhage|fall\s+from\s+height|amputation)\b",
                emergency_type=EmergencyType.TRAUMA_MAJOR,
                urgency=UrgencyLevel.PRIORITY_1_ECHO,
                apparatus=[ApparatusType.AMBULANCE_ALS, ApparatusType.FIRE_ENGINE],
                symptoms=["severe_hemorrhage", "hypovolemic_shock_risk"],
                circumstances=["penetrating_blunt_trauma"],
                hazards=[],
                confidence=0.94,
            ),
            # General Medical (Non-critical)
            _FixtureRule(
                pattern=r"\b(fever|mild\s+nausea|sprained\s+ankle|minor\s+cut|dizziness)\b",
                emergency_type=EmergencyType.MEDICAL_GENERAL,
                urgency=UrgencyLevel.PRIORITY_3_BRAVO,
                apparatus=[ApparatusType.AMBULANCE_BLS],
                symptoms=["mild_discomfort", "stable_vitals"],
                circumstances=["non_life_threatening_medical"],
                hazards=[],
                confidence=0.85,
            ),
        ]

    def _match_rule(self, text_lower: str) -> Optional[_FixtureRule]:
        for rule in self._rules:
            if re.search(rule.pattern, text_lower):
                return rule
        return None

    def _detect_candidate_types(self, text_lower: str) -> List[EmergencyType]:
        found: List[EmergencyType] = []
        for rule in self._rules:
            if rule.emergency_type and re.search(rule.pattern, text_lower):
                if rule.emergency_type not in found:
                    found.append(rule.emergency_type)
        return found

    def _pick_highest_priority_type(self, types: Sequence[EmergencyType]) -> EmergencyType:
        # Priority order for emergency types
        severity_rank = {
            EmergencyType.CARDIAC_ARREST: 1,
            EmergencyType.TRAUMA_MAJOR: 2,
            EmergencyType.STRUCTURAL_COLLAPSE: 3,
            EmergencyType.STRUCTURE_FIRE: 4,
            EmergencyType.HAZMAT_SPILL: 5,
            EmergencyType.FLASH_FLOOD: 6,
            EmergencyType.ROAD_TRAFFIC_COLLISION: 7,
            EmergencyType.WILDLAND_FIRE: 8,
            EmergencyType.MEDICAL_GENERAL: 9,
        }
        return min(types, key=lambda t: severity_rank.get(t, 99))

    def _extract_location(self, text: str) -> Optional[str]:
        # Regex patterns for common street, junction, and landmark descriptions
        patterns = [
            r"\b(?:at|on|near|along)\s+([0-9A-Za-z\s]+(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Way|Lane|Ln|Corridor|Highway|Hwy|Expressway))(?:\b|,|\.)",
            r"\b(?:intersection\s+of|corner\s+of)\s+([0-9A-Za-z\s]+and[0-9A-Za-z\s]+)(?:\b|,|\.)",
            r"\b([0-9]+\s+[0-9A-Za-z\s]+(?:Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd))(?:\b|,|\.)",
            r"\b(?:between)\s+([0-9A-Za-z\s]+and[0-9A-Za-z\s]+)(?:\b|,|\.)",
        ]
        for pat in patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                loc = match.group(1).strip()
                if len(loc) >= 3:
                    return loc
        return None

    def _is_emergency_domain(self, text_lower: str) -> bool:
        keywords = {
            "help", "emergency", "fire", "smoke", "crash", "accident", "patient", "hurt",
            "injured", "pain", "bleeding", "collapse", "water", "flood", "chemical",
            "trapped", "danger", "hazard", "victim", "unconscious", "hospital", "ambulance"
        }
        words = set(re.findall(r"\b\w+\b", text_lower))
        return bool(words.intersection(keywords))
