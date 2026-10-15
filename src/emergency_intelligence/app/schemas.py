"""
Request and response schemas and payload validators for the Emergency Intelligence AI web app.
=============================================================================================
Provides input validation, coordinate bounding checks, and standardized JSON envelopes
under strict zero external runtime dependencies.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple

from emergency_intelligence.events.incidents import ApparatusType, UrgencyLevel
from emergency_intelligence.data.osm import WeightingProfile


class ValidationError(Exception):
    """Raised when an incoming request payload fails structural or semantic validation."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        self.field = field


def format_json_response(
    data: Any = None,
    success: bool = True,
    error: Optional[str] = None,
    error_code: Optional[str] = None,
) -> bytes:
    """Format a standard JSON response envelope as UTF-8 encoded bytes.

    Parameters
    ----------
    data : Any, optional
        Payload data if successful.
    success : bool
        True if the request was processed successfully.
    error : str, optional
        Human-readable error explanation if unsuccessful.
    error_code : str, optional
        Machine-readable error identifier (e.g. 'INVALID_COORDINATES').

    Returns
    -------
    bytes
        UTF-8 encoded JSON bytes.
    """
    payload: Dict[str, Any] = {
        "success": success,
    }
    if success:
        payload["data"] = data
    else:
        payload["error"] = {
            "message": error or "An unexpected error occurred.",
            "code": error_code or "INTERNAL_ERROR",
        }

    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


def parse_json_body(raw_bytes: bytes, max_bytes: int = 1_048_576) -> Dict[str, Any]:
    """Safely decode and parse a raw HTTP request body into a JSON dictionary.

    Parameters
    ----------
    raw_bytes : bytes
        Raw HTTP body received.
    max_bytes : int
        Maximum permitted payload size (defaults to 1 MB).

    Returns
    -------
    Dict[str, Any]
        Parsed JSON dictionary.

    Raises
    ------
    ValidationError
        If payload exceeds size bounds, is not UTF-8, or is not a JSON object.
    """
    if len(raw_bytes) > max_bytes:
        raise ValidationError(
            f"Payload length ({len(raw_bytes)} bytes) exceeds limit of {max_bytes} bytes.",
            field="body",
        )

    if not raw_bytes:
        return {}

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"Request body is not valid UTF-8: {exc}", field="body") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Malformed JSON payload: {exc.msg} at line {exc.lineno}", field="body") from exc

    if not isinstance(data, dict):
        raise ValidationError("JSON body must be a root object/dictionary.", field="body")

    return data


def validate_coordinates(coords: Any, field_name: str = "coordinates") -> Tuple[float, float]:
    """Validate latitude and longitude tuple/list [lat, lon].

    Parameters
    ----------
    coords : Any
        Input list or tuple of 2 numbers.
    field_name : str
        Name of field for error reporting.

    Returns
    -------
    Tuple[float, float]
        Validated (lat, lon) tuple.
    """
    if not isinstance(coords, (list, tuple)) or len(coords) != 2:
        raise ValidationError(
            f"'{field_name}' must be a sequence of 2 numeric coordinates [latitude, longitude].",
            field=field_name,
        )

    try:
        lat = float(coords[0])
        lon = float(coords[1])
    except (ValueError, TypeError) as exc:
        raise ValidationError(
            f"'{field_name}' elements must be floating-point numbers.",
            field=field_name,
        ) from exc

    if not (-90.0 <= lat <= 90.0):
        raise ValidationError(
            f"Latitude {lat} in '{field_name}' is out of bounds [-90.0, 90.0].",
            field=field_name,
        )

    if not (-180.0 <= lon <= 180.0):
        raise ValidationError(
            f"Longitude {lon} in '{field_name}' is out of bounds [-180.0, 180.0].",
            field=field_name,
        )

    return lat, lon


