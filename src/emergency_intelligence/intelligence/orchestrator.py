"""
Emergency Intelligence End-to-End Orchestrator (Milestone 5.4).
==============================================================
Orchestrates the entire emergency intelligence journey from raw unstructured narrative
to deterministic routing and fleet dispatch:

Pipeline Stages:
----------------
Raw Text
  ↓
[Input Sanitization & Adversarial Defense]
  ↓
[EmergencyInterpreter (StructuredModelAdapter / Fixture)]
  ↓
[Candidate ProposedIncidentInterpretation (Untrusted DTO)]
  ↓
[validate_incident_proposal() (Deterministic Contract Boundary)]
  ↓
[ValidatedIncidentContract (Immutable Domain Contract)]
  ↓
[EmergencyPolicyEngine.evaluate() (Statutory SOP Enforcement)]
  ↓
[OperationalPolicyDirective (Authoritative Mandate)]
  ↓
[Downstream Fleet Allocation & Dynamic A* Routing Engine]

Architectural Invariant:
------------------------
The AI model proposes candidate interpretations. The deterministic validation layer
and statutory emergency policy engine remain 100% authoritative for all dispatch,
triage, and routing constraint enforcement.

Zero external runtime dependencies: 100% Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from emergency_intelligence.allocation.matcher import FleetManager, allocate_fleet_for_incident
from emergency_intelligence.allocation.models import DispatchAssignment, DispatchPlan
from emergency_intelligence.events.incidents import ApparatusType, Incident
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.graph.dijkstra import RouteResult
from emergency_intelligence.graph.models import Graph
from emergency_intelligence.intelligence.contracts import (
    ProposedIncidentInterpretation,
    ValidatedIncidentContract,
    ValidationSeverity,
    ValidationStatus,
    validate_incident_proposal,
)
from emergency_intelligence.intelligence.interpreter import (
    EmergencyInterpreter,
    InterpretationRequest,
    InterpretationResult,
    InterpreterErrorCode,
)
from emergency_intelligence.intelligence.policy import (
    EmergencyPolicyEngine,
    OperationalPolicyDirective,
    RoutingConstraint,
    RoutingObjective,
)


class OrchestrationStatus(str, Enum):
    """Overall status of end-to-end emergency intelligence processing."""

    DISPATCH_OPTIMIZED = "dispatch_optimized"            # Fully validated, policy applied, and vehicles routed
    STAGED_AWAITING_LOCATION = "staged_awaiting_location"# Valid policy & apparatus staged, awaiting geocoded location
    AMBIGUOUS_NEEDS_CLARIFICATION = "needs_clarification"# High ambiguity, missing data, or contradictory claims
    VALIDATION_FAILED = "validation_failed"              # Proposal failed deterministic contract validation
    INTERPRETATION_FAILED = "interpretation_failed"      # Model provider error, timeout, or malformed output


@dataclass(frozen=True)
class DispatchedRouteSummary:
    """Summary of an individual emergency vehicle's calculated trajectory."""

    unit_id: str
    station_id: str
    apparatus_type: ApparatusType
    route_path: Tuple[str, ...]
    eta_seconds: float
    total_distance_meters: float

    @property
    def eta_minutes(self) -> float:
        return self.eta_seconds / 60.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "station_id": self.station_id,
            "apparatus_type": self.apparatus_type.value,
            "route_path": list(self.route_path),
            "eta_seconds": round(self.eta_seconds, 2),
            "eta_minutes": round(self.eta_minutes, 2),
            "total_distance_meters": round(self.total_distance_meters, 2),
        }


