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

import sqlalchemy as sa
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
    # --- Phase 7: Solarion modules ---
    focused_beam_medium = "focused_beam_medium"
    focused_beam_large = "focused_beam_large"
    reactive_armor_membrane_medium = "reactive_armor_membrane_medium"
    reactive_armor_membrane_large = "reactive_armor_membrane_large"
    armor_repair_nexus_medium = "armor_repair_nexus_medium"
    armor_repair_nexus_large = "armor_repair_nexus_large"
    solar_lance = "solar_lance"
    # --- Phase 7: Voidborn modules ---
    light_leech_projector = "light_leech_projector"
    heavy_leech_projector = "heavy_leech_projector"
    phase_shield_amplifier_medium = "phase_shield_amplifier_medium"
    phase_shield_amplifier_large = "phase_shield_amplifier_large"
    small_stealth_field = "small_stealth_field"
    medium_stealth_field = "medium_stealth_field"
    bio_repair_swarm = "bio_repair_swarm"
    # --- Phase 7: Shared ---
    shield_purge = "shield_purge"
    # --- Phase 9: Starter modules ---
    starter_turret = "starter_turret"
    starter_mining_laser = "starter_mining_laser"
    starter_shield_extender = "starter_shield_extender"
    starter_armor_plate = "starter_armor_plate"
    starter_passive_detector = "starter_passive_detector"


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


class Faction(str, Enum):
    solarion = "solarion"
    voidborn = "voidborn"


class MatchStatus(str, Enum):
    pending = "pending"
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


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
    # --- Phase 7: Faction events ---
    leech_applied = "leech_applied"
    leech_incoming = "leech_incoming"
    leech_expired = "leech_expired"
    leech_cleansed = "leech_cleansed"
    leech_tick = "leech_tick"
    solar_lance_charging = "solar_lance_charging"
    solar_lance_fired = "solar_lance_fired"
    solar_lance_fizzled = "solar_lance_fizzled"
    stealth_activated = "stealth_activated"
    stealth_deactivated = "stealth_deactivated"
    bio_repair_swarm_active = "bio_repair_swarm_active"
    # --- Phase 8: Match events ---
    match_started = "match_started"
    mothership_under_attack = "mothership_under_attack"
    mothership_critical = "mothership_critical"
    match_ended = "match_ended"
    surrender_vote = "surrender_vote"
    # --- Phase 9: Points & loadout events ---
    points_earned = "points_earned"
    ship_claimed = "ship_claimed"
    reship_complete = "reship_complete"
    ship_boarded = "ship_boarded"
    ship_ejected = "ship_ejected"
    # --- Phase 8.5: Command events ---
    command_processed = "command_processed"
    command_rejected = "command_rejected"


class CommandType(str, Enum):
    create_ship = "create_ship"
    rename_ship = "rename_ship"
    install_module = "install_module"
    uninstall_module = "uninstall_module"
    undock = "undock"
    move = "move"
    cancel_order = "cancel_order"
    dock = "dock"
    stop = "stop"
    activate_module = "activate_module"
    deactivate_module = "deactivate_module"
    lock_target = "lock_target"
    unlock_target = "unlock_target"
    assign_weapon = "assign_weapon"
    fire_all = "fire_all"
    hold_fire = "hold_fire"
    build = "build"
    transfer_ore = "transfer_ore"
    scan = "scan"
    start_research = "start_research"
    cancel_research = "cancel_research"
    claim_ship = "claim_ship"
    reship = "reship"
    board_ship = "board_ship"
    eject = "eject"
    start_match = "start_match"
    surrender = "surrender"


class CommandStatus(str, Enum):
    pending = "pending"
    processed = "processed"
    rejected = "rejected"


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

# Solarion ship classes (final stats from FACTION_DESIGN.md)
SOLARION_SHIP_CLASSES: Dict[str, dict] = {
    "strike_craft": {
        "volume": 100, "signature": 29, "base_cap": 55, "base_speed": 360,
        "accel_time": 8, "base_shield": 43, "base_armor": 130,
        "scan_resolution": 500, "base_lock_time": 3, "faction_name": "Pilgrim",
    },
    "corvette": {
        "volume": 2_000, "signature": 115, "base_cap": 220, "base_speed": 225,
        "accel_time": 12, "base_shield": 255, "base_armor": 780,
        "scan_resolution": 400, "base_lock_time": 5, "faction_name": "Herald",
    },
    "frigate": {
        "volume": 20_000, "signature": 345, "base_cap": 1_100, "base_speed": 135,
        "accel_time": 20, "base_shield": 1_700, "base_armor": 5_200,
        "scan_resolution": 300, "base_lock_time": 8, "faction_name": "Sentinel",
    },
    "destroyer": {
        "volume": 80_000, "signature": 690, "base_cap": 3_300, "base_speed": 90,
        "accel_time": 30, "base_shield": 6_800, "base_armor": 20_800,
        "scan_resolution": 250, "base_lock_time": 12, "faction_name": "Justicar",
    },
    "cruiser": {
        "volume": 250_000, "signature": 1_150, "base_cap": 8_800, "base_speed": 54,
        "accel_time": 45, "base_shield": 25_500, "base_armor": 78_000,
        "scan_resolution": 200, "base_lock_time": 18, "faction_name": "Sovereign",
    },
    "mothership": {
        "volume": 2_000_000, "signature": 2_300, "base_cap": 27_500, "base_speed": 27,
        "accel_time": 60, "base_shield": 85_000, "base_armor": 260_000,
        "scan_resolution": 150, "base_lock_time": 30, "faction_name": "Exodus",
    },
}

