"""
Game-state routes.

GET /api/game/status          — current tick number and running state
GET /api/events?since=&limit= — paginated event log for the authenticated user
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import select

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    CARGO_TYPES,
    DOCKING_TYPES,
    ENGINE_TYPES,
    Event,
    EventType,
    FACTORY_TYPES,
    GameState,
    HULL_POINT_COSTS,
    MODULE_FIXED_VOLUMES,
    MODULE_POINT_COSTS,
    ModuleType,
    REACTOR_TYPES,
    SHIP_CLASSES,
    User,
)

router = APIRouter(prefix="/api", tags=["game"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class GameStatusResponse(BaseModel):
    current_tick: int
    running: bool
    tick_interval: float


class EventResponse(BaseModel):
    id: int
    tick: int
    type: str
    ship_id: Optional[int]
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/game/status", response_model=GameStatusResponse)
async def game_status(session=Depends(get_session)):
    """
    Return the current game tick and running state.
    No authentication required — useful for health checks and CLI status.
    """
    result = await session.exec(select(GameState))
    gs = result.first()
    if gs is None:
        return GameStatusResponse(current_tick=0, running=False, tick_interval=1.0)
    return GameStatusResponse(
        current_tick=gs.current_tick,
        running=gs.running,
        tick_interval=gs.tick_interval,
    )


@router.get("/events", response_model=list[EventResponse])
async def get_events(
    since_tick: int = Query(default=0, description="Return events at ticks strictly after this value"),
    since: Optional[int] = Query(default=None, description="Deprecated alias for since_tick"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of events to return"),
    ship_id: Optional[int] = Query(default=None, description="Filter to a specific ship"),
    types: Optional[str] = Query(
        default=None,
        description="Comma-separated list of event types to include (e.g. detection,mining)",
    ),
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Retrieve the authenticated player's event log.

    Supports:
    - ``since_tick`` — only return events with tick > since_tick (for polling)
    - ``since`` — deprecated alias for since_tick (backwards compatibility)
    - ``limit`` — cap the result set
    - ``ship_id`` — filter to events for a specific ship
    - ``types``  — comma-separated event type filter

    Events are ordered by tick ascending so the client can process them in order.

    This endpoint is the primary mechanism for LLM playability: an agent polls
    this with the tick of the last event it saw to receive a delta of new events.
    """
    # Support both since_tick (canonical) and since (legacy alias)
    effective_since = since if since is not None else since_tick
    query = (
        select(Event)
        .where(Event.user_id == current_user.id)
        .where(Event.tick > effective_since)
    )

    if ship_id is not None:
        query = query.where(Event.ship_id == ship_id)

    if types is not None:
        type_list = [t.strip() for t in types.split(",") if t.strip()]
        if type_list:
            valid_types = [
                EventType(t) for t in type_list if t in EventType.__members__
            ]
            if valid_types:
                query = query.where(
                    Event.event_type.in_(  # type: ignore[attr-defined]
                        [v.value for v in valid_types]
                    )
                )

    query = query.order_by(Event.tick).limit(limit)  # type: ignore[arg-type]

    result = await session.exec(query)
    events = result.all()

    return [
        EventResponse(
            id=e.id,
            tick=e.tick,
            type=e.event_type.value,
            ship_id=e.ship_id,
            message=e.message,
        )
        for e in events
    ]


@router.get("/loadout/costs")
async def loadout_costs():
    """Return hull and module point costs (no auth required)."""
    return {"hull_costs": HULL_POINT_COSTS, "module_costs": MODULE_POINT_COSTS}


def _module_category(mt: str) -> str:
    """Classify a module type string into a GUI category."""
    if mt in ENGINE_TYPES or mt in REACTOR_TYPES or mt in CARGO_TYPES:
        return "core"
    if mt in FACTORY_TYPES or mt in DOCKING_TYPES:
        return "utility"
    if "mining" in mt or "strip" in mt:
        return "mining"
    if "turret" in mt or "missile" in mt or "shield" in mt or "armor" in mt:
        return "combat"
    return "utility"


def _module_label(mt: str) -> str:
    """Generate a human-readable label from a module type string."""
    return mt.replace("_", " ").title()


@router.get("/modules")
async def list_modules():
    """Return all module definitions for client/GUI use (no auth required)."""
    modules = []
    for mt in ModuleType:
        mt_val = mt.value
        volume = MODULE_FIXED_VOLUMES.get(mt_val, 0)
        modules.append({
            "type": mt_val,
            "label": _module_label(mt_val),
            "fixedVolume": volume,
            "category": _module_category(mt_val),
            "pointCost": MODULE_POINT_COSTS.get(mt_val, 0),
        })
    return modules


@router.get("/ship_classes")
async def list_ship_classes():
    """Return ship class definitions (no auth required)."""
    return {
        name: {
            "total_volume": data["volume"],
            "base_shield": data["base_shield"],
            "base_armor": data["base_armor"],
            "base_capacitor": data["base_cap"],
            "signature": data["signature"],
            "hull_cost": HULL_POINT_COSTS.get(name, 0),
        }
        for name, data in SHIP_CLASSES.items()
    }
