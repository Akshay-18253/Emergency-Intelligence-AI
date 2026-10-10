"""
Unit tests for Incident data models, emergency taxonomies, and urgency tiers.
"""

from datetime import datetime, timezone
import pytest

from emergency_intelligence.events.incidents import (
    ApparatusType,
    EmergencyType,
    Incident,
    UrgencyLevel,
)


class TestIncidentModel:
    def test_incident_basic_creation(self):
        inc = Incident(
            incident_id="INC-001",
            emergency_type=EmergencyType.STRUCTURE_FIRE,
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
            coordinates=(-122.4194, 37.7749),
            required_apparatus=[ApparatusType.FIRE_ENGINE, ApparatusType.LADDER_TRUCK],
            description="Two-story residential smoke showing",
        )
        assert inc.incident_id == "INC-001"
        assert inc.emergency_type == EmergencyType.STRUCTURE_FIRE
        assert inc.urgency == UrgencyLevel.PRIORITY_1_ECHO
        assert inc.coordinates == (-122.4194, 37.7749)
        assert inc.longitude == -122.4194
        assert inc.latitude == 37.7749
        assert inc.active is True
        assert len(inc.required_apparatus) == 2
        assert inc.is_life_threatening() is True
        assert inc.requires_apparatus(ApparatusType.FIRE_ENGINE) is True
        assert inc.requires_apparatus(ApparatusType.AMBULANCE_ALS) is False

    def test_incident_string_enum_coercion(self):
        inc = Incident(
            incident_id="INC-002",
            emergency_type="cardiac_arrest",  # string coerced to EmergencyType
            urgency="priority_1_echo",        # string coerced to UrgencyLevel
            coordinates=[-122.4089, 37.7833], # list coerced to tuple
            required_apparatus=["ambulance_als"],
        )
        assert inc.emergency_type == EmergencyType.CARDIAC_ARREST
        assert inc.urgency == UrgencyLevel.PRIORITY_1_ECHO
        assert inc.coordinates == (-122.4089, 37.7833)
        assert inc.required_apparatus == [ApparatusType.AMBULANCE_ALS]

    def test_urgency_life_threatening_levels(self):
        echo = Incident("1", EmergencyType.CARDIAC_ARREST, UrgencyLevel.PRIORITY_1_ECHO, (0, 0))
        delta = Incident("2", EmergencyType.TRAUMA_MAJOR, UrgencyLevel.PRIORITY_2_DELTA, (0, 0))
        bravo = Incident("3", EmergencyType.MEDICAL_GENERAL, UrgencyLevel.PRIORITY_3_BRAVO, (0, 0))
        alpha = Incident("4", EmergencyType.MEDICAL_GENERAL, UrgencyLevel.PRIORITY_4_ALPHA, (0, 0))

        assert echo.is_life_threatening() is True
        assert delta.is_life_threatening() is True
        assert bravo.is_life_threatening() is False
        assert alpha.is_life_threatening() is False

    def test_validation_invalid_id(self):
        with pytest.raises(ValueError, match="non-empty string"):
            Incident("", EmergencyType.STRUCTURE_FIRE, UrgencyLevel.PRIORITY_1_ECHO, (0, 0))

    def test_validation_invalid_types(self):
        with pytest.raises(TypeError, match="EmergencyType enum"):
            Incident("1", 12345, UrgencyLevel.PRIORITY_1_ECHO, (0, 0))  # type: ignore

        with pytest.raises(TypeError, match="UrgencyLevel enum"):
            Incident("1", EmergencyType.STRUCTURE_FIRE, 999, (0, 0))  # type: ignore

    def test_validation_invalid_coordinates(self):
        with pytest.raises(ValueError, match="pair"):
            Incident("1", EmergencyType.STRUCTURE_FIRE, UrgencyLevel.PRIORITY_1_ECHO, (0,))  # type: ignore

        with pytest.raises(ValueError, match="Longitude.*out of valid"):
            Incident("1", EmergencyType.STRUCTURE_FIRE, UrgencyLevel.PRIORITY_1_ECHO, (200.0, 37.0))

        with pytest.raises(ValueError, match="Latitude.*out of valid"):
            Incident("1", EmergencyType.STRUCTURE_FIRE, UrgencyLevel.PRIORITY_1_ECHO, (-122.0, -95.0))

    def test_validation_invalid_apparatus(self):
        with pytest.raises(TypeError, match="Invalid apparatus specification"):
            Incident(
                "1",
                EmergencyType.STRUCTURE_FIRE,
                UrgencyLevel.PRIORITY_1_ECHO,
                (0, 0),
                required_apparatus=[123],  # type: ignore
            )

    def test_dict_serialization_round_trip(self):
        fixed_dt = datetime(2026, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
        original = Incident(
            incident_id="INC-999",
            emergency_type=EmergencyType.HAZMAT_SPILL,
            urgency=UrgencyLevel.PRIORITY_2_DELTA,
            coordinates=(-122.4150, 37.7750),
            required_apparatus=[ApparatusType.HAZMAT_UNIT, ApparatusType.BATTALION_CHIEF],
            description="Chlorine tank leak in warehouse loading dock",
            reported_at=fixed_dt,
            active=False,
            metadata={"tank_capacity_gallons": 500, "containment_status": "evacuating"},
        )

        d = original.to_dict()
        assert d["incident_id"] == "INC-999"
        assert d["emergency_type"] == "hazmat_spill"
        assert d["urgency"] == "priority_2_delta"
        assert d["coordinates"] == [-122.4150, 37.7750]
        assert d["required_apparatus"] == ["hazmat_unit", "battalion_chief"]
        assert d["active"] is False
        assert d["metadata"]["tank_capacity_gallons"] == 500

        reconstructed = Incident.from_dict(d)
        assert reconstructed.incident_id == original.incident_id
        assert reconstructed.emergency_type == original.emergency_type
        assert reconstructed.urgency == original.urgency
        assert reconstructed.coordinates == original.coordinates
        assert reconstructed.required_apparatus == original.required_apparatus
        assert reconstructed.reported_at == fixed_dt
        assert reconstructed.active is False
        assert reconstructed.metadata == original.metadata

    def test_from_dict_with_datetime_and_missing_reported_at(self):
        now_dt = datetime.now(timezone.utc)
        d = {
            "incident_id": "INC-100",
            "emergency_type": "flash_flood",
            "urgency": "priority_1_echo",
            "coordinates": [-122.4, 37.8],
            "reported_at": now_dt,  # already a datetime
        }
        inc = Incident.from_dict(d)
        assert inc.reported_at == now_dt

        d2 = {
            "incident_id": "INC-101",
            "emergency_type": "flash_flood",
            "urgency": "priority_1_echo",
            "coordinates": [-122.4, 37.8],
            # missing reported_at
        }
        inc2 = Incident.from_dict(d2)
        assert isinstance(inc2.reported_at, datetime)
