"""
Auth routes.

POST /api/auth/register — create a new user account and spawn the default
                          mothership loadout.
POST /api/auth/login    — retrieve token for an existing user.
"""

from __future__ import annotations

import hashlib
import math
import random
import secrets
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from server.auth import generate_token, get_current_user
from server.database import get_session
from server.models import (
    CelestialObject,
    CelestialType,
    ModuleType,
    ShipClass,
    Spaceship,
    User,
    create_default_ship,
    make_module,
    recalculate_max_capacitor,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    user_id: int
    username: str
    token: str


class MeResponse(BaseModel):
    user_id: int
    username: str
    ship_count: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    """Return a salted SHA-256 hash of the password as 'salt:hex_digest'."""
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return f"{salt}:{digest}"


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored 'salt:hex_digest' hash."""
    try:
        salt, stored_digest = password_hash.split(":", 1)
    except ValueError:
        return False
    digest = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
    return secrets.compare_digest(digest, stored_digest)


def _random_spawn_position(radius: float = 10_000.0) -> tuple[float, float, float]:
    """Return a uniformly distributed random point within ``radius`` metres of the origin."""
    theta = random.uniform(0, 2 * math.pi)
    phi = math.acos(1 - 2 * random.random())  # uniform distribution on sphere surface
    r = radius * (random.random() ** (1 / 3))  # cube-root for uniform distribution inside sphere
    x = r * math.sin(phi) * math.cos(theta)
    y = r * math.sin(phi) * math.sin(theta)
    z = r * math.cos(phi)
    return x, y, z


async def _spawn_starter_mothership(user_id: int, session: AsyncSession) -> Spaceship:
    """
    Create the starter mothership — a fully equipped capital ship that lets
    new players immediately access all game systems (mining, scanning,
    combat, production, research).

      Engines          200 000 m³
      Reactors         100 000 m³   (cap bonus: 500 000)
      Cargo Bay        200 000 m³
      Docking Bay      100 000 m³
      Factory          300 000 m³   (can build up to cruiser)
      Mining Lasers    4 ×     200 m³
      Strip Miner      1 ×   1 000 m³
      Scanner          1 ×     500 m³
      Passive Det.     1 ×     100 m³
      Research Module  1 ×   5 000 m³
      Small Turrets    4 × (fixed)      (2 kinetic, 2 thermal)
      Shield Ext.      1 × (fixed)
      Armor Plate      1 × (fixed)
      Shield Booster   1 × (fixed)
      Armor Repairer   1 × (fixed)
      Dropoff          1 ×     500 m³

    Starting capacitor = 525 000 (base 25 000 + reactor bonus 500 000).
    Fixed-size modules use their spec volumes automatically.
    """
    pos_x, pos_y, pos_z = _random_spawn_position(10_000.0)

    ship = create_default_ship(
        name="Mothership",
        ship_class=ShipClass.mothership,
        user_id=user_id,
        pos_x=pos_x,
        pos_y=pos_y,
        pos_z=pos_z,
    )
    session.add(ship)
    await session.flush()  # get ship.id

    # Install default modules — well-rounded loadout for all game systems
    modules = [
        make_module(ModuleType.engine, 200_000),
        make_module(ModuleType.reactor, 100_000),
        make_module(ModuleType.cargo_bay, 200_000),
        make_module(ModuleType.docking_bay, 100_000),
        make_module(ModuleType.factory, 300_000),
        make_module(ModuleType.mining_laser, 200),
        make_module(ModuleType.mining_laser, 200),
        make_module(ModuleType.mining_laser, 200),
        make_module(ModuleType.mining_laser, 200),
        make_module(ModuleType.strip_miner, 1_000),
        make_module(ModuleType.scanner, 500),
        make_module(ModuleType.passive_detector, 100),
        make_module(ModuleType.research_module, 5_000),
        make_module(ModuleType.small_turret_kinetic, 200),
        make_module(ModuleType.small_turret_kinetic, 200),
        make_module(ModuleType.small_turret_thermal, 200),
        make_module(ModuleType.small_turret_thermal, 200),
        make_module(ModuleType.small_shield_extender, 1_000),
        make_module(ModuleType.small_armor_plate, 1_000),
        make_module(ModuleType.small_shield_booster, 1_000),
        make_module(ModuleType.small_armor_repairer, 1_000),
        make_module(ModuleType.dropoff, 500),
    ]
    for mod in modules:
        mod.ship_id = ship.id
        session.add(mod)

    await session.flush()  # populate ship.modules via reload below

    # Reload ship with modules attached so recalculate works
    await session.refresh(ship, attribute_names=["modules"])
    recalculate_max_capacitor(ship)
    ship.capacitor = ship.max_capacitor  # start fully charged

    # Place a rich asteroid field (10-15) within 10 km of spawn
    num_asteroids = random.randint(10, 15)
    for i in range(num_asteroids):
        ax, ay, az = _random_spawn_position(10_000.0)
        ore_amount = random.uniform(5_000.0, 20_000.0)
        asteroid = CelestialObject(
            name=f"Asteroid {i + 1}",
            object_type=CelestialType.asteroid,
            pos_x=pos_x + ax,
            pos_y=pos_y + ay,
            pos_z=pos_z + az,
            ore_remaining=ore_amount,
            ore_initial=ore_amount,
        )
        session.add(asteroid)

    return ship


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    """
    Create a new player account.

    - Generates a unique bearer token.
    - Spawns the default starter mothership.
    - Returns the token the client must include in all future requests.
    """
    # Check username is not taken
    existing = await session.exec(select(User).where(User.username == body.username))
    if existing.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{body.username}' is already taken",
        )

    token = generate_token()
    password_hash = _hash_password(body.password)
    user = User(username=body.username, token=token, password_hash=password_hash)
    session.add(user)
    await session.flush()  # get user.id

    await _spawn_starter_mothership(user.id, session)

    await session.commit()
    await session.refresh(user)

    return AuthResponse(user_id=user.id, username=user.username, token=user.token)


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    """
    Retrieve the token for an existing user account.

    Returns HTTP 401 if the password is incorrect.
    """
    result = await session.exec(select(User).where(User.username == body.username))
    user = result.first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No account found for username '{body.username}'",
        )

    if not _verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AuthResponse(user_id=user.id, username=user.username, token=user.token)


@router.get("/me", response_model=MeResponse)
async def me(
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """Return the authenticated user's id, username, and ship count."""
    from server.models import Spaceship
    ships_result = await session.exec(
        select(Spaceship).where(Spaceship.user_id == current_user.id)
    )
    ship_count = len(list(ships_result.all()))
    return MeResponse(
        user_id=current_user.id,
        username=current_user.username,
        ship_count=ship_count,
    )
