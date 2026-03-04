"""
Unit tests for server/models.py

Covers:
- SHIP_CLASSES constants match spec values
- create_default_ship produces correct hull defaults
- recalculate_max_capacitor formula
- make_module fills correct parameters for each module type
- _factory_max_class returns correct max buildable class
- Spaceship helper methods: max_speed, acceleration, cargo_capacity, docking_capacity
- spawn_new_ship places new ship within 101m of builder
"""

import math
import pytest

from server.models import (
    BUILD_COSTS,
    CLASS_ORDER,
    FACTORY_REQUIREMENTS,
    MODULE_FIXED_VOLUMES,
    MODULE_PARAMS,
    REFERENCE_ENGINE_FRACTION,
    SHIP_CLASSES,
    ModuleType,
    ShipClass,
    Spaceship,
    ShipModule,
    create_default_ship,
    make_module,
    recalculate_max_capacitor,
    spawn_new_ship,
    _factory_max_class,
)
from tests.conftest import make_test_ship, add_module_to_ship


# ---------------------------------------------------------------------------
# Ship class constants match SPEC
# ---------------------------------------------------------------------------


class TestShipClassConstants:
    """Verify SHIP_CLASSES constants match the SPEC.md table."""

    def test_frigate_volume(self):
        assert SHIP_CLASSES["frigate"]["volume"] == 20_000

    def test_frigate_signature(self):
        assert SHIP_CLASSES["frigate"]["signature"] == 300

    def test_frigate_base_cap(self):
        assert SHIP_CLASSES["frigate"]["base_cap"] == 1_000

    def test_frigate_base_speed(self):
        assert SHIP_CLASSES["frigate"]["base_speed"] == 150

    def test_frigate_accel_time(self):
        assert SHIP_CLASSES["frigate"]["accel_time"] == 20

    def test_all_classes_present(self):
        expected = {"strike_craft", "corvette", "frigate", "destroyer", "cruiser", "mothership"}
        assert set(SHIP_CLASSES.keys()) == expected

    def test_spec_values_spot_check(self):
        """Check each class has expected base speed from spec."""
        expected_speeds = {
            "strike_craft": 400,
            "corvette": 250,
            "frigate": 150,
            "destroyer": 100,
            "cruiser": 60,
            "mothership": 30,
        }
        for cls, speed in expected_speeds.items():
            assert SHIP_CLASSES[cls]["base_speed"] == speed, f"Speed mismatch for {cls}"

    def test_spec_capacitor_values(self):
        """Verify base capacitor matches spec table."""
        expected_caps = {
            "strike_craft": 50,
            "corvette": 200,
            "frigate": 1_000,
            "destroyer": 3_000,
            "cruiser": 8_000,
            "mothership": 25_000,
        }
        for cls, cap in expected_caps.items():
            assert SHIP_CLASSES[cls]["base_cap"] == cap, f"Cap mismatch for {cls}"


# ---------------------------------------------------------------------------
# create_default_ship
# ---------------------------------------------------------------------------


class TestCreateDefaultShip:
    def test_creates_frigate_with_correct_volume(self):
        ship = create_default_ship("Test", ShipClass.frigate, user_id=1)
        assert ship.total_volume == 20_000

    def test_creates_frigate_with_correct_signature(self):
        ship = create_default_ship("Test", ShipClass.frigate, user_id=1)
        assert ship.signature_radius == 300.0

    def test_starts_with_full_base_capacitor(self):
        ship = create_default_ship("Test", ShipClass.frigate, user_id=1)
        assert ship.capacitor == 1_000.0
        assert ship.max_capacitor == 1_000.0

    def test_starts_with_zero_ore(self):
        ship = create_default_ship("Test", ShipClass.frigate, user_id=1)
        assert ship.ore == 0.0

    def test_position_set_correctly(self):
        ship = create_default_ship("Test", ShipClass.frigate, user_id=1,
                                   pos_x=100.0, pos_y=200.0, pos_z=300.0)
        assert ship.pos_x == 100.0
        assert ship.pos_y == 200.0
        assert ship.pos_z == 300.0

    def test_strike_craft_parameters(self):
        ship = create_default_ship("Fighter", ShipClass.strike_craft, user_id=1)
        assert ship.total_volume == 100
        assert ship.signature_radius == 25.0
        assert ship.capacitor == 50.0


# ---------------------------------------------------------------------------
# recalculate_max_capacitor
# ---------------------------------------------------------------------------


class TestRecalculateMaxCapacitor:
    def test_no_reactors_base_only(self):
        ship = make_test_ship(ShipClass.frigate)
        # No reactor modules
        recalculate_max_capacitor(ship)
        assert ship.max_capacitor == 1_000.0  # base cap for frigate

    def test_reactor_adds_five_per_m3(self):
        ship = make_test_ship(ShipClass.frigate)
        reactor = add_module_to_ship(ship, ModuleType.reactor, 2_000)
        recalculate_max_capacitor(ship)
        # base(1000) + 2000 * 5 = 11,000
        assert ship.max_capacitor == pytest.approx(11_000.0)

    def test_spec_example_frigate_with_2000_reactor(self):
        """SPEC says: frigate + 2000m3 reactor = 11,000 total cap."""
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.reactor, 2_000)
        recalculate_max_capacitor(ship)
        assert ship.max_capacitor == pytest.approx(11_000.0)

    def test_multiple_reactors(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.reactor, 1_000)
        add_module_to_ship(ship, ModuleType.reactor, 500)
        recalculate_max_capacitor(ship)
        # base(1000) + 1000*5 + 500*5 = 1000 + 5000 + 2500 = 8500
        assert ship.max_capacitor == pytest.approx(8_500.0)


