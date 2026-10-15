"""
End-to-End Prototype Validation Suite for Milestone 8.5.
========================================================
Comprehensive operational lifecycle tests validating:
  1. Full static web asset bundling and delivery.
  2. CAD 911 natural language intake, statutory policy enforcement & audit checksum.
  3. Discrete-event kinematic timeline scenario initialization, stepping, and reset.
  4. Dynamic disaster hazard injection, severance tracking, and clearing.
  5. Real-time Server-Sent Events (SSE) telemetry connection.
  6. Clinical trauma facilities and cryptographic CAD audit log retrieval.
  7. Structural integrity of the Phase 8 Empirical Evaluation Report.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

import pytest

from emergency_intelligence.app.server import EmergencyAppServer


def get_ephemeral_port() -> int:
    """Finds an available ephemeral TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def app_server() -> Any:
    """Fixture to launch a shared ephemeral EmergencyAppServer for the E2E suite."""
    port = get_ephemeral_port()
    server = EmergencyAppServer(host="127.0.0.1", port=port, enable_logging=False)
    server.start(blocking=False)
    time.sleep(0.05)
    base_url = f"http://127.0.0.1:{port}"
    yield {"server": server, "url": base_url, "port": port}
    server.stop()


def http_get_json(url: str) -> Any:
    """Helper to perform HTTP GET and parse JSON envelope."""
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data.get("success") is True
        return data.get("data")


def http_post_json(url: str, payload: Dict[str, Any]) -> Any:
    """Helper to perform HTTP POST with JSON body and parse JSON response."""
    body_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body_bytes,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3.0) as resp:
        assert resp.status in (200, 201)
        data = json.loads(resp.read().decode("utf-8"))
        assert data.get("success") is True
        return data.get("data")


