"""
Scanning routes.

GET  /api/ships/{id}/nearby — return nearby visible objects for a ship
GET  /api/nearby             — return nearby visible objects for a ship
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    CelestialObject,
    Spaceship,
    User,
)
from server.routes.common import get_owned_ship as _get_owned_ship_common
from server.scanning import (
    DETAIL_CLASSIFICATION,
    DETAIL_IDENTIFICATION,
    default_visibility_level,
)

router = APIRouter(tags=["scanning"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ContactOut(BaseModel):
    type: str                      # "ship" or "object"
    id: int
    distance: float
    detail: int                    # 1-4 per SPEC.md
    pos_x: float
    pos_y: float
    pos_z: float
    # populated at detail >= 2
    ship_class: Optional[str] = None
    object_type: Optional[str] = None
    vel_x: Optional[float] = None
    vel_y: Optional[float] = None
    vel_z: Optional[float] = None
    ore_remaining: Optional[float] = None
    # populated at detail >= 3
    name: Optional[str] = None
    owner_id: Optional[int] = None
    # populated at detail == 4
    ore: Optional[float] = None
    capacitor: Optional[float] = None
    max_capacitor: Optional[float] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dist(ax, ay, az, bx, by, bz) -> float:
    import math
    dx, dy, dz = ax - bx, ay - by, az - bz
    return math.sqrt(dx * dx + dy * dy + dz * dz)


async def _get_owned_ship(ship_id: int, user: User, session) -> Spaceship:
    return await _get_owned_ship_common(
        ship_id,
        user,
        session,
        selectinload(Spaceship.modules),
    )


def _contact_from_dict(d: dict) -> ContactOut:
    return ContactOut(
        type=d["type"],
        id=d["id"],
        distance=d["distance"],
        detail=d["detail"],
        pos_x=d["pos_x"],
        pos_y=d["pos_y"],
        pos_z=d["pos_z"],
        ship_class=d.get("ship_class"),
        object_type=d.get("object_type"),
        vel_x=d.get("vel_x"),
        vel_y=d.get("vel_y"),
        vel_z=d.get("vel_z"),
        ore_remaining=d.get("ore_remaining"),
        name=d.get("name"),
        owner_id=d.get("owner_id"),
        ore=d.get("ore"),
        capacitor=d.get("capacitor"),
        max_capacitor=d.get("max_capacitor"),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


async def _nearby_logic(
    ship_id: int,
    current_user: User,
    session,
) -> list[ContactOut]:
    """Shared logic for the nearby endpoints."""
    ship = await _get_owned_ship(ship_id, current_user, session)

    all_ships_result = await session.exec(
        select(Spaceship).options(selectinload(Spaceship.modules))
    )
    all_ships = list(all_ships_result.all())

    all_objects_result = await session.exec(select(CelestialObject))
    all_objects = list(all_objects_result.all())

    contacts: list[ContactOut] = []

    # Other ships
    for other in all_ships:
        if other.id == ship.id:
            continue
        if other.is_docked():
            continue

        dist = _dist(ship.pos_x, ship.pos_y, ship.pos_z,
                     other.pos_x, other.pos_y, other.pos_z)
        detail = default_visibility_level(dist)
        if detail == 0:
            continue

        contact = ContactOut(
            type="ship",
            id=other.id,
            distance=dist,
            detail=detail,
            pos_x=other.pos_x,
            pos_y=other.pos_y,
            pos_z=other.pos_z,
        )
        if detail >= DETAIL_CLASSIFICATION:
            contact.ship_class = other.ship_class.value
            contact.vel_x = other.vel_x
            contact.vel_y = other.vel_y
            contact.vel_z = other.vel_z
        if detail >= DETAIL_IDENTIFICATION:
            contact.name = other.name
            contact.owner_id = other.user_id

        contacts.append(contact)

    # Celestial objects (always visible within 1 km default)
    for obj in all_objects:
        dist = _dist(ship.pos_x, ship.pos_y, ship.pos_z,
                     obj.pos_x, obj.pos_y, obj.pos_z)
        detail = default_visibility_level(dist)
        if detail == 0:
            continue

        contact = ContactOut(
            type="object",
            id=obj.id,
            distance=dist,
            detail=detail,
            pos_x=obj.pos_x,
            pos_y=obj.pos_y,
            pos_z=obj.pos_z,
            object_type=obj.object_type.value,
        )
        if detail >= DETAIL_CLASSIFICATION:
            contact.ore_remaining = obj.ore_remaining

        contacts.append(contact)

    # Sort by distance
    contacts.sort(key=lambda c: c.distance)
    return contacts


@router.get("/api/ships/{ship_id}/nearby", response_model=list[ContactOut])
async def get_nearby_by_path(
    ship_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Return all ships and celestial objects visible to the given ship using
    the default visibility rules (no scanner required).

    Route: GET /api/ships/{ship_id}/nearby

    Default visibility (per SPEC.md):
    - Within 100 m: Level 3 (Identification)
    - Within 1 km: Level 2 (Classification)
    - Beyond 1 km: not visible (Level 0)
    """
    return await _nearby_logic(ship_id, current_user, session)


@router.get("/api/nearby", response_model=list[ContactOut])
async def get_nearby(
    ship_id: int = Query(..., description="ID of the observing ship"),
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Return all ships and celestial objects visible to the given ship using
    the default visibility rules (no scanner required).

    Default visibility (per SPEC.md):
    - Within 100 m: Level 3 (Identification)
    - Within 1 km: Level 2 (Classification)
    - Beyond 1 km: not visible (Level 0)

    If the ship has active scanner/detector modules, their last scan results
    are surfaced through the event log.  This endpoint always reflects
    real-time default visibility.
    """
    return await _nearby_logic(ship_id, current_user, session)