# Voidborn ship classes (final stats from FACTION_DESIGN.md)
VOIDBORN_SHIP_CLASSES: Dict[str, dict] = {
    "strike_craft": {
        "volume": 100, "signature": 21, "base_cap": 45, "base_speed": 440,
        "accel_time": 8, "base_shield": 60, "base_armor": 85,
        "scan_resolution": 500, "base_lock_time": 3, "faction_name": "Mite",
    },
    "corvette": {
        "volume": 2_000, "signature": 85, "base_cap": 180, "base_speed": 275,
        "accel_time": 12, "base_shield": 360, "base_armor": 510,
        "scan_resolution": 400, "base_lock_time": 5, "faction_name": "Mantis",
    },
    "frigate": {
        "volume": 20_000, "signature": 255, "base_cap": 900, "base_speed": 165,
        "accel_time": 20, "base_shield": 2_400, "base_armor": 3_400,
        "scan_resolution": 300, "base_lock_time": 8, "faction_name": "Widow",
    },
    "destroyer": {
        "volume": 80_000, "signature": 510, "base_cap": 2_700, "base_speed": 110,
        "accel_time": 30, "base_shield": 9_600, "base_armor": 13_600,
        "scan_resolution": 250, "base_lock_time": 12, "faction_name": "Scorpion",
    },
    "cruiser": {
        "volume": 250_000, "signature": 850, "base_cap": 7_200, "base_speed": 66,
        "accel_time": 45, "base_shield": 36_000, "base_armor": 51_000,
        "scan_resolution": 200, "base_lock_time": 18, "faction_name": "Kraken",
    },
    "mothership": {
        "volume": 2_000_000, "signature": 1_700, "base_cap": 22_500, "base_speed": 33,
        "accel_time": 60, "base_shield": 120_000, "base_armor": 170_000,
        "scan_resolution": 150, "base_lock_time": 30, "faction_name": "Broodmother",
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

# Solarion base resistances
SOLARION_SHIELD_RESISTS: Dict[str, float] = {"kinetic": 0.15, "thermal": 0.05, "explosive": 0.25}
SOLARION_ARMOR_RESISTS: Dict[str, float] = {"kinetic": 0.35, "thermal": 0.25, "explosive": 0.15}

# Voidborn base resistances
VOIDBORN_SHIELD_RESISTS: Dict[str, float] = {"kinetic": 0.25, "thermal": 0.15, "explosive": 0.35}
VOIDBORN_ARMOR_RESISTS: Dict[str, float] = {"kinetic": 0.25, "thermal": 0.15, "explosive": 0.05}

# Max target locks per ship class (2 + class_index)
MAX_LOCKS: Dict[str, int] = {
    "strike_craft": 2,
    "corvette": 3,
    "frigate": 4,
    "destroyer": 5,
    "cruiser": 6,
    "mothership": 7,
}

SOLARION_MAX_LOCKS: Dict[str, int] = {
    "strike_craft": 3, "corvette": 4, "frigate": 5,
    "destroyer": 6, "cruiser": 7, "mothership": 8,
}
VOIDBORN_MAX_LOCKS: Dict[str, int] = {
    "strike_craft": 2, "corvette": 3, "frigate": 4,
    "destroyer": 5, "cruiser": 6, "mothership": 7,
}

FACTION_TRAITS: Dict[str, dict] = {
    "solarion": {
        "armor_repair_hp_mult": 1.25,
        "armor_repair_cap_mult": 0.85,
        "turret_range_mult": 1.20,
        "module_cap_cost_mult": 1.10,  # non-armor-repair active modules
    },
    "voidborn": {
        "shield_booster_hp_mult": 1.25,
        "shield_booster_cap_mult": 0.85,
        "module_cap_cost_mult": 0.95,  # non-shield-booster active modules
        "passive_armor_regen": True,  # peak = max_armor / 200
    },
}

FACTION_BUILD_MODIFIERS: Dict[str, dict] = {
    "solarion": {
        "strike_craft": {"ore_mult": 1.0, "time_mult": 1.0},
        "corvette": {"ore_mult": 1.0, "time_mult": 1.0},
        "frigate": {"ore_mult": 1.0, "time_mult": 1.0},
        "destroyer": {"ore_mult": 1.15, "time_mult": 1.10},
        "cruiser": {"ore_mult": 1.15, "time_mult": 1.10},
    },
    "voidborn": {
        "strike_craft": {"ore_mult": 0.80, "time_mult": 0.80},
        "corvette": {"ore_mult": 0.80, "time_mult": 0.80},
        "frigate": {"ore_mult": 1.0, "time_mult": 1.0},
        "destroyer": {"ore_mult": 0.95, "time_mult": 1.0},
        "cruiser": {"ore_mult": 0.95, "time_mult": 1.0},
    },
}

FACTION_SHIP_NAMES: Dict[str, Dict[str, str]] = {
    "solarion": {
        "strike_craft": "Pilgrim", "corvette": "Herald", "frigate": "Sentinel",
        "destroyer": "Justicar", "cruiser": "Sovereign", "mothership": "Exodus",
    },
    "voidborn": {
        "strike_craft": "Mite", "corvette": "Mantis", "frigate": "Widow",
        "destroyer": "Scorpion", "cruiser": "Kraken", "mothership": "Broodmother",
    },
}


def get_ship_classes(faction: Optional[str] = None) -> Dict[str, dict]:
    """Return the ship class stats dict for a faction, or generic if no faction."""
    if faction == "solarion":
        return SOLARION_SHIP_CLASSES
    elif faction == "voidborn":
        return VOIDBORN_SHIP_CLASSES
    return SHIP_CLASSES


def get_base_resists(faction: Optional[str], layer: str) -> Dict[str, float]:
    """Return base resistance dict for a faction and layer."""
    if faction == "solarion":
        return dict(SOLARION_SHIELD_RESISTS if layer == "shield" else SOLARION_ARMOR_RESISTS)
    elif faction == "voidborn":
        return dict(VOIDBORN_SHIELD_RESISTS if layer == "shield" else VOIDBORN_ARMOR_RESISTS)
    return dict(SHIELD_BASE_RESISTS if layer == "shield" else ARMOR_BASE_RESISTS)


def get_max_locks(faction: Optional[str], ship_class: str) -> int:
    """Return max target locks for a faction and ship class."""
    if faction == "solarion":
        return SOLARION_MAX_LOCKS.get(ship_class, MAX_LOCKS.get(ship_class, 2))
    elif faction == "voidborn":
        return VOIDBORN_MAX_LOCKS.get(ship_class, MAX_LOCKS.get(ship_class, 2))
    return MAX_LOCKS.get(ship_class, 2)


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
    "strike_craft": {"ore": 200, "ticks": 60},       # 1 min
    "corvette": {"ore": 1_000, "ticks": 180},         # 3 min
    "frigate": {"ore": 3_000, "ticks": 360},           # 6 min
    "destroyer": {"ore": 15_000, "ticks": 900},        # 15 min
    "cruiser": {"ore": 50_000, "ticks": 1_800},        # 30 min
}

# ---------------------------------------------------------------------------
# Phase 9: Points & Loadout constants
# ---------------------------------------------------------------------------

EJECT_ALLOWED_CLASSES: set[str] = {"mothership"}

HULL_POINT_COSTS: Dict[str, int] = {
    "strike_craft": 0, "corvette": 250, "frigate": 2_000,
    "destroyer": 5_000, "cruiser": 10_000,
}

MODULE_POINT_COSTS: Dict[str, int] = {
    # Always free
    "engine": 0, "reactor": 0, "cargo_bay": 0, "docking_bay": 0,
    "dropoff": 0, "factory": 0, "mining_laser": 0,
    "starter_turret": 0, "starter_mining_laser": 0,
    "starter_shield_extender": 0, "starter_armor_plate": 0,
    "starter_passive_detector": 0,
    # Small modules
    "small_turret_kinetic": 50, "small_turret_thermal": 50,
    "light_missile_launcher": 75,
    "small_shield_extender": 25,
    "small_shield_hardener_kinetic": 40, "small_shield_hardener_thermal": 40,
    "small_shield_hardener_explosive": 40,
    "small_shield_booster": 50,
    "small_armor_plate": 25,
    "small_armor_hardener_kinetic": 40, "small_armor_hardener_thermal": 40,
    "small_armor_hardener_explosive": 40,
    "small_armor_repairer": 50,
    "passive_detector": 50, "scanner": 100, "research_module": 100,
    # Medium modules
    "medium_turret_kinetic": 200, "medium_turret_thermal": 200,
    "heavy_missile_launcher": 300,
    "medium_shield_extender": 150,
    "medium_shield_hardener_kinetic": 200, "medium_shield_hardener_thermal": 200,
    "medium_shield_hardener_explosive": 200,
    "medium_shield_booster": 250,
    "medium_armor_plate": 150,
    "medium_armor_hardener_kinetic": 200, "medium_armor_hardener_thermal": 200,
    "medium_armor_hardener_explosive": 200,
    "medium_armor_repairer": 250,
    "strip_miner": 300,
    # Large modules
    "large_turret_kinetic": 800, "large_turret_thermal": 800,
    "torpedo_launcher": 1_200,
    "large_shield_extender": 600,
    "large_shield_hardener_kinetic": 800, "large_shield_hardener_thermal": 800,
    "large_shield_hardener_explosive": 800,
    "large_shield_booster": 1_000,
    "large_armor_plate": 600,
    "large_armor_hardener_kinetic": 800, "large_armor_hardener_thermal": 800,
    "large_armor_hardener_explosive": 800,
    "large_armor_repairer": 1_000,
    "shield_purge": 400,
    "enhanced_docking_bay": 500,
    # Solarion faction
    "focused_beam_medium": 400, "focused_beam_large": 1_500,
    "reactive_armor_membrane_medium": 400, "reactive_armor_membrane_large": 1_500,
    "armor_repair_nexus_medium": 400, "armor_repair_nexus_large": 1_500,
    "solar_lance": 5_000,
    # Voidborn faction
    "light_leech_projector": 150, "heavy_leech_projector": 500,
    "phase_shield_amplifier_medium": 400, "phase_shield_amplifier_large": 1_500,
    "small_stealth_field": 200, "medium_stealth_field": 600,
    "bio_repair_swarm": 3_000,
    # Shared
    "fortress": 4_000,
}

BUILD_COMPLETE_POINTS: Dict[str, int] = {
    "strike_craft": 50, "corvette": 200, "frigate": 800,
    "destroyer": 2_000, "cruiser": 5_000,
}

KILL_POINTS: Dict[str, int] = {
    "strike_craft": 100, "corvette": 500, "frigate": 2_000,
    "destroyer": 5_000, "cruiser": 10_000, "mothership": 50_000,
}

RESEARCH_COMPLETE_POINTS: Dict[int, int] = {
    1: 200, 2: 500, 3: 1_000, 4: 2_000,
}

# ---------------------------------------------------------------------------
# Phase 8: Match system constants
# ---------------------------------------------------------------------------

ASTEROID_SIZES: Dict[str, float] = {
    "small": 500.0,
    "medium": 2_000.0,
    "large": 10_000.0,
    "huge": 50_000.0,
}

# Modules installed on each match mothership at start: (module_type, volume)
MATCH_MOTHERSHIP_LOADOUT: list[tuple[str, int]] = [
    ("reactor", 200),
    ("reactor", 200),
    ("cargo_bay", 10_000),
    ("docking_bay", 500),
    ("factory", 300_000),
    ("mining_laser", 50),
    ("passive_detector", 100),
    ("dropoff", 500),
    ("research_module", 5_000),
    ("large_turret_kinetic", 0),
    ("large_turret_thermal", 0),
    ("large_armor_plate", 0),
    ("large_shield_extender", 0),
]

# ---------------------------------------------------------------------------
# Phase 5: Research / Tech Tree
# ---------------------------------------------------------------------------

# Research tier costs
RESEARCH_COSTS: Dict[int, dict] = {
    1: {"ore": 500, "ticks": 180},           # 3 min
    2: {"ore": 1_500, "ticks": 300},          # 5 min
    3: {"ore": 5_000, "ticks": 600},          # 10 min
    4: {"ore": 15_000, "ticks": 1_200},       # 20 min
}

# Tech tree: each node has an id, tier, prerequisites, and what it unlocks.
# "unlocks_modules" lists module_type values, "unlocks_ships" lists ship class values.
# "duplicable" = True means multiple players can research simultaneously (pooled ticks).
# "prerequisites_any" = OR prereqs (at least one must be completed).
TECH_TREE: Dict[str, dict] = {
    # --- Tier 1: Foundation (500 ore, 300 ticks) ---
    "1a_medium_kinetic_turrets": {
        "name": "Medium Kinetic Turrets", "tier": 1,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": ["medium_turret_kinetic"], "unlocks_ships": [],
    },
    "1b_medium_thermal_turrets": {
        "name": "Medium Thermal Turrets", "tier": 1,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": ["medium_turret_thermal"], "unlocks_ships": [],
    },
    "1c_heavy_missiles": {
        "name": "Heavy Missiles", "tier": 1,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": ["heavy_missile_launcher"], "unlocks_ships": [],
    },
    "1d_medium_shield_extenders": {
        "name": "Medium Shield Systems", "tier": 1,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": ["medium_shield_extender"], "unlocks_ships": [],
    },
    "1e_medium_shield_hardeners": {
        "name": "Medium Shield Hardeners", "tier": 1,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": [
            "medium_shield_hardener_kinetic", "medium_shield_hardener_thermal",
            "medium_shield_hardener_explosive",
        ],
        "unlocks_ships": [],
    },
    "1f_medium_shield_boosters": {
        "name": "Medium Shield Boosters", "tier": 1,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": ["medium_shield_booster"], "unlocks_ships": [],
    },
    "1g_medium_armor_plates": {
        "name": "Medium Armor Plating", "tier": 1,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": ["medium_armor_plate"], "unlocks_ships": [],
    },
    "1h_medium_armor_hardeners": {
        "name": "Medium Armor Hardeners", "tier": 1,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": [
            "medium_armor_hardener_kinetic", "medium_armor_hardener_thermal",
            "medium_armor_hardener_explosive",
        ],
        "unlocks_ships": [],
    },
    "1i_medium_armor_repairers": {
        "name": "Medium Armor Repairers", "tier": 1,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": ["medium_armor_repairer"], "unlocks_ships": [],
    },
    "1j_advanced_mining": {
        "name": "Advanced Mining", "tier": 1,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": ["strip_miner"], "unlocks_ships": [],
    },
    "1h_corvette_hull": {
        "name": "Corvette Hull", "tier": 1,
        "prerequisites": [], "duplicable": True,
        "unlocks_modules": [], "unlocks_ships": ["corvette"],
    },
    # --- Tier 2: Escalation (2000 ore, 900 ticks) ---
    "2a_large_kinetic_turrets": {
        "name": "Large Kinetic Turrets", "tier": 2,
        "prerequisites": ["1a_medium_kinetic_turrets"], "duplicable": False,
        "unlocks_modules": ["large_turret_kinetic"], "unlocks_ships": [],
    },
    "2b_large_thermal_turrets": {
        "name": "Large Thermal Turrets", "tier": 2,
        "prerequisites": ["1b_medium_thermal_turrets"], "duplicable": False,
        "unlocks_modules": ["large_turret_thermal"], "unlocks_ships": [],
    },
    "2c_torpedoes": {
        "name": "Torpedoes", "tier": 2,
        "prerequisites": ["1c_heavy_missiles"], "duplicable": False,
        "unlocks_modules": ["torpedo_launcher"], "unlocks_ships": [],
    },
    "2d_large_shield_extenders": {
        "name": "Large Shield Systems", "tier": 2,
        "prerequisites": ["1d_medium_shield_extenders"], "duplicable": False,
        "unlocks_modules": ["large_shield_extender"], "unlocks_ships": [],
    },
    "2e_large_shield_hardeners": {
        "name": "Large Shield Hardeners", "tier": 2,
        "prerequisites": ["1e_medium_shield_hardeners"], "duplicable": False,
        "unlocks_modules": [
            "large_shield_hardener_kinetic", "large_shield_hardener_thermal",
            "large_shield_hardener_explosive",
        ],
        "unlocks_ships": [],
    },
    "2f_large_shield_boosters": {
        "name": "Large Shield Boosters", "tier": 2,
        "prerequisites": ["1f_medium_shield_boosters"], "duplicable": False,
        "unlocks_modules": ["large_shield_booster"], "unlocks_ships": [],
    },
    "2g_large_armor_plates": {
        "name": "Large Armor Plating", "tier": 2,
        "prerequisites": ["1g_medium_armor_plates"], "duplicable": False,
        "unlocks_modules": ["large_armor_plate"], "unlocks_ships": [],
    },
    "2h_large_armor_hardeners": {
        "name": "Large Armor Hardeners", "tier": 2,
        "prerequisites": ["1h_medium_armor_hardeners"], "duplicable": False,
        "unlocks_modules": [
            "large_armor_hardener_kinetic", "large_armor_hardener_thermal",
            "large_armor_hardener_explosive",
        ],
        "unlocks_ships": [],
    },
    "2i_large_armor_repairers": {
        "name": "Large Armor Repairers", "tier": 2,
        "prerequisites": ["1i_medium_armor_repairers"], "duplicable": False,
        "unlocks_modules": ["large_armor_repairer"], "unlocks_ships": [],
    },
    "2j_shield_purge": {
        "name": "Shield Purge", "tier": 2,
        "prerequisites": [], "duplicable": False,
        "prerequisites_any": ["1e_medium_shield_hardeners", "1h_medium_armor_hardeners"],
        "unlocks_modules": ["shield_purge"], "unlocks_ships": [],
    },
    "2k_enhanced_docking": {
        "name": "Enhanced Docking", "tier": 2,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": ["enhanced_docking_bay"], "unlocks_ships": [],
    },
    "2h_frigate_hull": {
        "name": "Frigate Hull", "tier": 2,
        "prerequisites": ["1h_corvette_hull"], "duplicable": True,
        "unlocks_modules": [], "unlocks_ships": ["frigate"],
    },
    # --- Tier 3: Specialization (8000 ore, 1800 ticks, faction-specific) ---
    # Solarion tier 3 (overridden per faction)
    "3a_focused_beams": {
        "name": "Focused Beam Weapons", "tier": 3,
        "prerequisites": [], "duplicable": False,
        "prerequisites_any": ["2a_large_kinetic_turrets", "2b_large_thermal_turrets"],
        "unlocks_modules": ["focused_beam_medium", "focused_beam_large"],
        "unlocks_ships": [], "faction": "solarion",
    },
    "3b_reactive_armor": {
        "name": "Reactive Armor Membranes", "tier": 3,
        "prerequisites": [], "duplicable": False,
        "prerequisites_any": ["2g_large_armor_plates", "2h_large_armor_hardeners"],
        "unlocks_modules": ["reactive_armor_membrane_medium", "reactive_armor_membrane_large"],
        "unlocks_ships": [], "faction": "solarion",
    },
    "3c_armor_nexus": {
        "name": "Armor Repair Nexus", "tier": 3,
        "prerequisites": ["2i_large_armor_repairers"], "duplicable": False,
        "unlocks_modules": ["armor_repair_nexus_medium", "armor_repair_nexus_large"],
        "unlocks_ships": [], "faction": "solarion",
    },
    # Voidborn tier 3
    "3a_leech_projectors": {
        "name": "Leech Projectors", "tier": 3,
        "prerequisites": [], "duplicable": False,
        "prerequisites_any": ["2a_large_kinetic_turrets", "2b_large_thermal_turrets"],
        "unlocks_modules": ["light_leech_projector", "heavy_leech_projector"],
        "unlocks_ships": [], "faction": "voidborn",
    },
    "3b_phase_shields": {
        "name": "Phase Shield Amplifiers", "tier": 3,
        "prerequisites": [], "duplicable": False,
        "prerequisites_any": ["2d_large_shield_extenders", "2f_large_shield_boosters"],
        "unlocks_modules": ["phase_shield_amplifier_medium", "phase_shield_amplifier_large"],
        "unlocks_ships": [], "faction": "voidborn",
    },
    "3c_stealth_fields": {
        "name": "Stealth Field Generators", "tier": 3,
        "prerequisites": [], "duplicable": False,
        "unlocks_modules": ["small_stealth_field", "medium_stealth_field"],
        "unlocks_ships": [], "faction": "voidborn",
    },
    # Hull (shared)
    "3h_destroyer_hull": {
        "name": "Destroyer Hull", "tier": 3,
        "prerequisites": ["2h_frigate_hull"], "duplicable": True,
        "unlocks_modules": [], "unlocks_ships": ["destroyer"],
    },
    # --- Tier 4: Endgame (25000 ore, 3600 ticks) ---
    "4a_solar_lance": {
        "name": "Solar Lance", "tier": 4,
        "prerequisites": ["3a_focused_beams"], "duplicable": False,
        "unlocks_modules": ["solar_lance"], "unlocks_ships": [],
        "faction": "solarion",
    },
    "4a_bio_repair_swarm": {
        "name": "Bio-Repair Swarm", "tier": 4,
        "prerequisites": ["3a_leech_projectors"], "duplicable": False,
        "unlocks_modules": ["bio_repair_swarm"], "unlocks_ships": [],
        "faction": "voidborn",
    },
    "4b_fortress": {
        "name": "Fortress Systems", "tier": 4,
        "prerequisites": ["2k_enhanced_docking"], "duplicable": False,
        "unlocks_modules": ["fortress"], "unlocks_ships": [],
    },
    "4h_cruiser_hull": {
        "name": "Cruiser Hull", "tier": 4,
        "prerequisites": ["3h_destroyer_hull"], "duplicable": True,
        "unlocks_modules": [], "unlocks_ships": ["cruiser"],
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
    "starter_turret": 15,
    "starter_mining_laser": 20,
    "starter_shield_extender": 15,
    "starter_armor_plate": 15,
    "starter_passive_detector": 10,
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
    "starter_mining_laser": {
        "cycle_time": 10,
        "cap_per_cycle": 10,
        "mining_yield": 2,
        "range": 500,
    },
    "starter_passive_detector": {
        "cycle_time": 10,
        "cap_per_cycle": 2,
        "base_detection_range": 10_000,
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
    "starter_turret": {
        "volume": 15, "damage": 5, "damage_type": "kinetic",
        "cycle_time": 5, "cap_per_cycle": 3,
        "optimal_range": 2_000, "falloff": 1_500,
        "tracking_speed": 0.12, "sig_resolution": 25,
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
    # Starter defensive modules
    "starter_shield_extender": {
        "volume": 15, "shield_bonus": 15, "sig_radius_bonus": 2,
    },
    "starter_armor_plate": {
        "volume": 15, "armor_bonus": 25, "speed_penalty": 0.03,
    },
}

# Solarion-exclusive module params
SOLARION_MODULE_PARAMS: Dict[str, dict] = {
    "focused_beam_medium": {
        "volume": 350, "damage": 100, "damage_type": "thermal",
        "cycle_time": 10, "cap_per_cycle": 55,
        "optimal_range": 25_000, "falloff": 12_000,
        "tracking_speed": 0.02, "sig_resolution": 250,
    },
    "focused_beam_large": {
        "volume": 2_500, "damage": 500, "damage_type": "thermal",
        "cycle_time": 15, "cap_per_cycle": 200,
        "optimal_range": 60_000, "falloff": 25_000,
        "tracking_speed": 0.005, "sig_resolution": 1_000,
    },
    "reactive_armor_membrane_medium": {
        "volume": 250, "all_resistance_bonus": 0.12, "speed_penalty": 0.05,
    },
    "reactive_armor_membrane_large": {
        "volume": 1_800, "all_resistance_bonus": 0.20, "speed_penalty": 0.08,
    },
    "armor_repair_nexus_medium": {
        "volume": 450, "armor_repair": 120,
        "cycle_time": 10, "cap_per_cycle": 80,
    },
    "armor_repair_nexus_large": {
        "volume": 2_800, "armor_repair": 600,
        "cycle_time": 10, "cap_per_cycle": 320,
    },
    "solar_lance": {
        "volume": 100_000, "damage": 50_000, "damage_type": "thermal",
        "range": 100_000, "charge_time": 60, "cooldown": 300,
        "cap_cost": 10_000, "max_angular_velocity": 0.001,
        "min_ship_class": "mothership",
    },
}

# Voidborn-exclusive module params
VOIDBORN_MODULE_PARAMS: Dict[str, dict] = {
    "light_leech_projector": {
        "volume": 80, "cycle_time": 5, "cap_per_cycle": 20,
        "range": 8_000,
        "leech_damage_per_tick": 3.0, "leech_damage_type": "kinetic",
        "leech_cap_drain_per_tick": 5.0, "leech_duration": 60, "leech_type": "light",
    },
    "heavy_leech_projector": {
        "volume": 400, "cycle_time": 8, "cap_per_cycle": 60,
        "range": 15_000,
        "leech_damage_per_tick": 8.0, "leech_damage_type": "kinetic",
        "leech_cap_drain_per_tick": 15.0, "leech_duration": 90, "leech_type": "heavy",
    },
    "phase_shield_amplifier_medium": {
        "volume": 280, "shield_repair": 150,
        "cycle_time": 8, "cap_per_cycle": 65,
    },
    "phase_shield_amplifier_large": {
        "volume": 1_800, "shield_repair": 750,
        "cycle_time": 8, "cap_per_cycle": 250,
    },
    "small_stealth_field": {
        "volume": 100, "sig_radius_mult": 0.50,
        "cycle_time": 3, "cap_per_cycle": 15,
        "decloak_cooldown": 10,
    },
    "medium_stealth_field": {
        "volume": 600, "sig_radius_mult": 0.50,
        "cycle_time": 3, "cap_per_cycle": 50,
        "decloak_cooldown": 10,
    },
    "bio_repair_swarm": {
        "volume": 80_000, "cycle_time": 1, "cap_per_cycle": 400,
        "repair_percent_per_tick": 0.02, "range": 30_000,
        "min_ship_class": "mothership",
    },
}

# Shared counter-module
SHARED_MODULE_PARAMS: Dict[str, dict] = {
    "shield_purge": {
        "volume": 200, "cycle_time": 30, "cap_per_cycle": 100,
        "shield_hp_cost_percent": 0.10,
    },
}

# Helper sets for module type classification
# Faction-specific classification sets
SOLARION_TURRET_TYPES: set[str] = {"focused_beam_medium", "focused_beam_large"}
SOLARION_BEAM_TURRET_TYPES = SOLARION_TURRET_TYPES  # alias for tick.py
LEECH_PROJECTOR_TYPES: set[str] = {"light_leech_projector", "heavy_leech_projector"}
STEALTH_FIELD_TYPES: set[str] = {"small_stealth_field", "medium_stealth_field"}
REACTIVE_MEMBRANE_TYPES: set[str] = {"reactive_armor_membrane_medium", "reactive_armor_membrane_large"}
SOLARION_ARMOR_REPAIRER_TYPES: set[str] = {"armor_repair_nexus_medium", "armor_repair_nexus_large"}
VOIDBORN_SHIELD_BOOSTER_TYPES: set[str] = {"phase_shield_amplifier_medium", "phase_shield_amplifier_large"}

# Solarion-exclusive module types (all modules only installable on Solarion ships)
SOLARION_EXCLUSIVE_MODULES: set[str] = set(SOLARION_MODULE_PARAMS.keys())
# Voidborn-exclusive module types
VOIDBORN_EXCLUSIVE_MODULES: set[str] = set(VOIDBORN_MODULE_PARAMS.keys())

TURRET_TYPES: set[str] = set(TURRET_PARAMS.keys()) | SOLARION_TURRET_TYPES
MISSILE_TYPES: set[str] = set(MISSILE_PARAMS.keys())
WEAPON_TYPES: set[str] = TURRET_TYPES | MISSILE_TYPES | SOLARION_TURRET_TYPES | LEECH_PROJECTOR_TYPES
SHIELD_EXTENDER_TYPES: set[str] = {
    "small_shield_extender", "medium_shield_extender", "large_shield_extender",
    "starter_shield_extender",
}
SHIELD_HARDENER_TYPES: set[str] = {
    k for k in DEFENSIVE_MODULE_PARAMS
    if "shield_hardener" in k
}
SHIELD_BOOSTER_TYPES: set[str] = {
    "small_shield_booster", "medium_shield_booster", "large_shield_booster",
} | VOIDBORN_SHIELD_BOOSTER_TYPES
ARMOR_PLATE_TYPES: set[str] = {
    "small_armor_plate", "medium_armor_plate", "large_armor_plate",
    "starter_armor_plate",
}
ARMOR_HARDENER_TYPES: set[str] = {
    k for k in DEFENSIVE_MODULE_PARAMS
    if "armor_hardener" in k
}
ARMOR_REPAIRER_TYPES: set[str] = {
    "small_armor_repairer", "medium_armor_repairer", "large_armor_repairer",
} | SOLARION_ARMOR_REPAIRER_TYPES
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


class Team(SQLModel, table=True):
    """A faction team that players join."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    faction: str  # "solarion" or "voidborn"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    users: List["User"] = Relationship(back_populates="team")
    ships: List["Spaceship"] = Relationship(back_populates="team")


class Match(SQLModel, table=True):
    """A competitive match between two teams."""
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    status: str = Field(default=MatchStatus.pending.value, index=True)

    team1_id: Optional[int] = Field(default=None, foreign_key="team.id")
    team2_id: Optional[int] = Field(default=None, foreign_key="team.id")
    # use_alter=True breaks circular FK dependency (match ↔ spaceship)
    team1_mothership_id: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, sa.ForeignKey("spaceship.id", use_alter=True), nullable=True),
    )
    team2_mothership_id: Optional[int] = Field(
        default=None,
        sa_column=sa.Column(sa.Integer, sa.ForeignKey("spaceship.id", use_alter=True), nullable=True),
    )
    winner_team_id: Optional[int] = Field(default=None, foreign_key="team.id")

    started_at_tick: Optional[int] = Field(default=None)
    ended_at_tick: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Surrender tracking: comma-separated user IDs who voted
    surrender_votes_team1: str = Field(default="")
    surrender_votes_team2: str = Field(default="")


class User(SQLModel, table=True):
    """Player account. Auth uses the token field."""

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    token: str = Field(unique=True, index=True)
    # password_hash stores a hex-encoded SHA-256(salt:password) string
    password_hash: Optional[str] = Field(default=None)

    # Points (Phase 9)
    points: float = Field(default=0.0)

    # Team membership (Phase 7)
    team_id: Optional[int] = Field(default=None, foreign_key="team.id")

    ships: List["Spaceship"] = Relationship(
        back_populates="owner",
        sa_relationship_kwargs={"foreign_keys": "Spaceship.user_id"},
    )
    events: List["Event"] = Relationship(back_populates="user")
    team: Optional["Team"] = Relationship(back_populates="users")


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

    # Ownership & loadout (Phase 9)
    user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    claimed_by_user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    built_by_user_id: Optional[int] = Field(default=None)
    loadout_points_spent: float = Field(default=0.0)
    last_damage_by_user_id: Optional[int] = Field(default=None)

    # Team membership (Phase 7)
    team_id: Optional[int] = Field(default=None, foreign_key="team.id")

    # Match scope (Phase 8) — NULL means free-play
    match_id: Optional[int] = Field(default=None, foreign_key="match.id", index=True)

    # Relationships
    owner: Optional[User] = Relationship(
        back_populates="ships",
        sa_relationship_kwargs={"foreign_keys": "Spaceship.user_id"},
    )
    team: Optional["Team"] = Relationship(back_populates="ships")
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

    @property
    def faction(self) -> Optional[str]:
        """Derive faction from team."""
        if self.team is not None:
            return self.team.faction
        return None

    def class_constants(self) -> dict:
        return get_ship_classes(self.faction)[self.ship_class.value]

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
        """Sum of speed penalties from all armor plate and reactive membrane modules."""
        total = 0.0
        for m in self.modules:
            if m.module_type.value in ARMOR_PLATE_TYPES:
                params = DEFENSIVE_MODULE_PARAMS.get(m.module_type.value, {})
                total += params.get("speed_penalty", 0.0)
            elif m.module_type.value in REACTIVE_MEMBRANE_TYPES:
                params = SOLARION_MODULE_PARAMS.get(m.module_type.value, {})
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
        """Signature radius including shield extender bonuses and stealth field."""
        extra = 0.0
        stealth_mult = 1.0
        for m in self.modules:
            if m.module_type.value in SHIELD_EXTENDER_TYPES:
                params = DEFENSIVE_MODULE_PARAMS.get(m.module_type.value, {})
                extra += params.get("sig_radius_bonus", 0.0)
            if m.module_type.value in STEALTH_FIELD_TYPES and m.active:
                params = VOIDBORN_MODULE_PARAMS.get(m.module_type.value, {})
                stealth_mult = min(stealth_mult, params.get("sig_radius_mult", 1.0))
        return (self.signature_radius + extra) * stealth_mult

    def compute_resistances(self, layer: str) -> Dict[str, float]:
        """
        Compute effective resistances for shield or armor layer,
        including active hardeners with stacking penalties.
        Returns {damage_type: resistance_fraction}.
        """
        base = get_base_resists(self.faction, layer)

        # Reactive armor membrane bonus (Solarion passive module)
        if layer == "armor":
            for m in self.modules:
                if m.module_type.value in REACTIVE_MEMBRANE_TYPES:
                    params = SOLARION_MODULE_PARAMS.get(m.module_type.value, {})
                    bonus = params.get("all_resistance_bonus", 0.0)
                    for dt in base:
                        base[dt] += bonus

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

    # --- Phase 7: Solar Lance state ---
    lance_state: str = Field(default="idle")  # idle, charging, cooldown
    lance_charge_remaining: int = Field(default=0)
    lance_cooldown_remaining: int = Field(default=0)
    lance_target_ship_id: Optional[int] = Field(default=None)
    # --- Phase 7: Stealth field ---
    stealth_cooldown_remaining: int = Field(default=0)

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
    ore_richness: float = Field(default=1.0)

    # Wreck-specific: tick when the object was created (for expiration)
    created_tick: Optional[int] = Field(default=None)

    # Match scope (Phase 8) — NULL means free-play
    match_id: Optional[int] = Field(default=None, foreign_key="match.id", index=True)


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

    # Unified stream fields (Phase 10)
    category: str = Field(default="action", index=True)  # "action" | "points" | "chat"
    amount: Optional[float] = Field(default=None)    # points amount
    reason: Optional[str] = Field(default=None)       # "damage dealt", "mining", etc.
    team_id: Optional[int] = Field(default=None, index=True)
    username: Optional[str] = Field(default=None)     # denormalized sender name

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
    Tracks active and completed research per user/team.

    Each row represents one research effort. Status is 'researching', 'paused',
    'complete', or 'cancelled'. Research benefits the user's team if they have one,
    otherwise it is per-user.
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
    team_id: Optional[int] = Field(default=None, foreign_key="team.id", index=True)


class ResearchContributor(SQLModel, table=True):
    """Join table tracking contributors to duplicable (hull) research."""
    id: Optional[int] = Field(default=None, primary_key=True)
    research_id: int = Field(foreign_key="researchprogress.id", index=True)
    ship_id: int = Field(foreign_key="spaceship.id")
    module_id: int = Field(default=0)
    user_id: int = Field(foreign_key="user.id")


class LeechDebuff(SQLModel, table=True):
    """An active leech debuff applied to a ship by a Voidborn leech projector."""
    id: Optional[int] = Field(default=None, primary_key=True)
    source_ship_id: int = Field(foreign_key="spaceship.id", index=True)
    target_ship_id: int = Field(foreign_key="spaceship.id", index=True)
    leech_type: str = Field(default="light")  # "light" or "heavy"
    damage_per_tick: float = Field(default=0.0)
    damage_type: str = Field(default="kinetic")
    cap_drain_per_tick: float = Field(default=0.0)
    ticks_remaining: int = Field(default=0)
    created_at_tick: int = Field(default=0)


class Command(SQLModel, table=True):
    """A queued player command to be processed by the tick loop."""
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    ship_id: Optional[int] = Field(default=None, foreign_key="spaceship.id")
    command_type: str
    payload: str = Field(default="{}")
    status: str = Field(default=CommandStatus.pending.value, index=True)
    rejection_reason: Optional[str] = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"server_default": sa.func.now()},
    )
    processed_at_tick: Optional[int] = None


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def create_default_ship(
    name: str,
    ship_class: ShipClass,
    user_id: Optional[int] = None,
    pos_x: float = 0.0,
    pos_y: float = 0.0,
    pos_z: float = 0.0,
    vel_x: float = 0.0,
    vel_y: float = 0.0,
    vel_z: float = 0.0,
    team_id: Optional[int] = None,
    faction: Optional[str] = None,
) -> Spaceship:
    """
    Instantiate a Spaceship with hull defaults from SHIP_CLASSES (or faction variant).

    NOTE: Does not populate modules or compute max_capacitor — callers must
    add modules and call ``recalculate_capacitor`` after persisting.
    """
    consts = get_ship_classes(faction)[ship_class.value]
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
        team_id=team_id,
    )
    return ship


def recalculate_max_capacitor(ship: Spaceship) -> None:
    """
    Recompute ship.max_capacitor from base hull value + reactor modules.
    Mutates the ship object in place.
    """
    consts = ship.class_constants()
    reactor_bonus = sum(
        m.volume * 5.0
        for m in ship.modules
        if m.module_type == ModuleType.reactor
    )
    ship.max_capacitor = consts["base_cap"] + reactor_bonus


def recalculate_max_shield(ship: Spaceship) -> None:
    """Recompute ship.max_shield_hp from base hull value + shield extenders."""
    consts = ship.class_constants()
    extender_bonus = sum(
        DEFENSIVE_MODULE_PARAMS.get(m.module_type.value, {}).get("shield_bonus", 0.0)
        for m in ship.modules
        if m.module_type.value in SHIELD_EXTENDER_TYPES
    )
    ship.max_shield_hp = consts["base_shield"] + extender_bonus


def recalculate_max_armor(ship: Spaceship) -> None:
    """Recompute ship.max_armor_hp from base hull value + armor plates."""
    consts = ship.class_constants()
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

    # --- Solarion turrets (focused beams) ---
    if mt_val in SOLARION_TURRET_TYPES:
        p = SOLARION_MODULE_PARAMS[mt_val]
        return ShipModule(
            module_type=module_type, volume=p["volume"], active=False,
            cycle_time=p["cycle_time"], ticks_until_cycle=p["cycle_time"],
            capacitor_per_cycle=p["cap_per_cycle"],
            damage_per_cycle=float(p["damage"]), damage_type=p["damage_type"],
            optimal_range=float(p["optimal_range"]), falloff_range=float(p["falloff"]),
            tracking_speed=p["tracking_speed"], sig_resolution=float(p["sig_resolution"]),
        )

    # --- Reactive armor membranes (passive) ---
    if mt_val in REACTIVE_MEMBRANE_TYPES:
        p = SOLARION_MODULE_PARAMS[mt_val]
        return ShipModule(
            module_type=module_type, volume=p["volume"], active=False,
            cycle_time=0, ticks_until_cycle=0, capacitor_per_cycle=0.0,
        )

    # --- Armor repair nexus ---
    if mt_val in SOLARION_ARMOR_REPAIRER_TYPES:
        p = SOLARION_MODULE_PARAMS[mt_val]
        return ShipModule(
            module_type=module_type, volume=p["volume"], active=False,
            cycle_time=p["cycle_time"], ticks_until_cycle=p["cycle_time"],
            capacitor_per_cycle=p["cap_per_cycle"],
            armor_repair_per_cycle=float(p["armor_repair"]),
        )

    # --- Solar Lance ---
    if mt_val == "solar_lance":
        p = SOLARION_MODULE_PARAMS["solar_lance"]
        return ShipModule(
            module_type=module_type, volume=p["volume"], active=False,
            cycle_time=0, ticks_until_cycle=0,
            capacitor_per_cycle=0.0,
            damage_per_cycle=float(p["damage"]), damage_type=p["damage_type"],
            optimal_range=float(p["range"]),
            lance_state="idle",
        )

    # --- Leech projectors ---
    if mt_val in LEECH_PROJECTOR_TYPES:
        p = VOIDBORN_MODULE_PARAMS[mt_val]
        return ShipModule(
            module_type=module_type, volume=p["volume"], active=False,
            cycle_time=p["cycle_time"], ticks_until_cycle=p["cycle_time"],
            capacitor_per_cycle=p["cap_per_cycle"],
            optimal_range=float(p["range"]),
        )

    # --- Phase shield amplifiers ---
    if mt_val in VOIDBORN_SHIELD_BOOSTER_TYPES:
        p = VOIDBORN_MODULE_PARAMS[mt_val]
        return ShipModule(
            module_type=module_type, volume=p["volume"], active=False,
            cycle_time=p["cycle_time"], ticks_until_cycle=p["cycle_time"],
            capacitor_per_cycle=p["cap_per_cycle"],
            shield_repair_per_cycle=float(p["shield_repair"]),
        )

    # --- Stealth fields ---
    if mt_val in STEALTH_FIELD_TYPES:
        p = VOIDBORN_MODULE_PARAMS[mt_val]
        return ShipModule(
            module_type=module_type, volume=p["volume"], active=False,
            cycle_time=p["cycle_time"], ticks_until_cycle=p["cycle_time"],
            capacitor_per_cycle=p["cap_per_cycle"],
        )

    # --- Bio-Repair Swarm ---
    if mt_val == "bio_repair_swarm":
        p = VOIDBORN_MODULE_PARAMS["bio_repair_swarm"]
        return ShipModule(
            module_type=module_type, volume=p["volume"], active=False,
            cycle_time=p["cycle_time"], ticks_until_cycle=p["cycle_time"],
            capacitor_per_cycle=p["cap_per_cycle"],
            optimal_range=float(p["range"]),
        )

    # --- Shield purge ---
    if mt_val == "shield_purge":
        p = SHARED_MODULE_PARAMS["shield_purge"]
        return ShipModule(
            module_type=module_type, volume=p["volume"], active=False,
            cycle_time=p["cycle_time"], ticks_until_cycle=p["cycle_time"],
            capacitor_per_cycle=p["cap_per_cycle"],
        )

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
    name: Optional[str] = None,
    built_by_user_id: Optional[int] = None,
) -> Spaceship:
    """
    Spawn a newly built ship docked in the builder.

    Returns an unsaved Spaceship (caller must add to session).
    The ship starts with no modules, full base capacitor, zero ore.
    Ship is docked inside the builder and unclaimed.
    """
    # Derive faction from builder's team
    faction = builder.faction
    consts = get_ship_classes(faction)[blueprint.value]
    ship = Spaceship(
        name=name or f"New {blueprint.value.replace('_', ' ').title()}",
        ship_class=blueprint,
        pos_x=builder.pos_x,
        pos_y=builder.pos_y,
        pos_z=builder.pos_z,
        vel_x=0.0,
        vel_y=0.0,
        vel_z=0.0,
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
        team_id=builder.team_id,
        match_id=builder.match_id,
        docked_in_id=builder.id,
        claimed_by_user_id=None,
        built_by_user_id=built_by_user_id or builder.user_id,
    )
    return ship
