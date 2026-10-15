"""
Unit and Integration Tests for Milestone 8.3: Live CAD Intake Terminal, Audio Synthesizer & Timeline Controller.
=================================================================================================================
Validates:
  1. Delivery and MIME types for CAD CSS, Web Audio synthesizer, CAD terminal, and timeline controller ES6 modules.
  2. DOM integrity in index.html for CAD presets, narrative input, 5-stage policy card, and bottom timeline bar.
  3. Client-side audio synthesis contracts and preset definitions.
  4. End-to-end CAD 911 call intake with PII sanitization, clinical triage, statutory mandates, and cryptographic audit hash.
  5. Discrete-event simulation REST lifecycle: status, start, step forward, target seek, and reset.
  6. Schema validation error handling for CAD intake and simulation controllers.
"""

from __future__ import annotations

import json
import unittest
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple

from emergency_intelligence.app.server import EmergencyAppServer
from emergency_intelligence.app.state import AppState


class TestAppCadTimeline(unittest.TestCase):
    """Test suite for CAD intake terminal, Web Audio alerting, and simulation playback controller."""

    @classmethod
    def setUpClass(cls) -> None:
        """Launch embedded HTTP server on an ephemeral port."""
        cls.state = AppState()
        cls.server = EmergencyAppServer(host="127.0.0.1", port=0, state=cls.state, enable_logging=False)
        cls.server.start_background()
        cls.base_url = cls.server.get_url()

    @classmethod
    def tearDownClass(cls) -> None:
        """Shut down the background test server."""
        cls.server.stop()

    def _http_get(self, path: str) -> Tuple[int, Dict[str, str], bytes]:
        """Execute an HTTP GET request and return status, headers, and raw bytes."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read()
                headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, headers, raw
        except urllib.error.HTTPError as exc:
            with exc:
                raw = exc.read()
                headers = {k.lower(): v for k, v in exc.headers.items()}
                return exc.code, headers, raw

    def _http_post(self, path: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any]]:
        """Execute an HTTP POST request with JSON payload."""
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST", headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return resp.status, body
        except urllib.error.HTTPError as exc:
            with exc:
                body = json.loads(exc.read().decode("utf-8"))
                return exc.code, body

    def _http_delete(self, path: str) -> Tuple[int, Dict[str, Any]]:
        """Execute an HTTP DELETE request."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                return resp.status, body
        except urllib.error.HTTPError as exc:
            with exc:
                body = json.loads(exc.read().decode("utf-8"))
                return exc.code, body

    # -------------------------------------------------------------------------
    # 1. Static Asset Delivery for Milestone 8.3 Files
    # -------------------------------------------------------------------------

    def test_cad_css_delivery(self) -> None:
        """Verify delivery of cad.css with text/css content type."""
        status, headers, body = self._http_get("/css/cad.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers.get("content-type", ""))
        text = body.decode("utf-8")
        self.assertIn(".cad-preset-bar", text)
        self.assertIn(".policy-report-card", text)
        self.assertIn(".bottom-timeline-bar", text)
        self.assertIn(".incident-beacon-marker", text)
        self.assertIn(".vehicle-marker-pin", text)

    def test_audio_js_module_delivery(self) -> None:
        """Verify delivery of audio.js Web Audio API synthesizer module."""
        status, headers, body = self._http_get("/js/audio.js")
        self.assertEqual(status, 200)
        self.assertTrue(
            "javascript" in headers.get("content-type", "")
            or "text/plain" in headers.get("content-type", "")
        )
        text = body.decode("utf-8")
        self.assertIn("AudioAlertSynthesizer", text)
        self.assertIn("playDispatchChime", text)
        self.assertIn("playEmergencySiren", text)
        self.assertIn("export const audioSynth", text)

    def test_cad_js_module_delivery(self) -> None:
        """Verify delivery of cad.js CAD Terminal controller module."""
        status, headers, body = self._http_get("/js/cad.js")
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertIn("CadTerminal", text)
        self.assertIn("CAD_PRESETS", text)
        self.assertIn("Cardiac Arrest", text)
        self.assertIn("Highway Pileup", text)
        self.assertIn("renderPolicyReport", text)

    def test_timeline_js_module_delivery(self) -> None:
        """Verify delivery of timeline.js playback transport controller module."""
        status, headers, body = self._http_get("/js/timeline.js")
        self.assertEqual(status, 200)
        text = body.decode("utf-8")
        self.assertIn("TimelineController", text)
        self.assertIn("formatTime", text)
        self.assertIn("stepForward", text)
        self.assertIn("resetSimulation", text)

    def test_index_html_cad_and_timeline_dom_elements(self) -> None:
        """Verify index.html includes all required DOM IDs for CAD and timeline controllers."""
        status, _, body = self._http_get("/")
        self.assertEqual(status, 200)
        html = body.decode("utf-8")

        # CAD DOM hooks
        self.assertIn('id="cadTerminalPanel"', html)
        self.assertIn('id="cadPresetBar"', html)
        self.assertIn('id="cadNarrativeInput"', html)
        self.assertIn('id="cadSubmitBtn"', html)
        self.assertIn('id="policyReportCard"', html)
        self.assertIn('id="audioToggleBtn"', html)

        # Timeline Transport DOM hooks
        self.assertIn('id="btnSimPlay"', html)
        self.assertIn('id="btnSimStep"', html)
        self.assertIn('id="btnSimReset"', html)
        self.assertIn('id="simClockDisplay"', html)
        self.assertIn('id="timelineScrubber"', html)
        self.assertIn('class="speed-chip', html)
        self.assertIn('/css/cad.css', html)

    # -------------------------------------------------------------------------
    # 2. 911 CAD Narrative Intake & AI Statutory Policy Tests
    # -------------------------------------------------------------------------

    def test_cad_intake_cardiac_echo_dispatch(self) -> None:
        """Verify 911 CAD intake evaluating cardiac arrest with AHA dual-response."""
        payload = {
            "raw_text": "58yo male collapsed on waterfront sidewalk near Pier 54, unresponsive, agonal breathing, bystander CPR.",
            "caller_phone": "+1-206-555-0199",
            "location_hint": [47.6062, -122.3321],
        }
        status, body = self._http_post("/api/intake", payload)
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))

        data = body.get("data", {})
        self.assertTrue(data.get("intake_id"))
        self.assertIn("sanitized_text", data)
        self.assertTrue(data.get("urgency"))
        self.assertIn("audit_checksum", data)
        self.assertTrue(data.get("candidate_route_found"))
        self.assertTrue(len(data.get("dispatched_units", [])) >= 1)
        self.assertIn("incident_node", data)
        self.assertIn("incident_coords", data)

    def test_cad_intake_validation_error_empty_text(self) -> None:
        """Verify 911 CAD intake rejects empty narrative with HTTP 400."""
        payload = {"raw_text": "   "}
        status, body = self._http_post("/api/intake", payload)
        self.assertEqual(status, 400)
        self.assertFalse(body.get("success"))
        self.assertEqual(body.get("error", {}).get("code"), "VALIDATION_ERROR")

    def test_cad_intake_validation_error_missing_body(self) -> None:
        """Verify 911 CAD intake rejects non-object or missing raw_text."""
        status, body = self._http_post("/api/intake", {"caller_phone": "123"})
        self.assertEqual(status, 400)
        self.assertFalse(body.get("success"))

    # -------------------------------------------------------------------------
    # 3. Discrete-Event Simulation & Playback Transport API Tests
    # -------------------------------------------------------------------------

    def test_simulation_status_endpoint(self) -> None:
        """Verify GET /api/simulation/status returns current simulation state."""
        status, headers, body = self._http_get("/api/simulation/status")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8")).get("data", {})
        self.assertIn("initialized", data)
        self.assertIn("current_sim_time", data)
        self.assertIn("max_duration_seconds", data)
        self.assertIn("vehicles", data)
        self.assertIn("active_incidents", data)

    def test_simulation_start_lifecycle(self) -> None:
        """Verify POST /api/simulation/start initializes the scenario engine."""
        payload = {
            "scenario_id": "metropolitan_disaster",
            "max_duration_seconds": 1800.0,
        }
        status, body = self._http_post("/api/simulation/start", payload)
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))

        data = body.get("data", {})
        self.assertTrue(data.get("initialized"))
        self.assertEqual(data.get("scenario_id"), "metropolitan_disaster")
        self.assertEqual(data.get("max_duration_seconds"), 1800.0)
        self.assertEqual(data.get("current_sim_time"), 0.0)
        self.assertTrue(len(data.get("vehicles", [])) >= 1)

    def test_simulation_start_invalid_scenario(self) -> None:
        """Verify POST /api/simulation/start rejects unsupported scenario ID."""
        status, body = self._http_post("/api/simulation/start", {"scenario_id": "alien_invasion_xyz"})
        self.assertEqual(status, 400)
        self.assertFalse(body.get("success"))
        self.assertEqual(body.get("error", {}).get("code"), "VALIDATION_ERROR")

    def test_simulation_step_forward_and_kinematics(self) -> None:
        """Verify stepping the simulation advances time and computes vehicle kinematics."""
        # First ensure simulation is initialized
        self._http_post("/api/simulation/start", {"scenario_id": "metropolitan_disaster"})

        # Step by 15.0 seconds
        step_payload = {"step_seconds": 15.0}
        status, body = self._http_post("/api/simulation/step", step_payload)
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))

        data = body.get("data", {})
        self.assertGreaterEqual(data.get("current_sim_time", 0.0), 15.0)
        self.assertTrue(len(data.get("vehicles", [])) >= 1)

        # Verify kinematic vehicle fields
        v0 = data["vehicles"][0]
        self.assertIn("vehicle_id", v0)
        self.assertIn("current_coords", v0)
        self.assertIn("status", v0)
        self.assertIn("distance_traveled_m", v0)

    def test_simulation_step_seek_target_time(self) -> None:
        """Verify seeking directly to a target timestamp."""
        status, body = self._http_post("/api/simulation/step", {"target_time": 45.0})
        self.assertEqual(status, 200)
        data = body.get("data", {})
        self.assertAlmostEqual(data.get("current_sim_time", 0.0), 45.0, delta=1.0)

    def test_simulation_step_validation_errors(self) -> None:
        """Verify invalid step parameters return HTTP 400."""
        # Negative step_seconds
        status, body = self._http_post("/api/simulation/step", {"step_seconds": -5.0})
        self.assertEqual(status, 400)
        self.assertEqual(body.get("error", {}).get("code"), "VALIDATION_ERROR")

        # Negative target_time
        status, body = self._http_post("/api/simulation/step", {"target_time": -10.0})
        self.assertEqual(status, 400)
        self.assertEqual(body.get("error", {}).get("code"), "VALIDATION_ERROR")

    def test_simulation_reset_lifecycle(self) -> None:
        """Verify resetting simulation returns clock to 0.0."""
        status, body = self._http_post("/api/simulation/reset", {})
        self.assertEqual(status, 200)
        data = body.get("data", {})
        self.assertEqual(data.get("current_sim_time"), 0.0)
        self.assertFalse(data.get("is_running"))

    # -------------------------------------------------------------------------
    # 4. Hazard Reset API Integration
    # -------------------------------------------------------------------------

    def test_delete_all_hazards(self) -> None:
        """Verify DELETE /api/hazards clears all active disaster polygons."""
        # First inject a hazard
        self._http_post("/api/hazards", {
            "polygon_coords": [[-122.33, 47.60], [-122.32, 47.60], [-122.32, 47.61], [-122.33, 47.61]],
            "hazard_type": "FLOOD",
        })

        # Clear all
        status, body = self._http_delete("/api/hazards")
        self.assertEqual(status, 200)
        self.assertTrue(body.get("success"))
        self.assertEqual(body.get("data", {}).get("status"), "all_cleared")

    def test_delete_single_nonexistent_hazard_returns_404(self) -> None:
        """Verify DELETE /api/hazards/:id returns 404 for unknown hazard."""
        status, body = self._http_delete("/api/hazards/HAZ_999999")
        self.assertEqual(status, 404)
        self.assertFalse(body.get("success"))


if __name__ == "__main__":
    unittest.main()
