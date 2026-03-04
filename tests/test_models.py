"""
Unit tests for server/models.py

Covers:
- SHIP_CLASSES constants match spec values
- create_default_ship produces correct hull defaults
- recalculate_max_capacitor formula (preset reactor cap_bonus)
- make_module fills correct parameters for each module type
- Spaceship helper methods: max_speed, acceleration, cargo_capacity, can_dock_ship_class
- spawn_new_ship places new ship docked inside builder
"""

import math
import pytest

from server.models import (
    BUILD_COSTS,
    SHIP_CLASSES,
    ModuleType,
    ShipClass,
    create_default_ship,
    make_module,
    recalculate_max_capacitor,
    spawn_new_ship,
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
# recalculate_max_capacitor (preset reactor cap_bonus)
# ---------------------------------------------------------------------------


class TestRecalculateMaxCapacitor:
    def test_no_reactors_base_only(self):
        ship = make_test_ship(ShipClass.frigate)
        # No reactor modules
        recalculate_max_capacitor(ship)
        assert ship.max_capacitor == 1_000.0  # base cap for frigate

    def test_reactor_adds_cap_bonus(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.medium_standard_reactor, 0)
        recalculate_max_capacitor(ship)
        # base(1000) + medium_standard_reactor cap_bonus(1000) = 2000
        assert ship.max_capacitor == pytest.approx(2_000.0)

    def test_capacity_reactor_larger_bonus(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.medium_capacity_reactor, 0)
        recalculate_max_capacitor(ship)
        # base(1000) + medium_capacity_reactor cap_bonus(2000) = 3000
        assert ship.max_capacitor == pytest.approx(3_000.0)

    def test_multiple_reactors(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.medium_standard_reactor, 0)   # +1000
        add_module_to_ship(ship, ModuleType.medium_recharge_reactor, 0)   # +500
        recalculate_max_capacitor(ship)
        # base(1000) + 1000 + 500 = 2500
        assert ship.max_capacitor == pytest.approx(2_500.0)


# ---------------------------------------------------------------------------
# make_module (preset modules)
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

    def test_engine_preset_has_correct_stats(self):
        mod = make_module(ModuleType.medium_standard_engine, 0)
        assert mod.volume == 5000
        assert mod.engine_speed == pytest.approx(150.0)
        assert mod.engine_accel_time == pytest.approx(20.0)
        assert mod.engine_cap_drain == pytest.approx(0.0)
        assert mod.cycle_time == 0  # passive

    def test_light_engine_has_cap_drain(self):
        mod = make_module(ModuleType.tiny_light_engine, 0)
        assert mod.volume == 25
        assert mod.engine_speed == pytest.approx(200.0)
        assert mod.engine_cap_drain == pytest.approx(2.0)

    def test_reactor_preset_has_correct_stats(self):
        mod = make_module(ModuleType.medium_standard_reactor, 0)
        assert mod.volume == 2000
        assert mod.reactor_cap_bonus == pytest.approx(1000.0)
        assert mod.reactor_regen_bonus == pytest.approx(0.0)
        assert mod.reactor_efficiency == pytest.approx(0.0)

    def test_recharge_reactor_has_regen(self):
        mod = make_module(ModuleType.medium_recharge_reactor, 0)
        assert mod.reactor_cap_bonus == pytest.approx(500.0)
        assert mod.reactor_regen_bonus == pytest.approx(30.0)

    def test_efficiency_reactor_has_efficiency(self):
        mod = make_module(ModuleType.medium_efficiency_reactor, 0)
        assert mod.reactor_efficiency == pytest.approx(0.08)

    def test_cargo_bay_preset_volume(self):
        mod = make_module(ModuleType.medium_cargo_bay, 0)
        assert mod.volume == 3000

    def test_factory_preset_has_max_class(self):
        mod = make_module(ModuleType.starter_factory, 0)
        assert mod.factory_max_class == "strike_craft"
        assert mod.factory_speed_mult == pytest.approx(1.0)
        assert mod.factory_efficiency_mult == pytest.approx(1.0)

    def test_fast_factory_has_speed_mult(self):
        mod = make_module(ModuleType.small_fast_factory, 0)
        assert mod.factory_speed_mult == pytest.approx(0.7)
        assert mod.factory_efficiency_mult == pytest.approx(1.2)
        assert mod.factory_max_class == "corvette"

    def test_docking_bay_preset_has_max_class(self):
        mod = make_module(ModuleType.small_docking_bay, 0)
        assert mod.docking_max_class == "corvette"
        assert mod.volume == 2000


# ---------------------------------------------------------------------------
# Spaceship helper methods
# ---------------------------------------------------------------------------


class TestSpaceshipHelpers:
    def test_max_speed_no_engines(self):
        ship = make_test_ship(ShipClass.frigate)
        # No engines installed
        assert ship.max_speed() == 0.0

    def test_max_speed_with_standard_engine(self):
        """medium_standard_engine provides 150 m/s for a frigate."""
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.medium_standard_engine, 0)
        assert ship.max_speed() == pytest.approx(150.0)

    def test_max_speed_multiple_engines_add(self):
        """Two engines: speeds add up."""
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.medium_standard_engine, 0)  # 150
        add_module_to_ship(ship, ModuleType.medium_agile_engine, 0)     # 100
        assert ship.max_speed() == pytest.approx(250.0)

    def test_max_speed_capped_at_2x_base(self):
        """Speed cap = 2 * base_speed (frigate base=150, cap=300)."""
        ship = make_test_ship(ShipClass.frigate)
        # 3 medium_standard_engines: 150*3 = 450, capped at 300
        add_module_to_ship(ship, ModuleType.medium_standard_engine, 0)
        add_module_to_ship(ship, ModuleType.medium_standard_engine, 0)
        add_module_to_ship(ship, ModuleType.medium_standard_engine, 0)
        assert ship.max_speed() == pytest.approx(300.0)

    def test_acceleration_formula(self):
        """acceleration = max_speed / weighted_avg_accel_time."""
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.medium_standard_engine, 0)
        # speed=150, accel_time=20 → accel = 150/20 = 7.5
        assert ship.acceleration() == pytest.approx(7.5)

    def test_acceleration_weighted_average(self):
        """With two engines, accel_time is speed-weighted average."""
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.medium_standard_engine, 0)  # 150 m/s, 20s
        add_module_to_ship(ship, ModuleType.medium_agile_engine, 0)     # 100 m/s, 8s
        # total speed = 250 (under 2x cap of 300)
        # weighted avg accel = (150*20 + 100*8) / (150+100) = (3000+800)/250 = 15.2
        # accel = 250 / 15.2 ≈ 16.45
        assert ship.acceleration() == pytest.approx(250.0 / 15.2, rel=0.01)

    def test_cargo_capacity_sum(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.medium_cargo_bay, 0)  # 3000
        add_module_to_ship(ship, ModuleType.small_cargo_bay, 0)   # 300
        assert ship.cargo_capacity() == pytest.approx(3_300.0)

    def test_cargo_capacity_zero_without_module(self):
        ship = make_test_ship(ShipClass.frigate)
        assert ship.cargo_capacity() == 0.0

    def test_can_dock_ship_class_corvette(self):
        """small_docking_bay accepts up to corvette."""
        ship = make_test_ship(ShipClass.cruiser)
        add_module_to_ship(ship, ModuleType.small_docking_bay, 0)
        assert ship.can_dock_ship_class("strike_craft") is True
        assert ship.can_dock_ship_class("corvette") is True
        assert ship.can_dock_ship_class("frigate") is False

    def test_can_dock_ship_class_frigate(self):
        """medium_docking_bay accepts up to frigate."""
        ship = make_test_ship(ShipClass.cruiser)
        add_module_to_ship(ship, ModuleType.medium_docking_bay, 0)
        assert ship.can_dock_ship_class("frigate") is True
        assert ship.can_dock_ship_class("destroyer") is False

    def test_max_dockable_volume(self):
        """max_dockable_volume = volume of largest docking bay module."""
        ship = make_test_ship(ShipClass.cruiser)
        add_module_to_ship(ship, ModuleType.large_docking_bay, 0)  # 100000 m³
        assert ship.max_dockable_volume() == pytest.approx(100_000.0)

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