def validate_route_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate parameters for the /api/route endpoint.

    Expected keys:
      - origin: node_id (str) OR [lat, lon]
      - destination: node_id (str) OR [lat, lon]
      - apparatus_type: optional str (e.g. 'ambulance_als', 'ladder_truck')
      - profile: optional str ('distance', 'travel_time', 'emergency_time')
      - elevation_aware: optional bool (defaults to False)
    """
    if "origin" not in data:
        raise ValidationError("Missing required field 'origin'.", field="origin")
    if "destination" not in data:
        raise ValidationError("Missing required field 'destination'.", field="destination")

    origin = data["origin"]
    destination = data["destination"]

    # Validate origin format
    if isinstance(origin, (list, tuple)):
        origin_val: Any = validate_coordinates(origin, "origin")
    elif isinstance(origin, str) and origin.strip():
        origin_val = origin.strip()
    else:
        raise ValidationError(
            "'origin' must be a node ID string or a [lat, lon] coordinate array.",
            field="origin",
        )

    # Validate destination format
    if isinstance(destination, (list, tuple)):
        destination_val: Any = validate_coordinates(destination, "destination")
    elif isinstance(destination, str) and destination.strip():
        destination_val = destination.strip()
    else:
        raise ValidationError(
            "'destination' must be a node ID string or a [lat, lon] coordinate array.",
            field="destination",
        )

    # Apparatus type
    app_str = data.get("apparatus_type", "ambulance_als")
    try:
        apparatus = ApparatusType(str(app_str).lower())
    except ValueError:
        valid_apps = [a.value for a in ApparatusType]
        raise ValidationError(
            f"Invalid 'apparatus_type': '{app_str}'. Must be one of: {valid_apps}",
            field="apparatus_type",
        )

    # Profile
    prof_str = str(data.get("profile", WeightingProfile.EMERGENCY_TIME)).lower()
    if prof_str not in WeightingProfile.VALID_PROFILES:
        valid_profs = sorted(list(WeightingProfile.VALID_PROFILES))
        raise ValidationError(
            f"Invalid 'profile': '{prof_str}'. Must be one of: {valid_profs}",
            field="profile",
        )
    profile = prof_str

    elevation_aware = bool(data.get("elevation_aware", False))

    return {
        "origin": origin_val,
        "destination": destination_val,
        "apparatus_type": apparatus,
        "profile": profile,
        "elevation_aware": elevation_aware,
    }


def validate_intake_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate parameters for the /api/intake endpoint.

    Expected keys:
      - raw_text: unstructured 911 caller description (str, 1-2048 chars)
      - caller_phone: optional phone number (str)
      - location_hint: optional string address or [lat, lon]
    """
    raw_text = data.get("raw_text")
    if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
        raise ValidationError(
            "Missing or empty required field 'raw_text'.",
            field="raw_text",
        )

    if len(raw_text) > 2048:
        raise ValidationError(
            f"'raw_text' length ({len(raw_text)}) exceeds limit of 2,048 characters.",
            field="raw_text",
        )

    caller_phone = str(data.get("caller_phone", "")).strip() or None
    location_hint = data.get("location_hint")

    validated_coords: Optional[Tuple[float, float]] = None
    if isinstance(location_hint, (list, tuple)):
        validated_coords = validate_coordinates(location_hint, "location_hint")

    return {
        "raw_text": raw_text.strip(),
        "caller_phone": caller_phone,
        "location_hint": location_hint,
        "location_coords": validated_coords,
    }


