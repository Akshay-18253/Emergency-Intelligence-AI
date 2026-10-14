"""
Unit tests for Milestone 8.1: Embedded HTTP Server & REST / Event-Stream API Gateway.
=====================================================================================
Validates:
  1. Ephemeral port lifecycle management, background thread startup, clean shutdown.
  2. REST API endpoints (/api/health, /api/network, /api/facilities, /api/route, /api/intake).
  3. Dynamic hazard injection, edge closures, and reset endpoints.
  4. Server-Sent Events (SSE) streaming gateway and live broadcasting.
  5. Static file serving and path traversal security guards.
  6. Payload bounds checking, CORS headers, and error envelope handling.
"""

from __future__ import annotations

import json
import time
import unittest
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple

from emergency_intelligence.app.server import EmergencyAppServer
from emergency_intelligence.app.state import AppState


class TestAppServer(unittest.TestCase):
    """Test suite for the embedded HTTP server and API gateway."""

    @classmethod
    def setUpClass(cls) -> None:
        """Launch the embedded server on an ephemeral port (port=0)."""
        cls.state = AppState()
        cls.server = EmergencyAppServer(host="127.0.0.1", port=0, state=cls.state, enable_logging=False)
        cls.server.start_background()
        cls.base_url = cls.server.get_url()

    @classmethod
    def tearDownClass(cls) -> None:
        """Terminate the background server."""
        cls.server.stop()

    def _http_get(self, path: str) -> Tuple[int, Dict[str, Any], bytes]:
        """Helper to execute an HTTP GET request."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read()
                try:
                    data = json.loads(raw.decode("utf-8"))
                except Exception:
                    data = {}
                return resp.status, data, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}
            return exc.code, data, raw

    def _http_post(self, path: str, payload: Dict[str, Any]) -> Tuple[int, Dict[str, Any], bytes]:
        """Helper to execute an HTTP POST request with JSON payload."""
        url = f"{self.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
                return resp.status, data, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}
            return exc.code, data, raw

    def _http_delete(self, path: str) -> Tuple[int, Dict[str, Any], bytes]:
        """Helper to execute an HTTP DELETE request."""
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read()
                data = json.loads(raw.decode("utf-8"))
                return resp.status, data, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                data = {}
            return exc.code, data, raw

    # -------------------------------------------------------------------------
    # Server Lifecycle & Health
    # -------------------------------------------------------------------------

    def test_server_lifecycle_and_port(self) -> None:
        """Verify server bound to a valid ephemeral non-zero port."""
        self.assertGreater(self.server.port, 1024)
        self.assertTrue(self.base_url.startswith("http://127.0.0.1:"))

    def test_api_health(self) -> None:
        """Verify GET /api/health returns operational metrics."""
        status_code, json_resp, _ = self._http_get("/api/health")
        self.assertEqual(status_code, 200)
        self.assertTrue(json_resp.get("success"))
        data = json_resp.get("data", {})
        self.assertEqual(data.get("status"), "healthy")
        self.assertEqual(data.get("graph_nodes"), 36)
        self.assertGreater(data.get("graph_edges"), 100)
        self.assertEqual(data.get("emergency_facilities"), 5)

    # -------------------------------------------------------------------------
    # Spatial Network & Facilities
    # -------------------------------------------------------------------------

    def test_api_network_geojson(self) -> None:
        """Verify GET /api/network returns standard RFC 7946 FeatureCollection."""
        status_code, json_resp, _ = self._http_get("/api/network")
        self.assertEqual(status_code, 200)
        self.assertTrue(json_resp.get("success"))
        data = json_resp.get("data", {})
        self.assertEqual(data.get("type"), "FeatureCollection")
        self.assertIn("bbox", data)
        features = data.get("features", [])
        self.assertGreater(len(features), 50)
        self.assertEqual(features[0]["type"], "Feature")
        self.assertEqual(features[0]["geometry"]["type"], "LineString")

    def test_api_facilities(self) -> None:
        """Verify GET /api/facilities returns hospitals and stations."""
        status_code, json_resp, _ = self._http_get("/api/facilities")
        self.assertEqual(status_code, 200)
        self.assertTrue(json_resp.get("success"))
        facilities = json_resp.get("data", [])
        self.assertEqual(len(facilities), 5)

        hospitals = [f for f in facilities if f["poi_type"] == "hospital"]
        stations = [f for f in facilities if f["poi_type"] == "fire_station"]
        self.assertEqual(len(hospitals), 3)
        self.assertEqual(len(stations), 2)

        # Harborview Trauma Level 1 check
        trauma_hospitals = [h for h in hospitals if h["trauma_level"] == 1]
        self.assertEqual(len(trauma_hospitals), 1)

    # -------------------------------------------------------------------------
    # Route Calculation Endpoint
    # -------------------------------------------------------------------------

    def test_api_route_baseline(self) -> None:
        """Verify POST /api/route computes optimal path between nodes."""
        payload = {
            "origin": "N_0_0",
            "destination": "N_3_5",
            "apparatus_type": "ambulance_als",
            "elevation_aware": False,
        }
        status_code, json_resp, _ = self._http_post("/api/route", payload)
        self.assertEqual(status_code, 200)
        self.assertTrue(json_resp.get("success"))
        data = json_resp.get("data", {})
        self.assertTrue(data.get("path_found"))
        self.assertGreater(data.get("duration_seconds"), 0.0)
        self.assertGreater(data.get("distance_2d_meters"), 0.0)
        self.assertGreater(data.get("node_count"), 2)
        self.assertEqual(data["origin_node"], "N_0_0")
        self.assertEqual(data["destination_node"], "N_3_5")
        self.assertIn("geojson", data)

    def test_api_route_coordinates(self) -> None:
        """Verify POST /api/route snaps GPS coordinates to network nodes."""
        payload = {
            "origin": [47.6050, -122.3300],
            "destination": [47.6100, -122.3200],
            "apparatus_type": "fire_engine",
        }
        status_code, json_resp, _ = self._http_post("/api/route", payload)
        self.assertEqual(status_code, 200)
        data = json_resp.get("data", {})
        self.assertTrue(data.get("path_found"))

    def test_api_route_elevation_aware(self) -> None:
        """Verify POST /api/route with elevation_aware=True extracts slope profile."""
        payload = {
            "origin": "N_0_0",
            "destination": "N_3_5",
            "apparatus_type": "ladder_truck",
            "elevation_aware": True,
        }
        status_code, json_resp, _ = self._http_post("/api/route", payload)
        self.assertEqual(status_code, 200)
        data = json_resp.get("data", {})
        self.assertTrue(data.get("path_found"))
        self.assertGreaterEqual(data.get("distance_3d_meters"), data.get("distance_2d_meters"))
        self.assertGreaterEqual(data.get("elevation_gain_meters"), 0.0)

    # -------------------------------------------------------------------------
    # 911 Intake & Policy Pipeline Endpoint
    # -------------------------------------------------------------------------

    def test_api_intake_cardiac_dual_response(self) -> None:
        """Verify POST /api/intake executes 5-stage dispatch pipeline with statutory overrules."""
        payload = {
            "raw_text": "55yo male sudden cardiac arrest collapse at 4th and Pine. Caller: 206-555-0199.",
            "caller_phone": "206-555-0199",
        }
        status_code, json_resp, _ = self._http_post("/api/intake", payload)
        self.assertEqual(status_code, 200)
        self.assertTrue(json_resp.get("success"))
        data = json_resp.get("data", {})
        self.assertIn("intake_id", data)
        self.assertIn("sanitized_text", data)
        self.assertEqual(data.get("urgency"), "priority_1_echo")
        self.assertIn("RULE_CARDIAC_DUAL_RESPONSE_MANDATE", data.get("policy_directives", []))
        self.assertGreater(len(data.get("dispatched_units", [])), 0)
        self.assertIsNotNone(data.get("destination_facility"))
        self.assertEqual(len(data.get("audit_checksum", "")), 64)

    # -------------------------------------------------------------------------
    # Dynamic Hazard Injection & Reset
    # -------------------------------------------------------------------------

    def test_api_hazards_lifecycle(self) -> None:
        """Verify hazard polygon injection, edge severance, and hazard clearance."""
        hazard_payload = {
            "hazard_type": "river_flood",
            "speed_multiplier": 0.0,
            "severity": "CRITICAL",
            "polygon_coords": [
                [-122.332, 47.600],
                [-122.328, 47.600],
                [-122.328, 47.610],
                [-122.332, 47.610],
            ],
        }
        # 1. Inject hazard
        status_code, json_resp, _ = self._http_post("/api/hazards", hazard_payload)
        self.assertEqual(status_code, 201)
        data = json_resp.get("data", {})
        hazard_id = data.get("hazard_id")
        self.assertIsNotNone(hazard_id)
        self.assertGreater(data.get("edges_closed"), 0)

        # 2. Delete specific hazard
        del_status, del_resp, _ = self._http_delete(f"/api/hazards/{hazard_id}")
        self.assertEqual(del_status, 200)
        self.assertEqual(del_resp["data"]["status"], "cleared")

        # 3. Test reset all hazards
        self._http_post("/api/hazards", hazard_payload)
        reset_status, reset_resp, _ = self._http_post("/api/hazards/reset", {})
        self.assertEqual(reset_status, 200)
        self.assertEqual(reset_resp["data"]["status"], "reset_successful")

    # -------------------------------------------------------------------------
    # Server-Sent Events (SSE) Streaming
    # -------------------------------------------------------------------------

    def test_api_simulation_sse_stream(self) -> None:
        """Verify GET /api/simulation/stream establishes connection and emits event frames."""
        url = f"{self.base_url}/api/simulation/stream"
        req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})

        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))

            # Read the first event frame (initial connected frame)
            line1 = resp.readline().decode("utf-8")
            line2 = resp.readline().decode("utf-8")
            line3 = resp.readline().decode("utf-8")

            combined = line1 + line2 + line3
            self.assertIn("event: connected", combined)
            self.assertIn("stream_established", combined)

    # -------------------------------------------------------------------------
    # Static File Server & Security Traversal Guard
    # -------------------------------------------------------------------------

    def test_static_index_html(self) -> None:
        """Verify GET / returns diagnostic index.html."""
        status_code, _, raw = self._http_get("/")
        self.assertEqual(status_code, 200)
        html = raw.decode("utf-8")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("Emergency Intelligence AI", html)

    def test_path_traversal_guard(self) -> None:
        """Verify attempts to escape static root return 403 or 404."""
        status_code, json_resp, _ = self._http_get("/../../etc/passwd")
        self.assertIn(status_code, (403, 404))

    # -------------------------------------------------------------------------
    # Error Handling & Validation
    # -------------------------------------------------------------------------

    def test_invalid_json_body(self) -> None:
        """Verify sending malformed JSON body returns 400."""
        url = f"{self.base_url}/api/route"
        req = urllib.request.Request(url, data=b"NOT_A_JSON{{{", headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=5.0)
            self.fail("Expected HTTPError 400")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 400)
            data = json.loads(exc.read().decode("utf-8"))
            self.assertFalse(data.get("success"))
            self.assertEqual(data["error"]["code"], "INVALID_PAYLOAD")

    def test_missing_route_fields(self) -> None:
        """Verify route request missing required destination returns 400."""
        payload = {"origin": "N_0_0"}
        status_code, json_resp, _ = self._http_post("/api/route", payload)
        self.assertEqual(status_code, 400)
        self.assertFalse(json_resp.get("success"))
        self.assertEqual(json_resp["error"]["code"], "VALIDATION_ERROR")

    def test_not_found_endpoint(self) -> None:
        """Verify querying non-existent API path returns 404."""
        status_code, json_resp, _ = self._http_get("/api/non_existent_endpoint")
        self.assertEqual(status_code, 404)
        self.assertFalse(json_resp.get("success"))

    def test_cors_options_preflight(self) -> None:
        """Verify OPTIONS request returns 204 with CORS headers."""
        url = f"{self.base_url}/api/route"
        req = urllib.request.Request(url, method="OPTIONS")
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            self.assertEqual(resp.status, 204)
            self.assertEqual(resp.headers.get("Access-Control-Allow-Origin"), "*")
            self.assertIn("POST", resp.headers.get("Access-Control-Allow-Methods", ""))


if __name__ == "__main__":
    unittest.main()
