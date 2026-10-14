"""
Unit and Integration Tests for Milestone 8.2: Tactical Operations Dashboard & Interactive GIS Map Canvas.
=======================================================================================================
Validates:
  1. Static asset delivery for all dashboard resources (HTML, CSS, ES6 modules) with correct Content-Type headers.
  2. SPA client routing fallback to index.html for non-API deep links.
  3. Strict directory traversal protection preventing filesystem escapes.
  4. Complete HTML5 semantic layout, DOM IDs, and accessibility hooks required by dashboard panels.
  5. Tactical CSS design tokens, glassmorphism card classes, and Leaflet dark-mode overrides.
  6. ES6 modular JavaScript export/import integrity across api.js, sse.js, map.js, and app.js.
  7. Full end-to-end API integration contract matching frontend requirements.
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


class TestAppDashboard(unittest.TestCase):
    """Test suite for the Tactical Operations Dashboard frontend assets and integration contracts."""

    @classmethod
    def setUpClass(cls) -> None:
        """Launch the embedded HTTP server on an ephemeral port."""
        cls.state = AppState()
        cls.server = EmergencyAppServer(host="127.0.0.1", port=0, state=cls.state, enable_logging=False)
        cls.server.start_background()
        cls.base_url = cls.server.get_url()

    @classmethod
    def tearDownClass(cls) -> None:
        """Shut down the background server."""
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
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            with exc:
                raw = exc.read()
                try:
                    err_json = json.loads(raw.decode("utf-8"))
                except Exception:
                    err_json = {}
                return exc.code, err_json

    # -----------------------------------------------------------------------
    # 1. Static Asset Delivery & MIME Types
    # -----------------------------------------------------------------------

    def test_root_index_html_delivery(self) -> None:
        """Test GET / returns index.html with text/html content-type."""
        status, headers, raw = self._http_get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("content-type", ""))
        content = raw.decode("utf-8")
        self.assertIn("Emergency Intelligence AI", content)
        self.assertIn('id="map"', content)

    def test_explicit_index_html_delivery(self) -> None:
        """Test GET /index.html returns index.html with text/html content-type."""
        status, headers, raw = self._http_get("/index.html")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("content-type", ""))
        content = raw.decode("utf-8")
        self.assertIn("EOC CONSOLE", content)

    def test_dashboard_css_delivery(self) -> None:
        """Test GET /css/dashboard.css delivers stylesheet with text/css content-type."""
        status, headers, raw = self._http_get("/css/dashboard.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers.get("content-type", ""))
        content = raw.decode("utf-8")
        self.assertIn(":root", content)
        self.assertIn("--bg-deep", content)
        self.assertIn(".sidebar-panel", content)
        self.assertIn(".map-canvas-container", content)

    def test_leaflet_custom_css_delivery(self) -> None:
        """Test GET /css/leaflet-custom.css delivers Leaflet dark theme overrides."""
        status, headers, raw = self._http_get("/css/leaflet-custom.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", headers.get("content-type", ""))
        content = raw.decode("utf-8")
        self.assertIn(".leaflet-container", content)
        self.assertIn(".poi-marker", content)
        self.assertIn(".poi-hospital", content)
        self.assertIn(".poi-fire", content)
        self.assertIn(".hazard-pulse-polygon", content)

    def test_js_modules_delivery(self) -> None:
        """Test GET /js/*.js delivers all ES6 modules with javascript content-type."""
        modules = [
            ("api.js", "class ApiClient"),
            ("sse.js", "class SSEClient"),
            ("map.js", "class TacticalMap"),
            ("app.js", "TacticalMap"),
        ]
        for mod_name, expected_snippet in modules:
            status, headers, raw = self._http_get(f"/js/{mod_name}")
            self.assertEqual(status, 200, f"Failed delivering /js/{mod_name}")
            self.assertIn("javascript", headers.get("content-type", ""))
            content = raw.decode("utf-8")
            self.assertIn(expected_snippet, content, f"Missing snippet in /js/{mod_name}")

    def test_spa_client_routing_fallback(self) -> None:
        """Test non-existent non-API routes fallback to index.html for SPA routing."""
        status, headers, raw = self._http_get("/dashboard/live/view")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("content-type", ""))
        content = raw.decode("utf-8")
        self.assertIn("EOC CONSOLE", content)

    def test_directory_traversal_protection(self) -> None:
        """Test directory traversal attempts are rejected."""
        status, _, _ = self._http_get("/../../pyproject.toml")
        self.assertIn(status, [403, 404])

        status, _, _ = self._http_get("/css/../../src/emergency_intelligence/app/server.py")
        self.assertIn(status, [403, 404])

    # -----------------------------------------------------------------------
    # 2. DOM & UI Structure Verification
    # -----------------------------------------------------------------------

    def test_html_semantic_structure_and_element_ids(self) -> None:
        """Verify index.html contains all expected DOM element IDs and semantic landmarks."""
        _, _, raw = self._http_get("/index.html")
        html = raw.decode("utf-8")

        # Essential Landmarks
        self.assertIn("<header", html)
        self.assertIn("<main", html)
        self.assertIn("<aside", html)
        self.assertIn("<section", html)

        # Telemetry Bar IDs
        self.assertIn('id="sse-status-dot"', html)
        self.assertIn('id="sse-status-text"', html)
        self.assertIn('id="telemetry-uptime"', html)
        self.assertIn('id="telemetry-nodes"', html)
        self.assertIn('id="telemetry-edges"', html)
        self.assertIn('id="telemetry-hazards"', html)
        self.assertIn('id="telemetry-severed"', html)

        # Routing Form IDs
        self.assertIn('id="select-origin"', html)
        self.assertIn('id="select-destination"', html)
        self.assertIn('name="apparatus"', html)
        self.assertIn('value="AMBULANCE_ALS"', html)
        self.assertIn('value="FIRE_ENGINE"', html)
        self.assertIn('id="toggle-elevation"', html)
        self.assertIn('id="btn-calculate-route"', html)

        # Kinematics IDs
        self.assertIn('id="metric-duration"', html)
        self.assertIn('id="metric-distance"', html)
        self.assertIn('id="metric-elevation"', html)
        self.assertIn('id="metric-grade"', html)
        self.assertIn('id="maneuver-list"', html)

        # Disaster Hazard IDs
        self.assertIn('id="btn-flood"', html)
        self.assertIn('id="btn-collapse"', html)
        self.assertIn('id="btn-wildfire"', html)
        self.assertIn('id="btn-reset-hazards"', html)

        # Terminal Log & Map Canvas IDs
        self.assertIn('id="terminal-feed"', html)
        self.assertIn('id="map"', html)

    # -----------------------------------------------------------------------
    # 3. Frontend-Backend Contract Integration
    # -----------------------------------------------------------------------

    def test_api_network_contract_for_map(self) -> None:
        """Verify /api/network response contains features and properties needed by map.js."""
        status, _, raw = self._http_get("/api/network")
        self.assertEqual(status, 200)
        envelope = json.loads(raw.decode("utf-8"))
        data = envelope.get("data", envelope)
        self.assertEqual(data.get("type"), "FeatureCollection")
        self.assertIn("features", data)
        self.assertGreater(len(data["features"]), 0)

        # Check first edge feature properties
        feat = data["features"][0]
        self.assertEqual(feat.get("type"), "Feature")
        self.assertIn("geometry", feat)
        self.assertEqual(feat["geometry"].get("type"), "LineString")
        props = feat.get("properties", {})
        self.assertIn("source", props)
        self.assertIn("target", props)
        self.assertIn("length_m", props)
        self.assertIn("is_severed", props)

    def test_api_facilities_contract_for_map(self) -> None:
        """Verify /api/facilities response contains POI metadata needed by map.js."""
        status, _, raw = self._http_get("/api/facilities")
        self.assertEqual(status, 200)
        envelope = json.loads(raw.decode("utf-8"))
        data = envelope.get("data", envelope)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

        # Verify hospital and fire station POI schema
        poi = data[0]
        self.assertIn("id", poi)
        self.assertIn("name", poi)
        self.assertIn("poi_type", poi)
        self.assertIn("coordinates", poi)
        self.assertEqual(len(poi["coordinates"]), 2)

    def test_api_route_calculation_contract_for_dashboard(self) -> None:
        """Verify /api/route returns full 2D/3D metrics, maneuvers, and GeoJSON for dashboard."""
        status, envelope = self._http_post(
            "/api/route",
            {
                "origin": "N_0_0",
                "destination": "N_3_3",
                "apparatus_type": "AMBULANCE_ALS",
                "elevation_aware": True,
            },
        )
        self.assertEqual(status, 200)
        result = envelope.get("data", envelope)
        self.assertTrue(result["path_found"])
        self.assertIn("duration_seconds", result)
        self.assertIn("distance_2d_meters", result)
        self.assertIn("distance_3d_meters", result)
        self.assertIn("elevation_gain_meters", result)
        self.assertIn("max_grade_percent", result)
        self.assertIn("maneuvers", result)
        self.assertIn("geojson", result)
        self.assertEqual(result["geojson"].get("type"), "FeatureCollection")
        features = result["geojson"].get("features", [])
        self.assertTrue(any(f.get("geometry", {}).get("type") == "LineString" for f in features))

    def test_api_disaster_injection_and_reset_workflow(self) -> None:
        """Verify hazard injection immediately affects network edge status and can be reset."""
        # 1. Reset baseline
        status, _ = self._http_post("/api/hazards/reset", {})
        self.assertEqual(status, 200)

        # 2. Inject river flood polygon
        flood_polygon = [
            [-122.332, 47.595],
            [-122.327, 47.595],
            [-122.327, 47.615],
            [-122.332, 47.615],
        ]
        status, hazard_env = self._http_post(
            "/api/hazards",
            {
                "polygon_coords": flood_polygon,
                "hazard_type": "RIVER_FLOOD",
                "speed_multiplier": 0.0,
                "severity": 1.0,
            },
        )
        self.assertEqual(status, 201)
        hazard_res = hazard_env.get("data", hazard_env)
        self.assertGreater(hazard_res["edges_closed"], 0)
        self.assertGreaterEqual(hazard_res["total_active_hazards"], 1)

        # 3. Check health reflects active hazards and severed edges
        status, _, raw = self._http_get("/api/health")
        self.assertEqual(status, 200)
        health_env = json.loads(raw.decode("utf-8"))
        health = health_env.get("data", health_env)
        self.assertGreaterEqual(health["active_hazards"], 1)
        self.assertGreater(health["severed_edges"], 0)

        # 4. Check network GeoJSON reflects severed edges
        status, _, raw = self._http_get("/api/network")
        self.assertEqual(status, 200)
        network_env = json.loads(raw.decode("utf-8"))
        network = network_env.get("data", network_env)
        severed_count = sum(1 for f in network["features"] if f["properties"].get("is_severed"))
        self.assertGreater(severed_count, 0)

        # 5. Reset all hazards
        status, reset_env = self._http_post("/api/hazards/reset", {})
        self.assertEqual(status, 200)
        reset_res = reset_env.get("data", reset_env)
        self.assertGreaterEqual(reset_res["cleared_count"], 1)

        # 6. Verify health cleared
        status, _, raw = self._http_get("/api/health")
        health_env = json.loads(raw.decode("utf-8"))
        health = health_env.get("data", health_env)
        self.assertEqual(health["active_hazards"], 0)
        self.assertEqual(health["severed_edges"], 0)


if __name__ == "__main__":
    unittest.main()