class TestAppE2ESuite:
    """Comprehensive End-to-End integration test suite."""

    def test_e2e_static_assets_delivery(self, app_server: Dict[str, Any]) -> None:
        """Verifies all HTML, CSS, and JS modules are served with valid MIME types."""
        assets = [
            ("/", "text/html"),
            ("/css/dashboard.css", "text/css"),
            ("/css/leaflet-custom.css", "text/css"),
            ("/css/cad.css", "text/css"),
            ("/js/api.js", "javascript"),
            ("/js/sse.js", "javascript"),
            ("/js/map.js", "javascript"),
            ("/js/audio.js", "javascript"),
            ("/js/cad.js", "javascript"),
            ("/js/timeline.js", "javascript"),
            ("/js/app.js", "javascript"),
        ]

        for path, expected_mime in assets:
            url = f"{app_server['url']}{path}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                assert resp.status == 200
                content_type = resp.headers.get("Content-Type", "")
                assert expected_mime in content_type, f"Expected {expected_mime} for {path}, got {content_type}"
                content = resp.read()
                assert len(content) > 0, f"Asset {path} should not be empty"

    def test_e2e_cad_dispatch_and_kinematic_timeline(self, app_server: Dict[str, Any]) -> None:
        """Validates 911 narrative evaluation, statutory policy enforcement, and kinematic stepping."""
        # 1. 911 Intake
        intake_url = f"{app_server['url']}/api/intake"
        narrative = "Caller reports elderly female collapsed at waterfront pier, unresponsive, CPR in progress."
        payload = {"raw_text": narrative}

        result = http_post_json(intake_url, payload)
        assert result.get("intake_id")
        assert result.get("urgency") in ("critical", "priority_1_echo")
        assert any("CARDIAC" in rule for rule in result.get("policy_directives", []))
        assert len(result.get("dispatched_units", [])) >= 1
        assert result.get("audit_checksum")

        # 2. Initialize simulation scenario
        start_url = f"{app_server['url']}/api/simulation/start"
        start_data = http_post_json(start_url, {"scenario_id": "metropolitan_disaster"})
        assert start_data.get("current_sim_time") == 0.0

        # 3. Advance discrete-event simulation timeline by 15 seconds
        step_url = f"{app_server['url']}/api/simulation/step"
        step_data = http_post_json(step_url, {"step_seconds": 15.0})
        assert step_data.get("current_sim_time", 0.0) >= 15.0

        # 4. Further advance to T+60s
        seek_data = http_post_json(step_url, {"step_seconds": 45.0})
        assert seek_data.get("current_sim_time", 0.0) >= 60.0

        # 5. Reset simulation back to T+0s
        reset_url = f"{app_server['url']}/api/simulation/reset"
        reset_data = http_post_json(reset_url, {})
        assert reset_data.get("current_sim_time") == 0.0

    def test_e2e_dynamic_hazard_rerouting_lifecycle(self, app_server: Dict[str, Any]) -> None:
        """Tests injecting dynamic hazard polygon, verifying severance, and clearing hazard."""
        hazards_url = f"{app_server['url']}/api/hazards"
        hazard_payload = {
            "polygon_coords": [
                [-122.335, 47.605],
                [-122.325, 47.605],
                [-122.325, 47.615],
                [-122.335, 47.615],
            ],
            "hazard_type": "flood",
            "speed_multiplier": 0.0,
            "severity": "CRITICAL",
        }

        # Inject hazard
        hz_result = http_post_json(hazards_url, hazard_payload)
        assert hz_result.get("hazard_id")
        assert hz_result.get("edges_closed", 0) > 0

        # Check health telemetry
        health_data = http_get_json(f"{app_server['url']}/api/health")
        assert health_data.get("active_hazards", 0) >= 1

        # Delete all dynamic hazards
        req_del = urllib.request.Request(hazards_url, method="DELETE")
        with urllib.request.urlopen(req_del, timeout=2.0) as resp:
            assert resp.status == 200
            del_data = json.loads(resp.read().decode("utf-8"))
            assert del_data.get("success") is True

        # Verify hazards cleared
        health_after = http_get_json(f"{app_server['url']}/api/health")
        assert health_after.get("active_hazards") == 0
        assert health_after.get("severed_edges") == 0

    def test_e2e_telemetry_sse_event_stream(self, app_server: Dict[str, Any]) -> None:
        """Verifies the Server-Sent Events (SSE) telemetry connection handshake."""
        for endpoint in ["/api/simulation/stream", "/api/telemetry/events"]:
            sse_url = f"{app_server['url']}{endpoint}"
            req = urllib.request.Request(sse_url, headers={"Accept": "text/event-stream"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                assert resp.status == 200
                content_type = resp.headers.get("Content-Type", "")
                assert "text/event-stream" in content_type

    def test_e2e_facilities_and_audit_log(self, app_server: Dict[str, Any]) -> None:
        """Validates clinical facility amenity catalog and CAD audit trail retrieval."""
        fac_data = http_get_json(f"{app_server['url']}/api/facilities")
        assert isinstance(fac_data, list)
        assert len(fac_data) > 0
        assert any(f.get("poi_type") == "hospital" for f in fac_data)

        audit_data = http_get_json(f"{app_server['url']}/api/cad/audit-log")
        assert "entries" in audit_data
        assert isinstance(audit_data["entries"], list)

    def test_e2e_evaluation_report_integrity(self) -> None:
        """Verifies docs/milestone_8_evaluation_report.md exists and is structurally complete."""
        repo_root = Path(__file__).resolve().parent.parent
        report_path = repo_root / "docs" / "milestone_8_evaluation_report.md"
        assert report_path.is_file(), "docs/milestone_8_evaluation_report.md must exist"

        content = report_path.read_text(encoding="utf-8")
        assert "Phase 8 Evaluation Report" in content
        assert "Architectural Benchmark" in content
        assert "Server-Sent Events" in content
        assert "5-Stage Orchestration Evaluation" in content
        assert "Continuous Kinematic Timeline" in content
        assert "Containerization & Production Packaging" in content
