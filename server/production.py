"""
Production system.

Handles factory build queues, ore consumption at build start, capacitor drain
per tick, pausing/resuming on cap depletion, and new ship spawning.
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from server.models import Spaceship, ShipModule, BuildOrder

from server.models import (
    BUILD_COSTS,
    DEFAULT_AUTOPILOT_PROFILES,
    FACTION_BUILD_MODIFIERS,
    FACTION_SHIP_NAMES,
    FACTORY_REQUIREMENTS,
    CLASS_ORDER,
    BuildStatus,
    ShipClass,
    spawn_new_ship,
)

logger = logging.getLogger(__name__)

# Factory capacitor drain per tick (while building)
FACTORY_CAP_PER_TICK: float = 100.0


# ---------------------------------------------------------------------------
# Faction-aware cost helpers
# ---------------------------------------------------------------------------


def get_faction_adjusted_cost(
    blueprint: ShipClass,
    faction: Optional[str] = None,
) -> dict:
    """
    Return the build cost dict (ore, ticks) for a blueprint, adjusted for
    faction modifiers.  If faction is None or has no modifiers, the base
    BUILD_COSTS are returned unchanged.
    """
    cost = BUILD_COSTS.get(blueprint.value)
    if cost is None:
        return {}
    ore_cost = cost["ore"]
    ticks = cost["ticks"]

    if faction and faction in FACTION_BUILD_MODIFIERS:
        faction_mods = FACTION_BUILD_MODIFIERS[faction]
        class_mods = faction_mods.get(blueprint.value, {"ore_mult": 1.0, "time_mult": 1.0})
        ore_cost = int(ore_cost * class_mods["ore_mult"])
        ticks = int(ticks * class_mods["time_mult"])

    return {"ore": ore_cost, "ticks": ticks}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def can_factory_build(factory_module: "ShipModule", blueprint: ShipClass) -> tuple[bool, str]:
    """
    Check whether ``factory_module`` is capable of building ``blueprint``.

    Returns (ok, reason).  ``reason`` is empty when ok is True.
    """
    from server.models import ModuleType  # local import

    if factory_module.module_type != ModuleType.factory:
        return False, "module is not a factory"

    required_vol = FACTORY_REQUIREMENTS.get(blueprint.value)
    if required_vol is None:
        return False, f"no build cost defined for {blueprint.value}"

    if factory_module.volume < required_vol:
        return (
            False,
            f"factory volume {factory_module.volume} m³ is below minimum "
            f"{required_vol} m³ required for {blueprint.value}",
        )

    return True, ""


def can_ship_build(
    ship: "Spaceship",
    blueprint: ShipClass,
    factory_module: "ShipModule",
    faction: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Comprehensive check: does the ship have the ore and a capable factory?

    If ``faction`` is provided, faction-adjusted build costs are used for
    the ore sufficiency check.

    Returns (ok, reason).
    """
    ok, reason = can_factory_build(factory_module, blueprint)
    if not ok:
        return False, reason

    cost = get_faction_adjusted_cost(blueprint, faction)
    if not cost:
        return False, f"no build cost defined for {blueprint.value}"

    if ship.ore < cost["ore"]:
        return (
            False,
            f"insufficient ore: have {ship.ore:.0f}, need {cost['ore']}",
        )

    return True, ""


# ---------------------------------------------------------------------------
# Start a build
# ---------------------------------------------------------------------------


def start_build(
    ship: "Spaceship",
    factory_module: "ShipModule",
    blueprint: ShipClass,
    faction: Optional[str] = None,
) -> "BuildOrder":
    """
    Create a BuildOrder and deduct ore immediately.

    If ``faction`` is provided, faction-adjusted build costs are applied
    (modified ore cost and build time).

    Does NOT add the order to the session — caller must do that.
    Raises ValueError if preconditions are not met.
    """
    from server.models import BuildOrder  # local import to avoid circular

    ok, reason = can_ship_build(ship, blueprint, factory_module, faction=faction)
    if not ok:
        raise ValueError(reason)

    cost = get_faction_adjusted_cost(blueprint, faction)
    ship.ore -= cost["ore"]  # ore consumed immediately

    order = BuildOrder(
        ship_id=ship.id,
        factory_module_id=factory_module.id,
        blueprint=blueprint,
        status=BuildStatus.queued,
        ore_cost=cost["ore"],
        ticks_remaining=cost["ticks"],
        total_ticks=cost["ticks"],
    )
    return order


# ---------------------------------------------------------------------------
# Per-tick production processing
# ---------------------------------------------------------------------------


def tick_build_order(
    ship: "Spaceship",
    order: "BuildOrder",
) -> dict:
    """
    Advance one build order by one tick.

    Drains FACTORY_CAP_PER_TICK from the ship's capacitor.  If the ship
    lacks the energy, the order is paused (not cancelled).

    Returns a dict:
        - ``completed``   : bool  — build finished this tick
        - ``paused``      : bool  — paused due to insufficient cap
        - ``unpaused``    : bool  — resumed (was paused, now has cap)
        - ``new_ship``    : Optional[Spaceship] — spawned ship if completed
    """
    result: dict = {
        "completed": False,
        "paused": False,
        "unpaused": False,
        "new_ship": None,
    }

    if order.status == BuildStatus.completed:
        return result

    # Check cap availability
    if ship.capacitor < FACTORY_CAP_PER_TICK:
        if order.status == BuildStatus.building:
            order.status = BuildStatus.paused
            result["paused"] = True
        return result

    # If we were paused and now have cap, resume
    if order.status == BuildStatus.paused:
        order.status = BuildStatus.building
        result["unpaused"] = True

    # Drain cap and advance build
    ship.capacitor -= FACTORY_CAP_PER_TICK
    order.ticks_remaining -= 1

    if order.ticks_remaining <= 0:
        order.ticks_remaining = 0
        order.status = BuildStatus.completed
        result["completed"] = True
        result["new_ship"] = spawn_new_ship(
            blueprint=order.blueprint,
            builder=ship,
            current_tick=0,  # tick is injected by the tick loop when creating Event
        )

        # Default newly built ships to autopilot mode
        new_ship = result["new_ship"]
        new_ship.autopilot_mode = "active"
        new_ship.autopilot_profile = DEFAULT_AUTOPILOT_PROFILES.get(order.blueprint.value)

    return result


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------


def get_next_queued_order(
    factory_module_id: int,
    build_orders: list["BuildOrder"],
) -> Optional["BuildOrder"]:
    """
    Return the next queued (not yet started) order for a given factory module,
    or None if all orders are building / completed.
    """
    for order in build_orders:
        if (
            order.factory_module_id == factory_module_id
            and order.status == BuildStatus.queued
        ):
            return order
    return None
