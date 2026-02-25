"""
Ship CRUD routes.

GET    /api/ships                         — list user's ships
POST   /api/ships                         — create a new ship
GET    /api/ships/{ship_id}               — ship detail + modules + active orders
GET    /api/ships/{ship_id}/modules       — list installed modules
POST   /api/ships/{ship_id}/modules       — install a module
DELETE /api/ships/{ship_id}/modules/{mod} — uninstall a module
"""

from __future__ import annotations

import math
import random
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    ARMOR_PLATE_TYPES,
    ARMOR_REPAIRER_TYPES,
    DEFENSIVE_TYPES,
    FACTION_SHIP_NAMES,
    MISSILE_TYPES,
    REFERENCE_ENGINE_FRACTION,
    SHIELD_BOOSTER_TYPES,
    SHIELD_EXTENDER_TYPES,
    SOLARION_EXCLUSIVE_MODULES,
    SOLARION_MODULE_PARAMS,
    STEALTH_FIELD_TYPES,
    TURRET_TYPES,
    VOIDBORN_EXCLUSIVE_MODULES,
    VOIDBORN_MODULE_PARAMS,
    WEAPON_TYPES,
    LockStatus,
    ModuleType,
    ShipClass,
    ShipModule,
    Spaceship,
    TargetLock,
    Team,
    User,
    ResearchProgress,
    create_default_ship,
    make_module,
    recalculate_max_capacitor,
    recalculate_max_shield,
    recalculate_max_armor,
)
from server.research import (
    get_completed_tech_ids,
    get_tech_name,
    is_module_unlocked,
    is_ship_unlocked,
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
    autopilot_mode: str = "off"
    autopilot_profile: Optional[str] = None
    # Phase 7: Faction
    team_id: Optional[int] = None
    faction: Optional[str] = None


class ShipDetailOut(ShipOut):
    modules: list[ModuleOut]
    active_orders: list[OrderOut]


class CreateShipRequest(BaseModel):
    name: Optional[str] = None
    ship_class: ShipClass


class RenameShipRequest(BaseModel):
    name: str


class InstallModuleRequest(BaseModel):
    module_type: ModuleType
    volume: int = 0  # ignored for fixed-size modules; required for variable-size ones


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
    if mt == ModuleType.mining_laser:
        base.mining_yield = m.mining_yield
        base.mining_range = m.mining_range
    elif mt == ModuleType.scanner:
        base.scan_range = m.scan_range
    elif mt == ModuleType.passive_detector:
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
        autopilot_mode=ship.autopilot_mode,
        autopilot_profile=ship.autopilot_profile,
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
# Endpoints
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


@router.post("", response_model=ShipOut, status_code=status.HTTP_201_CREATED)
async def create_ship(
    body: CreateShipRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Create a new ship for the authenticated user.

    The ship spawns near the player's first existing ship (or at the origin if
    they have none) with a basic engine module (~30% of total volume) so it has
    a nonzero max_speed.
    """
    # Research gating: check if this ship class is unlocked (includes team research)
    if current_user.team_id is not None:
        research_result = await session.exec(
            select(ResearchProgress).where(
                (ResearchProgress.user_id == current_user.id)
                | (ResearchProgress.team_id == current_user.team_id)
            )
        )
    else:
        research_result = await session.exec(
            select(ResearchProgress).where(ResearchProgress.user_id == current_user.id)
        )
    completed_techs = get_completed_tech_ids(research_result.all())
    if not is_ship_unlocked(body.ship_class.value, completed_techs):
        from server.models import SHIP_REQUIRED_TECH
        tech_id = SHIP_REQUIRED_TECH.get(body.ship_class.value, "?")
        raise HTTPException(
            status_code=422,
            detail=f"Research required: {get_tech_name(tech_id)} ({tech_id})",
        )

    # BUG-05: Spawn near the player's first existing ship, not at (0,0,0)
    existing_result = await session.exec(
        select(Spaceship)
        .where(Spaceship.user_id == current_user.id)
        .options(selectinload(Spaceship.modules))
    )
    existing_ships = list(existing_result.all())

    pos_x, pos_y, pos_z = 0.0, 0.0, 0.0
    if existing_ships:
        ref = existing_ships[0]
        # Place 100 m away in a random direction (same as spawn_new_ship helper)
        theta = random.uniform(0, 2 * math.pi)
        phi = random.uniform(0, math.pi)
        dx = math.sin(phi) * math.cos(theta)
        dy = math.sin(phi) * math.sin(theta)
        dz = math.cos(phi)
        pos_x = ref.pos_x + dx * 100.0
        pos_y = ref.pos_y + dy * 100.0
        pos_z = ref.pos_z + dz * 100.0

    # Derive team_id and faction from the user's team
    user_team_id = current_user.team_id
    user_faction = None
    if user_team_id is not None:
        team_result = await session.exec(
            select(Team).where(Team.id == user_team_id)
        )
        team = team_result.first()
        if team is not None:
            user_faction = team.faction

    # Auto-generate name if not provided
    ship_name = body.name
    if not ship_name:
        # Use faction-themed names if available, otherwise default "{Class}-{N+1}"
        same_class_count = sum(
            1 for s in existing_ships if s.ship_class == body.ship_class
        )
        if user_faction and user_faction in FACTION_SHIP_NAMES:
            faction_names = FACTION_SHIP_NAMES[user_faction].get(
                body.ship_class.value, []
            )
            if faction_names:
                name_index = same_class_count % len(faction_names)
                ship_name = f"{faction_names[name_index]}-{same_class_count + 1}"
            else:
                class_label = body.ship_class.value.replace("_", " ").title()
                ship_name = f"{class_label}-{same_class_count + 1}"
        else:
            class_label = body.ship_class.value.replace("_", " ").title()
            ship_name = f"{class_label}-{same_class_count + 1}"

    ship = create_default_ship(
        name=ship_name,
        ship_class=body.ship_class,
        user_id=current_user.id,
        pos_x=pos_x,
        pos_y=pos_y,
        pos_z=pos_z,
        team_id=user_team_id,
    )
    session.add(ship)
    await session.flush()  # Get ship.id before creating module

    # BUG-05: Give the new ship a basic engine module (~30% of total volume)
    engine_volume = max(1, int(ship.total_volume * REFERENCE_ENGINE_FRACTION))
    engine = make_module(ModuleType.engine, engine_volume)
    engine.ship_id = ship.id
    session.add(engine)

    await session.commit()
    # Re-query with selectinload to avoid MissingGreenlet on lazy relationship access
    result = await session.exec(
        select(Spaceship)
        .where(Spaceship.id == ship.id)
        .options(
            selectinload(Spaceship.modules),
            selectinload(Spaceship.team),
        )
    )
    ship = result.one()
    return _ship_to_out(ship)


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


@router.post("/{ship_id}/modules", response_model=ModuleOut, status_code=status.HTTP_201_CREATED)
async def install_module(
    ship_id: int,
    body: InstallModuleRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Install a new module on the ship.

    Fixed-size modules (mining_laser, scanner, passive_detector, dropoff) ignore
    the ``volume`` field and use the spec-defined size.  Variable-size modules
    (engine, reactor, cargo_bay, docking_bay, factory) require a positive volume.
    """
    ship = await _get_owned_ship(ship_id, current_user, session, load_relations=True)

    # Block module changes during combat (active target locks)
    lock_result = await session.exec(
        select(TargetLock).where(
            (
                (TargetLock.ship_id == ship.id) | (TargetLock.target_ship_id == ship.id)
            ),
            TargetLock.status.in_([LockStatus.locking.value, LockStatus.locked.value]),  # type: ignore[attr-defined]
        )
    )
    if lock_result.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot modify modules while in combat (active target locks)",
        )

    # Variable-size modules need an explicit volume
    VARIABLE_SIZE_MODULES = {
        ModuleType.engine,
        ModuleType.reactor,
        ModuleType.cargo_bay,
        ModuleType.docking_bay,
        ModuleType.factory,
        ModuleType.enhanced_docking_bay,
    }
    if body.module_type in VARIABLE_SIZE_MODULES and body.volume <= 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"module_type '{body.module_type.value}' requires a positive volume",
        )

    # Research gating (includes team research)
    if current_user.team_id is not None:
        research_result = await session.exec(
            select(ResearchProgress).where(
                (ResearchProgress.user_id == current_user.id)
                | (ResearchProgress.team_id == current_user.team_id)
            )
        )
    else:
        research_result = await session.exec(
            select(ResearchProgress).where(ResearchProgress.user_id == current_user.id)
        )
    completed_techs = get_completed_tech_ids(research_result.all())
    if not is_module_unlocked(body.module_type.value, completed_techs):
        from server.models import MODULE_REQUIRED_TECH
        tech_id = MODULE_REQUIRED_TECH.get(body.module_type.value, "?")
        raise HTTPException(
            status_code=422,
            detail=f"Research required: {get_tech_name(tech_id)} ({tech_id})",
        )

    # Faction exclusivity check
    mt_val = body.module_type.value
    if mt_val in SOLARION_EXCLUSIVE_MODULES or mt_val in VOIDBORN_EXCLUSIVE_MODULES:
        # Determine ship faction by loading team
        ship_faction = None
        if ship.team_id is not None:
            team_result = await session.exec(
                select(Team).where(Team.id == ship.team_id)
            )
            team_obj = team_result.first()
            if team_obj is not None:
                ship_faction = team_obj.faction

        if mt_val in SOLARION_EXCLUSIVE_MODULES:
            if ship_faction != "solarion":
                raise HTTPException(
                    status_code=422,
                    detail=f"Module '{mt_val}' requires Solarion faction",
                )
        if mt_val in VOIDBORN_EXCLUSIVE_MODULES:
            if ship_faction != "voidborn":
                raise HTTPException(
                    status_code=422,
                    detail=f"Module '{mt_val}' requires Voidborn faction",
                )

    # Volume cap check
    used = sum(m.volume for m in ship.modules)
    # For fixed-size modules we must look up the actual volume before checking
    test_module = make_module(body.module_type, body.volume)
    if used + test_module.volume > ship.total_volume:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Not enough volume: {test_module.volume} m³ needed, "
                f"only {ship.total_volume - used} m³ available"
            ),
        )

    module = make_module(body.module_type, body.volume)
    module.ship_id = ship.id
    session.add(module)
    await session.flush()  # gives module an id and registers it with the session

    ship.modules.append(module)

    # Recalculate derived stats for relevant module types
    if body.module_type == ModuleType.reactor:
        recalculate_max_capacitor(ship)
    if body.module_type.value in SHIELD_EXTENDER_TYPES:
        old_max = ship.max_shield_hp
        recalculate_max_shield(ship)
        # Add only the newly contributed HP (don't reset to full)
        bonus = ship.max_shield_hp - old_max
        ship.shield_hp = min(ship.shield_hp + bonus, ship.max_shield_hp)
    if body.module_type.value in ARMOR_PLATE_TYPES:
        old_max = ship.max_armor_hp
        recalculate_max_armor(ship)
        bonus = ship.max_armor_hp - old_max
        ship.armor_hp = min(ship.armor_hp + bonus, ship.max_armor_hp)

    await session.commit()
    await session.refresh(module)
    return _module_to_out(module)


