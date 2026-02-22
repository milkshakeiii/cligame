"""
Unit tests for server/production.py

Covers:
- can_factory_build: module type check, volume check
- can_ship_build: ore check
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
    get_next_queued_order,
    start_build,
    tick_build_order,
    FACTORY_CAP_PER_TICK,
)
from tests.conftest import make_test_ship, add_module_to_ship


# ---------------------------------------------------------------------------
# can_factory_build
# ---------------------------------------------------------------------------


class TestCanFactoryBuild:
    def test_non_factory_module_fails(self):
        ship = make_test_ship(ShipClass.frigate)
        engine = add_module_to_ship(ship, ModuleType.engine, 6_000)
        ok, reason = can_factory_build(engine, ShipClass.strike_craft)
        assert ok is False
        assert "not a factory" in reason

    def test_factory_too_small_fails(self):
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 100)  # too small
        ok, reason = can_factory_build(factory, ShipClass.strike_craft)
        assert ok is False
        assert "below minimum" in reason

    def test_factory_exactly_at_minimum_succeeds(self):
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 500)  # min for strike_craft
        ok, reason = can_factory_build(factory, ShipClass.strike_craft)
        assert ok is True
        assert reason == ""

    def test_factory_large_enough_for_corvette(self):
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 5_000)
        ok, _ = can_factory_build(factory, ShipClass.corvette)
        assert ok is True

    def test_factory_too_small_for_corvette(self):
        ship = make_test_ship(ShipClass.frigate)
        factory = add_module_to_ship(ship, ModuleType.factory, 500)  # only for strike_craft
        ok, reason = can_factory_build(factory, ShipClass.corvette)
        assert ok is False

    def test_mothership_not_buildable(self):
        """Mothership has no build cost — should fail."""
        ship = make_test_ship(ShipClass.mothership)
        factory = add_module_to_ship(ship, ModuleType.factory, 2_000_000)
        ok, reason = can_factory_build(factory, ShipClass.mothership)
        assert ok is False


# ---------------------------------------------------------------------------
# can_ship_build
# ---------------------------------------------------------------------------


class TestCanShipBuild:
    def test_insufficient_ore_fails(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.ore = 100.0  # less than 200 needed for strike_craft
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        ok, reason = can_ship_build(ship, ShipClass.strike_craft, factory)
        assert ok is False
        assert "insufficient ore" in reason.lower()

    def test_sufficient_ore_succeeds(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.ore = 200.0
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        ok, reason = can_ship_build(ship, ShipClass.strike_craft, factory)
        assert ok is True

    def test_factory_check_takes_precedence(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.ore = 10_000.0
        factory = add_module_to_ship(ship, ModuleType.factory, 100)  # too small
        ok, reason = can_ship_build(ship, ShipClass.strike_craft, factory)
        assert ok is False


# ---------------------------------------------------------------------------
# start_build
# ---------------------------------------------------------------------------


class TestStartBuild:
    def test_deducts_ore_immediately(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.ore = 500.0
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        factory.id = 1
        ship.id = 1

        start_build(ship, factory, ShipClass.strike_craft)

        assert ship.ore == pytest.approx(500.0 - 200.0)  # 200 ore for strike_craft

    def test_returns_build_order(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.ore = 500.0
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        factory.id = 1
        ship.id = 1

        order = start_build(ship, factory, ShipClass.strike_craft)

        assert order.blueprint == ShipClass.strike_craft
        assert order.status == BuildStatus.queued
        assert order.ticks_remaining == BUILD_COSTS["strike_craft"]["ticks"]
        assert order.total_ticks == BUILD_COSTS["strike_craft"]["ticks"]
        assert order.ore_cost == BUILD_COSTS["strike_craft"]["ore"]

    def test_raises_when_insufficient_ore(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.ore = 0.0
        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        factory.id = 1
        ship.id = 1

        with pytest.raises(ValueError, match="insufficient ore"):
            start_build(ship, factory, ShipClass.strike_craft)

    def test_raises_when_factory_too_small(self):
        ship = make_test_ship(ShipClass.frigate)
        ship.ore = 10_000.0
        factory = add_module_to_ship(ship, ModuleType.factory, 100)  # too small
        factory.id = 1
        ship.id = 1

        with pytest.raises(ValueError):
            start_build(ship, factory, ShipClass.strike_craft)


# ---------------------------------------------------------------------------
# tick_build_order
# ---------------------------------------------------------------------------


class TestTickBuildOrder:
    def _make_ship_and_order(self, blueprint=ShipClass.strike_craft, ore=None):
        ship = make_test_ship(ShipClass.frigate)
        ship.id = 1
        ship.max_capacitor = 11_000.0
        ship.capacitor = 11_000.0  # full cap

        factory = add_module_to_ship(ship, ModuleType.factory, 500)
        factory.id = 1

        ship.ore = ore or BUILD_COSTS[blueprint.value]["ore"]

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
