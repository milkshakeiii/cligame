"""
Capacitor (energy) system.

Implements the EVE Online-inspired regen curve and module drain/depletion logic.
All functions are pure or take explicit session parameters — no FastAPI context.
"""

from __future__ import annotations

import math
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from server.models import Spaceship, ShipModule

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regen formula
# ---------------------------------------------------------------------------


def capacitor_regen_rate(capacitor: float, max_capacitor: float) -> float:
    """
    Calculate the capacitor regen rate for one tick.

    Formula (EVE-inspired, peaks near 25 % capacity):
        regen = peak_regen * sqrt(cap / max_cap) * (1 - cap / max_cap)
        peak_regen = max_capacitor / 25

    Edge cases:
    - Returns 0 if max_capacitor <= 0.
    - Clamps cap/max to [0, 1] to avoid math errors.
    """
    if max_capacitor <= 0.0:
        return 0.0

    fraction = max(0.0, min(1.0, capacitor / max_capacitor))
    if fraction <= 0.0 or fraction >= 1.0:
        return 0.0

    peak_regen = max_capacitor / 25.0
    return peak_regen * math.sqrt(fraction) * (1.0 - fraction)


def apply_regen(ship: "Spaceship") -> None:
    """
    Regenerate capacitor for one tick.

    Mutates ship.capacitor in place.  Clamps to [0, max_capacitor].
    """
    regen = capacitor_regen_rate(ship.capacitor, ship.max_capacitor)
    ship.capacitor = min(ship.max_capacitor, ship.capacitor + regen)


# ---------------------------------------------------------------------------
# Module drain
# ---------------------------------------------------------------------------


def drain_module(ship: "Spaceship", module: "ShipModule") -> bool:
    """
    Drain capacitor for one module cycle.

    Returns True if the drain succeeded (ship had enough cap).
    Returns False if the cap was insufficient — the caller should deactivate
    the module.

    Engines are exempt from capacitor drain (free in Phase 1).
    """
    from server.models import ModuleType  # local import to avoid circular deps

    if module.module_type == ModuleType.engine:
        return True
    if module.capacitor_per_cycle <= 0.0:
        return True

    if ship.capacitor >= module.capacitor_per_cycle:
        ship.capacitor -= module.capacitor_per_cycle
        return True

    return False


# ---------------------------------------------------------------------------
# Depletion check
# ---------------------------------------------------------------------------


def check_depletion(ship: "Spaceship") -> bool:
    """
    Check if the ship's capacitor has been depleted.

    If depleted, deactivate all non-engine modules and clamp cap to 0.

    Returns True if cap was depleted (caller should emit a cap_depleted event).
    """
    from server.models import ModuleType  # local import to avoid circular deps

    if ship.capacitor <= 0.0:
        ship.capacitor = 0.0
        depleted = False
        for module in ship.modules:
            if module.active and module.module_type != ModuleType.engine:
                module.active = False
                depleted = True
        return depleted
    return False
