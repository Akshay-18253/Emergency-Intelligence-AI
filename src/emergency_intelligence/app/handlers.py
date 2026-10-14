"""
HTTP request dispatcher and API route handlers for Emergency Intelligence AI.
=============================================================================
Implements REST routing, Server-Sent Events (SSE) streaming, path-traversal guarded
static file serving, and CORS preflight headers using standard library BaseHTTPRequestHandler.
"""

from __future__ import annotations

import mimetypes
import os
import queue
import re
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from emergency_intelligence.app.schemas import (
    ValidationError,
    format_json_response,
    parse_json_body,
    validate_hazard_request,
    validate_intake_request,
    validate_route_request,
)
from emergency_intelligence.app.state import AppState


class EmergencyRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler dispatching REST calls, SSE streams, and static files."""

    server_version = "EmergencyIntelligenceAI/0.2.0"
    static_directory: Path = Path(__file__).resolve().parent / "static"

    @property
    def app_state(self) -> AppState:
        """Retrieve AppState reference from the parent server instance."""
        state = getattr(self.server, "state", None)
        if state is None:
            raise RuntimeError("AppState not initialized on server.")
        return state

    def log_message(self, format_str: str, *args: Any) -> None:
        """Suppress default stdout access logging unless specifically enabled."""
        if getattr(self.server, "enable_logging", False):
            super().log_message(format_str, *args)

    # -------------------------------------------------------------------------
    # Response Sending Helpers
    # -------------------------------------------------------------------------

    def send_cors_headers(self) -> None:
        """Send standard Cross-Origin Resource Sharing (CORS) and security headers."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, Accept")
        self.send_header("X-Content-Type-Options", "nosniff")

    def reply_json(
        self,
        status_code: int,
        data: Any = None,
        success: bool = True,
        error: Optional[str] = None,
        error_code: Optional[str] = None,
    ) -> None:
        """Send a standardized JSON response envelope."""
        body = format_json_response(data=data, success=success, error=error, error_code=error_code)
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def read_request_body(self) -> bytes:
        """Read request body bytes based on Content-Length header."""
        length_header = self.headers.get("Content-Length", "0")
        try:
            length = int(length_header)
        except ValueError:
            length = 0
        if length <= 0:
            return b""
        return self.rfile.read(length)

    # -------------------------------------------------------------------------
    # HTTP Method Handlers
    # -------------------------------------------------------------------------

    def do_OPTIONS(self) -> None:
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        """Dispatch HTTP GET requests."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == "/api/health":
            self._handle_get_health()
        elif path == "/api/network":
            self._handle_get_network()
        elif path == "/api/facilities":
            self._handle_get_facilities()
        elif path == "/api/simulation/stream":
            self._handle_sse_stream()
        elif path.startswith("/api/"):
            self.reply_json(404, success=False, error=f"Endpoint GET '{path}' not found.", error_code="NOT_FOUND")
        else:
            self._handle_static_file(path)

    def do_POST(self) -> None:
        """Dispatch HTTP POST requests."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        try:
            raw_body = self.read_request_body()
            body_json = parse_json_body(raw_body)
        except ValidationError as exc:
            self.reply_json(400, success=False, error=exc.message, error_code="INVALID_PAYLOAD")
            return

        try:
            if path == "/api/route":
                self._handle_post_route(body_json)
            elif path == "/api/intake":
                self._handle_post_intake(body_json)
            elif path == "/api/hazards":
                self._handle_post_hazards(body_json)
            elif path == "/api/hazards/reset":
                self._handle_post_hazards_reset()
            else:
                self.reply_json(404, success=False, error=f"Endpoint POST '{path}' not found.", error_code="NOT_FOUND")
        except ValidationError as exc:
            self.reply_json(400, success=False, error=exc.message, error_code="VALIDATION_ERROR")
        except Exception as exc:
            self.reply_json(500, success=False, error=str(exc), error_code="INTERNAL_SERVER_ERROR")

    def do_DELETE(self) -> None:
        """Dispatch HTTP DELETE requests."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        match = re.match(r"^/api/hazards/([^/]+)$", path)
        if match:
            hazard_id = match.group(1)
            cleared = self.app_state.clear_hazard(hazard_id)
            if cleared:
                self.reply_json(200, success=True, data={"hazard_id": hazard_id, "status": "cleared"})
            else:
                self.reply_json(404, success=False, error=f"Hazard ID '{hazard_id}' not found.", error_code="NOT_FOUND")
        else:
            self.reply_json(404, success=False, error=f"Endpoint DELETE '{path}' not found.", error_code="NOT_FOUND")

    # -------------------------------------------------------------------------
    # Route Execution Handlers
    # -------------------------------------------------------------------------

    def _handle_get_health(self) -> None:
        """GET /api/health -> Return system health metrics."""
        status = self.app_state.get_health_status()
        self.reply_json(200, data=status)

    def _handle_get_network(self) -> None:
        """GET /api/network -> Return road network GeoJSON."""
        geojson_data = self.app_state.get_network_geojson()
        self.reply_json(200, data=geojson_data)

    def _handle_get_facilities(self) -> None:
        """GET /api/facilities -> Return hospital and station amenities."""
        facilities = self.app_state.get_facilities_data()
        self.reply_json(200, data=facilities)

    def _handle_post_route(self, body: Dict[str, Any]) -> None:
        """POST /api/route -> Compute multi-criteria emergency route."""
        validated = validate_route_request(body)
        result = self.app_state.compute_route(
            origin=validated["origin"],
            destination=validated["destination"],
            apparatus_type=validated["apparatus_type"],
            profile=validated["profile"],
            elevation_aware=validated["elevation_aware"],
        )
        if result.get("path_found"):
            self.reply_json(200, data=result)
        else:
            self.reply_json(200, success=True, data=result)

    def _handle_post_intake(self, body: Dict[str, Any]) -> None:
        """POST /api/intake -> Process natural language 911 report."""
        validated = validate_intake_request(body)
        result = self.app_state.process_911_intake(
            raw_text=validated["raw_text"],
            caller_phone=validated["caller_phone"],
            location_coords=validated["location_coords"],
        )
        self.reply_json(200, data=result)

    def _handle_post_hazards(self, body: Dict[str, Any]) -> None:
        """POST /api/hazards -> Inject a 2D hazard polygon."""
        validated = validate_hazard_request(body)
        result = self.app_state.inject_hazard_polygon(
            polygon_coords=validated["polygon_coords"],
            hazard_type=validated["hazard_type"],
            speed_multiplier=validated["speed_multiplier"],
            severity=validated["severity"],
        )
        self.reply_json(201, data=result)

    def _handle_post_hazards_reset(self) -> None:
        """POST /api/hazards/reset -> Clear all active dynamic mutations."""
        cleared_count = self.app_state.reset_all_hazards()
        self.reply_json(200, data={"cleared_count": cleared_count, "status": "reset_successful"})

    # -------------------------------------------------------------------------
    # Server-Sent Events (SSE) Stream
    # -------------------------------------------------------------------------

    def _handle_sse_stream(self) -> None:
        """GET /api/simulation/stream -> Push live event frames."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_cors_headers()
        self.end_headers()

        client_queue = self.app_state.register_sse_client()

        # Send initial connected greeting
        initial_frame = "event: connected\ndata: {\"status\": \"stream_established\"}\n\n"
        try:
            self.wfile.write(initial_frame.encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            self.app_state.unregister_sse_client(client_queue)
            return

        try:
            while True:
                try:
                    # Wait up to 5 seconds for an event; if timeout, send a keep-alive comment
                    frame = client_queue.get(timeout=5.0)
                    self.wfile.write(frame.encode("utf-8"))
                    self.wfile.flush()
                except queue.Empty:
                    # Keep-alive comment
                    ping_frame = ": ping\n\n"
                    self.wfile.write(ping_frame.encode("utf-8"))
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.app_state.unregister_sse_client(client_queue)

    # -------------------------------------------------------------------------
    # Static File Server
    # -------------------------------------------------------------------------

    def _handle_static_file(self, path: str) -> None:
        """Serve static files with directory traversal security and SPA fallback."""
        if path in ("", "/"):
            req_file = "index.html"
        else:
            req_file = path.lstrip("/")

        # Guard against path traversal
        try:
            target_path = (self.static_directory / req_file).resolve()
            static_root = self.static_directory.resolve()
            target_path.relative_to(static_root)
        except (ValueError, RuntimeError):
            self.reply_json(403, success=False, error="Forbidden: Path traversal detected.", error_code="FORBIDDEN")
            return

        # Fallback to index.html if file doesn't exist (SPA client-side routing)
        if not target_path.is_file():
            fallback_path = static_root / "index.html"
            if fallback_path.is_file():
                target_path = fallback_path
            else:
                self.reply_json(404, success=False, error=f"File '{req_file}' not found.", error_code="NOT_FOUND")
                return

        # Determine MIME type
        content_type, _ = mimetypes.guess_type(str(target_path))
        if content_type is None:
            content_type = "application/octet-stream"

        try:
            with open(target_path, "rb") as f:
                content = f.read()

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(content)
        except OSError as exc:
            self.reply_json(500, success=False, error=f"Error reading file: {exc}", error_code="IO_ERROR")
