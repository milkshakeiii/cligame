"""
Unit tests for server/production.py

Covers:
- can_factory_build: docking bay class check + factory class gate
- factory speed/efficiency multipliers (from preset modules)
- can_ship_build: ore check (with factory efficiency)
- start_build: ore deduction, BuildOrder creation
- tick_build_order: cap drain, completion, pausing/resuming
- get_next_queued_order
"""

import pytest

from server.models import (
    BUILD_COSTS,
    BuildStatus,
    ModuleType,
    ShipClass,
)
from server.production import (
    can_factory_build,
    can_ship_build,
    factory_speed_multiplier,
    factory_efficiency_multiplier,
    get_factory_adjusted_cost,
    get_next_queued_order,
    start_build,
    tick_build_order,
    FACTORY_CAP_PER_TICK,
)
from tests.conftest import make_test_ship, add_module_to_ship


def _make_buildable_ship(
    ship_class=ShipClass.frigate,
    docking_type=ModuleType.small_docking_bay,
    factory_type=ModuleType.starter_factory,
    ore=500.0,
):
    """Helper: make a ship with docking bay + factory preset, ready to build."""
    ship = make_test_ship(ship_class)
    ship.id = 1
    add_module_to_ship(ship, docking_type, 0)
    factory = add_module_to_ship(ship, factory_type, 0)
    factory.id = 1
    ship.ore = ore
    return ship, factory


# ---------------------------------------------------------------------------
# can_factory_build (class-based gating)
# ---------------------------------------------------------------------------


class TestCanFactoryBuild:
    def test_non_factory_module_fails(self):
        ship = make_test_ship(ShipClass.frigate)
        add_module_to_ship(ship, ModuleType.small_docking_bay, 0)
        engine = add_module_to_ship(ship, ModuleType.medium_standard_engine, 0)
        ok, reason = can_factory_build(ship, engine, ShipClass.strike_craft)
        assert ok is False
        assert "not a factory" in reason

    def test_factory_class_gate_fails(self):
        """starter_factory can only build strike_craft, not corvette."""
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.small_docking_bay,
            factory_type=ModuleType.starter_factory,
        )
        ok, reason = can_factory_build(ship, factory, ShipClass.corvette)
        assert ok is False
        assert "cannot build corvette" in reason

    def test_docking_bay_class_gate_fails(self):
        """tiny_docking_bay only accepts strike_craft; can't build corvette even with small_factory."""
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.tiny_docking_bay,
            factory_type=ModuleType.small_factory,
        )
        ok, reason = can_factory_build(ship, factory, ShipClass.corvette)
        assert ok is False
        assert "docking bay" in reason.lower()

    def test_factory_and_bay_match_succeeds(self):
        """starter_factory + tiny_docking_bay → can build strike_craft."""
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.tiny_docking_bay,
            factory_type=ModuleType.starter_factory,
        )
        ok, reason = can_factory_build(ship, factory, ShipClass.strike_craft)
        assert ok is True
        assert reason == ""

    def test_small_factory_builds_corvette(self):
        """small_factory + small_docking_bay → can build corvette."""
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.small_docking_bay,
            factory_type=ModuleType.small_factory,
        )
        ok, _ = can_factory_build(ship, factory, ShipClass.corvette)
        assert ok is True

    def test_medium_factory_builds_frigate(self):
        """medium_factory + medium_docking_bay → can build frigate."""
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.medium_docking_bay,
            factory_type=ModuleType.medium_factory,
        )
        ok, _ = can_factory_build(ship, factory, ShipClass.frigate)
        assert ok is True

    def test_mothership_not_buildable(self):
        """Mothership is not in DOCKING_CLASS_INDEX as a dockable class target."""
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.huge_docking_bay,
            factory_type=ModuleType.huge_factory,
        )
        ok, reason = can_factory_build(ship, factory, ShipClass.mothership)
        assert ok is False


# ---------------------------------------------------------------------------
# Factory speed/efficiency multipliers (from preset module fields)
# ---------------------------------------------------------------------------


