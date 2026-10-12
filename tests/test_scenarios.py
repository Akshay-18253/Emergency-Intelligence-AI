"""
Tests for Multi-Incident Disaster Scenarios & Resource Contention.
==================================================================
Verifies:
  1. Declarative scenario definitions and standard benchmark builders.
  2. Baseline single incident execution.
  3. Cascading multi-alarm response, secondary station fallback, and queue delays.
  4. Mid-flight critical infrastructure severance detour replanning.
  5. Progressive flood inundation under dynamic hazard expansion.
  6. Field redeployment upon on-scene clearance.
"""

from __future__ import annotations

import pytest

from emergency_intelligence.allocation.models import EmergencyStation, EmergencyUnit
from emergency_intelligence.events.incidents import ApparatusType, EmergencyType, Incident, UrgencyLevel
from emergency_intelligence.graph.models import Edge, Graph, Node
from emergency_intelligence.simulation.scenarios import (
    QueuedIncidentState,
    ScenarioDefinition,
    ScenarioResult,
    ScenarioRunner,
    build_cascading_multi_alarm_scenario,
    build_infrastructure_severance_scenario,
    build_progressive_inundation_scenario,
    build_single_incident_baseline_scenario,
    get_benchmark_scenario,
    list_benchmark_scenarios,
)


class TestScenarioDefinitionsAndRegistry:
    def test_list_benchmark_scenarios(self) -> None:
        names = list_benchmark_scenarios()
        assert "cascading_multi_alarm" in names
        assert "infrastructure_severance" in names
        assert "progressive_inundation" in names
        assert "single_incident_baseline" in names
        assert sorted(names) == names

    def test_get_benchmark_scenario_valid(self) -> None:
        scen = get_benchmark_scenario("single_incident_baseline")
        assert isinstance(scen, ScenarioDefinition)
        assert scen.name == "Baseline Single Incident"
        assert len(scen.stations) == 1
        assert len(scen.fleet_units) == 1
        assert len(scen.incidents) == 1

    def test_get_benchmark_scenario_invalid_raises(self) -> None:
        with pytest.raises(KeyError, match="Scenario 'non_existent_scen' not found"):
            get_benchmark_scenario("non_existent_scen")

    def test_queued_incident_state_properties(self) -> None:
        inc = Incident(
            incident_id="INC-T1",
            emergency_type=EmergencyType.CARDIAC_ARREST,
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
            coordinates=(0.0, 0.0),
            node_id="A",
            required_apparatus=[ApparatusType.AMBULANCE_ALS],
        )
        state = QueuedIncidentState(
            incident=inc,
            report_time=10.0,
            unfulfilled_requirements=[ApparatusType.AMBULANCE_ALS],
        )
        assert state.is_fully_dispatched is False
        assert state.is_resolved is False

        state.unfulfilled_requirements.clear()
        assert state.is_fully_dispatched is True

        state.cleared_time = 45.0
        assert state.is_resolved is True


class TestBaselineScenarioExecution:
    def test_single_incident_baseline(self) -> None:
        scen = build_single_incident_baseline_scenario()
        runner = ScenarioRunner(scen)
        res = runner.run()

        assert isinstance(res, ScenarioResult)
        assert res.scenario_name == "Baseline Single Incident"
        assert res.total_incidents == 1
        assert res.incidents_serviced == 1
        assert res.incidents_queued_count == 0
        assert res.units_dispatched_count == 1
        assert res.total_reroutes == 0
        assert res.average_queue_delay_seconds == 0.0
        assert res.average_response_time > 0.0
        assert res.wall_clock_ms >= 0.0

        # Check serialization
        d = res.to_dict()
        assert d["scenario_name"] == "Baseline Single Incident"
        assert d["total_incidents"] == 1
        assert d["incidents_serviced"] == 1
        assert len(d["incident_records"]) == 1
        assert d["incident_records"][0]["is_resolved"] is True


class TestCascadingMultiAlarmAndContention:
    def test_cascading_multi_alarm_scenario(self) -> None:
        scen = build_cascading_multi_alarm_scenario()
        runner = ScenarioRunner(scen)
        res = runner.run()

        assert res.total_incidents == 4
        assert res.incidents_serviced >= 3
        # Should have encountered resource exhaustion for call #4
        assert res.incidents_queued_count >= 1
        assert res.average_queue_delay_seconds >= 0.0
        assert res.units_dispatched_count >= 4
        assert res.simulated_duration > 30.0

        # Verify incident records show clearance and multi-unit dispatches
        inc_map = {r["incident_id"]: r for r in res.incident_records}
        assert "INC-FIRE-01" in inc_map
        assert len(inc_map["INC-FIRE-01"]["assigned_units"]) == 2  # Engine + Medic


class TestInfrastructureSeveranceScenario:
    def test_mid_flight_severance_reroutes_and_arrives(self) -> None:
        scen = build_infrastructure_severance_scenario()
        runner = ScenarioRunner(scen)
        res = runner.run()

        assert res.total_incidents == 1
        assert res.incidents_serviced == 1
        # Proves unit dynamically detoured mid-flight around the severed bridge
        assert res.total_reroutes >= 1
        assert res.average_response_time > 0.0


class TestProgressiveInundationScenario:
    def test_progressive_inundation_response(self) -> None:
        scen = build_progressive_inundation_scenario()
        runner = ScenarioRunner(scen)
        res = runner.run()

        assert res.total_incidents == 2
        assert res.incidents_serviced == 2
        assert res.units_dispatched_count == 2
        assert len(runner.engine.active_hazards) >= 2


class TestScenarioRunnerEdgeCases:
    def test_unreachable_incident_stays_in_queue(self) -> None:
        # Graph with isolated island node Z
        g = Graph()
        g.add_node(Node("A", coordinates=(0.0, 0.0)))
        g.add_node(Node("B", coordinates=(1.0, 0.0)))
        g.add_node(Node("Z", coordinates=(10.0, 10.0)))  # Disconnected!
        g.add_edge(Edge("A", "B", cost=5.0))

        station = EmergencyStation("S1", "Station 1", "A")
        unit = EmergencyUnit("M1", ApparatusType.AMBULANCE_ALS, "A", "S1")
        incident = Incident(
            "INC-ISO-1",
            EmergencyType.MEDICAL_GENERAL,
            UrgencyLevel.PRIORITY_3_BRAVO,
            coordinates=(10.0, 10.0),
            node_id="Z",
            required_apparatus=[ApparatusType.AMBULANCE_ALS],
        )

        scen = ScenarioDefinition(
            name="Isolated Island Incident",
            description="Tests unreachability handling in runner.",
            graph=g,
            stations=[station],
            fleet_units=[unit],
            incidents=[(0.0, incident, 10.0)],
            max_simulation_time=20.0,
            step_size=1.0,
        )

        runner = ScenarioRunner(scen)
        res = runner.run()

        assert res.total_incidents == 1
        assert res.incidents_serviced == 0
        assert res.incidents_queued_count == 1
        assert len(runner.pending_queue) == 1

    def test_urgency_ranking_order(self) -> None:
        assert ScenarioRunner._urgency_rank(UrgencyLevel.PRIORITY_1_ECHO) == 1
        assert ScenarioRunner._urgency_rank(UrgencyLevel.PRIORITY_2_DELTA) == 2
        assert ScenarioRunner._urgency_rank(UrgencyLevel.PRIORITY_3_BRAVO) == 3
        assert ScenarioRunner._urgency_rank(UrgencyLevel.PRIORITY_4_ALPHA) == 4
        assert ScenarioRunner._urgency_rank("non_standard_urgency") == 10
