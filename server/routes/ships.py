"""
Ship read-only routes.

GET    /api/ships                         — list user's ships
GET    /api/ships/{ship_id}               — ship detail + modules + active orders
GET    /api/ships/{ship_id}/modules       — list installed modules

Mutation endpoints (create, install, uninstall, rename, undock) removed in
Phase 8.5.  Use POST /api/commands to enqueue commands instead.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    ARMOR_REPAIRER_TYPES,
    ARMOR_PLATE_TYPES,
    MISSILE_TYPES,
    SHIELD_BOOSTER_TYPES,
    SHIELD_EXTENDER_TYPES,
    SOLARION_MODULE_PARAMS,
    STEALTH_FIELD_TYPES,
    TURRET_TYPES,
    VOIDBORN_MODULE_PARAMS,
    ModuleType,
    ShipModule,
    Spaceship,
    User,
)
from server.routes.common import get_owned_ship as _get_owned_ship_common

router = APIRouter(prefix="/api/ships", tags=["ships"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ModuleOut(BaseModel):
    id: int
    module_type: str
    volume: int
    active: bool
    cycle_time: int
    ticks_until_cycle: int
    capacitor_per_cycle: float
    # Type-specific fields — only populated for relevant module types
    mining_yield: Optional[float] = None
    mining_range: Optional[float] = None
    scan_range: Optional[float] = None
    detection_range: Optional[float] = None
    factory_max_class: Optional[str] = None
    # Weapon fields
    damage_per_cycle: Optional[float] = None
    damage_type: Optional[str] = None
    optimal_range: Optional[float] = None
    falloff_range: Optional[float] = None
    tracking_speed: Optional[float] = None
    sig_resolution: Optional[float] = None
    missile_speed: Optional[float] = None
    missile_flight_time: Optional[int] = None
    explosion_radius: Optional[float] = None
    explosion_velocity: Optional[float] = None
    # Defensive fields
    shield_hp_bonus: Optional[float] = None
    armor_hp_bonus: Optional[float] = None
    shield_repair_per_cycle: Optional[float] = None
    armor_repair_per_cycle: Optional[float] = None


class OrderOut(BaseModel):
    id: int
    order_type: str
    status: str
    target_ship_id: Optional[int]
    target_object_id: Optional[int]
    target_x: Optional[float]
    target_y: Optional[float]
    target_z: Optional[float]
    desired_distance: float
    orbit_radius: float


class ShipOut(BaseModel):
    id: int
    name: str
    ship_class: str
    pos_x: float
    pos_y: float
    pos_z: float
    vel_x: float
    vel_y: float
    vel_z: float
    ore: float
    capacitor: float
    max_capacitor: float
    total_volume: int
    signature_radius: float
    docked_in_id: Optional[int]
    used_volume: int
    cargo_capacity: float
    max_speed: float
    acceleration: float
    # Combat stats
    shield_hp: float
    max_shield_hp: float
    armor_hp: float
    max_armor_hp: float
    is_destroyed: bool
    scan_resolution: float
    effective_signature_radius: float
    # Phase 7: Faction
    team_id: Optional[int] = None
    faction: Optional[str] = None


class ShipDetailOut(ShipOut):
    modules: list[ModuleOut]
    active_orders: list[OrderOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _module_to_out(m: ShipModule) -> ModuleOut:
    """
    Build a ModuleOut with only the fields relevant to the module type.

    CONF-05: Irrelevant fields (e.g. mining_yield on a cargo_bay) are omitted
    (left as None) so the API response doesn't expose confusing zero values.
    """
    base = ModuleOut(
        id=m.id,
        module_type=m.module_type.value,
        volume=m.volume,
        active=m.active,
        cycle_time=m.cycle_time,
        ticks_until_cycle=m.ticks_until_cycle,
        capacitor_per_cycle=m.capacitor_per_cycle,
    )
    mt = m.module_type
    mt_val = mt.value
    if mt in (ModuleType.mining_laser, ModuleType.strip_miner, ModuleType.starter_mining_laser):
        base.mining_yield = m.mining_yield
        base.mining_range = m.mining_range
    elif mt == ModuleType.scanner:
        base.scan_range = m.scan_range
    elif mt in (ModuleType.passive_detector, ModuleType.starter_passive_detector):
        base.detection_range = m.detection_range
    elif mt == ModuleType.factory:
        base.factory_max_class = m.factory_max_class
    elif mt_val in TURRET_TYPES:
        base.damage_per_cycle = m.damage_per_cycle
        base.damage_type = m.damage_type
        base.optimal_range = m.optimal_range
        base.falloff_range = m.falloff_range
        base.tracking_speed = m.tracking_speed
        base.sig_resolution = m.sig_resolution
    elif mt_val in MISSILE_TYPES:
        base.damage_per_cycle = m.damage_per_cycle
        base.damage_type = m.damage_type
        base.optimal_range = m.optimal_range
        base.missile_speed = m.missile_speed
        base.missile_flight_time = m.missile_flight_time
        base.explosion_radius = m.explosion_radius
        base.explosion_velocity = m.explosion_velocity
    elif mt_val in SHIELD_EXTENDER_TYPES:
        base.shield_hp_bonus = m.shield_hp_bonus
    elif mt_val in SHIELD_BOOSTER_TYPES:
        base.shield_repair_per_cycle = m.shield_repair_per_cycle
    elif mt_val in ARMOR_PLATE_TYPES:
        base.armor_hp_bonus = m.armor_hp_bonus
    elif mt_val in ARMOR_REPAIRER_TYPES:
        base.armor_repair_per_cycle = m.armor_repair_per_cycle
    # hardener types have no extra fields beyond cycle/cap (already in base)
    return base


def _ship_to_out(ship: Spaceship) -> ShipOut:
    used = sum(m.volume for m in ship.modules)
    # Derive faction safely — requires team relationship to be loaded
    faction = None
    try:
        faction = ship.faction
    except Exception:
        pass
    return ShipOut(
        id=ship.id,
        name=ship.name,
        ship_class=ship.ship_class.value,
        pos_x=ship.pos_x,
        pos_y=ship.pos_y,
        pos_z=ship.pos_z,
        vel_x=ship.vel_x,
        vel_y=ship.vel_y,
        vel_z=ship.vel_z,
        ore=ship.ore,
        capacitor=ship.capacitor,
        max_capacitor=ship.max_capacitor,
        total_volume=ship.total_volume,
        signature_radius=ship.signature_radius,
        docked_in_id=ship.docked_in_id,
        used_volume=used,
        cargo_capacity=ship.cargo_capacity(),
        max_speed=ship.max_speed(),
        acceleration=ship.acceleration(),
        shield_hp=ship.shield_hp,
        max_shield_hp=ship.max_shield_hp,
        armor_hp=ship.armor_hp,
        max_armor_hp=ship.max_armor_hp,
        is_destroyed=ship.is_destroyed,
        scan_resolution=ship.scan_resolution,
        effective_signature_radius=ship.effective_signature_radius(),
        team_id=ship.team_id,
        faction=faction,
    )


async def _get_owned_ship(
    ship_id: int,
    current_user: User,
    session,
    *,
    load_relations: bool = False,
) -> Spaceship:
    """Fetch a ship by ID and verify it belongs to the current user."""
    if load_relations:
        return await _get_owned_ship_common(
            ship_id,
            current_user,
            session,
            selectinload(Spaceship.modules),
            selectinload(Spaceship.movement_orders),
            selectinload(Spaceship.build_orders),
            selectinload(Spaceship.team),
        )
    return await _get_owned_ship_common(
        ship_id, current_user, session,
        selectinload(Spaceship.team),
    )


# ---------------------------------------------------------------------------
# Endpoints (read-only)
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ShipOut])
async def list_ships(
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """List all ships owned by the authenticated user."""
    result = await session.exec(
        select(Spaceship)
        .where(Spaceship.user_id == current_user.id)
        .options(
            selectinload(Spaceship.modules),
            selectinload(Spaceship.team),
        )
    )
    ships = result.all()
    return [_ship_to_out(s) for s in ships]


@router.get("/{ship_id}", response_model=ShipDetailOut)
async def get_ship(
    ship_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Return full ship detail: stats, all modules, and active movement orders."""
    ship = await _get_owned_ship(ship_id, current_user, session, load_relations=True)

    from server.models import OrderStatus

    active_orders = [
        OrderOut(
            id=o.id,
            order_type=o.order_type.value,
            status=o.status.value,
            target_ship_id=o.target_ship_id,
            target_object_id=o.target_object_id,
            target_x=o.target_x,
            target_y=o.target_y,
            target_z=o.target_z,
            desired_distance=o.desired_distance,
            orbit_radius=o.orbit_radius,
        )
        for o in ship.movement_orders
        if o.status == OrderStatus.active
    ]

    out = _ship_to_out(ship)
    return ShipDetailOut(
        **out.model_dump(),
        modules=[_module_to_out(m) for m in ship.modules],
        active_orders=active_orders,
    )


@router.get("/{ship_id}/modules", response_model=list[ModuleOut])
async def list_modules(
    ship_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Return all installed modules for the ship."""
    ship = await _get_owned_ship(ship_id, current_user, session, load_relations=True)
    return [_module_to_out(m) for m in ship.modules]
