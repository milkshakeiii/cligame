"""
Production routes.

GET  /api/ships/{id}/build  — list build queue status
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import selectinload

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    BuildOrder,
    BuildStatus,
    Spaceship,
    User,
)
from server.routes.common import get_owned_ship as _get_owned_ship_common

router = APIRouter(prefix="/api/ships", tags=["production"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


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
        selectinload(Spaceship.team),
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
