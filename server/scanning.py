"""
Scanning and detection system.

Handles:
  - Passive detector cycling and range calculations
  - Active scanner cycling and detail level resolution
  - Scan-reveal logic (scanners are detectable)
  - Default visibility (no sensors)
  - Fog-of-war detail level constants
"""

from __future__ import annotations

import logging
import math
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from server.models import Spaceship, ShipModule, CelestialObject

from server.models import DETECTION_REFERENCE_SIGNATURE, ModuleType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detail level constants
# ---------------------------------------------------------------------------

DETAIL_UNKNOWN = 0         # not detected
DETAIL_CONTACT = 1         # position only
DETAIL_CLASSIFICATION = 2  # class / type + position + velocity
DETAIL_IDENTIFICATION = 3  # name, owner, class + pos, vel, heading
DETAIL_DETAILED = 4        # full loadout, cargo, capacitor, orders

# Active scan range thresholds (metres)
SCAN_DETAIL_THRESHOLDS = [
    (50_000, DETAIL_DETAILED),        # 0 – 50 km
    (100_000, DETAIL_IDENTIFICATION), # 50 – 100 km
    (150_000, DETAIL_CLASSIFICATION), # 100 – 150 km
    (200_000, DETAIL_CONTACT),        # 150 – 200 km
    # beyond 200 km: not detected by scan
]

# Scan reveal: passive detectors within this range detect the scanning ship
SCAN_REVEAL_RANGE: float = 100_000.0  # 100 km

# Default (no-sensor) visibility
DEFAULT_LEVEL2_RANGE: float = 1_000.0   # 1 km
DEFAULT_LEVEL3_RANGE: float = 100.0     # 100 m


# ---------------------------------------------------------------------------
# Range helpers
# ---------------------------------------------------------------------------


def _dist(ax: float, ay: float, az: float,
          bx: float, by: float, bz: float) -> float:
    dx, dy, dz = ax - bx, ay - by, az - bz
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def passive_detection_range(
    base_range: float,
    target_signature_radius: float,
) -> float:
    """
    Effective passive detection range for a target with the given signature radius.

        effective_range = base_range * (target_sig / REFERENCE_SIG)

    Reference signature is 300 m (frigate), which gives exactly base_range.
    """
    return base_range * (target_signature_radius / DETECTION_REFERENCE_SIGNATURE)


def active_scan_detail_level(distance: float) -> int:
    """
    Return the scan detail level for a target at ``distance`` metres.
    Returns DETAIL_UNKNOWN if outside scan range.
    """
    for threshold, level in SCAN_DETAIL_THRESHOLDS:
        if distance <= threshold:
            return level
    return DETAIL_UNKNOWN


def default_visibility_level(distance: float) -> int:
    """
    Detail level available without any scanner or detector modules.
    """
    if distance <= DEFAULT_LEVEL3_RANGE:
        return DETAIL_IDENTIFICATION
    if distance <= DEFAULT_LEVEL2_RANGE:
        return DETAIL_CLASSIFICATION
    return DETAIL_UNKNOWN


# ---------------------------------------------------------------------------
# Passive detection tick
# ---------------------------------------------------------------------------


class DetectionResult:
    """Outcome of running one passive detector cycle."""

    __slots__ = ("new_contacts", "scan_reveal_received")

    def __init__(self) -> None:
        self.new_contacts: list[dict] = []      # list of detected objects
        self.scan_reveal_received: bool = False


def tick_passive_detector(
    detector_ship: "Spaceship",
    detector_module: "ShipModule",
    all_ships: list["Spaceship"],
    all_objects: list["CelestialObject"],
) -> DetectionResult:
    """
    Run one passive detector cycle for a single detector module.

    Checks all other ships and celestial objects against the effective
    detection range.  The caller is responsible for verifying that the
    module's cycle counter has fired before calling.

    Returns a DetectionResult listing newly detected items.
    """
    result = DetectionResult()

    if detector_module.module_type not in (ModuleType.passive_detector, ModuleType.starter_passive_detector):
        return result
    if not detector_module.active:
        return result

    base_range = detector_module.detection_range

    # Detect other ships
    for ship in all_ships:
        if ship.id == detector_ship.id:
            continue
        if ship.is_docked():
            continue  # docked ships are hidden
        distance = _dist(
            detector_ship.pos_x, detector_ship.pos_y, detector_ship.pos_z,
            ship.pos_x, ship.pos_y, ship.pos_z,
        )
        effective_range = passive_detection_range(base_range, ship.effective_signature_radius())
        if distance <= effective_range:
            result.new_contacts.append({
                "type": "ship",
                "id": ship.id,
                "distance": distance,
                "detail": DETAIL_CONTACT,
                "pos_x": ship.pos_x,
                "pos_y": ship.pos_y,
                "pos_z": ship.pos_z,
            })

    # Detect celestial objects (asteroids etc.) at contact level
    for obj in all_objects:
        distance = _dist(
            detector_ship.pos_x, detector_ship.pos_y, detector_ship.pos_z,
            obj.pos_x, obj.pos_y, obj.pos_z,
        )
        # Use a fixed signature radius for celestial objects (large = always detectable nearby)
        obj_signature = 500.0
        effective_range = passive_detection_range(base_range, obj_signature)
        if distance <= effective_range:
            result.new_contacts.append({
                "type": "object",
                "id": obj.id,
                "object_type": obj.object_type.value,
                "distance": distance,
                "detail": DETAIL_CONTACT,
                "pos_x": obj.pos_x,
                "pos_y": obj.pos_y,
                "pos_z": obj.pos_z,
            })

    return result


