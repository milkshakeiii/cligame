"""
Combat system for Phase 4.

Implements:
  - Turret tracking formula (angular velocity + hit chance)
  - Range factor calculation
  - Damage application (sig ratio, resistances, shield-then-armor)
  - Missile damage reduction
  - Shield regeneration
  - Target lock time calculation
"""

from __future__ import annotations

import math
import random
from typing import Dict, Optional

from server.models import (
    ARMOR_BASE_RESISTS,
    SHIELD_BASE_RESISTS,
    SHIP_CLASSES,
    Spaceship,
    ShipModule,
)
from server.physics import (
    Vec3,
    vec_distance,
    vec_dot,
    vec_magnitude,
    vec_scale,
    vec_sub,
)


# ---------------------------------------------------------------------------
# Transversal velocity
# ---------------------------------------------------------------------------

def compute_transversal_velocity(
    attacker_pos: Vec3,
    attacker_vel: Vec3,
    target_pos: Vec3,
    target_vel: Vec3,
) -> float:
    """
    Compute the transversal velocity between attacker and target.
    Transversal = component of relative velocity perpendicular to the
    line between attacker and target.
    """
    direction = vec_sub(target_pos, attacker_pos)
    dist = vec_magnitude(direction)
    if dist < 1e-6:
        return 0.0

    direction_unit = vec_scale(direction, 1.0 / dist)
    relative_vel = vec_sub(target_vel, attacker_vel)

    # Radial component (along the line)
    radial_speed = vec_dot(relative_vel, direction_unit)
    radial_component = vec_scale(direction_unit, radial_speed)

    # Transversal = relative_vel - radial_component
    transversal = vec_sub(relative_vel, radial_component)
    return vec_magnitude(transversal)


def compute_angular_velocity(
    transversal_velocity: float,
    distance: float,
) -> float:
    """Angular velocity = transversal / distance."""
    if distance < 1e-6:
        return float("inf")
    return transversal_velocity / distance


# ---------------------------------------------------------------------------
# Hit chance
# ---------------------------------------------------------------------------

def compute_tracking_hit_chance(
    angular_velocity: float,
    turret_tracking_speed: float,
    turret_sig_resolution: float,
    target_sig_radius: float,
) -> float:
    """
    EVE-style tracking formula:
      tracking_term = (angular_velocity / tracking_speed) * (sig_resolution / target_sig_radius)
      hit_chance = 0.5 ^ (tracking_term ^ 2)
    """
    if turret_tracking_speed <= 0:
        return 0.0
    if target_sig_radius <= 0:
        return 0.0

    tracking_term = (angular_velocity / turret_tracking_speed) * (turret_sig_resolution / target_sig_radius)
    return 0.5 ** (tracking_term ** 2)


def compute_range_factor(
    distance: float,
    optimal_range: float,
    falloff: float,
) -> float:
    """
    Range-based accuracy factor:
      Within optimal: 1.0
      Beyond optimal: 0.5 ^ ((distance - optimal) / falloff) ^ 2
    """
    if distance <= optimal_range:
        return 1.0
    if falloff <= 0:
        return 0.0
    excess = (distance - optimal_range) / falloff
    return 0.5 ** (excess ** 2)


def compute_final_hit_chance(
    attacker_pos: Vec3,
    attacker_vel: Vec3,
    target_pos: Vec3,
    target_vel: Vec3,
    turret_tracking_speed: float,
    turret_sig_resolution: float,
    target_sig_radius: float,
    optimal_range: float,
    falloff: float,
) -> float:
    """Compute final hit chance combining tracking and range."""
    distance = vec_distance(target_pos, attacker_pos)
    transversal = compute_transversal_velocity(
        attacker_pos, attacker_vel, target_pos, target_vel
    )
    angular_vel = compute_angular_velocity(transversal, distance)

    tracking_chance = compute_tracking_hit_chance(
        angular_vel, turret_tracking_speed, turret_sig_resolution, target_sig_radius
    )
    range_factor = compute_range_factor(distance, optimal_range, falloff)

    return range_factor * tracking_chance


# ---------------------------------------------------------------------------
# Damage application
# ---------------------------------------------------------------------------

def compute_turret_damage(
    base_damage: float,
    turret_sig_resolution: float,
    target_sig_radius: float,
) -> float:
    """
    Turret damage is reduced when shooting small targets with big guns:
      damage_multiplier = min(1.0, target_sig_radius / turret_sig_resolution)
    """
    if turret_sig_resolution <= 0:
        return base_damage
    multiplier = min(1.0, target_sig_radius / turret_sig_resolution)
    return base_damage * multiplier


