"""
Match system — map generation and mothership creation for Phase 8.

Provides:
  - generate_match_map()       — procedurally creates asteroids for a match
  - create_match_mothership()  — spawns a fully-fitted mothership for a team
"""

from __future__ import annotations

import logging
import math
import random
from typing import Optional

from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.models import (
    ASTEROID_SIZES,
    MATCH_MOTHERSHIP_LOADOUT,
    CelestialObject,
    CelestialType,
    ModuleType,
    ShipClass,
    ShipModule,
    Spaceship,
    Team,
    User,
    create_default_ship,
    make_module,
    recalculate_max_armor,
    recalculate_max_capacitor,
    recalculate_max_shield,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _random_point_in_sphere(
    center_x: float,
    center_y: float,
    center_z: float,
    radius: float,
) -> tuple[float, float, float]:
    """Return a uniformly distributed point inside a sphere."""
    theta = random.uniform(0, 2 * math.pi)
    phi = math.acos(1 - 2 * random.random())
    r = radius * (random.random() ** (1 / 3))
    x = center_x + r * math.sin(phi) * math.cos(theta)
    y = center_y + r * math.sin(phi) * math.sin(theta)
    z = center_z + r * math.cos(phi)
    return x, y, z


def _random_point_in_shell(
    center_x: float,
    center_y: float,
    center_z: float,
    inner_radius: float,
    outer_radius: float,
) -> tuple[float, float, float]:
    """Return a uniformly distributed point in a spherical shell."""
    theta = random.uniform(0, 2 * math.pi)
    phi = math.acos(1 - 2 * random.random())
    # Uniform in shell volume
    r = (random.uniform(inner_radius**3, outer_radius**3)) ** (1 / 3)
    x = center_x + r * math.sin(phi) * math.cos(theta)
    y = center_y + r * math.sin(phi) * math.sin(theta)
    z = center_z + r * math.cos(phi)
    return x, y, z


def _pick_size(distribution: list[tuple[str, float]]) -> tuple[str, float]:
    """Pick an asteroid size based on weighted distribution.

    distribution: list of (size_name, probability) pairs.
    Returns (size_name, ore_amount).
    """
    roll = random.random()
    cumulative = 0.0
    for size_name, prob in distribution:
        cumulative += prob
        if roll < cumulative:
            return size_name, ASTEROID_SIZES[size_name]
    # Fallback to last entry
    last = distribution[-1]
    return last[0], ASTEROID_SIZES[last[0]]


def _make_asteroid(
    name: str,
    pos: tuple[float, float, float],
    ore: float,
    match_id: int,
    richness: float = 1.0,
) -> CelestialObject:
    return CelestialObject(
        name=name,
        object_type=CelestialType.asteroid,
        pos_x=pos[0],
        pos_y=pos[1],
        pos_z=pos[2],
        ore_remaining=ore,
        ore_initial=ore,
        ore_richness=richness,
        match_id=match_id,
    )


# ---------------------------------------------------------------------------
# Map generation
# ---------------------------------------------------------------------------


async def generate_match_map(session, match, team1, team2, current_tick: int) -> None:
    """
    Create all CelestialObjects for a match.

    Layout (distances in metres, 1 km = 1000 m):
      - Team 1 home: (-100_000, 0, 0) — 8 medium nearby + 10 scattered
      - Team 2 home: (+100_000, 0, 0) — mirror
      - Contested center: 30-40 asteroids within 50 km of origin
      - Flanking fields: 2 clusters of 8-12 at ~25 km off-axis
    """
    match_id = match.id
    asteroids: list[CelestialObject] = []
    idx = 0

    # --- Team home zones ---
    for label, home_x in [("Alpha", -100_000.0), ("Bravo", 100_000.0)]:
        # 8 medium asteroids within 5 km of home
        for _ in range(8):
            pos = _random_point_in_sphere(home_x, 0.0, 0.0, 5_000.0)
            idx += 1
            asteroids.append(_make_asteroid(
                f"{label} Home Asteroid {idx}",
                pos,
                ASTEROID_SIZES["medium"],
                match_id,
            ))

        # 10 scattered in 5-12.5 km zone around the home position
        for _ in range(10):
            size_name, ore = _pick_size([("medium", 0.6), ("large", 0.4)])
            # Scatter in a shell around the home position
            pos = _random_point_in_shell(home_x, 0.0, 0.0, 5_000.0, 12_500.0)
            idx += 1
            asteroids.append(_make_asteroid(
                f"{label} {size_name.title()} Asteroid {idx}",
                pos,
                ore,
                match_id,
            ))

    # --- Contested center (0-50 km from origin) ---
    num_center = random.randint(30, 40)
    for _ in range(num_center):
        size_name, ore = _pick_size([
            ("medium", 0.4),
            ("large", 0.4),
            ("huge", 0.2),
        ])
        pos = _random_point_in_sphere(0.0, 0.0, 0.0, 50_000.0)
        idx += 1
        asteroids.append(_make_asteroid(
            f"Center {size_name.title()} Asteroid {idx}",
            pos,
            ore,
            match_id,
        ))

    # --- Flanking fields (off-axis) ---
    for flank_label, offset_y in [("North", 25_000.0), ("South", -25_000.0)]:
        num_flank = random.randint(8, 12)
        for _ in range(num_flank):
            size_name, ore = _pick_size([("medium", 0.5), ("large", 0.5)])
            pos = _random_point_in_sphere(0.0, offset_y, 0.0, 25_000.0)
            idx += 1
            asteroids.append(_make_asteroid(
                f"{flank_label} {size_name.title()} Asteroid {idx}",
                pos,
                ore,
                match_id,
            ))

    # --- Rich asteroid belt (between teams, high yield) ---
    num_rich = random.randint(8, 14)
    for _ in range(num_rich):
        size_name, ore = _pick_size([("large", 0.5), ("huge", 0.5)])
        richness = round(random.uniform(2.0, 5.0), 1)
        pos = _random_point_in_shell(0.0, 0.0, 0.0, 15_000.0, 50_000.0)
        idx += 1
        asteroids.append(_make_asteroid(
            f"Rich {size_name.title()} Asteroid {idx}",
            pos,
            ore,
            match_id,
            richness=richness,
        ))

    for asteroid in asteroids:
        session.add(asteroid)

    logger.info("Generated %d asteroids for match #%d", len(asteroids), match_id)


# ---------------------------------------------------------------------------
# Mothership creation
# ---------------------------------------------------------------------------


async def create_match_mothership(
    session,
    team: Team,
    position: tuple[float, float, float],
    match_id: int,
    current_tick: int,
) -> Spaceship:
    """
    Create a fully-fitted mothership for a team in a match.

    - Uses create_default_ship() with faction from team
    - Installs modules per MATCH_MOTHERSHIP_LOADOUT
    - Sets 5,000 starting ore
    - Recalculates capacitor/shield/armor
    - Sets match_id
    """
    faction = team.faction
    ship_name = f"{team.name} Mothership"

    ship = create_default_ship(
        name=ship_name,
        ship_class=ShipClass.mothership,
        user_id=None,
        pos_x=position[0],
        pos_y=position[1],
        pos_z=position[2],
        team_id=team.id,
        faction=faction,
    )
    ship.match_id = match_id
    ship.ore = 7_500.0
    ship.claimed_by_user_id = None

    session.add(ship)
    await session.flush()  # get ship.id

    # Install loadout modules
    for module_type_str, volume in MATCH_MOTHERSHIP_LOADOUT:
        mod = make_module(ModuleType(module_type_str), volume)
        mod.ship_id = ship.id
        session.add(mod)

    await session.flush()

    # Reload ship with relationships eagerly loaded so recalculate_* helpers
    # work and callers don't trigger lazy-loads in async context
    result = await session.exec(
        select(Spaceship)
        .where(Spaceship.id == ship.id)
        .options(
            selectinload(Spaceship.modules),
            selectinload(Spaceship.movement_orders),
            selectinload(Spaceship.build_orders),
            selectinload(Spaceship.target_locks),
            selectinload(Spaceship.team),
        )
    )
    ship = result.one()

    # Recalculate derived stats
    recalculate_max_capacitor(ship)
    ship.capacitor = ship.max_capacitor
    recalculate_max_shield(ship)
    ship.shield_hp = ship.max_shield_hp
    recalculate_max_armor(ship)
    ship.armor_hp = ship.max_armor_hp

    await session.flush()
    return ship


# ---------------------------------------------------------------------------
# Post-match cleanup
# ---------------------------------------------------------------------------


async def cleanup_match_assignments(session, match) -> None:
    """Clear team_id from users and ships so players can join new matches."""
    for tid in [match.team1_id, match.team2_id]:
        if tid is None:
            continue
        # Clear user team assignments
        user_result = await session.exec(select(User).where(User.team_id == tid))
        for user in user_result.all():
            user.team_id = None
        # Clear ship team assignments for match-scoped ships only
        ship_result = await session.exec(
            select(Spaceship).where(Spaceship.team_id == tid, Spaceship.match_id == match.id)
        )
        for ship in ship_result.all():
            ship.team_id = None
