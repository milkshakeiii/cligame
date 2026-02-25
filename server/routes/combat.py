"""
Combat routes for Phase 4.

POST   /api/ships/{id}/lock                 — Begin locking a target
DELETE /api/ships/{id}/lock/{target_id}      — Release lock on target
GET    /api/ships/{id}/locks                 — List all current locks
POST   /api/ships/{id}/weapons/{module_id}/assign — Assign weapon to locked target
POST   /api/ships/{id}/weapons/fire-all      — Assign all weapons to target
POST   /api/ships/{id}/weapons/hold          — Deactivate all weapon modules
"""

from __future__ import annotations

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.auth import get_current_user
from server.combat import compute_lock_time
from server.database import get_session
from server.models import (
    LeechDebuff,
    LockStatus,
    MAX_LOCKS,
    ModuleType,
    SHIP_CLASSES,
    STEALTH_FIELD_TYPES,
    VOIDBORN_MODULE_PARAMS,
    Spaceship,
    ShipModule,
    TargetLock,
    User,
    WeaponAssignment,
    WEAPON_TYPES,
    get_max_locks,
    get_ship_classes,
)
from server.routes.common import get_owned_ship

router = APIRouter(prefix="/api/ships", tags=["combat"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LockRequest(BaseModel):
    target_ship_id: int


class LockOut(BaseModel):
    id: int
    target_ship_id: int
    status: str
    ticks_remaining: int


class WeaponAssignRequest(BaseModel):
    target_ship_id: int


class WeaponAssignmentOut(BaseModel):
    module_id: int
    target_ship_id: int


class LeechOut(BaseModel):
    id: int
    source_ship_id: int
    target_ship_id: int
    leech_type: str
    damage_per_tick: float
    cap_drain_per_tick: float
    ticks_remaining: int


# ---------------------------------------------------------------------------
# Target Locking
# ---------------------------------------------------------------------------

@router.post("/{ship_id}/lock", response_model=LockOut, status_code=status.HTTP_201_CREATED)
async def lock_target(
    ship_id: int,
    body: LockRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Begin locking a target ship."""
    ship = await get_owned_ship(
        ship_id, current_user, session,
        selectinload(Spaceship.modules),
        selectinload(Spaceship.target_locks),
        selectinload(Spaceship.team),
    )

    if ship.is_destroyed:
        raise HTTPException(status_code=422, detail="Ship is destroyed")

    # Check max locks
    active_locks = [
        l for l in ship.target_locks
        if l.status in (LockStatus.locking, LockStatus.locked)
    ]
    max_locks = get_max_locks(ship.faction, ship.ship_class.value)
    if len(active_locks) >= max_locks:
        raise HTTPException(
            status_code=422,
            detail=f"Maximum target locks reached ({max_locks})",
        )

    # Check not already locking this target
    for l in active_locks:
        if l.target_ship_id == body.target_ship_id:
            raise HTTPException(
                status_code=422,
                detail=f"Already locking/locked Ship #{body.target_ship_id}",
            )

    # Can't lock yourself
    if body.target_ship_id == ship_id:
        raise HTTPException(status_code=422, detail="Cannot lock your own ship")

    # Verify target exists (need modules for effective_signature_radius)
    target_result = await session.exec(
        select(Spaceship)
        .where(
            Spaceship.id == body.target_ship_id,
            Spaceship.is_destroyed == False,  # noqa: E712
        )
        .options(selectinload(Spaceship.modules), selectinload(Spaceship.team))
    )
    target = target_result.first()
    if target is None:
        raise HTTPException(status_code=404, detail="Target ship not found")

    # Range check — scanner range (200km) if ship has scanner, else default visibility (1km)
    has_scanner = any(
        m.module_type == ModuleType.scanner for m in ship.modules
    )
    lock_range = 200_000.0 if has_scanner else 1_000.0  # meters
    dx = ship.pos_x - target.pos_x
    dy = ship.pos_y - target.pos_y
    dz = ship.pos_z - target.pos_z
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    if distance > lock_range:
        raise HTTPException(
            status_code=422,
            detail=f"Target out of range: {distance/1000:.1f} km (max {lock_range/1000:.0f} km)",
        )

    # Deactivate any active stealth field on the locking ship (decloak on lock)
    for m in ship.modules:
        if m.module_type.value in STEALTH_FIELD_TYPES and m.active:
            m.active = False
            m.stealth_cooldown_remaining = VOIDBORN_MODULE_PARAMS.get(
                m.module_type.value, {}
            ).get("decloak_cooldown", 10)

    # Compute lock time
    consts = get_ship_classes(ship.faction)[ship.ship_class.value]
    lock_time = compute_lock_time(
        ship.scan_resolution,
        target.effective_signature_radius(),
        consts["base_lock_time"],
    )

    lock = TargetLock(
        ship_id=ship.id,
        target_ship_id=body.target_ship_id,
        status=LockStatus.locking,
        ticks_remaining=lock_time,
    )
    session.add(lock)
    await session.commit()
    await session.refresh(lock)

    return LockOut(
        id=lock.id,
        target_ship_id=lock.target_ship_id,
        status=lock.status.value,
        ticks_remaining=lock.ticks_remaining,
    )


@router.delete("/{ship_id}/lock/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlock_target(
    ship_id: int,
    target_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Release a target lock."""
    ship = await get_owned_ship(
        ship_id, current_user, session,
        selectinload(Spaceship.target_locks),
    )

    lock = next(
        (l for l in ship.target_locks
         if l.target_ship_id == target_id
         and l.status in (LockStatus.locking, LockStatus.locked)),
        None,
    )
    if lock is None:
        raise HTTPException(status_code=404, detail="No active lock on that target")

    # Also remove weapon assignments to this target
    wa_result = await session.exec(
        select(WeaponAssignment).where(
            WeaponAssignment.ship_id == ship.id,
            WeaponAssignment.target_ship_id == target_id,
        )
    )
    for wa in wa_result.all():
        await session.delete(wa)

    lock.status = LockStatus.broken
    await session.commit()


@router.get("/{ship_id}/locks", response_model=list[LockOut])
async def list_locks(
    ship_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """List all current target locks (including locking/locked/broken)."""
    ship = await get_owned_ship(
        ship_id, current_user, session,
        selectinload(Spaceship.target_locks),
    )

    return [
        LockOut(
            id=l.id,
            target_ship_id=l.target_ship_id,
            status=l.status.value,
            ticks_remaining=l.ticks_remaining,
        )
        for l in ship.target_locks
        if l.status in (LockStatus.locking, LockStatus.locked)
    ]


# ---------------------------------------------------------------------------
# Weapon Assignment
# ---------------------------------------------------------------------------

@router.post(
    "/{ship_id}/weapons/{module_id}/assign",
    response_model=WeaponAssignmentOut,
)
async def assign_weapon(
    ship_id: int,
    module_id: int,
    body: WeaponAssignRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Assign a weapon module to a locked target."""
    ship = await get_owned_ship(
        ship_id, current_user, session,
        selectinload(Spaceship.modules),
        selectinload(Spaceship.target_locks),
    )

    # Verify the module is a weapon on this ship
    module = next((m for m in ship.modules if m.id == module_id), None)
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found on this ship")
    if module.module_type.value not in WEAPON_TYPES:
        raise HTTPException(status_code=422, detail="Module is not a weapon")

    # Verify target is locked
    locked = any(
        l.target_ship_id == body.target_ship_id and l.status == LockStatus.locked
        for l in ship.target_locks
    )
    if not locked:
        raise HTTPException(
            status_code=422,
            detail=f"Ship #{body.target_ship_id} is not locked",
        )

    # Upsert weapon assignment
    wa_result = await session.exec(
        select(WeaponAssignment).where(
            WeaponAssignment.module_id == module_id,
        )
    )
    existing = wa_result.first()
    if existing:
        existing.target_ship_id = body.target_ship_id
    else:
        wa = WeaponAssignment(
            module_id=module_id,
            ship_id=ship.id,
            target_ship_id=body.target_ship_id,
        )
        session.add(wa)

    # Activate the weapon module
    module.active = True

    await session.commit()
    return WeaponAssignmentOut(
        module_id=module_id,
        target_ship_id=body.target_ship_id,
    )


@router.post("/{ship_id}/weapons/fire-all", response_model=list[WeaponAssignmentOut])
async def fire_all_weapons(
    ship_id: int,
    body: WeaponAssignRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Assign all weapon modules to a locked target and activate them."""
    ship = await get_owned_ship(
        ship_id, current_user, session,
        selectinload(Spaceship.modules),
        selectinload(Spaceship.target_locks),
    )

    # Verify target is locked
    locked = any(
        l.target_ship_id == body.target_ship_id and l.status == LockStatus.locked
        for l in ship.target_locks
    )
    if not locked:
        raise HTTPException(
            status_code=422,
            detail=f"Ship #{body.target_ship_id} is not locked",
        )

    results = []
    for module in ship.modules:
        if module.module_type.value not in WEAPON_TYPES:
            continue

        # Upsert
        wa_result = await session.exec(
            select(WeaponAssignment).where(
                WeaponAssignment.module_id == module.id,
            )
        )
        existing = wa_result.first()
        if existing:
            existing.target_ship_id = body.target_ship_id
        else:
            wa = WeaponAssignment(
                module_id=module.id,
                ship_id=ship.id,
                target_ship_id=body.target_ship_id,
            )
            session.add(wa)

        module.active = True
        results.append(WeaponAssignmentOut(
            module_id=module.id,
            target_ship_id=body.target_ship_id,
        ))

    await session.commit()
    return results


@router.post("/{ship_id}/weapons/hold", status_code=status.HTTP_204_NO_CONTENT)
async def hold_fire(
    ship_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Deactivate all weapon modules and clear weapon assignments."""
    ship = await get_owned_ship(
        ship_id, current_user, session,
        selectinload(Spaceship.modules),
    )

    for module in ship.modules:
        if module.module_type.value in WEAPON_TYPES:
            module.active = False

    # Clear weapon assignments
    wa_result = await session.exec(
        select(WeaponAssignment).where(WeaponAssignment.ship_id == ship.id)
    )
    for wa in wa_result.all():
        await session.delete(wa)

    await session.commit()


# ---------------------------------------------------------------------------
# Leech Status
# ---------------------------------------------------------------------------


@router.get("/{ship_id}/leeches", response_model=list[LeechOut])
async def list_leeches(
    ship_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """List all active leech debuffs on a ship."""
    ship = await get_owned_ship(ship_id, current_user, session)

    result = await session.exec(
        select(LeechDebuff).where(
            LeechDebuff.target_ship_id == ship.id,
            LeechDebuff.ticks_remaining > 0,
        )
    )

    return [
        LeechOut(
            id=ld.id,
            source_ship_id=ld.source_ship_id,
            target_ship_id=ld.target_ship_id,
            leech_type=ld.leech_type,
            damage_per_tick=ld.damage_per_tick,
            cap_drain_per_tick=ld.cap_drain_per_tick,
            ticks_remaining=ld.ticks_remaining,
        )
        for ld in result.all()
    ]
