"""
Unit tests for server/scanning.py

Covers:
- passive_detection_range: formula and spec table values
- active_scan_detail_level: distance thresholds
- default_visibility_level: no-sensor ranges
- tick_passive_detector: detects ships in range, skips self, skips docked ships
- tick_active_scanner: detail levels at various distances
- get_ships_that_detect_scan: reveal logic
"""

import pytest

from server.scanning import (
    DETAIL_CLASSIFICATION,
    DETAIL_CONTACT,
    DETAIL_DETAILED,
    DETAIL_IDENTIFICATION,
    DETAIL_UNKNOWN,
    SCAN_REVEAL_RANGE,
    active_scan_detail_level,
    default_visibility_level,
    get_ships_that_detect_scan,
    passive_detection_range,
    tick_active_scanner,
    tick_passive_detector,
)
from server.models import ModuleType, ShipClass
from tests.conftest import make_test_ship, add_module_to_ship


# ---------------------------------------------------------------------------
# passive_detection_range
# ---------------------------------------------------------------------------


class TestPassiveDetectionRange:
    def test_frigate_at_reference_returns_base_range(self):
        """Frigate sig_radius=300 is the reference; effective_range = base_range."""
        assert passive_detection_range(50_000.0, 300.0) == pytest.approx(50_000.0)

    def test_strike_craft_smaller_range(self):
        """Strike craft sig=25 -> 50000 * (25/300) = 4166.7 km"""
        expected = 50_000.0 * (25.0 / 300.0)
        assert passive_detection_range(50_000.0, 25.0) == pytest.approx(expected)

    def test_mothership_larger_range(self):
        """Mothership sig=2000 -> 50000 * (2000/300) = 333333 m"""
        expected = 50_000.0 * (2000.0 / 300.0)
        assert passive_detection_range(50_000.0, 2000.0) == pytest.approx(expected)

    def test_spec_table_corvette(self):
        """Corvette sig=100; detection at 50km base ≈ 16666.7m ≈ 16.7 km"""
        expected = 50_000.0 * (100.0 / 300.0)
        assert passive_detection_range(50_000.0, 100.0) == pytest.approx(expected, rel=0.01)

    def test_spec_table_destroyer(self):
        """Destroyer sig=600; detection = 50000 * (600/300) = 100,000m = 100 km"""
        assert passive_detection_range(50_000.0, 600.0) == pytest.approx(100_000.0)


# ---------------------------------------------------------------------------
# active_scan_detail_level
# ---------------------------------------------------------------------------


class TestActiveScanDetailLevel:
    def test_within_50km_is_detailed(self):
        assert active_scan_detail_level(10_000.0) == DETAIL_DETAILED
        assert active_scan_detail_level(50_000.0) == DETAIL_DETAILED

    def test_50_to_100km_is_identification(self):
        assert active_scan_detail_level(51_000.0) == DETAIL_IDENTIFICATION
        assert active_scan_detail_level(100_000.0) == DETAIL_IDENTIFICATION

    def test_100_to_150km_is_classification(self):
        assert active_scan_detail_level(100_001.0) == DETAIL_CLASSIFICATION
        assert active_scan_detail_level(150_000.0) == DETAIL_CLASSIFICATION

    def test_150_to_200km_is_contact(self):
        assert active_scan_detail_level(150_001.0) == DETAIL_CONTACT
        assert active_scan_detail_level(200_000.0) == DETAIL_CONTACT

    def test_beyond_200km_is_unknown(self):
        assert active_scan_detail_level(200_001.0) == DETAIL_UNKNOWN
        assert active_scan_detail_level(1_000_000.0) == DETAIL_UNKNOWN


# ---------------------------------------------------------------------------
# default_visibility_level
# ---------------------------------------------------------------------------


class TestDefaultVisibilityLevel:
    def test_within_100m_is_identification(self):
        assert default_visibility_level(0.0) == DETAIL_IDENTIFICATION
        assert default_visibility_level(100.0) == DETAIL_IDENTIFICATION

    def test_100m_to_1km_is_classification(self):
        assert default_visibility_level(101.0) == DETAIL_CLASSIFICATION
        assert default_visibility_level(1_000.0) == DETAIL_CLASSIFICATION

    def test_beyond_1km_is_unknown(self):
        assert default_visibility_level(1_001.0) == DETAIL_UNKNOWN
        assert default_visibility_level(10_000.0) == DETAIL_UNKNOWN


# ---------------------------------------------------------------------------
# tick_passive_detector
# ---------------------------------------------------------------------------