# ---------------------------------------------------------------------------
# Active scan tick
# ---------------------------------------------------------------------------


class ScanResult:
    """Outcome of running one active scanner cycle."""

    __slots__ = ("contacts",)

    def __init__(self) -> None:
        self.contacts: list[dict] = []  # all detectable objects with detail levels


def tick_active_scanner(
    scanning_ship: "Spaceship",
    scanner_module: "ShipModule",
    all_ships: list["Spaceship"],
    all_objects: list["CelestialObject"],
) -> ScanResult:
    """
    Run one active scanner cycle.

    Reveals all ships and celestial objects within the scanner's range,
    with decreasing detail at longer distances.

    The caller is responsible for:
      1. Verifying the module cycle counter has fired.
      2. Draining the capacitor before calling.
      3. Generating scan_detected events for nearby ships.
    """
    result = ScanResult()

    if scanner_module.module_type != ModuleType.scanner:
        return result
    if not scanner_module.active:
        return result

    scan_range = scanner_module.scan_range

    # Scan other ships
    for ship in all_ships:
        if ship.id == scanning_ship.id:
            continue
        if ship.is_docked():
            continue
        distance = _dist(
            scanning_ship.pos_x, scanning_ship.pos_y, scanning_ship.pos_z,
            ship.pos_x, ship.pos_y, ship.pos_z,
        )
        if distance > scan_range:
            continue
        detail = active_scan_detail_level(distance)
        if detail == DETAIL_UNKNOWN:
            continue

        contact: dict = {
            "type": "ship",
            "id": ship.id,
            "distance": distance,
            "detail": detail,
            "pos_x": ship.pos_x,
            "pos_y": ship.pos_y,
            "pos_z": ship.pos_z,
        }
        if detail >= DETAIL_CLASSIFICATION:
            contact["ship_class"] = ship.ship_class.value
            contact["vel_x"] = ship.vel_x
            contact["vel_y"] = ship.vel_y
            contact["vel_z"] = ship.vel_z
        if detail >= DETAIL_IDENTIFICATION:
            contact["name"] = ship.name
            contact["owner_id"] = ship.user_id
        if detail >= DETAIL_DETAILED:
            contact["ore"] = ship.ore
            contact["capacitor"] = ship.capacitor
            contact["max_capacitor"] = ship.max_capacitor

        result.contacts.append(contact)

    # Scan celestial objects
    for obj in all_objects:
        distance = _dist(
            scanning_ship.pos_x, scanning_ship.pos_y, scanning_ship.pos_z,
            obj.pos_x, obj.pos_y, obj.pos_z,
        )
        if distance > scan_range:
            continue
        detail = active_scan_detail_level(distance)
        if detail == DETAIL_UNKNOWN:
            continue

        contact = {
            "type": "object",
            "id": obj.id,
            "object_type": obj.object_type.value,
            "distance": distance,
            "detail": detail,
            "pos_x": obj.pos_x,
            "pos_y": obj.pos_y,
            "pos_z": obj.pos_z,
        }
        if detail >= DETAIL_CLASSIFICATION:
            contact["ore_remaining"] = obj.ore_remaining

        result.contacts.append(contact)

    return result


# ---------------------------------------------------------------------------
# Scan reveal (passive detectors detecting the scanner)
# ---------------------------------------------------------------------------


def get_ships_that_detect_scan(
    scanning_ship: "Spaceship",
    all_ships: list["Spaceship"],
) -> list["Spaceship"]:
    """
    Return a list of ships that can passively detect the active scan.

    Any ship with a passive detector module within SCAN_REVEAL_RANGE of the
    scanning ship can detect the scan as a Level 2 (Classification) contact.
    """
    detecting_ships = []
    for ship in all_ships:
        if ship.id == scanning_ship.id:
            continue
        if ship.is_docked():
            continue
        distance = _dist(
            scanning_ship.pos_x, scanning_ship.pos_y, scanning_ship.pos_z,
            ship.pos_x, ship.pos_y, ship.pos_z,
        )
        if distance > SCAN_REVEAL_RANGE:
            continue
        # Check if the ship has an active passive detector
        has_detector = any(
            m.module_type in (ModuleType.passive_detector, ModuleType.starter_passive_detector) and m.active
            for m in ship.modules
        )
        if has_detector:
            detecting_ships.append(ship)
    return detecting_ships
