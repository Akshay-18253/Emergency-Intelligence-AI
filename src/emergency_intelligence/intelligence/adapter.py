"""
Schema-Constrained Model Adapter & Provider Protocol (Milestone 5.4).
=====================================================================
Defines the provider-independent structured-output model adapter layer that connects
the `EmergencyInterpreter` abstraction to LLM providers or inference engines.

Architectural Invariant:
------------------------
1. Model proposals are strictly untrusted candidate extractions (DTOs).
2. The model NEVER selects routes, dispatches vehicles, or overrides statutory safety rules.
3. Every response undergoes independent JSON Schema and domain contract validation.
4. Transient failures trigger bounded, deterministic retries; permanent errors fail fast.
5. Zero secrets or credentials in source code, telemetry, or logs.
6. Zero external runtime dependencies: 100% Python standard library.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
import re
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple, Type, Union

from emergency_intelligence.events.hazards import HazardSeverity, HazardType
from emergency_intelligence.events.incidents import (
    ApparatusType,
    EmergencyType,
    UrgencyLevel,
)
from emergency_intelligence.intelligence.contracts import (
    ProposedIncidentInterpretation,
)
from emergency_intelligence.intelligence.interpreter import (
    AmbiguityType,
    DEFAULT_MAX_INPUT_LENGTH,
    EmergencyInterpreter,
    InterpretationRequest,
    InterpretationResult,
    InterpreterErrorCode,
    detect_adversarial_patterns,
    mask_sensitive_telemetry,
    sanitize_emergency_text,
)


# Standard JSON Schema defining the structured output contract for emergency proposals
EMERGENCY_PROPOSAL_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "EmergencyIncidentProposal",
    "description": "Structured candidate extraction emitted by an emergency intelligence model.",
    "type": "object",
    "required": ["emergency_type", "urgency", "suggested_apparatus"],
    "properties": {
        "emergency_type": {
            "type": "string",
            "enum": [e.value for e in EmergencyType],
            "description": "Candidate emergency taxonomy category.",
        },
        "urgency": {
            "type": "string",
            "enum": [u.value for u in UrgencyLevel],
            "description": "Triage urgency tier following dispatch standards.",
        },
        "location_text": {
            "type": ["string", "null"],
            "description": "Extracted address, intersection, or landmark, if mentioned.",
        },
        "suggested_coordinates": {
            "type": ["array", "null"],
            "items": {"type": "number"},
            "minItems": 2,
            "maxItems": 2,
            "description": "Optional (longitude, latitude) coordinates if geocoded.",
        },
        "suggested_node_id": {
            "type": ["string", "null"],
            "description": "Optional road network graph junction node ID.",
        },
        "suggested_apparatus": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [a.value for a in ApparatusType],
            },
            "description": "List of emergency apparatus classes recommended.",
        },
        "hazards_detected": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["hazard_type", "description"],
                "properties": {
                    "hazard_type": {
                        "type": "string",
                        "enum": [h.value for h in HazardType],
                    },
                    "description": {"type": "string"},
                    "severity": {
                        "type": ["string", "null"],
                        "enum": [s.value for s in HazardSeverity] + [None],
                    },
                    "location_text": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                },
            },
            "description": "Disaster hazards identified in the narrative.",
        },
        "reported_symptoms": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific patient symptoms or injuries described in text.",
        },
        "reported_circumstances": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Environmental or physical circumstances described in text.",
        },
        "confidence_score": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Self-reported model confidence in [0.0, 1.0].",
        },
        "uncertainty_notes": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Explanations of missing, ambiguous, or unconfirmed facts.",
        },
        "clarification_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Recommended follow-up questions to resolve ambiguity.",
        },
    },
    "additionalProperties": False,
}


# ===========================================================================
# Typed Provider Exceptions
# ===========================================================================

class ProviderError(Exception):
    """Base exception for model provider integration failures."""

    def __init__(
        self,
        message: str,
        provider_name: str = "unknown",
        status_code: Optional[int] = None,
        is_retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.provider_name = provider_name
        self.status_code = status_code
        self.is_retryable = is_retryable


class ProviderTimeoutError(ProviderError):
    """Model request timed out before receiving a response."""

    def __init__(self, message: str, provider_name: str = "unknown") -> None:
        super().__init__(message, provider_name=provider_name, status_code=408, is_retryable=True)


class ProviderRateLimitError(ProviderError):
    """Provider rate limit or quota exceeded."""

    def __init__(self, message: str, provider_name: str = "unknown") -> None:
        super().__init__(message, provider_name=provider_name, status_code=429, is_retryable=True)


class ProviderNetworkError(ProviderError):
    """Low-level socket, connection reset, or transport failure."""

    def __init__(self, message: str, provider_name: str = "unknown") -> None:
        super().__init__(message, provider_name=provider_name, is_retryable=True)


class ProviderAuthenticationError(ProviderError):
    """Authentication or authorization failure (strictly non-retryable)."""

    def __init__(self, message: str, provider_name: str = "unknown") -> None:
        # Note: Must never include raw credentials or tokens in message
        super().__init__(
            message="Provider authentication failed. Check credentials/permissions.",
            provider_name=provider_name,
            status_code=401,
            is_retryable=False,
        )


class ProviderMalformedOutputError(ProviderError):
    """Model produced unparseable non-JSON or severely corrupted payload."""

    def __init__(self, message: str, provider_name: str = "unknown") -> None:
        super().__init__(message, provider_name=provider_name, is_retryable=False)


# ===========================================================================
# Bounded Retry Policy
# ===========================================================================

@dataclass(frozen=True)
class RetryPolicy:
    """Configures deterministic, bounded retry behavior for transient errors.

    Attributes:
        max_retries: Maximum number of re-execution attempts.
        initial_backoff_seconds: Initial backoff sleep delay.
        backoff_multiplier: Multiplier applied per subsequent retry.
        retryable_exceptions: Tuple of exception types permitted to trigger a retry.
    """

    max_retries: int = 2
    initial_backoff_seconds: float = 0.05
    backoff_multiplier: float = 2.0
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        ProviderTimeoutError,
        ProviderRateLimitError,
        ProviderNetworkError,
    )

    def is_retryable(self, exc: Exception) -> bool:
        """Determines if the given exception is eligible for retry."""
        if isinstance(exc, ProviderError) and not exc.is_retryable:
            return False
        return isinstance(exc, self.retryable_exceptions)


# ===========================================================================
# Provider Client Protocol
# ===========================================================================

class ModelProvider(ABC):
    """Abstract interface defining the communication contract with a model provider."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Human-readable provider identifier (e.g. 'fake-provider', 'anthropic', 'openai')."""
        raise NotImplementedError

    @abstractmethod
    def generate(
        self,
        prompt: str,
        schema: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        """Sends the prompt and returns raw model text or JSON string response.

        Must raise typed subclasses of `ProviderError` on failure.
        """
        raise NotImplementedError


# ===========================================================================
# Deterministic Fake Model Provider (Test Double & Interface Baseline)
# ===========================================================================

class FakeModelProvider(ModelProvider):
    """Deterministic, network-free test double for model provider adapters.

    Permits:
    - Registering exact prompt-to-response mappings.
    - Scripting error sequences (e.g. timeout on 1st call, success on 2nd).
    - Simulating rate limits, malformed JSON, and authentication failures.
    - Inspecting call history without credentials or external API calls.
    """

    def __init__(
        self,
        default_response: Optional[str] = None,
        prompt_mappings: Optional[Dict[str, str]] = None,
    ) -> None:
        self._provider_id: str = "fake-model-provider"
        self._default_response: Optional[str] = default_response
        self._prompt_mappings: Dict[str, str] = {k.lower(): v for k, v in prompt_mappings.items()} if prompt_mappings else {}
        self._scripted_responses: List[Union[str, Exception]] = []
        self._call_history: List[Dict[str, Any]] = []

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def call_count(self) -> int:
        return len(self._call_history)

    @property
    def call_history(self) -> List[Dict[str, Any]]:
        return list(self._call_history)

    def clear_history(self) -> None:
        """Clears all recorded call telemetry."""
        self._call_history.clear()

    def set_mapping(self, prompt_substring: str, response: str) -> None:
        """Maps any prompt containing the given substring to a specific response."""
        self._prompt_mappings[prompt_substring.lower()] = response

    def script_sequence(self, sequence: Sequence[Union[str, Exception]]) -> None:
        """Enqueues a sequence of responses or exceptions to be yielded on successive calls."""
        self._scripted_responses.extend(sequence)

    def generate(
        self,
        prompt: str,
        schema: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.0,
    ) -> str:
        self._call_history.append({
            "prompt": prompt,
            "schema_present": schema is not None,
            "system_prompt": system_prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timestamp": time.time(),
        })

        # 1. Check scripted sequence first
        if self._scripted_responses:
            item = self._scripted_responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        # 2. Check prompt mappings
        prompt_lower = prompt.lower()
        for sub, resp in self._prompt_mappings.items():
            if sub in prompt_lower:
                return resp

        # 3. Fallback to default
        if self._default_response is not None:
            return self._default_response

        # Default fallback valid JSON
        return json.dumps({
            "emergency_type": "road_traffic_collision",
            "urgency": "priority_1_echo",
            "location_text": "Market Street and 8th St",
            "suggested_apparatus": ["fire_engine", "ambulance_als"],
            "hazards_detected": [],
            "reported_symptoms": ["trauma"],
            "reported_circumstances": ["crash"],
            "confidence_score": 0.9,
            "uncertainty_notes": [],
            "clarification_questions": [],
        })


# ===========================================================================
# Structured Output JSON Parsing & Heuristic Extraction
# ===========================================================================

def extract_json_payload(raw_output: str) -> str:
    """Extracts a valid JSON string from potentially decorated model output.

    Handles markdown ```json ... ``` code fences, leading/trailing conversational
    commentary, and raw JSON strings.
    """
    cleaned = raw_output.strip()

    # Match markdown code fence: ```json { ... } ``` or ``` { ... } ```
    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()

    # Search for outer balanced curly braces if surrounded by conversational text
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return cleaned[first_brace : last_brace + 1].strip()

    return cleaned


# ===========================================================================
# Schema-Constrained Model Adapter
# ===========================================================================

class StructuredModelAdapter(EmergencyInterpreter):
    """Provider-independent model adapter implementing `EmergencyInterpreter`.

    Transforms unstructured emergency reports into structured proposals by querying
    an underlying `ModelProvider`, enforcing JSON Schema compliance, and applying
    independent contract normalization.
    """

    def __init__(
        self,
        provider: ModelProvider,
        retry_policy: Optional[RetryPolicy] = None,
        system_prompt: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
        max_response_chars: int = 16000,
    ) -> None:
        if not isinstance(provider, ModelProvider):
            raise TypeError(f"provider must be an instance of ModelProvider, got {type(provider)}.")

        self._provider = provider
        self._retry_policy = retry_policy or RetryPolicy()
        self._system_prompt = system_prompt or (
            "You are an emergency dispatch natural-language interpretation intelligence. "
            "Extract structured incident information strictly complying with the provided JSON Schema. "
            "Never invent missing facts or locations. Identify symptoms, circumstances, and safety risks. "
            "Output valid JSON only."
        )
        self._schema = schema or EMERGENCY_PROPOSAL_JSON_SCHEMA
        self._max_response_chars = max_response_chars

    @property
    def provider(self) -> ModelProvider:
        return self._provider

    @property
    def retry_policy(self) -> RetryPolicy:
        return self._retry_policy

    def interpret(self, request: InterpretationRequest) -> InterpretationResult:
        """Interprets raw emergency text using the model provider."""
        raw = request.raw_text

        # 1. Input sanitization and bounds check
        try:
            cleaned_text = sanitize_emergency_text(raw, max_length=request.max_length)
        except ValueError as exc:
            err_msg = str(exc)
            err_code = InterpreterErrorCode.INPUT_TOO_LONG if "exceeds maximum length" in err_msg else InterpreterErrorCode.EMPTY_INPUT
            return InterpretationResult(
                success=False,
                error_code=err_code,
                error_message=err_msg,
                metadata={"provider_id": self._provider.provider_id},
            )

        # 2. Privacy & PII protection (mask sensitive data prior to model submission)
        sanitized_prompt_text = mask_sensitive_telemetry(cleaned_text)

        # 3. Detect prompt injection & adversarial override attempts
        adv_flags = detect_adversarial_patterns(cleaned_text)

        # Build prompt payload
        prompt = (
            f"Analyze the following 911 emergency report and emit structured JSON matching the schema:\n\n"
            f"REPORT:\n\"{sanitized_prompt_text}\""
        )

        # 4. Invoke provider with bounded retry policy
        raw_model_output, invocation_meta = self._invoke_with_retry(prompt)

        # Check for provider failure
        if invocation_meta.get("error_code") is not None:
            return InterpretationResult(
                success=False,
                error_code=invocation_meta["error_code"],
                error_message=invocation_meta.get("error_message"),
                adversarial_flags=tuple(adv_flags),
                metadata={
                    "provider_id": self._provider.provider_id,
                    "retries_attempted": invocation_meta.get("retries", 0),
                    "status_code": invocation_meta.get("status_code"),
                },
            )

        # 5. Extract, validate, and parse JSON response
        return self._parse_and_validate_response(
            raw_output=raw_model_output,
            cleaned_report=cleaned_text,
            adv_flags=adv_flags,
            invocation_meta=invocation_meta,
        )

    # -----------------------------------------------------------------------
    # Private Helpers: Invocation & Validation
    # -----------------------------------------------------------------------

    def _invoke_with_retry(self, prompt: str) -> Tuple[str, Dict[str, Any]]:
        """Executes provider generation under bounded retry rules."""
        attempts = 0
        backoff = self._retry_policy.initial_backoff_seconds
        last_error: Optional[Exception] = None

        while attempts <= self._retry_policy.max_retries:
            try:
                t0 = time.perf_counter()
                raw_response = self._provider.generate(
                    prompt=prompt,
                    schema=self._schema,
                    system_prompt=self._system_prompt,
                )
                latency_ms = (time.perf_counter() - t0) * 1000.0

                if len(raw_response) > self._max_response_chars:
                    return "", {
                        "error_code": InterpreterErrorCode.INPUT_TOO_LONG,
                        "error_message": f"Provider response exceeded max length ({len(raw_response)} > {self._max_response_chars}).",
                        "retries": attempts,
                    }

                return raw_response, {
                    "provider_id": self._provider.provider_id,
                    "retries": attempts,
                    "latency_ms": latency_ms,
                }

            except Exception as exc:
                last_error = exc
                attempts += 1

                # If non-retryable or retries exhausted, break out
                if not self._retry_policy.is_retryable(exc) or attempts > self._retry_policy.max_retries:
                    break

                # Sleep bounded backoff before retrying
                time.sleep(backoff)
                backoff *= self._retry_policy.backoff_multiplier

        # Map error to standardized InterpreterErrorCode
        error_code = InterpreterErrorCode.PROVIDER_UNAVAILABLE
        if isinstance(last_error, ProviderAuthenticationError):
            error_code = InterpreterErrorCode.PROVIDER_UNAVAILABLE
        elif isinstance(last_error, ProviderTimeoutError):
            error_code = InterpreterErrorCode.PROVIDER_UNAVAILABLE
        elif isinstance(last_error, ProviderRateLimitError):
            error_code = InterpreterErrorCode.PROVIDER_UNAVAILABLE
        elif isinstance(last_error, ProviderMalformedOutputError):
            error_code = InterpreterErrorCode.MALFORMED_INPUT

        return "", {
            "error_code": error_code,
            "error_message": str(last_error),
            "retries": attempts - 1,
            "status_code": getattr(last_error, "status_code", None),
        }

    def _parse_and_validate_response(
        self,
        raw_output: str,
        cleaned_report: str,
        adv_flags: List[str],
        invocation_meta: Dict[str, Any],
    ) -> InterpretationResult:
        """Independently extracts and validates JSON data against domain contracts."""
        json_str = extract_json_payload(raw_output)

        try:
            payload = json.loads(json_str)
        except (json.JSONDecodeError, TypeError) as exc:
            return InterpretationResult(
                success=False,
                error_code=InterpreterErrorCode.MALFORMED_INPUT,
                error_message=f"Model output could not be decoded as JSON: {exc}",
                adversarial_flags=tuple(adv_flags),
                metadata=dict(invocation_meta),
            )

        if not isinstance(payload, dict):
            return InterpretationResult(
                success=False,
                error_code=InterpreterErrorCode.MALFORMED_INPUT,
                error_message=f"Model output root must be a JSON object, got {type(payload)}.",
                adversarial_flags=tuple(adv_flags),
                metadata=dict(invocation_meta),
            )

        # Independent Schema & Enum Validation
        # 1. Emergency Type
        raw_type = payload.get("emergency_type")
        parsed_type: Optional[EmergencyType] = None
        if raw_type:
            try:
                parsed_type = EmergencyType(str(raw_type).strip().lower())
            except ValueError:
                # Unsupported / unknown category
                return InterpretationResult(
                    success=False,
                    error_code=InterpreterErrorCode.UNSUPPORTED_INCIDENT_TYPE,
                    error_message=f"Model proposed unrecognized emergency type '{raw_type}'.",
                    adversarial_flags=tuple(adv_flags),
                    clarification_needed=True,
                    clarification_questions=("Please clarify what kind of emergency service is required.",),
                    metadata=dict(invocation_meta),
                )
        else:
            return InterpretationResult(
                success=False,
                error_code=InterpreterErrorCode.INSUFFICIENT_INFORMATION,
                error_message="Model proposal omitted required field 'emergency_type'.",
                adversarial_flags=tuple(adv_flags),
                clarification_needed=True,
                clarification_questions=("What type of emergency is taking place?",),
                metadata=dict(invocation_meta),
            )

        # 2. Urgency Level
        raw_urgency = payload.get("urgency")
        parsed_urgency: Optional[UrgencyLevel] = None
        if raw_urgency:
            try:
                parsed_urgency = UrgencyLevel(str(raw_urgency).strip().lower())
            except ValueError:
                return InterpretationResult(
                    success=False,
                    error_code=InterpreterErrorCode.MALFORMED_INPUT,
                    error_message=f"Model proposed unrecognized urgency tier '{raw_urgency}'.",
                    adversarial_flags=tuple(adv_flags),
                    metadata=dict(invocation_meta),
                )
        else:
            return InterpretationResult(
                success=False,
                error_code=InterpreterErrorCode.INSUFFICIENT_INFORMATION,
                error_message="Model proposal omitted required field 'urgency'.",
                adversarial_flags=tuple(adv_flags),
                metadata=dict(invocation_meta),
            )

        # 3. Location extraction and missing location detection
        loc_text = payload.get("location_text")
        if loc_text is not None and not isinstance(loc_text, str):
            loc_text = str(loc_text)
        if loc_text and len(loc_text.strip()) == 0:
            loc_text = None

        coords_raw = payload.get("suggested_coordinates")
        suggested_coords: Optional[Tuple[float, float]] = None
        if coords_raw and isinstance(coords_raw, (list, tuple)) and len(coords_raw) == 2:
            try:
                suggested_coords = (float(coords_raw[0]), float(coords_raw[1]))
            except (ValueError, TypeError):
                suggested_coords = None

        node_id_raw = payload.get("suggested_node_id")
        suggested_node = str(node_id_raw).strip() if node_id_raw is not None else None

        # 4. Suggested Apparatus Validation
        raw_apparatus_list = payload.get("suggested_apparatus", [])
        validated_apparatus: List[ApparatusType] = []
        if isinstance(raw_apparatus_list, list):
            for item in raw_apparatus_list:
                try:
                    validated_apparatus.append(ApparatusType(str(item).strip().lower()))
                except ValueError:
                    # Reject or skip unrecognized apparatus
                    continue

        # 5. Hazards validation
        raw_hazards = payload.get("hazards_detected", [])
        validated_hazards: List[Dict[str, Any]] = []
        if isinstance(raw_hazards, list):
            for h in raw_hazards:
                if isinstance(h, dict) and "hazard_type" in h:
                    try:
                        h_type = HazardType(str(h["hazard_type"]).strip().lower())
                        validated_hazards.append({
                            "hazard_type": h_type,
                            "description": str(h.get("description", "")),
                            "severity": str(h.get("severity", "")) if h.get("severity") else None,
                            "location_text": str(h.get("location_text", "")) if h.get("location_text") else None,
                            "confidence": max(0.0, min(1.0, float(h.get("confidence", 0.5)))),
                        })
                    except (ValueError, TypeError):
                        continue

        # 6. Ambiguities & Uncertainty Tracking
        ambiguities: List[AmbiguityType] = []
        clarification_qs: List[str] = list(payload.get("clarification_questions", []))
        uncertainty_notes: List[str] = list(payload.get("uncertainty_notes", []))

        if not loc_text and not suggested_coords and not suggested_node:
            ambiguities.append(AmbiguityType.MISSING_LOCATION)
            uncertainty_notes.append("missing_location_in_report")
            if not clarification_qs:
                clarification_qs.append("What is the exact location or nearest intersection?")

        if adv_flags:
            uncertainty_notes.append(f"adversarial_instruction_flags: {adv_flags}")

        # Check self-reported confidence
        raw_conf = payload.get("confidence_score", 0.7)
        try:
            model_conf = max(0.0, min(1.0, float(raw_conf)))
        except (ValueError, TypeError):
            model_conf = 0.5

        # 7. Formulate Candidate ProposedIncidentInterpretation DTO
        proposal = ProposedIncidentInterpretation(
            raw_report=cleaned_report,
            emergency_type=parsed_type,
            urgency=parsed_urgency,
            location_text=loc_text,
            suggested_coordinates=suggested_coords,
            suggested_node_id=suggested_node,
            suggested_apparatus=validated_apparatus,
            hazards_detected=validated_hazards,
            confidence_score=model_conf,
            uncertainty_notes=uncertainty_notes,
            model_metadata={
                "provider_id": self._provider.provider_id,
                "adversarial_flags": adv_flags,
                "retries": invocation_meta.get("retries", 0),
                "latency_ms": invocation_meta.get("latency_ms", 0.0),
            },
        )

        return InterpretationResult(
            success=True,
            proposal=proposal,
            clarification_needed=bool(clarification_qs),
            clarification_questions=tuple(clarification_qs),
            reported_symptoms=tuple(str(s) for s in payload.get("reported_symptoms", [])),
            reported_circumstances=tuple(str(c) for c in payload.get("reported_circumstances", [])),
            ambiguities=tuple(ambiguities),
            adversarial_flags=tuple(adv_flags),
            confidence_score=model_conf,
            uncertainty_notes=tuple(uncertainty_notes),
            metadata=dict(invocation_meta),
        )