# ---------------------------------------------------------------------------
# make_module
# ---------------------------------------------------------------------------


class TestMakeModule:
    def test_mining_laser_fixed_volume(self):
        mod = make_module(ModuleType.mining_laser, 999)  # volume ignored for fixed
        assert mod.volume == 200
        assert mod.mining_yield == pytest.approx(10.0)
        assert mod.mining_range == pytest.approx(500.0)
        assert mod.cycle_time == 10
        assert mod.capacitor_per_cycle == pytest.approx(50.0)

    def test_scanner_fixed_volume(self):
        mod = make_module(ModuleType.scanner, 999)
        assert mod.volume == 500
        assert mod.scan_range == pytest.approx(200_000.0)
        assert mod.cycle_time == 30
        assert mod.capacitor_per_cycle == pytest.approx(200.0)

    def test_passive_detector_fixed_volume(self):
        mod = make_module(ModuleType.passive_detector, 999)
        assert mod.volume == 100
        assert mod.detection_range == pytest.approx(50_000.0)
        assert mod.cycle_time == 5
        assert mod.capacitor_per_cycle == pytest.approx(5.0)

    def test_dropoff_fixed_volume(self):
        mod = make_module(ModuleType.dropoff, 999)
        assert mod.volume == 500

    def test_engine_variable_volume(self):
        mod = make_module(ModuleType.engine, 6_000)
        assert mod.volume == 6_000
        assert mod.cycle_time == 0  # passive
        assert mod.capacitor_per_cycle == 0.0

    def test_reactor_variable_volume(self):
        mod = make_module(ModuleType.reactor, 2_000)
        assert mod.volume == 2_000
        assert mod.cycle_time == 0

    def test_cargo_bay_variable_volume(self):
        mod = make_module(ModuleType.cargo_bay, 5_000)
        assert mod.volume == 5_000

    def test_factory_max_class_small(self):
        mod = make_module(ModuleType.factory, 500)
        assert mod.factory_max_class == "strike_craft"

    def test_factory_max_class_corvette(self):
        mod = make_module(ModuleType.factory, 5_000)
        assert mod.factory_max_class == "corvette"

    def test_factory_max_class_large(self):
        mod = make_module(ModuleType.factory, 300_000)
        assert mod.factory_max_class == "cruiser"

    def test_factory_too_small_returns_none(self):
        mod = make_module(ModuleType.factory, 100)
        assert mod.factory_max_class is None


# ---------------------------------------------------------------------------
# _factory_max_class
# ---------------------------------------------------------------------------


class TestFactoryMaxClass:
    def test_below_minimum(self):
        assert _factory_max_class(100) is None

    def test_exactly_at_strike_craft(self):
        assert _factory_max_class(500) == "strike_craft"

    def test_between_strike_craft_and_corvette(self):
        assert _factory_max_class(2_000) == "strike_craft"

    def test_exactly_at_corvette(self):
        assert _factory_max_class(5_000) == "corvette"

    def test_large_factory_builds_cruiser(self):
        assert _factory_max_class(300_000) == "cruiser"

    def test_massive_factory_still_cruiser_max(self):
        # Mothership can't be built (not in FACTORY_REQUIREMENTS)
        assert _factory_max_class(2_000_000) == "cruiser"


# ---------------------------------------------------------------------------
# Spaceship helper methods
# ---------------------------------------------------------------------------