@router.delete("/{ship_id}/modules/{module_id}", status_code=status.HTTP_204_NO_CONTENT)
async def uninstall_module(
    ship_id: int,
    module_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Uninstall a module from the ship.

    The module is deleted from the database.  Reactors immediately reduce
    max_capacitor; if current capacitor exceeds the new max it is clamped.
    """
    ship = await _get_owned_ship(ship_id, current_user, session, load_relations=True)

    # Block module changes during combat (active target locks)
    lock_result = await session.exec(
        select(TargetLock).where(
            (
                (TargetLock.ship_id == ship.id) | (TargetLock.target_ship_id == ship.id)
            ),
            TargetLock.status.in_([LockStatus.locking.value, LockStatus.locked.value]),  # type: ignore[attr-defined]
        )
    )
    if lock_result.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot modify modules while in combat (active target locks)",
        )

    module = next((m for m in ship.modules if m.id == module_id), None)
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Module not found on this ship",
        )

    ship.modules.remove(module)
    await session.delete(module)

    # Recalculate derived stats
    if module.module_type == ModuleType.reactor:
        recalculate_max_capacitor(ship)
        ship.capacitor = min(ship.capacitor, ship.max_capacitor)
    if module.module_type.value in SHIELD_EXTENDER_TYPES:
        recalculate_max_shield(ship)
        ship.shield_hp = min(ship.shield_hp, ship.max_shield_hp)
    if module.module_type.value in ARMOR_PLATE_TYPES:
        recalculate_max_armor(ship)
        ship.armor_hp = min(ship.armor_hp, ship.max_armor_hp)

    await session.commit()


@router.post("/{ship_id}/rename", response_model=ShipOut)
async def rename_ship(
    ship_id: int,
    body: RenameShipRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Rename a ship."""
    ship = await _get_owned_ship(ship_id, current_user, session, load_relations=True)
    ship.name = body.name
    await session.commit()
    # Re-query with modules and team loaded
    result = await session.exec(
        select(Spaceship)
        .where(Spaceship.id == ship.id)
        .options(
            selectinload(Spaceship.modules),
            selectinload(Spaceship.team),
        )
    )
    ship = result.one()
    return _ship_to_out(ship)


@router.post("/{ship_id}/undock", response_model=ShipOut)
async def undock_ship(
    ship_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Undock a ship that is currently docked inside another ship.

    Sets ``docked_in_id`` to None and returns the updated ship.
    """
    ship = await _get_owned_ship(ship_id, current_user, session, load_relations=True)

    if not ship.is_docked():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ship is not currently docked",
        )

    ship.docked_in_id = None
    await session.commit()

    # Re-query to ensure modules and team are loaded for _ship_to_out
    result = await session.exec(
        select(Spaceship)
        .where(Spaceship.id == ship.id)
        .options(
            selectinload(Spaceship.modules),
            selectinload(Spaceship.team),
        )
    )
    ship = result.one()
    return _ship_to_out(ship)
