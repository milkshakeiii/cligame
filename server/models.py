"""
SQLModel ORM models for the space simulation game.

Covers: GameState, User, Spaceship, ShipModule, MovementOrder, BuildOrder,
        CelestialObject, Event
"""

import math
import random
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from sqlmodel import Field, Relationship, SQLModel


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class ShipClass(str, Enum):
    strike_craft = "strike_craft"
    corvette = "corvette"
    frigate = "frigate"
    destroyer = "destroyer"
    cruiser = "cruiser"
    mothership = "mothership"


class DamageType(str, Enum):
    kinetic = "kinetic"
    thermal = "thermal"
    explosive = "explosive"


class LockStatus(str, Enum):
    locking = "locking"
    locked = "locked"
    broken = "broken"


class ModuleType(str, Enum):
    engine = "engine"
    reactor = "reactor"
    cargo_bay = "cargo_bay"
    docking_bay = "docking_bay"
    dropoff = "dropoff"
    factory = "factory"
    mining_laser = "mining_laser"
    scanner = "scanner"
    passive_detector = "passive_detector"
    # --- Phase 4: Turrets ---
    small_turret_kinetic = "small_turret_kinetic"
    small_turret_thermal = "small_turret_thermal"
    medium_turret_kinetic = "medium_turret_kinetic"
    medium_turret_thermal = "medium_turret_thermal"
    large_turret_kinetic = "large_turret_kinetic"
    large_turret_thermal = "large_turret_thermal"
    # --- Phase 4: Missile launchers ---
    light_missile_launcher = "light_missile_launcher"
    heavy_missile_launcher = "heavy_missile_launcher"
    torpedo_launcher = "torpedo_launcher"
    # --- Phase 4: Shield modules ---
    small_shield_extender = "small_shield_extender"
    medium_shield_extender = "medium_shield_extender"
    large_shield_extender = "large_shield_extender"
    small_shield_hardener_kinetic = "small_shield_hardener_kinetic"
    small_shield_hardener_thermal = "small_shield_hardener_thermal"
    small_shield_hardener_explosive = "small_shield_hardener_explosive"
    medium_shield_hardener_kinetic = "medium_shield_hardener_kinetic"
    medium_shield_hardener_thermal = "medium_shield_hardener_thermal"
    medium_shield_hardener_explosive = "medium_shield_hardener_explosive"
    large_shield_hardener_kinetic = "large_shield_hardener_kinetic"
    large_shield_hardener_thermal = "large_shield_hardener_thermal"
    large_shield_hardener_explosive = "large_shield_hardener_explosive"
    small_shield_booster = "small_shield_booster"
    medium_shield_booster = "medium_shield_booster"
    large_shield_booster = "large_shield_booster"
    # --- Phase 4: Armor modules ---
    small_armor_plate = "small_armor_plate"
    medium_armor_plate = "medium_armor_plate"
    large_armor_plate = "large_armor_plate"
    small_armor_hardener_kinetic = "small_armor_hardener_kinetic"
    small_armor_hardener_thermal = "small_armor_hardener_thermal"
    small_armor_hardener_explosive = "small_armor_hardener_explosive"
    medium_armor_hardener_kinetic = "medium_armor_hardener_kinetic"
    medium_armor_hardener_thermal = "medium_armor_hardener_thermal"
    medium_armor_hardener_explosive = "medium_armor_hardener_explosive"
    large_armor_hardener_kinetic = "large_armor_hardener_kinetic"
    large_armor_hardener_thermal = "large_armor_hardener_thermal"
    large_armor_hardener_explosive = "large_armor_hardener_explosive"
    small_armor_repairer = "small_armor_repairer"
    medium_armor_repairer = "medium_armor_repairer"
    large_armor_repairer = "large_armor_repairer"
    # --- Phase 5: Research & unlocked modules ---
    research_module = "research_module"
    strip_miner = "strip_miner"
    enhanced_docking_bay = "enhanced_docking_bay"
    fortress = "fortress"


class OrderType(str, Enum):
    approach = "approach"
    orbit = "orbit"
    keep_distance = "keep_distance"
    dock = "dock"
    stop = "stop"


