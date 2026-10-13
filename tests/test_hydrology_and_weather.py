"""
Unit tests for Real-Time Hydrology & Weather Feeds (USGS & Open-Meteo).
======================================================================
Tests USGS NWIS REST query URL generation, JSON time-series parsing,
flood stage classification against NWS thresholds, Open-Meteo weather
observation parsing, WMO code interpretation, dynamic flood/weather
hazard polygon synthesis, and dynamic graph rerouting around inundations.

Strict zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import pytest

from emergency_intelligence.events.hazards import (
    HazardPolygon,
    HazardSeverity,
    HazardType,
)
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.external.hydrology import (
    DEFAULT_GAUGE_THRESHOLDS,
    EnvironmentalMutationSummary,
    FloodStage,
    USGSGaugeReading,
    USGSGaugeThresholds,
    WeatherAlertLevel,
    WeatherConditions,
    apply_environmental_hazards_to_graph,
    build_usgs_water_query_url,
    classify_wmo_weather_code,
    create_flood_inundation_polygon,
    create_weather_hazard_polygon,
    parse_open_meteo_response,
    parse_usgs_water_response,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.models import Edge, Graph, Node


# ===========================================================================
# 1. Enums and Threshold Classification Tests
# ===========================================================================


def test_flood_stage_enums() -> None:
    """Verify FloodStage enum values and string behaviors."""
    assert FloodStage.NORMAL.value == "normal"
    assert FloodStage.ACTION.value == "action"
    assert FloodStage.MINOR.value == "minor"
    assert FloodStage.MODERATE.value == "moderate"
    assert FloodStage.MAJOR.value == "major"


def test_weather_alert_level_enums() -> None:
    """Verify WeatherAlertLevel enum values."""
    assert WeatherAlertLevel.NONE.value == "none"
    assert WeatherAlertLevel.ADVISORY.value == "advisory"
    assert WeatherAlertLevel.WATCH.value == "watch"
    assert WeatherAlertLevel.WARNING.value == "warning"


def test_usgs_gauge_thresholds_classification() -> None:
    """Verify NWS flood stage classification tiers."""
    thresholds = USGSGaugeThresholds(
        action_stage_ft=12.0,
        minor_stage_ft=15.0,
        moderate_stage_ft=18.0,
        major_stage_ft=22.0,
    )

    assert thresholds.classify_stage(10.0) == FloodStage.NORMAL
    assert thresholds.classify_stage(11.9) == FloodStage.NORMAL
    assert thresholds.classify_stage(12.0) == FloodStage.ACTION
    assert thresholds.classify_stage(14.5) == FloodStage.ACTION
    assert thresholds.classify_stage(15.0) == FloodStage.MINOR
    assert thresholds.classify_stage(17.8) == FloodStage.MINOR
    assert thresholds.classify_stage(18.0) == FloodStage.MODERATE
    assert thresholds.classify_stage(21.9) == FloodStage.MODERATE
    assert thresholds.classify_stage(22.0) == FloodStage.MAJOR
    assert thresholds.classify_stage(30.0) == FloodStage.MAJOR


# ===========================================================================
# 2. USGS Gauge Reading Validation & Properties
# ===========================================================================


def test_usgs_gauge_reading_properties() -> None:
    """Verify gauge reading metric conversion and flooding detection."""
    reading = USGSGaugeReading(
        site_id="12119000",
        site_name="Cedar River at Renton, WA",
        latitude=47.478,
        longitude=-122.204,
        timestamp=datetime.now(timezone.utc),
        gage_height_ft=15.0,
        streamflow_cfs=3200.0,
        flood_stage=FloodStage.MINOR,
    )

    assert abs(reading.gage_height_m - (15.0 * 0.3048)) < 1e-4
    assert reading.is_flooding() is True

    normal_reading = USGSGaugeReading(
        site_id="12119000",
        site_name="Cedar River at Renton, WA",
        latitude=47.478,
        longitude=-122.204,
        timestamp=datetime.now(timezone.utc),
        gage_height_ft=8.0,
        flood_stage=FloodStage.NORMAL,
    )
    assert normal_reading.is_flooding() is False


def test_usgs_gauge_reading_invalid_coordinates() -> None:
    """Verify validation triggers on non-finite or out-of-range coordinates."""
    now = datetime.now(timezone.utc)

    with pytest.raises(ValueError, match="finite floats"):
        USGSGaugeReading(
            site_id="123",
            site_name="Test",
            latitude=float("nan"),
            longitude=-122.0,
            timestamp=now,
            gage_height_ft=5.0,
        )

    with pytest.raises(ValueError, match="out of geographic range"):
        USGSGaugeReading(
            site_id="123",
            site_name="Test",
            latitude=95.0,
            longitude=-122.0,
            timestamp=now,
            gage_height_ft=5.0,
        )

    with pytest.raises(ValueError, match="Gage height must be a finite float"):
        USGSGaugeReading(
            site_id="123",
            site_name="Test",
            latitude=47.0,
            longitude=-122.0,
            timestamp=now,
            gage_height_ft=float("inf"),
        )


def test_weather_conditions_validation() -> None:
    """Verify WeatherConditions validates finite coordinates."""
    with pytest.raises(ValueError, match="finite floats"):
        WeatherConditions(
            latitude=float("inf"),
            longitude=-122.0,
            timestamp=datetime.now(timezone.utc),
            weather_code=0,
            temperature_c=20.0,
            wind_speed_kmh=10.0,
            precipitation_mm=0.0,
        )


# ===========================================================================
# 3. USGS URL Construction & Response Parsing
# ===========================================================================


def test_build_usgs_water_query_url() -> None:
    """Verify USGS NWIS REST query URL parameters."""
    url = build_usgs_water_query_url(
        site_ids=["12119000", " 12113000 "],
        parameters=["00065", "00060"],
    )

    assert "https://waterservices.usgs.gov/nwis/iv/" in url
    assert "format=json" in url
    assert "sites=12119000%2C12113000" in url
    assert "parameterCd=00065%2C00060" in url
    assert "siteStatus=all" in url


def test_parse_usgs_water_response_valid() -> None:
    """Verify parsing a standard multi-station USGS JSON payload."""
    payload = {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {
                        "siteName": "SNOQUALMIE RIVER NEAR SNOQUALMIE, WA",
                        "siteCode": [{"value": "12144500"}],
                        "geoLocation": {
                            "geogLocation": {
                                "latitude": 47.532,
                                "longitude": -121.842,
                            }
                        },
                    },
                    "variable": {
                        "variableCode": [{"value": "00065"}],
                    },
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "18.5",
                                    "dateTime": "2026-10-13T10:00:00.000-07:00",
                                }
                            ]
                        }
                    ],
                },
                {
                    "sourceInfo": {
                        "siteName": "SNOQUALMIE RIVER NEAR SNOQUALMIE, WA",
                        "siteCode": [{"value": "12144500"}],
                        "geoLocation": {
                            "geogLocation": {
                                "latitude": 47.532,
                                "longitude": -121.842,
                            }
                        },
                    },
                    "variable": {
                        "variableCode": [{"value": "00060"}],
                    },
                    "values": [
                        {
                            "value": [
                                {
                                    "value": "24500.0",
                                    "dateTime": "2026-10-13T10:00:00.000-07:00",
                                }
                            ]
                        }
                    ],
                },
            ]
        }
    }

    custom_thresh = {
        "12144500": USGSGaugeThresholds(
            action_stage_ft=12.0,
            minor_stage_ft=15.0,
            moderate_stage_ft=18.0,
            major_stage_ft=21.0,
        )
    }

    readings = parse_usgs_water_response(payload, custom_thresholds=custom_thresh)
    assert len(readings) == 1
    gauge = readings[0]
    assert gauge.site_id == "12144500"
    assert "SNOQUALMIE" in gauge.site_name
    assert gauge.latitude == 47.532
    assert gauge.longitude == -121.842
    assert gauge.gage_height_ft == 18.5
    assert gauge.streamflow_cfs == 24500.0
    assert gauge.flood_stage == FloodStage.MODERATE
    assert gauge.is_flooding() is True


def test_parse_usgs_water_response_edge_cases() -> None:
    """Verify parser robustness against empty, malformed, or missing data."""
    # Empty payload
    assert parse_usgs_water_response({}) == []
    assert parse_usgs_water_response({"value": {"timeSeries": "not-a-list"}}) == []

    # Missing site code
    payload_no_site = {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {"siteCode": []},
                    "variable": {"variableCode": [{"value": "00065"}]},
                    "values": [{"value": [{"value": "12.0"}]}],
                }
            ]
        }
    }
    assert parse_usgs_water_response(payload_no_site) == []

    # Invalid latitude/longitude format
    payload_bad_geo = {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {
                        "siteCode": [{"value": "123"}],
                        "geoLocation": {"geogLocation": {"latitude": "invalid"}},
                    },
                    "variable": {"variableCode": [{"value": "00065"}]},
                    "values": [{"value": [{"value": "12.0"}]}],
                }
            ]
        }
    }
    assert parse_usgs_water_response(payload_bad_geo) == []

    # Non-numeric gage reading
    payload_bad_val = {
        "value": {
            "timeSeries": [
                {
                    "sourceInfo": {
                        "siteCode": [{"value": "123"}],
                        "geoLocation": {"geogLocation": {"latitude": 47.0, "longitude": -122.0}},
                    },
                    "variable": {"variableCode": [{"value": "00065"}]},
                    "values": [{"value": [{"value": "IceAffected", "dateTime": "not-a-date"}]}],
                }
            ]
        }
    }
    assert parse_usgs_water_response(payload_bad_val) == []


# ===========================================================================
# 4. Open-Meteo Weather Parsing & WMO Classification
# ===========================================================================


def test_classify_wmo_weather_code() -> None:
    """Verify standard WMO weather translation and alert levels."""
    desc, alert = classify_wmo_weather_code(95)
    assert "Thunderstorm" in desc
    assert alert == WeatherAlertLevel.WARNING

    desc, alert = classify_wmo_weather_code(75)
    assert "Blizzard" in desc
    assert alert == WeatherAlertLevel.WARNING

    desc, alert = classify_wmo_weather_code(71)
    assert "Snowfall" in desc
    assert alert == WeatherAlertLevel.WATCH

    desc, alert = classify_wmo_weather_code(65)
    assert "Torrential Rain" in desc
    assert alert == WeatherAlertLevel.WATCH

    desc, alert = classify_wmo_weather_code(61)
    assert "Moderate Rain" in desc
    assert alert == WeatherAlertLevel.ADVISORY

    desc, alert = classify_wmo_weather_code(45)
    assert "Dense Fog" in desc
    assert alert == WeatherAlertLevel.ADVISORY

    desc, alert = classify_wmo_weather_code(0)
    assert alert == WeatherAlertLevel.NONE


def test_parse_open_meteo_response_normal() -> None:
    """Verify parsing normal weather conditions."""
    payload = {
        "latitude": 47.606,
        "longitude": -122.332,
        "current": {
            "time": "2026-10-13T10:30",
            "weather_code": 3,
            "temperature_2m": 16.5,
            "wind_speed_10m": 12.0,
            "precipitation": 0.0,
        },
    }
    weather = parse_open_meteo_response(payload)
    assert weather.latitude == 47.606
    assert weather.longitude == -122.332
    assert weather.temperature_c == 16.5
    assert weather.wind_speed_kmh == 12.0
    assert weather.alert_level == WeatherAlertLevel.NONE


def test_parse_open_meteo_response_wind_and_rain_overrides() -> None:
    """Verify wind and torrential rain alert upgrades."""
    # High wind warning (>= 75 km/h)
    high_wind_payload = {
        "latitude": 47.606,
        "longitude": -122.332,
        "current": {
            "time": "invalid_date_format",
            "weather_code": 0,
            "temperature_2m": 14.0,
            "wind_speed_10m": 82.5,
            "precipitation": 2.0,
        },
    }
    w_wind = parse_open_meteo_response(high_wind_payload)
    assert w_wind.alert_level == WeatherAlertLevel.WARNING
    assert "Dangerous High Winds" in w_wind.summary

    # Brisk gusts advisory (50 - 74 km/h)
    gusts_payload = {
        "latitude": 47.606,
        "longitude": -122.332,
        "current": {
            "time": "2026-10-13T10:30",
            "weather_code": 0,
            "temperature_2m": 14.0,
            "wind_speed_10m": 58.0,
            "precipitation": 0.0,
        },
    }
    w_gusts = parse_open_meteo_response(gusts_payload)
    assert w_gusts.alert_level == WeatherAlertLevel.ADVISORY
    assert "Brisk Gusts" in w_gusts.summary

    # Extreme precipitation override (>= 25 mm)
    rain_payload = {
        "latitude": 47.606,
        "longitude": -122.332,
        "current": {
            "time": "2026-10-13T10:30",
            "weather_code": 61,
            "temperature_2m": 12.0,
            "wind_speed_10m": 15.0,
            "precipitation": 32.0,
        },
    }
    w_rain = parse_open_meteo_response(rain_payload)
    assert w_rain.alert_level == WeatherAlertLevel.WARNING
    assert "Extreme Precipitation" in w_rain.summary


# ===========================================================================
# 5. Dynamic Hazard Polygon Generation
# ===========================================================================


def test_create_flood_inundation_polygon_stages() -> None:
    """Verify flood inundation polygon buffering for various flood stages."""
    now = datetime.now(timezone.utc)

    # Major flood -> 1000m buffer, CRITICAL_BLOCKED severity
    major_gauge = USGSGaugeReading(
        site_id="12144500",
        site_name="Snoqualmie River",
        latitude=47.532,
        longitude=-121.842,
        timestamp=now,
        gage_height_ft=22.0,
        flood_stage=FloodStage.MAJOR,
    )
    poly_major = create_flood_inundation_polygon(major_gauge)
    assert poly_major.severity == HazardSeverity.CRITICAL_BLOCKED
    assert poly_major.speed_multiplier == 0.0
    assert len(poly_major.boundary_coordinates) == 12  # Normalized unrepeated vertex ring

    # Moderate flood -> 500m buffer, SEVERE severity
    mod_gauge = USGSGaugeReading(
        site_id="12144500",
        site_name="Snoqualmie River",
        latitude=47.532,
        longitude=-121.842,
        timestamp=now,
        gage_height_ft=18.0,
        flood_stage=FloodStage.MODERATE,
    )
    poly_mod = create_flood_inundation_polygon(mod_gauge)
    assert poly_mod.severity == HazardSeverity.SEVERE
    assert poly_mod.speed_multiplier == 0.20

    # Minor flood -> 250m buffer, MODERATE severity
    minor_gauge = USGSGaugeReading(
        site_id="12144500",
        site_name="Snoqualmie River",
        latitude=47.532,
        longitude=-121.842,
        timestamp=now,
        gage_height_ft=15.0,
        flood_stage=FloodStage.MINOR,
    )
    poly_minor = create_flood_inundation_polygon(minor_gauge)
    assert poly_minor.severity == HazardSeverity.MODERATE
    assert poly_minor.speed_multiplier == 0.50

    # Normal stage -> 100m buffer, LOW severity
    normal_gauge = USGSGaugeReading(
        site_id="12144500",
        site_name="Snoqualmie River",
        latitude=47.532,
        longitude=-121.842,
        timestamp=now,
        gage_height_ft=8.0,
        flood_stage=FloodStage.NORMAL,
    )
    poly_normal = create_flood_inundation_polygon(normal_gauge)
    assert poly_normal.severity == HazardSeverity.LOW
    assert poly_normal.speed_multiplier == 0.75

    # Custom buffer radius override
    poly_custom = create_flood_inundation_polygon(minor_gauge, buffer_radius_m=750.0)
    assert poly_custom.speed_multiplier == 0.25


def test_create_weather_hazard_polygon() -> None:
    """Verify weather hazard polygon creation and suppression for non-alerts."""
    now = datetime.now(timezone.utc)

    # No alert -> returns None
    w_calm = WeatherConditions(
        latitude=47.5,
        longitude=-122.0,
        timestamp=now,
        weather_code=0,
        temperature_c=22.0,
        wind_speed_kmh=10.0,
        precipitation_mm=0.0,
        alert_level=WeatherAlertLevel.NONE,
    )
    assert create_weather_hazard_polygon(w_calm) is None

    # Advisory alert -> returns None
    w_advisory = WeatherConditions(
        latitude=47.5,
        longitude=-122.0,
        timestamp=now,
        weather_code=45,
        temperature_c=10.0,
        wind_speed_kmh=20.0,
        precipitation_mm=0.0,
        alert_level=WeatherAlertLevel.ADVISORY,
    )
    assert create_weather_hazard_polygon(w_advisory) is None

    # Watch alert -> SEVERE hazard polygon
    w_watch = WeatherConditions(
        latitude=47.5,
        longitude=-122.0,
        timestamp=now,
        weather_code=65,
        temperature_c=14.0,
        wind_speed_kmh=35.0,
        precipitation_mm=20.0,
        alert_level=WeatherAlertLevel.WATCH,
    )
    poly_watch = create_weather_hazard_polygon(w_watch)
    assert poly_watch is not None
    assert poly_watch.severity == HazardSeverity.SEVERE
    assert poly_watch.speed_multiplier == 0.35

    # Warning alert with hurricane-force winds (>= 85 km/h) -> CRITICAL_BLOCKED
    w_extreme = WeatherConditions(
        latitude=47.5,
        longitude=-122.0,
        timestamp=now,
        weather_code=95,
        temperature_c=12.0,
        wind_speed_kmh=92.0,
        precipitation_mm=15.0,
        alert_level=WeatherAlertLevel.WARNING,
    )
    poly_extreme = create_weather_hazard_polygon(w_extreme)
    assert poly_extreme is not None
    assert poly_extreme.severity == HazardSeverity.CRITICAL_BLOCKED
    assert poly_extreme.speed_multiplier == 0.0

    # Extreme heat wave (> 38 C) -> WILDFIRE category
    w_heat = WeatherConditions(
        latitude=47.5,
        longitude=-122.0,
        timestamp=now,
        weather_code=0,
        temperature_c=41.0,
        wind_speed_kmh=40.0,
        precipitation_mm=0.0,
        alert_level=WeatherAlertLevel.WATCH,
    )
    poly_heat = create_weather_hazard_polygon(w_heat)
    assert poly_heat is not None
    assert poly_heat.hazard_type == HazardType.WILDFIRE_PERIMETER


# ===========================================================================
# 6. Environmental Graph Mutation & Dynamic Rerouting Tests
# ===========================================================================


def test_apply_environmental_hazards_and_dynamic_rerouting() -> None:
    """Verify that river flood breach triggers road closure and reroutes vehicle."""
    # Build a road network across a river
    #
    # Node N1: Station (west)       [47.500, -122.040] (Safe upland location)
    # Node N2: River Low-Bridge     [47.500, -122.000] (Floods during major stage)
    # Node N3: Hospital (east)      [47.500, -121.960] (Safe upland location)
    # Node N4: High-Level Bypass    [47.530, -122.000] (Elevated bridge, unflooded detour)
    graph = Graph()
    graph.add_node(Node("N1", coordinates=(-122.040, 47.500)))
    graph.add_node(Node("N2", coordinates=(-122.000, 47.500)))
    graph.add_node(Node("N3", coordinates=(-121.960, 47.500)))
    graph.add_node(Node("N4", coordinates=(-122.000, 47.530)))

    # Direct river crossing path N1 -> N2 -> N3 (Flat & direct, 1000m each)
    graph.add_edge(Edge("N1", "N2", cost=1000.0))
    graph.add_edge(Edge("N2", "N1", cost=1000.0))
    graph.add_edge(Edge("N2", "N3", cost=1000.0))
    graph.add_edge(Edge("N3", "N2", cost=1000.0))

    # Bypass bridge path N1 -> N4 -> N3 (Longer detour, 1800m each)
    graph.add_edge(Edge("N1", "N4", cost=1800.0))
    graph.add_edge(Edge("N4", "N1", cost=1800.0))
    graph.add_edge(Edge("N4", "N3", cost=1800.0))
    graph.add_edge(Edge("N3", "N4", cost=1800.0))

    # Baseline: Normal weather & normal river stage
    res_base = astar(graph, "N1", "N3")
    assert res_base is not None
    assert res_base.path == ["N1", "N2", "N3"]
    assert res_base.total_cost == 2000.0

    # Create DynamicGraphView
    dynamic_view = DynamicGraphView(graph)

    # 1. Test Minor Flood: Applies speed penalty (not closure)
    minor_gauge = USGSGaugeReading(
        site_id="12110001",
        site_name="Valley River Gauge",
        latitude=47.500,
        longitude=-122.000,
        timestamp=datetime.now(timezone.utc),
        gage_height_ft=14.0,
        flood_stage=FloodStage.MINOR,
    )

    summary_minor = apply_environmental_hazards_to_graph(
        graph=graph,
        dynamic_view=dynamic_view,
        gauges=[minor_gauge],
    )
    assert summary_minor.floods_detected == 1
    assert summary_minor.edges_speed_penalized > 0
    assert summary_minor.edges_closed == 0

    # 2. Test Major Flood: Breaches riverbanks -> Complete road closure
    major_gauge = USGSGaugeReading(
        site_id="12110001",
        site_name="Valley River Gauge",
        latitude=47.500,
        longitude=-122.000,
        timestamp=datetime.now(timezone.utc),
        gage_height_ft=24.0,
        flood_stage=FloodStage.MAJOR,
    )

    summary_major = apply_environmental_hazards_to_graph(
        graph=graph,
        dynamic_view=dynamic_view,
        gauges=[major_gauge],
    )
    assert summary_major.floods_detected == 1
    assert summary_major.edges_closed > 0

    # Now route through dynamic_view: the low bridge N2 is severed, ambulance must take N4 detour!
    res_flooded = astar(dynamic_view, "N1", "N3")
    assert res_flooded is not None
    assert res_flooded.path == ["N1", "N4", "N3"]
    assert res_flooded.total_cost == 3600.0


def test_apply_environmental_hazards_empty() -> None:
    """Verify behavior when no gauges or weather hazards are present."""
    graph = Graph()
    graph.add_node(Node("A", coordinates=(-122.0, 47.0)))
    graph.add_node(Node("B", coordinates=(-122.0, 47.1)))
    graph.add_edge(Edge("A", "B", cost=100.0))

    dynamic_view = DynamicGraphView(graph)
    summary = apply_environmental_hazards_to_graph(
        graph=graph,
        dynamic_view=dynamic_view,
        gauges=[],
        weather_reports=[],
    )
    assert summary.floods_detected == 0
    assert summary.weather_hazards_detected == 0
    assert summary.edges_closed == 0
    assert summary.edges_speed_penalized == 0
    assert len(summary.active_hazard_polygons) == 0


def test_parse_usgs_water_response_additional_branches() -> None:
    """Verify default site name, non-dict series, missing date, and discharge-only filtering."""
    payload = {
        "value": {
            "timeSeries": [
                "not_a_dict_series",  # Non-dict series
                {
                    # Series with streamflow only (no gage height)
                    "sourceInfo": {
                        "siteCode": [{"value": "12115000"}],
                        "geoLocation": {"geogLocation": {"latitude": 47.1, "longitude": -122.1}},
                    },
                    "variable": {"variableCode": [{"value": "00060"}]},
                    "values": [{"value": [{"value": "500.0"}]}],
                },
                {
                    # Series with gage height, no siteName, no dateTime
                    "sourceInfo": {
                        "siteCode": [{"value": "12116000"}],
                        "geoLocation": {"geogLocation": {"latitude": 47.2, "longitude": -122.2}},
                    },
                    "variable": {"variableCode": [{"value": "00065"}]},
                    "values": [{"value": [{"value": "9.5"}]}],
                },
            ]
        }
    }

    readings = parse_usgs_water_response(payload)
    # The discharge-only station should be excluded because gage height is None
    assert len(readings) == 1
    r = readings[0]
    assert r.site_id == "12116000"
    assert r.site_name == "USGS-12116000"
    assert r.gage_height_ft == 9.5
    assert r.flood_stage == FloodStage.NORMAL


def test_apply_environmental_hazards_with_weather_warnings() -> None:
    """Verify applying severe weather hazard polygons to DynamicGraphView."""
    graph = Graph()
    graph.add_node(Node("W1", coordinates=(-122.000, 47.000)))
    graph.add_node(Node("W2", coordinates=(-122.000, 47.010)))
    graph.add_edge(Edge("W1", "W2", cost=500.0))
    graph.add_edge(Edge("W2", "W1", cost=500.0))

    dynamic_view = DynamicGraphView(graph)
    weather_warning = WeatherConditions(
        latitude=47.005,
        longitude=-122.000,
        timestamp=datetime.now(timezone.utc),
        weather_code=95,
        temperature_c=15.0,
        wind_speed_kmh=90.0,  # Extreme winds -> CRITICAL_BLOCKED
        precipitation_mm=20.0,
        alert_level=WeatherAlertLevel.WARNING,
        summary="Severe Hurricane Gusts",
    )

    summary = apply_environmental_hazards_to_graph(
        graph=graph,
        dynamic_view=dynamic_view,
        gauges=[],
        weather_reports=[weather_warning],
    )
    assert summary.weather_hazards_detected == 1
    assert summary.edges_closed > 0
    assert dynamic_view.is_edge_blocked("W1", "W2") is True

