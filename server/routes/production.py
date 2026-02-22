"""
Production routes.

POST /api/ships/{id}/build  — queue a ship construction order
GET  /api/ships/{id}/build  — list build queue status
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
    BuildOrder,
    BuildStatus,
    ModuleType,
    ShipClass,
    Spaceship,
    User,
)
from server.production import start_build
from server.routes.common import get_owned_ship as _get_owned_ship_common

router = APIRouter(prefix="/api/ships", tags=["production"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class BuildRequest(BaseModel):
    blueprint: ShipClass
    factory_module_id: Optional[int] = None  # if None, first capable factory is used


class BuildOrderOut(BaseModel):
    id: int
    blueprint: str
    status: str
    ore_cost: int
    ticks_remaining: int
    total_ticks: int
    progress_pct: float
    factory_module_id: int


class BuildQueueResponse(BaseModel):
    ship_id: int
    active_build: Optional[BuildOrderOut]
    queued: list[BuildOrderOut]
    completed: list[BuildOrderOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_owned_ship(ship_id: int, user: User, session) -> Spaceship:
    return await _get_owned_ship_common(
        ship_id,
        user,
        session,
        selectinload(Spaceship.modules),
        selectinload(Spaceship.build_orders),
    )


def _order_to_out(order: BuildOrder) -> BuildOrderOut:
    total = order.total_ticks or 1
    ticks_done = total - order.ticks_remaining
    pct = round((ticks_done / total) * 100.0, 1)
    return BuildOrderOut(
        id=order.id,
        blueprint=order.blueprint.value,
        status=order.status.value,
        ore_cost=order.ore_cost,
        ticks_remaining=order.ticks_remaining,
        total_ticks=order.total_ticks,
        progress_pct=pct,
        factory_module_id=order.factory_module_id,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{ship_id}/build", response_model=BuildOrderOut, status_code=status.HTTP_201_CREATED)
async def queue_build(
    ship_id: int,
    body: BuildRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Queue a ship construction order.

    - The ship must have a factory module large enough for the requested class.
    - Ore is consumed immediately when the build starts.
    - If a specific ``factory_module_id`` is not given, the first factory
      capable of building the blueprint is selected automatically.
    - Only one build order can be active per factory module at a time.
    """
    ship = await _get_owned_ship(ship_id, current_user, session)

    # Find the factory module
    factory_modules = [m for m in ship.modules if m.module_type == ModuleType.factory]
    if not factory_modules:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Ship has no factory module installed",
        )

    if body.factory_module_id is not None:
        factory = next((m for m in factory_modules if m.id == body.factory_module_id), None)
        if factory is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Factory module not found on this ship",
            )
    else:
        # Pick the first factory capable of building the blueprint
        from server.production import can_factory_build
        factory = None
        for m in factory_modules:
            ok, _ = can_factory_build(m, body.blueprint)
            if ok:
                factory = m
                break
        if factory is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"No factory module capable of building {body.blueprint.value}",
            )

    # Check that this factory is not already building
    active_for_factory = [
        o for o in ship.build_orders
        if o.factory_module_id == factory.id
        and o.status in (BuildStatus.building, BuildStatus.paused)
    ]
    if active_for_factory:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Factory module #{factory.id} is already building "
                f"{active_for_factory[0].blueprint.value}"
            ),
        )

    # Validate and create the build order (ore is consumed inside start_build)
    try:
        order = start_build(ship, factory, body.blueprint)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )

    session.add(order)
    await session.commit()
    await session.refresh(order)
    return _order_to_out(order)


@router.get("/{ship_id}/build", response_model=BuildQueueResponse)
async def get_build_queue(
    ship_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Return the current build queue for a ship, grouped by status.
    """
    ship = await _get_owned_ship(ship_id, current_user, session)

    active_build: Optional[BuildOrderOut] = None
    queued: list[BuildOrderOut] = []
    completed: list[BuildOrderOut] = []

    for order in ship.build_orders:
        out = _order_to_out(order)
        if order.status in (BuildStatus.building, BuildStatus.paused):
            active_build = out
        elif order.status == BuildStatus.queued:
            queued.append(out)
        elif order.status == BuildStatus.completed:
            completed.append(out)

    return BuildQueueResponse(
        ship_id=ship_id,
        active_build=active_build,
        queued=queued,
        completed=completed,
    )