class TestSpaceshipHelpers:
    def test_max_speed_no_engines(self):
        ship = make_test_ship(ShipClass.frigate)
        # No engines installed
        assert ship.max_speed() == 0.0

    def test_max_speed_at_reference_fraction(self):
        """30% engine volume gives base_max_speed."""
        ship = make_test_ship(ShipClass.frigate)
        # Frigate total volume = 20,000; 30% = 6,000
        add_module_to_ship(ship, ModuleType.engine, 6_000)
        assert ship.max_speed() == pytest.approx(150.0)

    def test_max_speed_above_reference_scales_linearly(self):
        """45% engine volume gives 150 * (0.45/0.30) = 225 m/s per SPEC."""
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.engine, 9_000)  # 45% of 20,000
        assert ship.max_speed() == pytest.approx(225.0)

    def test_max_speed_below_reference(self):
        """15% engine volume gives 150 * (0.15/0.30) = 75 m/s per SPEC."""
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.engine, 3_000)  # 15% of 20,000
        assert ship.max_speed() == pytest.approx(75.0)

    def test_max_speed_capped_at_2x_base(self):
        """Speed cap = 2 * base_max_speed."""
        ship = make_test_ship(ShipClass.frigate)
        # Give it 100% engine volume — fraction = 1.0 > 2 * reference
        add_module_to_ship(ship, ModuleType.engine, 20_000)
        # Would be 150 * (1.0/0.30) = 500, but capped at 2 * 150 = 300
        assert ship.max_speed() == pytest.approx(300.0)

    def test_acceleration_formula(self):
        """acceleration = max_speed / accel_time."""
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.engine, 6_000)  # 150 m/s
        # accel_time for frigate = 20
        assert ship.acceleration() == pytest.approx(150.0 / 20.0)

    def test_cargo_capacity_sum(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.cargo_bay, 5_000)
        add_module_to_ship(ship, ModuleType.cargo_bay, 2_000)
        assert ship.cargo_capacity() == pytest.approx(7_000.0)

    def test_cargo_capacity_zero_without_module(self):
        ship = make_test_ship(ShipClass.frigate)
        assert ship.cargo_capacity() == 0.0

    def test_docking_capacity_half_volume(self):
        """docking_capacity = 0.5 * module volume per spec."""
        ship = make_test_ship(ShipClass.cruiser)
        add_module_to_ship(ship, ModuleType.docking_bay, 50_000)
        assert ship.docking_capacity() == pytest.approx(25_000.0)

    def test_has_dropoff_false_when_none(self):
        ship = make_test_ship(ShipClass.frigate)
        assert ship.has_dropoff() is False

    def test_has_dropoff_true_when_installed(self):
        ship = make_test_ship(ShipClass.corvette)
        add_module_to_ship(ship, ModuleType.dropoff, 500)
        assert ship.has_dropoff() is True

    def test_speed_magnitude(self):
        ship = make_test_ship(ShipClass.frigate, vel_x=3.0, vel_y=4.0, vel_z=0.0)
        assert ship.speed() == pytest.approx(5.0)

    def test_is_docked_false_by_default(self):
        ship = make_test_ship(ShipClass.frigate)
        assert ship.is_docked() is False


# ---------------------------------------------------------------------------
# spawn_new_ship
# ---------------------------------------------------------------------------


class TestSpawnNewShip:
    def test_spawns_docked_in_builder(self):
        builder = make_test_ship(ShipClass.frigate, pos_x=1000.0, pos_y=2000.0, pos_z=3000.0)
        new_ship = spawn_new_ship(ShipClass.strike_craft, builder, current_tick=0)
        # New ships spawn docked inside the builder
        assert new_ship.docked_in_id == builder.id
        assert new_ship.claimed_by_user_id is None

    def test_docked_ship_has_zero_velocity(self):
        builder = make_test_ship(ShipClass.frigate, vel_x=50.0, vel_y=10.0, vel_z=0.0)
        new_ship = spawn_new_ship(ShipClass.strike_craft, builder, current_tick=0)
        # Docked ships have zero velocity
        assert new_ship.vel_x == 0.0
        assert new_ship.vel_y == 0.0
        assert new_ship.vel_z == 0.0

    def test_new_ship_has_correct_class(self):
        builder = make_test_ship(ShipClass.frigate)
        new_ship = spawn_new_ship(ShipClass.corvette, builder, current_tick=0)
        assert new_ship.ship_class == ShipClass.corvette

    def test_new_ship_has_base_capacitor(self):
        builder = make_test_ship(ShipClass.frigate)
        new_ship = spawn_new_ship(ShipClass.strike_craft, builder, current_tick=0)
        expected_cap = SHIP_CLASSES["strike_craft"]["base_cap"]
        assert new_ship.capacitor == pytest.approx(expected_cap)
        assert new_ship.max_capacitor == pytest.approx(expected_cap)

    def test_new_ship_has_zero_ore(self):
        builder = make_test_ship(ShipClass.frigate)
        new_ship = spawn_new_ship(ShipClass.strike_craft, builder, current_tick=0)
        assert new_ship.ore == 0.0

    def test_new_ship_inherits_owner(self):
        builder = make_test_ship(ShipClass.frigate, user_id=42)
        new_ship = spawn_new_ship(ShipClass.strike_craft, builder, current_tick=0)
        assert new_ship.user_id == 42


# ---------------------------------------------------------------------------
# Build costs match spec
# ---------------------------------------------------------------------------


class TestBuildCosts:
    def test_strike_craft_cost(self):
        assert BUILD_COSTS["strike_craft"]["ore"] == 200
        assert BUILD_COSTS["strike_craft"]["ticks"] == 60

    def test_corvette_cost(self):
        assert BUILD_COSTS["corvette"]["ore"] == 1_000
        assert BUILD_COSTS["corvette"]["ticks"] == 180

    def test_frigate_cost(self):
        assert BUILD_COSTS["frigate"]["ore"] == 3_000
        assert BUILD_COSTS["frigate"]["ticks"] == 360

    def test_cruiser_cost(self):
        assert BUILD_COSTS["cruiser"]["ore"] == 50_000
        assert BUILD_COSTS["cruiser"]["ticks"] == 1_800
