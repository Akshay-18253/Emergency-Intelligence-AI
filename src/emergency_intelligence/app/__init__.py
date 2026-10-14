"""
Emergency Intelligence AI — Web Application & API Gateway.
==========================================================
Zero-dependency embedded HTTP server hosting REST endpoints, Server-Sent Events,
and tactical operations center UI.
"""

from __future__ import annotations

from emergency_intelligence.app.handlers import EmergencyRequestHandler
from emergency_intelligence.app.schemas import ValidationError
from emergency_intelligence.app.server import EmergencyAppServer, create_app
from emergency_intelligence.app.state import AppState

__all__ = [
    "AppState",
    "EmergencyAppServer",
    "EmergencyRequestHandler",
    "ValidationError",
    "create_app",
]