def compute_missile_damage(
    base_damage: float,
    explosion_radius: float,
    explosion_velocity: float,
    target_sig_radius: float,
    target_speed: float,
) -> float:
    """
    Missile damage reduction against small/fast targets:
      sig_factor = min(1.0, target_sig / explosion_radius)
      speed_factor = min(1.0, explosion_velocity / target_speed)
      damage = base_damage * min(1.0, sig_factor * speed_factor)
    """
    sig_factor = min(1.0, target_sig_radius / explosion_radius) if explosion_radius > 0 else 1.0
    speed_factor = min(1.0, explosion_velocity / target_speed) if target_speed > 0 else 1.0
    reduction = min(1.0, sig_factor * speed_factor)
    return base_damage * reduction


def apply_damage(
    target: Spaceship,
    damage: float,
    damage_type: str,
) -> Dict[str, float]:
    """
    Apply damage to a ship, respecting resistances and shield-before-armor order.

    Returns a dict with details:
      {
        "shield_damage": float,
        "armor_damage": float,
        "total_applied": float,
        "shields_broken": bool,
        "armor_critical": bool,  # armor dropped below 25%
        "destroyed": bool,
      }
    """
    result = {
        "shield_damage": 0.0,
        "armor_damage": 0.0,
        "total_applied": 0.0,
        "shields_broken": False,
        "armor_critical": False,
        "destroyed": False,
    }

    if target.is_destroyed:
        return result

    remaining = damage

    # --- Shield layer ---
    if target.shield_hp > 0:
        shield_resists = target.compute_resistances("shield")
        resist = shield_resists.get(damage_type, 0.0)
        effective_dmg = remaining * (1.0 - resist)

        absorbed = min(effective_dmg, target.shield_hp)
        target.shield_hp -= absorbed
        result["shield_damage"] = absorbed

        # How much raw damage was consumed by shields?
        if resist < 1.0:
            raw_consumed = absorbed / (1.0 - resist)
        else:
            raw_consumed = remaining
        remaining -= raw_consumed

        if target.shield_hp <= 0:
            target.shield_hp = 0.0
            result["shields_broken"] = True

    # --- Armor layer ---
    if remaining > 0 and target.armor_hp > 0:
        armor_resists = target.compute_resistances("armor")
        resist = armor_resists.get(damage_type, 0.0)
        effective_dmg = remaining * (1.0 - resist)

        absorbed = min(effective_dmg, target.armor_hp)
        target.armor_hp -= absorbed
        result["armor_damage"] = absorbed

        if target.armor_hp <= 0:
            target.armor_hp = 0.0
            target.is_destroyed = True
            result["destroyed"] = True
        elif target.armor_hp <= target.max_armor_hp * 0.25:
            result["armor_critical"] = True

    result["total_applied"] = result["shield_damage"] + result["armor_damage"]
    return result


# ---------------------------------------------------------------------------
# Shield regeneration
# ---------------------------------------------------------------------------

def apply_shield_regen(ship: Spaceship) -> None:
    """
    Apply shield regeneration using the same curve as capacitor regen,
    but with different constants:
      peak_regen = max_shield / 50
    Peaks at ~25% shield.
    """
    if ship.is_destroyed:
        return
    if ship.max_shield_hp <= 0:
        return
    if ship.shield_hp >= ship.max_shield_hp:
        return

    ratio = ship.shield_hp / ship.max_shield_hp
    peak_regen = ship.max_shield_hp / 50.0
    regen = peak_regen * math.sqrt(max(0.0, ratio)) * (1.0 - ratio)
    ship.shield_hp = min(ship.max_shield_hp, ship.shield_hp + regen)


# ---------------------------------------------------------------------------
# Target lock time
# ---------------------------------------------------------------------------

def apply_armor_regen(ship: Spaceship) -> None:
    """Passive armor regen for Voidborn ships. Peak regen = max_armor / 200."""
    if ship.is_destroyed:
        return
    if ship.max_armor_hp <= 0:
        return
    if ship.armor_hp >= ship.max_armor_hp:
        return
    ratio = ship.armor_hp / ship.max_armor_hp
    peak_regen = ship.max_armor_hp / 200.0
    regen = peak_regen * math.sqrt(max(0.0, ratio)) * (1.0 - ratio)
    ship.armor_hp = min(ship.max_armor_hp, ship.armor_hp + regen)


def compute_lock_time(
    attacker_scan_resolution: float,
    target_sig_radius: float,
    base_lock_time: int,
) -> int:
    """
    Lock time = max(1, base_lock_time * (scan_resolution / target_sig_radius))

    Bigger scan_resolution (worse) and smaller target sig = longer lock time.
    """
    if target_sig_radius <= 0:
        return base_lock_time * 10  # very long for zero-sig targets
    raw = base_lock_time * (attacker_scan_resolution / target_sig_radius)
    return max(1, int(round(raw)))