@dataclass(frozen=True)
class OrchestrationResult:
    """The complete result of an end-to-end emergency intelligence orchestration run.

    Attributes:
        request_id: Globally unique tracking correlation ID.
        raw_report: Original raw report text submitted.
        status: Overall orchestration completion status.
        interpretation: Result emitted by the model adapter / interpreter.
        contract: Validated domain contract (if validation succeeded).
        directive: Statutory policy directive (if policy evaluation succeeded).
        dispatch_plan: Multi-unit fleet dispatch allocation (if routing executed).
        dispatched_routes: Tuple of calculated vehicle route summaries.
        clarification_needed: True if operator clarification is required.
        clarification_questions: Tuple of questions recommended for caller/operator.
        latency_ms: Total pipeline wall-clock execution time in milliseconds.
        audit_trail: Step-by-step chronology of pipeline actions and decisions.
        metadata: Diagnostic and telemetry metadata.
    """

    request_id: str
    raw_report: str
    status: OrchestrationStatus
    interpretation: Optional[InterpretationResult] = None
    contract: Optional[ValidatedIncidentContract] = None
    directive: Optional[OperationalPolicyDirective] = None
    dispatch_plan: Optional[DispatchPlan] = None
    dispatched_routes: Tuple[DispatchedRouteSummary, ...] = field(default_factory=tuple)
    clarification_needed: bool = False
    clarification_questions: Tuple[str, ...] = field(default_factory=tuple)
    latency_ms: float = 0.0
    audit_trail: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes result to a dictionary suitable for JSON responses."""
        return {
            "request_id": self.request_id,
            "raw_report": self.raw_report,
            "status": self.status.value,
            "is_dispatchable": self.is_dispatchable,
            "clarification_needed": self.clarification_needed,
            "clarification_questions": list(self.clarification_questions),
            "assigned_unit_count": self.assigned_unit_count,
            "dispatched_routes": [r.to_dict() for r in self.dispatched_routes],
            "latency_ms": round(self.latency_ms, 2),
            "audit_trail": list(self.audit_trail),
            "metadata": dict(self.metadata),
        }

    @property
    def is_dispatchable(self) -> bool:
        """Returns True if vehicles were allocated or are staged ready for departure."""
        return self.status in (OrchestrationStatus.DISPATCH_OPTIMIZED, OrchestrationStatus.STAGED_AWAITING_LOCATION)

    @property
    def assigned_unit_count(self) -> int:
        """Returns number of vehicles successfully assigned with routes."""
        return len(self.dispatched_routes)


class EmergencyIntelligenceOrchestrator:
    """End-to-end emergency response coordinator.

    Unifies the interpretation adapter, deterministic contract validation,
    statutory policy enforcement, and dynamic road network dispatch allocation.
    """

    def __init__(
        self,
        interpreter: EmergencyInterpreter,
        policy_engine: Optional[EmergencyPolicyEngine] = None,
        fleet_manager: Optional[FleetManager] = None,
        graph: Optional[Union[Graph, DynamicGraphView]] = None,
    ) -> None:
        if not isinstance(interpreter, EmergencyInterpreter):
            raise TypeError(f"interpreter must be an EmergencyInterpreter, got {type(interpreter)}.")

        self._interpreter = interpreter
        self._policy_engine = policy_engine or EmergencyPolicyEngine()
        self._fleet_manager = fleet_manager
        self._graph = graph

    @property
    def interpreter(self) -> EmergencyInterpreter:
        return self._interpreter

    @property
    def policy_engine(self) -> EmergencyPolicyEngine:
        return self._policy_engine

    @property
    def fleet_manager(self) -> Optional[FleetManager]:
        return self._fleet_manager

    @property
    def graph(self) -> Optional[Union[Graph, DynamicGraphView]]:
        return self._graph

    def process(
        self,
        report: Union[str, InterpretationRequest],
        coordinates: Optional[Tuple[float, float]] = None,
        node_id: Optional[str] = None,
        incident_id: Optional[str] = None,
    ) -> OrchestrationResult:
        """Executes the full emergency intelligence pipeline for an emergency call.

        Parameters:
            report: Raw text string or typed InterpretationRequest.
            coordinates: Optional authoritative CAD/GPS coordinates override.
            node_id: Optional road network graph junction node override.
            incident_id: Optional incident tracking ID.

        Returns:
            OrchestrationResult containing all pipeline stages, validation findings,
            statutory policy directives, and calculated emergency routes.
        """
        t0 = time.perf_counter()
        audit: List[str] = []

        if isinstance(report, str):
            req = InterpretationRequest(raw_text=report)
        elif isinstance(report, InterpretationRequest):
            req = report
        else:
            raise TypeError(f"report must be str or InterpretationRequest, got {type(report)}.")

        audit.append(f"STAGE_1_INTAKE: Received request {req.request_id} ({len(req.raw_text)} chars)")

        # Stage 2: Interpretation via Model Adapter / Interpreter
        interp_res = self._interpreter.interpret(req)
        audit.append(
            f"STAGE_2_INTERPRETATION: Success={interp_res.success}, "
            f"Error={interp_res.error_code.value if interp_res.error_code else 'None'}, "
            f"AdversarialFlags={list(interp_res.adversarial_flags)}"
        )

        if not interp_res.success or interp_res.proposal is None:
            latency = (time.perf_counter() - t0) * 1000.0
            audit.append(f"STAGE_ABORT: Interpretation failed ({interp_res.error_message})")
            return OrchestrationResult(
                request_id=req.request_id,
                raw_report=req.raw_text,
                status=OrchestrationStatus.INTERPRETATION_FAILED,
                interpretation=interp_res,
                clarification_needed=interp_res.clarification_needed,
                clarification_questions=interp_res.clarification_questions,
                latency_ms=latency,
                audit_trail=tuple(audit),
                metadata={"error_code": interp_res.error_code.value if interp_res.error_code else None},
            )

        proposal = interp_res.proposal

        # Apply external CAD / GPS telemetry overrides if provided
        if coordinates is not None:
            proposal.suggested_coordinates = coordinates
            audit.append(f"STAGE_CAD_OVERRIDE: Applied verified coordinates {coordinates}")
        if node_id is not None:
            proposal.suggested_node_id = node_id
            audit.append(f"STAGE_CAD_OVERRIDE: Applied verified node {node_id}")

        # Stage 3: Deterministic Contract Validation
        valid_nodes = set(self._graph.node_ids()) if self._graph is not None else None
        contract = validate_incident_proposal(
            proposal=proposal,
            incident_id=incident_id,
            valid_node_ids=valid_nodes,
        )
        audit.append(
            f"STAGE_3_CONTRACT_VALIDATION: Status={contract.validation_status.value}, "
            f"IssuesCount={len(contract.validation_issues)}, "
            f"OperableForRouting={contract.is_operable_for_routing}"
        )

        # Fatal validation failure
        if not contract.is_valid:
            latency = (time.perf_counter() - t0) * 1000.0
            audit.append("STAGE_ABORT: Contract validation failed with fatal errors.")
            all_questions = list(interp_res.clarification_questions)
            for issue in contract.validation_issues:
                if issue.severity == ValidationSeverity.ERROR:
                    all_questions.append(f"Validation issue [{issue.code.value}]: {issue.message}")

            return OrchestrationResult(
                request_id=req.request_id,
                raw_report=req.raw_text,
                status=OrchestrationStatus.VALIDATION_FAILED,
                interpretation=interp_res,
                contract=contract,
                clarification_needed=True,
                clarification_questions=tuple(all_questions),
                latency_ms=latency,
                audit_trail=tuple(audit),
                metadata={"validation_status": contract.validation_status.value},
            )

        # Stage 4: Authoritative Policy Evaluation
        directive = self._policy_engine.evaluate(contract)
        audit.append(
            f"STAGE_4_POLICY_EVALUATION: DirectiveID={directive.incident_id}, "
            f"EffectiveUrgency={directive.effective_urgency.value}, "
            f"MandatedUnitsCount={directive.total_apparatus_count}, "
            f"RulesApplied={list(directive.policy_rules_applied)}"
        )

        # Stage 5: Downstream Dispatch & Siren Routing
        dispatched_routes: List[DispatchedRouteSummary] = []
        dispatch_plan: Optional[DispatchPlan] = None
        status = OrchestrationStatus.DISPATCH_OPTIMIZED

        can_route = (
            self._fleet_manager is not None
            and self._graph is not None
            and contract.is_operable_for_routing
        )

        if can_route:
            assert self._fleet_manager is not None
            assert self._graph is not None
            try:
                op_incident = contract.to_operational_incident()
                # Use policy-mandated apparatus types for allocation
                required_apparatus_types = [
                    req.apparatus_type
                    for req in directive.required_apparatus
                    for _ in range(req.quantity)
                ]
                op_incident.required_apparatus = required_apparatus_types

                dispatch_plan = allocate_fleet_for_incident(
                    graph=self._graph,
                    incident=op_incident,
                    fleet=self._fleet_manager,
                    auto_dispatch=False,
                )

                for assignment in dispatch_plan.assignments:
                    unit = assignment.assigned_unit
                    eta = assignment.eta_record
                    if assignment.fulfilled and unit is not None and eta is not None and eta.reachable:
                        dispatched_routes.append(
                            DispatchedRouteSummary(
                                unit_id=unit.unit_id,
                                station_id=unit.station_id,
                                apparatus_type=unit.apparatus_type,
                                route_path=tuple(eta.path),
                                eta_seconds=eta.travel_time_seconds,
                                total_distance_meters=eta.distance_meters,
                            )
                        )

                audit.append(
                    f"STAGE_5_FLEET_ALLOCATION: Allocated {len(dispatched_routes)} units "
                    f"({[r.unit_id for r in dispatched_routes]})"
                )
            except Exception as exc:
                audit.append(f"STAGE_5_WARNING: Routing allocation failed: {exc}")
                status = OrchestrationStatus.STAGED_AWAITING_LOCATION
        else:
            if not contract.is_operable_for_routing:
                status = OrchestrationStatus.STAGED_AWAITING_LOCATION
                audit.append("STAGE_5_STAGING: Incident lacking coordinates or node ID. Apparatus staged at station depots.")
            else:
                audit.append("STAGE_5_STANDBY: No graph or fleet manager attached. Ready for external dispatcher.")

        # Aggregate any outstanding operator clarification questions
        all_questions = list(interp_res.clarification_questions)
        if status == OrchestrationStatus.STAGED_AWAITING_LOCATION and not all_questions:
            all_questions.append("Incident is staged. Please provide exact street address or coordinates for route calculation.")

        latency = (time.perf_counter() - t0) * 1000.0
        audit.append(f"PIPELINE_COMPLETE: Total latency {latency:.2f} ms with status {status.value}")

        return OrchestrationResult(
            request_id=req.request_id,
            raw_report=req.raw_text,
            status=status,
            interpretation=interp_res,
            contract=contract,
            directive=directive,
            dispatch_plan=dispatch_plan,
            dispatched_routes=tuple(dispatched_routes),
            clarification_needed=bool(all_questions),
            clarification_questions=tuple(all_questions),
            latency_ms=latency,
            audit_trail=tuple(audit),
            metadata={
                "rules_applied": list(directive.policy_rules_applied),
                "routing_constraints": [c.value for c in directive.routing_constraints],
                "effective_urgency": directive.effective_urgency.value,
            },
        )