class TestFactoryMultipliers:
    def test_standard_factory_1x_speed(self):
        mod = add_module_to_ship(make_test_ship(), ModuleType.starter_factory, 0)
        assert factory_speed_multiplier(mod) == pytest.approx(1.0)

    def test_standard_factory_1x_efficiency(self):
        mod = add_module_to_ship(make_test_ship(), ModuleType.starter_factory, 0)
        assert factory_efficiency_multiplier(mod) == pytest.approx(1.0)

    def test_fast_factory_speed(self):
        mod = add_module_to_ship(make_test_ship(), ModuleType.small_fast_factory, 0)
        assert factory_speed_multiplier(mod) == pytest.approx(0.7)

    def test_fast_factory_efficiency(self):
        mod = add_module_to_ship(make_test_ship(), ModuleType.small_fast_factory, 0)
        assert factory_efficiency_multiplier(mod) == pytest.approx(1.2)

    def test_efficient_factory_speed(self):
        mod = add_module_to_ship(make_test_ship(), ModuleType.small_efficient_factory, 0)
        assert factory_speed_multiplier(mod) == pytest.approx(1.3)

    def test_efficient_factory_efficiency(self):
        mod = add_module_to_ship(make_test_ship(), ModuleType.small_efficient_factory, 0)
        assert factory_efficiency_multiplier(mod) == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# can_ship_build
# ---------------------------------------------------------------------------


class TestCanShipBuild:
    def test_insufficient_ore_fails(self):
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.tiny_docking_bay,
            factory_type=ModuleType.starter_factory,
            ore=10.0,
        )
        ok, reason = can_ship_build(ship, ShipClass.strike_craft, factory)
        assert ok is False
        assert "insufficient ore" in reason.lower()

    def test_sufficient_ore_succeeds(self):
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.tiny_docking_bay,
            factory_type=ModuleType.starter_factory,
            ore=500.0,
        )
        ok, reason = can_ship_build(ship, ShipClass.strike_craft, factory)
        assert ok is True

    def test_docking_bay_check_takes_precedence(self):
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.tiny_docking_bay,  # only strike_craft
            factory_type=ModuleType.small_factory,      # can build corvette
            ore=10_000.0,
        )
        ok, reason = can_ship_build(ship, ShipClass.corvette, factory)
        assert ok is False
        assert "docking bay" in reason.lower()


# ---------------------------------------------------------------------------
# start_build
# ---------------------------------------------------------------------------


class TestStartBuild:
    def test_deducts_ore_immediately(self):
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.tiny_docking_bay,
            factory_type=ModuleType.starter_factory,
            ore=500.0,
        )
        cost = get_factory_adjusted_cost(ShipClass.strike_craft, factory)

        start_build(ship, factory, ShipClass.strike_craft)

        assert ship.ore == pytest.approx(500.0 - cost["ore"])

    def test_returns_build_order(self):
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.tiny_docking_bay,
            factory_type=ModuleType.starter_factory,
            ore=500.0,
        )
        cost = get_factory_adjusted_cost(ShipClass.strike_craft, factory)

        order = start_build(ship, factory, ShipClass.strike_craft)

        assert order.blueprint == ShipClass.strike_craft
        assert order.status == BuildStatus.queued
        assert order.ticks_remaining == cost["ticks"]
        assert order.total_ticks == cost["ticks"]
        assert order.ore_cost == cost["ore"]

    def test_raises_when_insufficient_ore(self):
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.tiny_docking_bay,
            factory_type=ModuleType.starter_factory,
            ore=0.0,
        )

        with pytest.raises(ValueError, match="insufficient ore"):
            start_build(ship, factory, ShipClass.strike_craft)

    def test_raises_when_docking_bay_too_small(self):
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.tiny_docking_bay,  # only strike_craft
            factory_type=ModuleType.small_factory,      # can build corvette
            ore=10_000.0,
        )

        with pytest.raises(ValueError):
            start_build(ship, factory, ShipClass.corvette)


# ---------------------------------------------------------------------------
# tick_build_order
# ---------------------------------------------------------------------------


