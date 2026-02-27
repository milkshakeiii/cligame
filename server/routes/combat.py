"""
Combat routes — read-only endpoints.

GET    /api/ships/{id}/locks                 — List all current locks
GET    /api/ships/{id}/leeches               — List active leech debuffs
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import selectinload
from sqlmodel import select

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    LeechDebuff,
    LockStatus,
    Spaceship,
    User,
)
from server.routes.common import get_owned_ship

router = APIRouter(prefix="/api/ships", tags=["combat"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LockOut(BaseModel):
    id: int
    target_ship_id: int
    status: str
    ticks_remaining: int


class LeechOut(BaseModel):
    id: int
    source_ship_id: int
    target_ship_id: int
    leech_type: str
    damage_per_tick: float
    cap_drain_per_tick: float
    ticks_remaining: int


# ---------------------------------------------------------------------------
# Target Locks
# ---------------------------------------------------------------------------

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