class TestTickPassiveDetector:
    def _make_detector_ship(self, pos_x=0.0) -> object:
        ship = make_test_ship(ShipClass.frigate, pos_x=pos_x)
        detector = add_module_to_ship(ship, ModuleType.passive_detector, 100)
        detector.active = True
        return ship

    def test_detects_ship_in_range(self):
        detector_ship = self._make_detector_ship(pos_x=0.0)
        detector_module = detector_ship.modules[0]

        # Place a corvette near the detector (well within range)
        target = make_test_ship(ShipClass.corvette, pos_x=1_000.0)
        target.id = 2
        target.signature_radius = 100.0

        result = tick_passive_detector(detector_ship, detector_module, [target], [])

        assert len(result.new_contacts) == 1
        assert result.new_contacts[0]["type"] == "ship"
        assert result.new_contacts[0]["id"] == 2

    def test_does_not_detect_self(self):
        detector_ship = self._make_detector_ship(pos_x=0.0)
        detector_module = detector_ship.modules[0]

        result = tick_passive_detector(
            detector_ship, detector_module, [detector_ship], []
        )

        # Self should not appear in contacts
        for contact in result.new_contacts:
            assert contact.get("id") != detector_ship.id

    def test_does_not_detect_out_of_range_ship(self):
        detector_ship = self._make_detector_ship(pos_x=0.0)
        detector_module = detector_ship.modules[0]

        # A strike craft at 10,000m: effective_range = 50000 * (25/300) ≈ 4167m
        target = make_test_ship(ShipClass.strike_craft, pos_x=10_000.0)
        target.id = 2
        target.signature_radius = 25.0

        result = tick_passive_detector(detector_ship, detector_module, [target], [])

        assert len(result.new_contacts) == 0

    def test_skips_docked_ships(self):
        detector_ship = self._make_detector_ship(pos_x=0.0)
        detector_module = detector_ship.modules[0]

        target = make_test_ship(ShipClass.corvette, pos_x=100.0)
        target.id = 2
        target.docked_in_id = 99  # Mark as docked
        target.signature_radius = 100.0

        result = tick_passive_detector(detector_ship, detector_module, [target], [])

        assert len(result.new_contacts) == 0

    def test_inactive_module_detects_nothing(self):
        detector_ship = self._make_detector_ship(pos_x=0.0)
        detector_module = detector_ship.modules[0]
        detector_module.active = False  # disabled

        target = make_test_ship(ShipClass.corvette, pos_x=100.0)
        target.id = 2
        target.signature_radius = 100.0

        result = tick_passive_detector(detector_ship, detector_module, [target], [])

        assert len(result.new_contacts) == 0

    def test_detects_asteroid_in_range(self):
        from server.models import CelestialObject, CelestialType
        detector_ship = self._make_detector_ship(pos_x=0.0)
        detector_module = detector_ship.modules[0]

        asteroid = CelestialObject(
            id=1,
            name="Asteroid",
            object_type=CelestialType.asteroid,
            pos_x=1_000.0,
            pos_y=0.0,
            pos_z=0.0,
            ore_remaining=500.0,
            ore_initial=500.0,
        )

        result = tick_passive_detector(detector_ship, detector_module, [], [asteroid])

        # Asteroid uses fixed signature 500m -> effective_range = 50000*(500/300) ≈ 83333m
        assert len(result.new_contacts) >= 1
        object_contacts = [c for c in result.new_contacts if c["type"] == "object"]
        assert len(object_contacts) == 1


# ---------------------------------------------------------------------------
# tick_active_scanner
# ---------------------------------------------------------------------------


