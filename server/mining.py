"""
Mining system.

Handles mining laser cycling, ore extraction from asteroids, and cargo checks.
All functions accept explicit ORM objects — no FastAPI context needed.
"""

from __future__ import annotations

import logging
import math
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from server.models import Spaceship, ShipModule, CelestialObject

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Distance helper (repeated here to keep mining.py self-contained)
# ---------------------------------------------------------------------------


def _distance(
    ship: "Spaceship",
    asteroid: "CelestialObject",
) -> float:
    dx = ship.pos_x - asteroid.pos_x
    dy = ship.pos_y - asteroid.pos_y
    dz = ship.pos_z - asteroid.pos_z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


# ---------------------------------------------------------------------------
# Per-module mining cycle
# ---------------------------------------------------------------------------


def tick_mining_laser(
    ship: "Spaceship",
    module: "ShipModule",
    asteroid: Optional["CelestialObject"],
) -> dict:
    """
    Process one tick for a single active mining laser module.

    Returns a dict with keys:
        - ``ore_mined``      : float — ore actually added to cargo
        - ``ore_lost``       : float — ore that would have been mined but cargo was full
        - ``asteroid_done``  : bool  — True if the asteroid is now depleted
        - ``out_of_range``   : bool  — True if target is out of laser range
        - ``no_asteroid``    : bool  — True if no valid asteroid target

    When cargo is full the laser still cycles (capacitor consumed by the caller)
    but the asteroid ore is NOT extracted — it remains in the asteroid.

    The caller is responsible for:
        - Ensuring the module's capacitor was already drained before calling.
        - Committing database changes.
    """
    from server.models import ModuleType  # local import

    result = {
        "ore_mined": 0.0,
        "ore_lost": 0.0,
        "asteroid_done": False,
        "out_of_range": False,
        "no_asteroid": False,
    }

    if module.module_type not in (ModuleType.mining_laser, ModuleType.strip_miner):
        return result

    if asteroid is None:
        result["no_asteroid"] = True
        return result

    if asteroid.ore_remaining <= 0.0:
        result["asteroid_done"] = True
        return result

    # Range check
    distance = _distance(ship, asteroid)
    if distance > module.mining_range:
        result["out_of_range"] = True
        return result

    # Determine available cargo space
    cargo_cap = ship.cargo_capacity()
    available_space = cargo_cap - ship.ore

    yield_amount = min(module.mining_yield, asteroid.ore_remaining)

    if available_space <= 0.0:
        # Cargo full — laser cycles (cap already drained) but asteroid ore is preserved
        result["ore_lost"] = yield_amount
    else:
        ore_added = min(yield_amount, available_space)
        ore_lost = yield_amount - ore_added

        ship.ore += ore_added
        asteroid.ore_remaining -= ore_added
        asteroid.ore_remaining = max(0.0, asteroid.ore_remaining)

        result["ore_mined"] = ore_added
        result["ore_lost"] = ore_lost

    if asteroid.ore_remaining <= 0.0:
        result["asteroid_done"] = True

    return result


# ---------------------------------------------------------------------------
# Ore transfer
# ---------------------------------------------------------------------------


def tick_ore_transfer(
    source: "Spaceship",
    target: "Spaceship",
    transfer_rate: float = 100.0,
    transfer_range: float = 100.0,
) -> dict:
    """
    Transfer ore from ``source`` to ``target`` for one tick.

    Requirements (checked here; return early with ``error`` key on failure):
        - Target must have a Resource Drop-off module.
        - Both ships within ``transfer_range`` metres.
        - Source must have ore.
        - Target cargo must not be full.

    Returns a dict with keys:
        - ``transferred``    : float — ore moved this tick
        - ``complete``       : bool  — True if source is now empty or target is full
        - ``error``          : Optional[str] — human-readable failure reason
    """
    result: dict = {"transferred": 0.0, "complete": False, "error": None}

    # Target must have a drop-off module
    if not target.has_dropoff():
        result["error"] = "target has no Resource Drop-off module"
        return result

    # Range check
    dx = source.pos_x - target.pos_x
    dy = source.pos_y - target.pos_y
    dz = source.pos_z - target.pos_z
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    if distance > transfer_range:
        result["error"] = f"ships are {distance:.0f} m apart, maximum {transfer_range:.0f} m"
        return result

    # Check cargo state
    if source.ore <= 0.0:
        result["complete"] = True
        return result

    target_cargo_cap = target.cargo_capacity()
    target_space = target_cargo_cap - target.ore
    if target_space <= 0.0:
        result["complete"] = True
        return result

    amount = min(transfer_rate, source.ore, target_space)
    source.ore -= amount
    target.ore += amount
    result["transferred"] = amount

    # Transfer is complete when source is empty or target is full
    if source.ore <= 0.0 or (target_cargo_cap - target.ore) < 1e-3:
        result["complete"] = True

    return result