class TestTickBuildOrder:
    def _make_ship_and_order(self, blueprint=ShipClass.strike_craft, ore=None):
        ship, factory = _make_buildable_ship(
            docking_type=ModuleType.small_docking_bay,
            factory_type=ModuleType.small_factory,
            ore=ore or 10_000.0,
        )
        ship.max_capacitor = 11_000.0
        ship.capacitor = 11_000.0

        order = start_build(ship, factory, blueprint)
        order.status = BuildStatus.building  # promote from queued for tick testing
        order.ship_id = 1
        order.factory_module_id = 1
        return ship, order

    def test_drains_capacitor_per_tick(self):
        ship, order = self._make_ship_and_order()
        cap_before = ship.capacitor

        tick_build_order(ship, order)

        assert ship.capacitor == pytest.approx(cap_before - FACTORY_CAP_PER_TICK)

    def test_advances_ticks_remaining(self):
        ship, order = self._make_ship_and_order()
        ticks_before = order.ticks_remaining

        tick_build_order(ship, order)

        assert order.ticks_remaining == ticks_before - 1

    def test_pauses_when_cap_insufficient(self):
        ship, order = self._make_ship_and_order()
        ship.capacitor = 50.0  # less than FACTORY_CAP_PER_TICK

        result = tick_build_order(ship, order)

        assert result["paused"] is True
        assert order.status == BuildStatus.paused

    def test_resumes_when_cap_recovers(self):
        ship, order = self._make_ship_and_order()
        order.status = BuildStatus.paused  # manually set to paused
        ship.capacitor = 5_000.0  # enough cap

        result = tick_build_order(ship, order)

        assert result["unpaused"] is True
        assert order.status == BuildStatus.building

    def test_completes_when_ticks_reach_zero(self):
        ship, order = self._make_ship_and_order()
        order.ticks_remaining = 1  # one tick left

        result = tick_build_order(ship, order)

        assert result["completed"] is True
        assert order.status == BuildStatus.completed
        assert result["new_ship"] is not None

    def test_new_ship_has_correct_class(self):
        ship, order = self._make_ship_and_order(ShipClass.strike_craft)
        order.ticks_remaining = 1
        result = tick_build_order(ship, order)
        assert result["new_ship"].ship_class == ShipClass.strike_craft

    def test_already_completed_order_skipped(self):
        ship, order = self._make_ship_and_order()
        order.status = BuildStatus.completed
        cap_before = ship.capacitor

        result = tick_build_order(ship, order)

        assert result["completed"] is False
        assert ship.capacitor == cap_before  # no drain

    def test_build_paused_does_not_advance_ticks(self):
        ship, order = self._make_ship_and_order()
        ship.capacitor = 0.0
        ticks_before = order.ticks_remaining

        tick_build_order(ship, order)

        assert order.ticks_remaining == ticks_before  # no advancement


# ---------------------------------------------------------------------------
# get_next_queued_order
# ---------------------------------------------------------------------------


class TestGetNextQueuedOrder:
    def _make_order(self, factory_module_id: int, status: BuildStatus, ord_id: int):
        from server.models import BuildOrder, ShipClass
        order = BuildOrder(
            id=ord_id,
            ship_id=1,
            factory_module_id=factory_module_id,
            blueprint=ShipClass.strike_craft,
            status=status,
            ore_cost=200,
            ticks_remaining=120,
            total_ticks=120,
        )
        return order

    def test_returns_none_when_no_queued_orders(self):
        orders = [
            self._make_order(1, BuildStatus.building, 1),
            self._make_order(1, BuildStatus.completed, 2),
        ]
        result = get_next_queued_order(1, orders)
        assert result is None

    def test_returns_first_queued_order(self):
        queued = self._make_order(1, BuildStatus.queued, 3)
        orders = [
            self._make_order(1, BuildStatus.building, 1),
            queued,
        ]
        result = get_next_queued_order(1, orders)
        assert result is queued

    def test_filters_by_factory_module_id(self):
        order_for_other_factory = self._make_order(2, BuildStatus.queued, 1)
        orders = [order_for_other_factory]
        result = get_next_queued_order(1, orders)  # looking for factory 1
        assert result is None