class TestTickActiveScanner:
    def _make_scanner_ship(self, pos_x=0.0):
        ship = make_test_ship(ShipClass.frigate, pos_x=pos_x)
        scanner = add_module_to_ship(ship, ModuleType.scanner, 500)
        scanner.active = True
        return ship

    def test_no_contacts_when_no_ships(self):
        scanner_ship = self._make_scanner_ship()
        scanner_module = scanner_ship.modules[0]
        result = tick_active_scanner(scanner_ship, scanner_module, [], [])
        assert len(result.contacts) == 0

    def test_detailed_scan_within_50km(self):
        scanner_ship = self._make_scanner_ship(pos_x=0.0)
        scanner_module = scanner_ship.modules[0]
        target = make_test_ship(ShipClass.corvette, pos_x=10_000.0)  # 10km away
        target.id = 2

        result = tick_active_scanner(scanner_ship, scanner_module, [target], [])

        assert len(result.contacts) == 1
        contact = result.contacts[0]
        assert contact["detail"] == DETAIL_DETAILED
        assert "ore" in contact
        assert "capacitor" in contact
        assert "name" in contact

    def test_identification_level_50_to_100km(self):
        scanner_ship = self._make_scanner_ship(pos_x=0.0)
        scanner_module = scanner_ship.modules[0]
        target = make_test_ship(ShipClass.corvette, pos_x=75_000.0)  # 75km away
        target.id = 2

        result = tick_active_scanner(scanner_ship, scanner_module, [target], [])

        assert len(result.contacts) == 1
        contact = result.contacts[0]
        assert contact["detail"] == DETAIL_IDENTIFICATION
        assert "name" in contact
        assert "ore" not in contact

    def test_classification_level_100_to_150km(self):
        scanner_ship = self._make_scanner_ship(pos_x=0.0)
        scanner_module = scanner_ship.modules[0]
        target = make_test_ship(ShipClass.corvette, pos_x=125_000.0)  # 125km away
        target.id = 2

        result = tick_active_scanner(scanner_ship, scanner_module, [target], [])

        assert len(result.contacts) == 1
        contact = result.contacts[0]
        assert contact["detail"] == DETAIL_CLASSIFICATION
        assert "ship_class" in contact
        assert "name" not in contact

    def test_contact_level_150_to_200km(self):
        scanner_ship = self._make_scanner_ship(pos_x=0.0)
        scanner_module = scanner_ship.modules[0]
        target = make_test_ship(ShipClass.corvette, pos_x=175_000.0)  # 175km away
        target.id = 2

        result = tick_active_scanner(scanner_ship, scanner_module, [target], [])

        assert len(result.contacts) == 1
        assert result.contacts[0]["detail"] == DETAIL_CONTACT

    def test_beyond_scan_range_not_detected(self):
        scanner_ship = self._make_scanner_ship(pos_x=0.0)
        scanner_module = scanner_ship.modules[0]
        target = make_test_ship(ShipClass.corvette, pos_x=250_000.0)  # 250km > 200km
        target.id = 2

        result = tick_active_scanner(scanner_ship, scanner_module, [target], [])

        assert len(result.contacts) == 0

    def test_does_not_scan_self(self):
        scanner_ship = self._make_scanner_ship(pos_x=0.0)
        scanner_module = scanner_ship.modules[0]

        result = tick_active_scanner(
            scanner_ship, scanner_module, [scanner_ship], []
        )
        assert len(result.contacts) == 0

    def test_docked_ships_not_scanned(self):
        scanner_ship = self._make_scanner_ship(pos_x=0.0)
        scanner_module = scanner_ship.modules[0]
        target = make_test_ship(ShipClass.corvette, pos_x=1_000.0)
        target.id = 2
        target.docked_in_id = 99  # docked

        result = tick_active_scanner(scanner_ship, scanner_module, [target], [])
        assert len(result.contacts) == 0

    def test_inactive_scanner_returns_nothing(self):
        scanner_ship = self._make_scanner_ship(pos_x=0.0)
        scanner_module = scanner_ship.modules[0]
        scanner_module.active = False

        target = make_test_ship(ShipClass.corvette, pos_x=1_000.0)
        target.id = 2

        result = tick_active_scanner(scanner_ship, scanner_module, [target], [])
        assert len(result.contacts) == 0


# ---------------------------------------------------------------------------
# get_ships_that_detect_scan
# ---------------------------------------------------------------------------


class TestGetShipsThatDetectScan:
    def test_ship_with_active_detector_in_range_is_returned(self):
        scanner_ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        scanner_ship.id = 1

        observer = make_test_ship(ShipClass.corvette, pos_x=50_000.0)  # 50km, within 100km
        observer.id = 2
        detector = add_module_to_ship(observer, ModuleType.passive_detector, 100)
        detector.active = True

        detectors = get_ships_that_detect_scan(scanner_ship, [scanner_ship, observer])

        assert observer in detectors

    def test_ship_without_detector_not_returned(self):
        scanner_ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        scanner_ship.id = 1

        observer = make_test_ship(ShipClass.corvette, pos_x=50_000.0)
        observer.id = 2
        # No passive detector module

        detectors = get_ships_that_detect_scan(scanner_ship, [scanner_ship, observer])

        assert observer not in detectors

    def test_ship_beyond_reveal_range_not_returned(self):
        scanner_ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        scanner_ship.id = 1

        observer = make_test_ship(ShipClass.corvette, pos_x=150_000.0)  # 150km > 100km
        observer.id = 2
        detector = add_module_to_ship(observer, ModuleType.passive_detector, 100)
        detector.active = True

        detectors = get_ships_that_detect_scan(scanner_ship, [scanner_ship, observer])

        assert observer not in detectors

    def test_inactive_detector_does_not_detect_scan(self):
        scanner_ship = make_test_ship(ShipClass.frigate, pos_x=0.0)
        scanner_ship.id = 1

        observer = make_test_ship(ShipClass.corvette, pos_x=50_000.0)
        observer.id = 2
        detector = add_module_to_ship(observer, ModuleType.passive_detector, 100)
        detector.active = False  # inactive

        detectors = get_ships_that_detect_scan(scanner_ship, [scanner_ship, observer])

        assert observer not in detectors
