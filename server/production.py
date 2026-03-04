"""
Production system.

Handles factory build queues, ore consumption at build start, capacitor drain
per tick, pausing/resuming on cap depletion, and new ship spawning.

Factory presets have two independent multiplier stats:
- **Speed**: factory_speed_mult (<1 = faster, >1 = slower)
- **Efficiency**: factory_efficiency_mult (<1 = cheaper, >1 = more ore)

Docking bay class gates *what* can be built (bay must accept the ship class).
"""

from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from server.models import Spaceship, ShipModule, BuildOrder

from server.models import (
    BUILD_COSTS,
    DOCKING_CLASS_INDEX,
    FACTORY_TYPES,
    FACTION_BUILD_MODIFIERS,
    FACTION_SHIP_NAMES,
    CLASS_ORDER,
    BuildStatus,
    ModuleType,
    ShipClass,
    spawn_new_ship,
)

logger = logging.getLogger(__name__)

# Factory capacitor drain per tick (while building)
FACTORY_CAP_PER_TICK: float = 100.0

# Clamps for factory multipliers
SPEED_MULT_MIN = 0.5    # max 2x faster than base
SPEED_MULT_MAX = 3.0    # max 3x slower than base
EFFICIENCY_MULT_MIN = 0.75  # max 25% cheaper than base
EFFICIENCY_MULT_MAX = 2.0   # max 2x more expensive


# ---------------------------------------------------------------------------
# Factory multiplier helpers
# ---------------------------------------------------------------------------


def factory_speed_multiplier(factory_module: "ShipModule") -> float:
    """
    Build time multiplier from the factory module's preset.
    < 1.0 = faster, > 1.0 = slower.
    """
    return max(SPEED_MULT_MIN, min(SPEED_MULT_MAX, factory_module.factory_speed_mult))


def factory_efficiency_multiplier(factory_module: "ShipModule") -> float:
    """
    Ore cost multiplier from the factory module's preset.
    < 1.0 = cheaper, > 1.0 = more expensive.
    """
    return max(EFFICIENCY_MULT_MIN, min(EFFICIENCY_MULT_MAX, factory_module.factory_efficiency_mult))


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


def get_factory_adjusted_cost(
    blueprint: ShipClass,
    factory_module: "ShipModule",
    faction: Optional[str] = None,
) -> dict:
    """
    Return build cost adjusted for both faction AND factory preset multipliers.
    Factory speed/efficiency are independent multipliers on top of faction mods.
    """
    cost = get_faction_adjusted_cost(blueprint, faction)
    if not cost:
        return {}

    speed_mult = factory_speed_multiplier(factory_module)
    eff_mult = factory_efficiency_multiplier(factory_module)

    return {
        "ore": max(1, int(cost["ore"] * eff_mult)),
        "ticks": max(1, int(cost["ticks"] * speed_mult)),
    }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def can_factory_build(
    ship: "Spaceship",
    factory_module: "ShipModule",
    blueprint: ShipClass,
) -> tuple[bool, str]:
    """
    Check whether the ship can build this blueprint.

    - Module must be a factory type.
    - Factory's max_class must cover the blueprint.
    - Ship must have a docking bay that can accept the built ship class.

    Returns (ok, reason).
    """
    if factory_module.module_type.value not in FACTORY_TYPES:
        return False, "module is not a factory"

    # Factory class gate
    factory_max = factory_module.factory_max_class
    if factory_max is None:
        return False, "factory has no max_class set"
    factory_idx = DOCKING_CLASS_INDEX.get(factory_max, -1)
    blueprint_idx = DOCKING_CLASS_INDEX.get(blueprint.value, 999)
    if factory_idx < blueprint_idx:
        return (
            False,
            f"factory can only build up to {factory_max}, "
            f"cannot build {blueprint.value}",
        )

    # Docking bay class gate
    if not ship.can_dock_ship_class(blueprint.value):
        return (
            False,
            f"no docking bay can accept {blueprint.value} class ships",
        )

    return True, ""


def can_ship_build(
    ship: "Spaceship",
    blueprint: ShipClass,
    factory_module: "ShipModule",
    faction: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Comprehensive check: factory can build class, docking bay accepts class, enough ore?

    Ore cost accounts for factory efficiency.
    """
    ok, reason = can_factory_build(ship, factory_module, blueprint)
    if not ok:
        return False, reason

    cost = get_factory_adjusted_cost(blueprint, factory_module, faction)
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

    Build time and ore cost are adjusted for factory size (speed & efficiency).
    If ``faction`` is provided, faction modifiers are applied first.

    Does NOT add the order to the session — caller must do that.
    Raises ValueError if preconditions are not met.
    """
    from server.models import BuildOrder  # local import to avoid circular

    ok, reason = can_ship_build(ship, blueprint, factory_module, faction=faction)
    if not ok:
        raise ValueError(reason)

    cost = get_factory_adjusted_cost(blueprint, factory_module, faction)
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
            built_by_user_id=ship.user_id,
        )

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