def validate_hazard_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate parameters for dynamic hazard injection via /api/hazards.

    Expected keys:
      - polygon_coords: sequence of at least 3 [lon, lat] or [lat, lon] pairs
      - hazard_type: optional str (e.g. 'flood', 'fire', 'debris')
      - speed_multiplier: float in [0.0, 1.0] (0.0 = full road closure)
      - severity: optional str ('CRITICAL', 'HIGH', 'MODERATE', 'LOW')
    """
    polygon_raw = data.get("polygon_coords")
    if not isinstance(polygon_raw, (list, tuple)) or len(polygon_raw) < 3:
        raise ValidationError(
            "'polygon_coords' must be a sequence of at least 3 coordinate points forming a 2D boundary.",
            field="polygon_coords",
        )

    cleaned_coords: List[Tuple[float, float]] = []
    for idx, pt in enumerate(polygon_raw):
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            raise ValidationError(
                f"Point at index {idx} in 'polygon_coords' must be a [lon, lat] coordinate pair.",
                field="polygon_coords",
            )
        try:
            x, y = float(pt[0]), float(pt[1])
        except (ValueError, TypeError) as exc:
            raise ValidationError(
                f"Point at index {idx} has non-numeric coordinates.",
                field="polygon_coords",
            ) from exc
        cleaned_coords.append((x, y))

    # Speed multiplier
    speed_mult = data.get("speed_multiplier", 0.0)
    try:
        speed_mult = float(speed_mult)
    except (ValueError, TypeError) as exc:
        raise ValidationError("'speed_multiplier' must be a float between 0.0 and 1.0.", field="speed_multiplier") from exc

    if not (0.0 <= speed_mult <= 1.0):
        raise ValidationError(
            f"'speed_multiplier' ({speed_mult}) must be within [0.0, 1.0].",
            field="speed_multiplier",
        )

    hazard_type = str(data.get("hazard_type", "disaster_zone")).strip()
    severity_str = str(data.get("severity", "CRITICAL")).upper()

    return {
        "polygon_coords": cleaned_coords,
        "speed_multiplier": speed_mult,
        "hazard_type": hazard_type,
        "severity": severity_str,
    }


SUPPORTED_SCENARIOS = {"metropolitan_disaster", "seattle_earthquake", "waterfront_flood"}


def validate_simulation_start_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate parameters for POST /api/simulation/start.

    Expected keys:
      - scenario_id: optional str (default 'metropolitan_disaster')
      - max_duration_seconds: optional positive float (default 3600.0)
    """
    scenario_id = str(data.get("scenario_id", "metropolitan_disaster")).strip() or "metropolitan_disaster"
    if scenario_id not in SUPPORTED_SCENARIOS:
        raise ValidationError(
            f"Scenario '{scenario_id}' is not supported. Supported scenarios: {sorted(SUPPORTED_SCENARIOS)}.",
            field="scenario_id",
        )

    max_duration = data.get("max_duration_seconds", 3600.0)
    try:
        max_duration = float(max_duration)
    except (ValueError, TypeError) as exc:
        raise ValidationError("'max_duration_seconds' must be a numeric value.", field="max_duration_seconds") from exc

    if max_duration <= 0.0:
        raise ValidationError("'max_duration_seconds' must be greater than 0.", field="max_duration_seconds")

    return {
        "scenario_id": scenario_id,
        "max_duration_seconds": max_duration,
    }


def validate_simulation_step_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate parameters for POST /api/simulation/step.

    Expected keys:
      - step_seconds: optional positive float (default 5.0, max 300.0)
      - target_time: optional non-negative float
    """
    step_seconds = data.get("step_seconds", 5.0)
    try:
        step_seconds = float(step_seconds)
    except (ValueError, TypeError) as exc:
        raise ValidationError("'step_seconds' must be a numeric value.", field="step_seconds") from exc

    if step_seconds <= 0.0 or step_seconds > 300.0:
        raise ValidationError(
            f"'step_seconds' ({step_seconds}) must be between 0.1 and 300.0 seconds.",
            field="step_seconds",
        )

    target_time = data.get("target_time")
    validated_target: Optional[float] = None
    if target_time is not None:
        try:
            validated_target = float(target_time)
        except (ValueError, TypeError) as exc:
            raise ValidationError("'target_time' must be a numeric value.", field="target_time") from exc
        if validated_target < 0.0:
            raise ValidationError("'target_time' must be non-negative.", field="target_time")

    return {
        "step_seconds": step_seconds,
        "target_time": validated_target,
    }