class OrderStatus(str, Enum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class BuildStatus(str, Enum):
    queued = "queued"
    building = "building"
    paused = "paused"
    completed = "completed"


class CelestialType(str, Enum):
    asteroid = "asteroid"
    planet = "planet"
    station = "station"
    waypoint = "waypoint"
    wreck = "wreck"


class EventType(str, Enum):
    detection = "detection"
    scan_complete = "scan_complete"
    scan_detected = "scan_detected"
    mining = "mining"
    cargo_full = "cargo_full"
    asteroid_depleted = "asteroid_depleted"
    build_complete = "build_complete"
    build_paused = "build_paused"
    order_complete = "order_complete"
    dock_complete = "dock_complete"
    cap_depleted = "cap_depleted"
    transfer_complete = "transfer_complete"
    # --- Phase 4: Combat events ---
    target_locked = "target_locked"
    target_lost = "target_lost"
    incoming_lock = "incoming_lock"
    weapon_hit = "weapon_hit"
    weapon_miss = "weapon_miss"
    incoming_damage = "incoming_damage"
    shield_depleted = "shield_depleted"
    armor_critical = "armor_critical"
    ship_destroyed = "ship_destroyed"
    you_destroyed = "you_destroyed"
    # --- Phase 5: Research events ---
    research_started = "research_started"
    research_complete = "research_complete"
    research_paused = "research_paused"


# ---------------------------------------------------------------------------
# Ship class constants
# ---------------------------------------------------------------------------

# These constants define per-class physics and resource parameters.
# Keys correspond to ShipClass enum values.
SHIP_CLASSES: Dict[str, dict] = {
    "strike_craft": {
        "volume": 100,
        "signature": 25,
        "base_cap": 50,
        "base_speed": 400,
        "accel_time": 8,
        "base_shield": 50,
        "base_armor": 100,
        "scan_resolution": 500,
        "base_lock_time": 3,
    },
    "corvette": {
        "volume": 2_000,
        "signature": 100,
        "base_cap": 200,
        "base_speed": 250,
        "accel_time": 12,
        "base_shield": 300,
        "base_armor": 600,
        "scan_resolution": 400,
        "base_lock_time": 5,
    },
    "frigate": {
        "volume": 20_000,
        "signature": 300,
        "base_cap": 1_000,
        "base_speed": 150,
        "accel_time": 20,
        "base_shield": 2_000,
        "base_armor": 4_000,
        "scan_resolution": 300,
        "base_lock_time": 8,
    },
    "destroyer": {
        "volume": 80_000,
        "signature": 600,
        "base_cap": 3_000,
        "base_speed": 100,
        "accel_time": 30,
        "base_shield": 8_000,
        "base_armor": 16_000,
        "scan_resolution": 250,
        "base_lock_time": 12,
    },
    "cruiser": {
        "volume": 250_000,
        "signature": 1_000,
        "base_cap": 8_000,
        "base_speed": 60,
        "accel_time": 45,
        "base_shield": 30_000,
        "base_armor": 60_000,
        "scan_resolution": 200,
        "base_lock_time": 18,
    },
    "mothership": {
        "volume": 2_000_000,
        "signature": 2_000,
        "base_cap": 25_000,
        "base_speed": 30,
        "accel_time": 60,
        "base_shield": 100_000,
        "base_armor": 200_000,
        "scan_resolution": 150,
        "base_lock_time": 30,
    },
}

# Shield base resistance profiles (fraction, 0.0 to 1.0)
SHIELD_BASE_RESISTS: Dict[str, float] = {
    "kinetic": 0.20,
    "thermal": 0.10,
    "explosive": 0.30,
}

# Armor base resistance profiles
ARMOR_BASE_RESISTS: Dict[str, float] = {
    "kinetic": 0.30,
    "thermal": 0.20,
    "explosive": 0.10,
}

# Max target locks per ship class (2 + class_index)
MAX_LOCKS: Dict[str, int] = {
    "strike_craft": 2,
    "corvette": 3,
    "frigate": 4,
    "destroyer": 5,
    "cruiser": 6,
    "mothership": 7,
}

# Minimum factory volume required to build each ship class (from SPEC.md)
FACTORY_REQUIREMENTS: dict[str, int] = {
    "strike_craft": 500,
    "corvette": 5_000,
    "frigate": 30_000,
    "destroyer": 100_000,
    "cruiser": 300_000,
}

# Build costs (ore, ticks) per ship class
BUILD_COSTS: Dict[str, dict] = {
    "strike_craft": {"ore": 200, "ticks": 120},
    "corvette": {"ore": 1_500, "ticks": 480},
    "frigate": {"ore": 10_000, "ticks": 1_800},
    "destroyer": {"ore": 50_000, "ticks": 5_400},
    "cruiser": {"ore": 200_000, "ticks": 18_000},
}

# ---------------------------------------------------------------------------
# Phase 5: Research / Tech Tree
# ---------------------------------------------------------------------------

# Research tier costs
RESEARCH_COSTS: Dict[int, dict] = {
    1: {"ore": 500, "ticks": 300},
    2: {"ore": 2_000, "ticks": 900},
    3: {"ore": 8_000, "ticks": 1_800},
    4: {"ore": 25_000, "ticks": 3_600},
}

# Tech tree: each node has an id, tier, prerequisites, and what it unlocks.
# "unlocks_modules" lists module_type values, "unlocks_ships" lists ship class values.
TECH_TREE: Dict[str, dict] = {
    "1a_medium_weapons": {
        "name": "Medium Weapons",
        "tier": 1,
        "prerequisites": [],
        "unlocks_modules": [
            "medium_turret_kinetic", "medium_turret_thermal",
            "heavy_missile_launcher",
        ],
        "unlocks_ships": [],
    },
    "1b_medium_defenses": {
        "name": "Medium Defenses",
        "tier": 1,
        "prerequisites": [],
        "unlocks_modules": [
            "medium_shield_extender",
            "medium_shield_hardener_kinetic", "medium_shield_hardener_thermal",
            "medium_shield_hardener_explosive", "medium_shield_booster",
            "medium_armor_plate",
            "medium_armor_hardener_kinetic", "medium_armor_hardener_thermal",
            "medium_armor_hardener_explosive", "medium_armor_repairer",
        ],
        "unlocks_ships": [],
    },
    "1c_destroyer_hull": {
        "name": "Destroyer Hull",
        "tier": 1,
        "prerequisites": [],
        "unlocks_modules": [],
        "unlocks_ships": ["destroyer"],
    },
    "2a_large_weapons": {
        "name": "Large Weapons",
        "tier": 2,
        "prerequisites": ["1a_medium_weapons"],
        "unlocks_modules": [
            "large_turret_kinetic", "large_turret_thermal",
            "torpedo_launcher",
        ],
        "unlocks_ships": [],
    },
    "2b_large_defenses": {
        "name": "Large Defenses",
        "tier": 2,
        "prerequisites": ["1b_medium_defenses"],
        "unlocks_modules": [
            "large_shield_extender",
            "large_shield_hardener_kinetic", "large_shield_hardener_thermal",
            "large_shield_hardener_explosive", "large_shield_booster",
            "large_armor_plate",
            "large_armor_hardener_kinetic", "large_armor_hardener_thermal",
            "large_armor_hardener_explosive", "large_armor_repairer",
        ],
        "unlocks_ships": [],
    },
    "2c_cruiser_hull": {
        "name": "Cruiser Hull",
        "tier": 2,
        "prerequisites": ["1c_destroyer_hull"],
        "unlocks_modules": [],
        "unlocks_ships": ["cruiser"],
    },
    "2d_advanced_mining": {
        "name": "Advanced Mining",
        "tier": 2,
        "prerequisites": [],
        "unlocks_modules": ["strip_miner"],
        "unlocks_ships": [],
    },
    "3a_advanced_weapons": {
        "name": "Advanced Weapons",
        "tier": 3,
        "prerequisites": ["2a_large_weapons"],
        "unlocks_modules": [],
        "unlocks_ships": [],
    },
    "3b_advanced_defenses": {
        "name": "Advanced Defenses",
        "tier": 3,
        "prerequisites": ["2b_large_defenses"],
        "unlocks_modules": [],
        "unlocks_ships": [],
    },
    "3c_capital_systems": {
        "name": "Capital Systems",
        "tier": 3,
        "prerequisites": ["2c_cruiser_hull"],
        "unlocks_modules": ["enhanced_docking_bay"],
        "unlocks_ships": [],
    },
    "4a_superweapons": {
        "name": "Superweapons",
        "tier": 4,
        "prerequisites": ["3a_advanced_weapons"],
        "unlocks_modules": [],
        "unlocks_ships": [],
    },
    "4b_fortress": {
        "name": "Fortress",
        "tier": 4,
        "prerequisites": ["3b_advanced_defenses", "3c_capital_systems"],
        "unlocks_modules": ["fortress"],
        "unlocks_ships": [],
    },
}

# Build a set of all modules/ships that require research (not available at start)
RESEARCH_GATED_MODULES: set[str] = set()
RESEARCH_GATED_SHIPS: set[str] = set()
for _node in TECH_TREE.values():
    RESEARCH_GATED_MODULES.update(_node["unlocks_modules"])
    RESEARCH_GATED_SHIPS.update(_node["unlocks_ships"])

# Reverse lookup: module_type -> tech_id required
MODULE_REQUIRED_TECH: Dict[str, str] = {}
SHIP_REQUIRED_TECH: Dict[str, str] = {}
for _tech_id, _node in TECH_TREE.items():
    for _mod in _node["unlocks_modules"]:
        MODULE_REQUIRED_TECH[_mod] = _tech_id
    for _ship in _node["unlocks_ships"]:
        SHIP_REQUIRED_TECH[_ship] = _tech_id


# Class ordering used for docking eligibility checks (smaller index = smaller class)
CLASS_ORDER: list[str] = [
    "strike_craft",
    "corvette",
    "frigate",
    "destroyer",
    "cruiser",
    "mothership",
]

# Reference engine fraction for max-speed calculations
REFERENCE_ENGINE_FRACTION: float = 0.30

# Fixed module volumes (m^3) for modules with a fixed size
MODULE_FIXED_VOLUMES: dict[str, int] = {
    "dropoff": 500,
    "mining_laser": 200,
    "scanner": 500,
    "passive_detector": 100,
    "research_module": 5_000,
    "strip_miner": 1_000,
    "fortress": 50_000,
}

# Module cycling parameters for non-passive modules
MODULE_PARAMS: Dict[str, dict] = {
    "mining_laser": {
        "cycle_time": 10,
        "cap_per_cycle": 50,
        "mining_yield": 10,
        "range": 500,
    },
    "factory": {
        "cycle_time": 1,
        "cap_per_cycle": 100,
    },
    "scanner": {
        "cycle_time": 30,
        "cap_per_cycle": 200,
        "scan_range": 200_000,  # 200 km in meters
    },
    "passive_detector": {
        "cycle_time": 5,
        "cap_per_cycle": 5,
        "base_detection_range": 50_000,  # 50 km in meters
    },
    "research_module": {
        "cycle_time": 1,
        "cap_per_cycle": 50,
    },
    "strip_miner": {
        "cycle_time": 15,
        "cap_per_cycle": 150,
        "mining_yield": 50,
        "range": 1_000,
    },
    "fortress": {
        "cycle_time": 1,
        "cap_per_cycle": 500,
    },
}

# Reference signature radius for passive detection range scaling
DETECTION_REFERENCE_SIGNATURE: float = 300.0  # frigate's sig radius


# ---------------------------------------------------------------------------
# Phase 4: Combat module constants
# ---------------------------------------------------------------------------

# Turret parameters keyed by module_type value
TURRET_PARAMS: Dict[str, dict] = {
    "small_turret_kinetic": {
        "volume": 50, "damage": 15, "damage_type": "kinetic",
        "cycle_time": 5, "cap_per_cycle": 10,
        "optimal_range": 5_000, "falloff": 3_000,
        "tracking_speed": 0.08, "sig_resolution": 40,
    },
    "small_turret_thermal": {
        "volume": 50, "damage": 15, "damage_type": "thermal",
        "cycle_time": 5, "cap_per_cycle": 10,
        "optimal_range": 5_000, "falloff": 3_000,
        "tracking_speed": 0.08, "sig_resolution": 40,
    },
    "medium_turret_kinetic": {
        "volume": 300, "damage": 80, "damage_type": "kinetic",
        "cycle_time": 8, "cap_per_cycle": 40,
        "optimal_range": 15_000, "falloff": 8_000,
        "tracking_speed": 0.03, "sig_resolution": 200,
    },
    "medium_turret_thermal": {
        "volume": 300, "damage": 80, "damage_type": "thermal",
        "cycle_time": 8, "cap_per_cycle": 40,
        "optimal_range": 15_000, "falloff": 8_000,
        "tracking_speed": 0.03, "sig_resolution": 200,
    },
    "large_turret_kinetic": {
        "volume": 2_000, "damage": 400, "damage_type": "kinetic",
        "cycle_time": 12, "cap_per_cycle": 150,
        "optimal_range": 40_000, "falloff": 20_000,
        "tracking_speed": 0.008, "sig_resolution": 800,
    },
    "large_turret_thermal": {
        "volume": 2_000, "damage": 400, "damage_type": "thermal",
        "cycle_time": 12, "cap_per_cycle": 150,
        "optimal_range": 40_000, "falloff": 20_000,
        "tracking_speed": 0.008, "sig_resolution": 800,
    },
}

# Missile launcher parameters keyed by module_type value
MISSILE_PARAMS: Dict[str, dict] = {
    "light_missile_launcher": {
        "volume": 100, "damage": 25, "damage_type": "explosive",
        "cycle_time": 10, "cap_per_cycle": 15,
        "range": 20_000, "missile_speed": 500, "max_flight_time": 40,
        "explosion_radius": 50, "explosion_velocity": 200,
    },
    "heavy_missile_launcher": {
        "volume": 500, "damage": 120, "damage_type": "explosive",
        "cycle_time": 15, "cap_per_cycle": 50,
        "range": 35_000, "missile_speed": 300, "max_flight_time": 117,
        "explosion_radius": 200, "explosion_velocity": 100,
    },
    "torpedo_launcher": {
        "volume": 3_000, "damage": 600, "damage_type": "explosive",
        "cycle_time": 20, "cap_per_cycle": 200,
        "range": 50_000, "missile_speed": 150, "max_flight_time": 333,
        "explosion_radius": 800, "explosion_velocity": 50,
    },
}

# Defensive module parameters keyed by module_type value
DEFENSIVE_MODULE_PARAMS: Dict[str, dict] = {
    # Shield extenders (passive — increase max shield HP and sig radius)
    "small_shield_extender": {
        "volume": 50, "shield_bonus": 30, "sig_radius_bonus": 5,
    },
    "medium_shield_extender": {
        "volume": 300, "shield_bonus": 200, "sig_radius_bonus": 30,
    },
    "large_shield_extender": {
        "volume": 2_000, "shield_bonus": 1_500, "sig_radius_bonus": 100,
    },
    # Shield hardeners (active — increase resistance to specific damage type)
    "small_shield_hardener_kinetic": {
        "volume": 30, "resistance_bonus": 0.15, "resistance_type": "kinetic",
        "layer": "shield", "cycle_time": 5, "cap_per_cycle": 5,
    },
    "small_shield_hardener_thermal": {
        "volume": 30, "resistance_bonus": 0.15, "resistance_type": "thermal",
        "layer": "shield", "cycle_time": 5, "cap_per_cycle": 5,
    },
    "small_shield_hardener_explosive": {
        "volume": 30, "resistance_bonus": 0.15, "resistance_type": "explosive",
        "layer": "shield", "cycle_time": 5, "cap_per_cycle": 5,
    },
    "medium_shield_hardener_kinetic": {
        "volume": 200, "resistance_bonus": 0.25, "resistance_type": "kinetic",
        "layer": "shield", "cycle_time": 5, "cap_per_cycle": 20,
    },
    "medium_shield_hardener_thermal": {
        "volume": 200, "resistance_bonus": 0.25, "resistance_type": "thermal",
        "layer": "shield", "cycle_time": 5, "cap_per_cycle": 20,
    },
    "medium_shield_hardener_explosive": {
        "volume": 200, "resistance_bonus": 0.25, "resistance_type": "explosive",
        "layer": "shield", "cycle_time": 5, "cap_per_cycle": 20,
    },
    "large_shield_hardener_kinetic": {
        "volume": 1_500, "resistance_bonus": 0.35, "resistance_type": "kinetic",
        "layer": "shield", "cycle_time": 5, "cap_per_cycle": 60,
    },
    "large_shield_hardener_thermal": {
        "volume": 1_500, "resistance_bonus": 0.35, "resistance_type": "thermal",
        "layer": "shield", "cycle_time": 5, "cap_per_cycle": 60,
    },
    "large_shield_hardener_explosive": {
        "volume": 1_500, "resistance_bonus": 0.35, "resistance_type": "explosive",
        "layer": "shield", "cycle_time": 5, "cap_per_cycle": 60,
    },
    # Shield boosters (active — repair shield HP)
    "small_shield_booster": {
        "volume": 50, "shield_repair": 20,
        "cycle_time": 8, "cap_per_cycle": 20,
    },
    "medium_shield_booster": {
        "volume": 300, "shield_repair": 100,
        "cycle_time": 8, "cap_per_cycle": 80,
    },
    "large_shield_booster": {
        "volume": 2_000, "shield_repair": 500,
        "cycle_time": 8, "cap_per_cycle": 300,
    },
    # Armor plates (passive — increase max armor HP, reduce speed)
    "small_armor_plate": {
        "volume": 50, "armor_bonus": 50, "speed_penalty": 0.05,
    },
    "medium_armor_plate": {
        "volume": 300, "armor_bonus": 400, "speed_penalty": 0.10,
    },
    "large_armor_plate": {
        "volume": 2_000, "armor_bonus": 3_000, "speed_penalty": 0.15,
    },
    # Armor hardeners (active)
    "small_armor_hardener_kinetic": {
        "volume": 30, "resistance_bonus": 0.15, "resistance_type": "kinetic",
        "layer": "armor", "cycle_time": 5, "cap_per_cycle": 5,
    },
    "small_armor_hardener_thermal": {
        "volume": 30, "resistance_bonus": 0.15, "resistance_type": "thermal",
        "layer": "armor", "cycle_time": 5, "cap_per_cycle": 5,
    },
    "small_armor_hardener_explosive": {
        "volume": 30, "resistance_bonus": 0.15, "resistance_type": "explosive",
        "layer": "armor", "cycle_time": 5, "cap_per_cycle": 5,
    },
    "medium_armor_hardener_kinetic": {
        "volume": 200, "resistance_bonus": 0.25, "resistance_type": "kinetic",
        "layer": "armor", "cycle_time": 5, "cap_per_cycle": 20,
    },
    "medium_armor_hardener_thermal": {
        "volume": 200, "resistance_bonus": 0.25, "resistance_type": "thermal",
        "layer": "armor", "cycle_time": 5, "cap_per_cycle": 20,
    },
    "medium_armor_hardener_explosive": {
        "volume": 200, "resistance_bonus": 0.25, "resistance_type": "explosive",
        "layer": "armor", "cycle_time": 5, "cap_per_cycle": 20,
    },
    "large_armor_hardener_kinetic": {
        "volume": 1_500, "resistance_bonus": 0.35, "resistance_type": "kinetic",
        "layer": "armor", "cycle_time": 5, "cap_per_cycle": 60,
    },
    "large_armor_hardener_thermal": {
        "volume": 1_500, "resistance_bonus": 0.35, "resistance_type": "thermal",
        "layer": "armor", "cycle_time": 5, "cap_per_cycle": 60,
    },
    "large_armor_hardener_explosive": {
        "volume": 1_500, "resistance_bonus": 0.35, "resistance_type": "explosive",
        "layer": "armor", "cycle_time": 5, "cap_per_cycle": 60,
    },
    # Armor repairers (active — repair armor HP)
    "small_armor_repairer": {
        "volume": 80, "armor_repair": 15,
        "cycle_time": 10, "cap_per_cycle": 25,
    },
    "medium_armor_repairer": {
        "volume": 500, "armor_repair": 80,
        "cycle_time": 10, "cap_per_cycle": 100,
    },
    "large_armor_repairer": {
        "volume": 3_000, "armor_repair": 400,
        "cycle_time": 10, "cap_per_cycle": 400,
    },
}

# Helper sets for module type classification
TURRET_TYPES: set[str] = set(TURRET_PARAMS.keys())
MISSILE_TYPES: set[str] = set(MISSILE_PARAMS.keys())
WEAPON_TYPES: set[str] = TURRET_TYPES | MISSILE_TYPES
SHIELD_EXTENDER_TYPES: set[str] = {
    "small_shield_extender", "medium_shield_extender", "large_shield_extender",
}
SHIELD_HARDENER_TYPES: set[str] = {
    k for k in DEFENSIVE_MODULE_PARAMS
    if "shield_hardener" in k
}
SHIELD_BOOSTER_TYPES: set[str] = {
    "small_shield_booster", "medium_shield_booster", "large_shield_booster",
}
ARMOR_PLATE_TYPES: set[str] = {
    "small_armor_plate", "medium_armor_plate", "large_armor_plate",
}
ARMOR_HARDENER_TYPES: set[str] = {
    k for k in DEFENSIVE_MODULE_PARAMS
    if "armor_hardener" in k
}
ARMOR_REPAIRER_TYPES: set[str] = {
    "small_armor_repairer", "medium_armor_repairer", "large_armor_repairer",
}
HARDENER_TYPES: set[str] = SHIELD_HARDENER_TYPES | ARMOR_HARDENER_TYPES
DEFENSIVE_TYPES: set[str] = set(DEFENSIVE_MODULE_PARAMS.keys())


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class GameState(SQLModel, table=True):
    """Singleton row tracking the global simulation state."""

    id: Optional[int] = Field(default=None, primary_key=True)
    current_tick: int = Field(default=0)
    running: bool = Field(default=False)
    tick_interval: float = Field(default=1.0)


class User(SQLModel, table=True):
    """Player account. Auth uses the token field."""

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    token: str = Field(unique=True, index=True)
    # password_hash stores a hex-encoded SHA-256(salt:password) string
    password_hash: Optional[str] = Field(default=None)

    ships: List["Spaceship"] = Relationship(back_populates="owner")
    events: List["Event"] = Relationship(back_populates="user")


class Spaceship(SQLModel, table=True):
    """A player-owned ship with physics state and resource pools."""

    id: Optional[int] = Field(default=None, primary_key=True)

    # Identity
    name: str
    ship_class: ShipClass

    # Physics state (3-D Euler integration)
    pos_x: float = Field(default=0.0)
    pos_y: float = Field(default=0.0)
    pos_z: float = Field(default=0.0)
    vel_x: float = Field(default=0.0)
    vel_y: float = Field(default=0.0)
    vel_z: float = Field(default=0.0)

    # Docking state
    docked_in_id: Optional[int] = Field(default=None, foreign_key="spaceship.id")

    # Resources
    ore: float = Field(default=0.0)
    capacitor: float = Field(default=0.0)
    max_capacitor: float = Field(default=0.0)

    # Combat HP (Phase 4)
    shield_hp: float = Field(default=0.0)
    max_shield_hp: float = Field(default=0.0)
    armor_hp: float = Field(default=0.0)
    max_armor_hp: float = Field(default=0.0)
    is_destroyed: bool = Field(default=False)
    scan_resolution: float = Field(default=0.0)

    # Hull properties (denormalised from SHIP_CLASSES for query convenience)
    total_volume: int = Field(default=0)
    signature_radius: float = Field(default=0.0)

    # Ownership
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")

    # Relationships
    owner: Optional[User] = Relationship(back_populates="ships")
    modules: List["ShipModule"] = Relationship(back_populates="ship")
    movement_orders: List["MovementOrder"] = Relationship(
        back_populates="ship",
        sa_relationship_kwargs={"foreign_keys": "MovementOrder.ship_id"},
    )
    build_orders: List["BuildOrder"] = Relationship(back_populates="ship")
    events: List["Event"] = Relationship(back_populates="ship")
    target_locks: List["TargetLock"] = Relationship(
        back_populates="ship",
        sa_relationship_kwargs={"foreign_keys": "TargetLock.ship_id"},
    )

    # ------------------------------------------------------------------
    # Derived helpers (pure Python, no DB access needed)
    # ------------------------------------------------------------------

    def class_constants(self) -> dict:
        return SHIP_CLASSES[self.ship_class.value]

    def engine_volume(self) -> float:
        """Sum of all engine module volumes."""
        return sum(m.volume for m in self.modules if m.module_type == ModuleType.engine)

    def max_speed(self) -> float:
        """Derived max speed based on engine allocation."""
        consts = self.class_constants()
        if self.total_volume == 0:
            return 0.0
        fraction = self.engine_volume() / self.total_volume
        speed = consts["base_speed"] * (fraction / REFERENCE_ENGINE_FRACTION)
        return min(speed, 2.0 * consts["base_speed"])

    def acceleration(self) -> float:
        """Derived acceleration (m/s^2)."""
        consts = self.class_constants()
        return self.max_speed() / consts["accel_time"]

    def cargo_capacity(self) -> float:
        """Total cargo capacity (m^3 of ore)."""
        return sum(
            m.volume
            for m in self.modules
            if m.module_type == ModuleType.cargo_bay
        )

    def docking_capacity(self) -> float:
        """Total docking bay capacity in m^3 of dockable ship volume."""
        return sum(
            m.volume * 0.5
            for m in self.modules
            if m.module_type == ModuleType.docking_bay
        )

    def has_dropoff(self) -> bool:
        return any(m.module_type == ModuleType.dropoff for m in self.modules)

    def is_docked(self) -> bool:
        return self.docked_in_id is not None

    def speed(self) -> float:
        return math.sqrt(self.vel_x**2 + self.vel_y**2 + self.vel_z**2)

    def armor_plate_speed_penalty(self) -> float:
        """Sum of speed penalties from all armor plate modules."""
        total = 0.0
        for m in self.modules:
            if m.module_type.value in ARMOR_PLATE_TYPES:
                params = DEFENSIVE_MODULE_PARAMS.get(m.module_type.value, {})
                total += params.get("speed_penalty", 0.0)
        return min(total, 0.75)  # cap at 75% penalty (25% min speed)

    def effective_max_speed(self) -> float:
        """Max speed accounting for armor plate penalties."""
        return self.max_speed() * (1.0 - self.armor_plate_speed_penalty())

    def effective_acceleration(self) -> float:
        """Acceleration based on effective max speed."""
        consts = self.class_constants()
        return self.effective_max_speed() / consts["accel_time"]

    def effective_signature_radius(self) -> float:
        """Signature radius including shield extender bonuses."""
        extra = 0.0
        for m in self.modules:
            if m.module_type.value in SHIELD_EXTENDER_TYPES:
                params = DEFENSIVE_MODULE_PARAMS.get(m.module_type.value, {})
                extra += params.get("sig_radius_bonus", 0.0)
        return self.signature_radius + extra

    def compute_resistances(self, layer: str) -> Dict[str, float]:
        """
        Compute effective resistances for shield or armor layer,
        including active hardeners with stacking penalties.
        Returns {damage_type: resistance_fraction}.
        """
        base = dict(SHIELD_BASE_RESISTS if layer == "shield" else ARMOR_BASE_RESISTS)
        # Collect active hardener bonuses per damage type
        bonuses: Dict[str, list[float]] = {"kinetic": [], "thermal": [], "explosive": []}
        for m in self.modules:
            if not m.active:
                continue
            params = DEFENSIVE_MODULE_PARAMS.get(m.module_type.value)
            if params is None:
                continue
            if params.get("layer") != layer:
                continue
            if "resistance_bonus" not in params:
                continue
            dmg_type = params["resistance_type"]
            bonuses[dmg_type].append(params["resistance_bonus"])

        # Apply stacking penalties: effective_bonus_n = base_bonus * 0.87^(n-1)
        for dmg_type, bonus_list in bonuses.items():
            bonus_list.sort(reverse=True)  # largest first
            total_bonus = 0.0
            for i, b in enumerate(bonus_list):
                total_bonus += b * (0.87 ** i)
            base[dmg_type] = min(0.95, base[dmg_type] + total_bonus)  # cap at 95%

        return base


class ShipModule(SQLModel, table=True):
    """An installed module on a ship."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ship_id: int = Field(foreign_key="spaceship.id", index=True)
    module_type: ModuleType
    volume: int = Field(default=0)

    # Activation state
    active: bool = Field(default=False)

    # Cycle tracking
    cycle_time: int = Field(default=0)   # ticks between cycles (0 = passive)
    ticks_until_cycle: int = Field(default=0)  # countdown until next cycle fires
    capacitor_per_cycle: float = Field(default=0.0)

    # Module-specific parameters (nullable; used only by relevant types)
    # Engine
    # (no extra fields — derived from volume fraction)

    # Reactor
    # capacitor_bonus is derived: volume * 5.0

    # Cargo bay
    # cargo_capacity is derived: volume * 1.0

    # Docking bay
    # docking_capacity is derived: volume * 0.5

    # Mining laser
    mining_yield: float = Field(default=0.0)   # ore per cycle
    mining_range: float = Field(default=0.0)   # meters

    # Scanner
    scan_range: float = Field(default=0.0)     # meters

    # Passive detector
    detection_range: float = Field(default=0.0)  # base detection range in meters

    # Factory
    factory_max_class: Optional[str] = Field(default=None)  # max buildable class

    # --- Phase 4: Weapon fields ---
    damage_per_cycle: float = Field(default=0.0)
    damage_type: Optional[str] = Field(default=None)  # kinetic, thermal, explosive
    optimal_range: float = Field(default=0.0)
    falloff_range: float = Field(default=0.0)
    tracking_speed: float = Field(default=0.0)  # rad/s for turrets
    sig_resolution: float = Field(default=0.0)  # turret sig resolution
    # Missile-specific
    missile_speed: float = Field(default=0.0)
    missile_flight_time: int = Field(default=0)
    explosion_radius: float = Field(default=0.0)
    explosion_velocity: float = Field(default=0.0)

    # --- Phase 4: Defensive fields ---
    shield_hp_bonus: float = Field(default=0.0)
    armor_hp_bonus: float = Field(default=0.0)
    shield_repair_per_cycle: float = Field(default=0.0)
    armor_repair_per_cycle: float = Field(default=0.0)

    # Relationship
    ship: Optional[Spaceship] = Relationship(back_populates="modules")
    build_orders: List["BuildOrder"] = Relationship(back_populates="factory_module")

    @property
    def is_passive(self) -> bool:
        return self.cycle_time == 0

    @property
    def capacitor_bonus(self) -> float:
        """Extra capacitor provided by a reactor (5 cap per m^3)."""
        if self.module_type == ModuleType.reactor:
            return self.volume * 5.0
        return 0.0

    @property
    def effective_cargo_capacity(self) -> float:
        """Cargo capacity for cargo_bay modules."""
        if self.module_type == ModuleType.cargo_bay:
            return float(self.volume)
        return 0.0

    @property
    def effective_docking_capacity(self) -> float:
        """Dockable ship volume for docking_bay modules."""
        if self.module_type == ModuleType.docking_bay:
            return self.volume * 0.5
        return 0.0


class MovementOrder(SQLModel, table=True):
    """A pending or active movement instruction for a ship."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ship_id: int = Field(foreign_key="spaceship.id", index=True)
    order_type: OrderType
    status: OrderStatus = Field(default=OrderStatus.active)

    # Target (only one of these is set)
    target_ship_id: Optional[int] = Field(default=None, foreign_key="spaceship.id")
    target_object_id: Optional[int] = Field(
        default=None, foreign_key="celestialobject.id"
    )
    # Absolute coordinate target
    target_x: Optional[float] = Field(default=None)
    target_y: Optional[float] = Field(default=None)
    target_z: Optional[float] = Field(default=None)

    # Parameters
    desired_distance: float = Field(default=0.0)  # metres; for orbit / keep_distance
    orbit_radius: float = Field(default=0.0)       # metres; for orbit

    # Docking countdown (set when within range)
    docking_ticks_remaining: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    ship: Optional[Spaceship] = Relationship(
        back_populates="movement_orders",
        sa_relationship_kwargs={"foreign_keys": "[MovementOrder.ship_id]"},
    )


class BuildOrder(SQLModel, table=True):
    """A factory build order in the production queue."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ship_id: int = Field(foreign_key="spaceship.id", index=True)
    factory_module_id: int = Field(foreign_key="shipmodule.id", index=True)

    blueprint: ShipClass  # ship class to build
    status: BuildStatus = Field(default=BuildStatus.queued)

    ore_cost: int = Field(default=0)
    ticks_remaining: int = Field(default=0)
    total_ticks: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    ship: Optional[Spaceship] = Relationship(back_populates="build_orders")
    factory_module: Optional[ShipModule] = Relationship(back_populates="build_orders")


class CelestialObject(SQLModel, table=True):
    """Asteroids, planets, stations, and waypoints."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    object_type: CelestialType

    pos_x: float = Field(default=0.0)
    pos_y: float = Field(default=0.0)
    pos_z: float = Field(default=0.0)

    # Asteroid-specific
    ore_remaining: float = Field(default=0.0)
    ore_initial: float = Field(default=0.0)


class Event(SQLModel, table=True):
    """Persistent event log entry for a player."""

    id: Optional[int] = Field(default=None, primary_key=True)
    tick: int = Field(index=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    ship_id: Optional[int] = Field(default=None, foreign_key="spaceship.id")
    event_type: EventType
    message: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    user: Optional[User] = Relationship(back_populates="events")
    ship: Optional[Spaceship] = Relationship(back_populates="events")


class TargetLock(SQLModel, table=True):
    """An active or pending target lock between two ships."""

    id: Optional[int] = Field(default=None, primary_key=True)
    ship_id: int = Field(foreign_key="spaceship.id", index=True)
    target_ship_id: int = Field(foreign_key="spaceship.id", index=True)
    status: LockStatus = Field(default=LockStatus.locking)
    ticks_remaining: int = Field(default=0)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    ship: Optional[Spaceship] = Relationship(
        back_populates="target_locks",
        sa_relationship_kwargs={"foreign_keys": "[TargetLock.ship_id]"},
    )


class WeaponAssignment(SQLModel, table=True):
    """Maps a weapon module to a locked target."""

    id: Optional[int] = Field(default=None, primary_key=True)
    module_id: int = Field(foreign_key="shipmodule.id", index=True)
    ship_id: int = Field(foreign_key="spaceship.id", index=True)
    target_ship_id: int = Field(foreign_key="spaceship.id", index=True)


class PendingMissile(SQLModel, table=True):
    """A missile in flight (delayed damage)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    source_ship_id: int = Field(foreign_key="spaceship.id", index=True)
    target_ship_id: int = Field(foreign_key="spaceship.id", index=True)
    damage: float = Field(default=0.0)
    damage_type: str = Field(default="explosive")
    explosion_radius: float = Field(default=0.0)
    explosion_velocity: float = Field(default=0.0)
    ticks_remaining: int = Field(default=0)
    source_user_id: int = Field(default=0)


class ResearchProgress(SQLModel, table=True):
    """
    Tracks active and completed research per user.

    Each row represents one research effort. Status is 'researching', 'paused',
    'complete', or 'cancelled'. Since teams aren't implemented yet (Phase 7/8),
    research is per-user: all ships owned by the same user benefit from
    completed research.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    tech_id: str = Field(index=True)  # key into TECH_TREE
    ship_id: int = Field(foreign_key="spaceship.id")  # ship doing the research
    module_id: int = Field(default=0)  # research module used
    status: str = Field(default="researching")  # researching, paused, complete, cancelled
    ticks_remaining: int = Field(default=0)
    total_ticks: int = Field(default=0)
    ore_cost: int = Field(default=0)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def create_default_ship(
    name: str,
    ship_class: ShipClass,
    user_id: int,
    pos_x: float = 0.0,
    pos_y: float = 0.0,
    pos_z: float = 0.0,
    vel_x: float = 0.0,
    vel_y: float = 0.0,
    vel_z: float = 0.0,
) -> Spaceship:
    """
    Instantiate a Spaceship with hull defaults from SHIP_CLASSES.

    NOTE: Does not populate modules or compute max_capacitor — callers must
    add modules and call ``recalculate_capacitor`` after persisting.
    """
    consts = SHIP_CLASSES[ship_class.value]
    ship = Spaceship(
        name=name,
        ship_class=ship_class,
        pos_x=pos_x,
        pos_y=pos_y,
        pos_z=pos_z,
        vel_x=vel_x,
        vel_y=vel_y,
        vel_z=vel_z,
        total_volume=consts["volume"],
        signature_radius=float(consts["signature"]),
        max_capacitor=float(consts["base_cap"]),
        capacitor=float(consts["base_cap"]),
        shield_hp=float(consts["base_shield"]),
        max_shield_hp=float(consts["base_shield"]),
        armor_hp=float(consts["base_armor"]),
        max_armor_hp=float(consts["base_armor"]),
        scan_resolution=float(consts["scan_resolution"]),
        ore=0.0,
        user_id=user_id,
    )
    return ship


def recalculate_max_capacitor(ship: Spaceship) -> None:
    """
    Recompute ship.max_capacitor from base hull value + reactor modules.
    Mutates the ship object in place.
    """
    consts = SHIP_CLASSES[ship.ship_class.value]
    reactor_bonus = sum(
        m.volume * 5.0
        for m in ship.modules
        if m.module_type == ModuleType.reactor
    )
    ship.max_capacitor = consts["base_cap"] + reactor_bonus


def recalculate_max_shield(ship: Spaceship) -> None:
    """Recompute ship.max_shield_hp from base hull value + shield extenders."""
    consts = SHIP_CLASSES[ship.ship_class.value]
    extender_bonus = sum(
        DEFENSIVE_MODULE_PARAMS.get(m.module_type.value, {}).get("shield_bonus", 0.0)
        for m in ship.modules
        if m.module_type.value in SHIELD_EXTENDER_TYPES
    )
    ship.max_shield_hp = consts["base_shield"] + extender_bonus


def recalculate_max_armor(ship: Spaceship) -> None:
    """Recompute ship.max_armor_hp from base hull value + armor plates."""
    consts = SHIP_CLASSES[ship.ship_class.value]
    plate_bonus = sum(
        DEFENSIVE_MODULE_PARAMS.get(m.module_type.value, {}).get("armor_bonus", 0.0)
        for m in ship.modules
        if m.module_type.value in ARMOR_PLATE_TYPES
    )
    ship.max_armor_hp = consts["base_armor"] + plate_bonus


def make_module(module_type: ModuleType, volume: int) -> ShipModule:
    """
    Create a ShipModule with the correct cycle parameters filled in.
    For fixed-size modules the ``volume`` parameter is ignored and the
    spec value is used instead.
    """
    mt_val = module_type.value

    # --- Turrets ---
    if mt_val in TURRET_PARAMS:
        p = TURRET_PARAMS[mt_val]
        return ShipModule(
            module_type=module_type,
            volume=p["volume"],
            active=False,
            cycle_time=p["cycle_time"],
            ticks_until_cycle=p["cycle_time"],
            capacitor_per_cycle=p["cap_per_cycle"],
            damage_per_cycle=float(p["damage"]),
            damage_type=p["damage_type"],
            optimal_range=float(p["optimal_range"]),
            falloff_range=float(p["falloff"]),
            tracking_speed=p["tracking_speed"],
            sig_resolution=float(p["sig_resolution"]),
        )

    # --- Missile launchers ---
    if mt_val in MISSILE_PARAMS:
        p = MISSILE_PARAMS[mt_val]
        return ShipModule(
            module_type=module_type,
            volume=p["volume"],
            active=False,
            cycle_time=p["cycle_time"],
            ticks_until_cycle=p["cycle_time"],
            capacitor_per_cycle=p["cap_per_cycle"],
            damage_per_cycle=float(p["damage"]),
            damage_type=p["damage_type"],
            missile_speed=float(p["missile_speed"]),
            missile_flight_time=p["max_flight_time"],
            explosion_radius=float(p["explosion_radius"]),
            explosion_velocity=float(p["explosion_velocity"]),
            optimal_range=float(p["range"]),
        )

    # --- Defensive modules ---
    if mt_val in DEFENSIVE_MODULE_PARAMS:
        p = DEFENSIVE_MODULE_PARAMS[mt_val]
        return ShipModule(
            module_type=module_type,
            volume=p["volume"],
            active=False,
            cycle_time=p.get("cycle_time", 0),
            ticks_until_cycle=p.get("cycle_time", 0),
            capacitor_per_cycle=p.get("cap_per_cycle", 0.0),
            shield_hp_bonus=float(p.get("shield_bonus", 0)),
            armor_hp_bonus=float(p.get("armor_bonus", 0)),
            shield_repair_per_cycle=float(p.get("shield_repair", 0)),
            armor_repair_per_cycle=float(p.get("armor_repair", 0)),
        )

    # --- Original module types ---
    fixed = MODULE_FIXED_VOLUMES.get(mt_val)
    if fixed is not None:
        volume = fixed

    params = MODULE_PARAMS.get(mt_val, {})
    module = ShipModule(
        module_type=module_type,
        volume=volume,
        active=False,
        cycle_time=params.get("cycle_time", 0),
        ticks_until_cycle=params.get("cycle_time", 0),
        capacitor_per_cycle=params.get("cap_per_cycle", 0.0),
        mining_yield=float(params.get("mining_yield", 0)),
        mining_range=float(params.get("range", 0)),
        scan_range=float(params.get("scan_range", 0)),
        detection_range=float(params.get("base_detection_range", 0)),
    )
    # Determine max buildable class for factories
    if module_type == ModuleType.factory:
        module.factory_max_class = _factory_max_class(volume)
    return module


def _factory_max_class(volume: int) -> Optional[str]:
    """Return the largest ship class a factory of given volume can build."""
    result: Optional[str] = None
    for cls, min_vol in sorted(FACTORY_REQUIREMENTS.items(), key=lambda x: x[1]):
        if volume >= min_vol:
            result = cls
    return result


def spawn_new_ship(
    blueprint: ShipClass,
    builder: Spaceship,
    current_tick: int,
) -> Spaceship:
    """
    Spawn a newly built ship adjacent to the builder.

    Returns an unsaved Spaceship (caller must add to session).
    The ship starts with no modules, full base capacitor, zero ore.
    Position is 100 m away from the builder in a random direction.
    Velocity matches the builder.
    """
    # Random unit vector for offset direction
    theta = random.uniform(0, 2 * math.pi)
    phi = random.uniform(0, math.pi)
    dx = math.sin(phi) * math.cos(theta)
    dy = math.sin(phi) * math.sin(theta)
    dz = math.cos(phi)
    offset = 100.0  # metres

    consts = SHIP_CLASSES[blueprint.value]
    ship = Spaceship(
        name=f"New {blueprint.value.replace('_', ' ').title()}",
        ship_class=blueprint,
        pos_x=builder.pos_x + dx * offset,
        pos_y=builder.pos_y + dy * offset,
        pos_z=builder.pos_z + dz * offset,
        vel_x=builder.vel_x,
        vel_y=builder.vel_y,
        vel_z=builder.vel_z,
        total_volume=consts["volume"],
        signature_radius=float(consts["signature"]),
        max_capacitor=float(consts["base_cap"]),
        capacitor=float(consts["base_cap"]),
        shield_hp=float(consts["base_shield"]),
        max_shield_hp=float(consts["base_shield"]),
        armor_hp=float(consts["base_armor"]),
        max_armor_hp=float(consts["base_armor"]),
        scan_resolution=float(consts["scan_resolution"]),
        ore=0.0,
        user_id=builder.user_id,
    )
    return ship
