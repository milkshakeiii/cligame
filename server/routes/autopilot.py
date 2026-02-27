"""
Autopilot routes for Phase 6.

GET  /api/ships/{id}/autopilot/tick       -- Aggregated state for autopilot decisions
"""

import math

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import selectinload
from sqlmodel import select

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    CelestialObject,
    Event,
    LockStatus,
    Spaceship,
    TargetLock,
    User,
)
from server.routes.common import get_owned_ship

router = APIRouter(prefix="/api/ships", tags=["autopilot"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ship_dict(ship: Spaceship) -> dict:
    """Build a dict representation of a ship for autopilot responses."""
    used = sum(m.volume for m in ship.modules)
    return {
        "id": ship.id,
        "name": ship.name,
        "ship_class": ship.ship_class.value,
        "pos_x": ship.pos_x,
        "pos_y": ship.pos_y,
        "pos_z": ship.pos_z,
        "vel_x": ship.vel_x,
        "vel_y": ship.vel_y,
        "vel_z": ship.vel_z,
        "ore": ship.ore,
        "capacitor": ship.capacitor,
        "max_capacitor": ship.max_capacitor,
        "shield_hp": ship.shield_hp,
        "max_shield_hp": ship.max_shield_hp,
        "armor_hp": ship.armor_hp,
        "max_armor_hp": ship.max_armor_hp,
        "is_destroyed": ship.is_destroyed,
        "total_volume": ship.total_volume,
        "used_volume": used,
        "cargo_capacity": ship.cargo_capacity(),
        "max_speed": ship.max_speed(),
        "acceleration": ship.acceleration(),
        "signature_radius": ship.signature_radius,
        "autopilot_mode": ship.autopilot_mode,
        "autopilot_profile": ship.autopilot_profile,
        "autopilot_priority_target_id": ship.autopilot_priority_target_id,
        "modules": [
            {
                "id": m.id,
                "module_type": m.module_type.value,
                "volume": m.volume,
                "active": m.active,
                "cycle_time": m.cycle_time,
                "capacitor_per_cycle": m.capacitor_per_cycle,
                "damage_per_cycle": m.damage_per_cycle,
                "damage_type": m.damage_type,
                "optimal_range": m.optimal_range,
                "tracking_speed": m.tracking_speed,
                "mining_yield": m.mining_yield,
                "mining_range": m.mining_range,
                "shield_hp_bonus": m.shield_hp_bonus,
                "armor_hp_bonus": m.armor_hp_bonus,
                "shield_repair_per_cycle": m.shield_repair_per_cycle,
                "armor_repair_per_cycle": m.armor_repair_per_cycle,
            }
            for m in ship.modules
        ],
    }


def _dist(ax, ay, az, bx, by, bz) -> float:
    dx, dy, dz = ax - bx, ay - by, az - bz
    return math.sqrt(dx * dx + dy * dy + dz * dz)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{ship_id}/autopilot/tick")
async def autopilot_tick(
    ship_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Aggregated state snapshot for autopilot decision-making.

    Returns ship info, target locks, nearby contacts, recent events,
    and a threat assessment showing ships targeting this ship.
    """
    ship = await get_owned_ship(
        ship_id, current_user, session,
        selectinload(Spaceship.modules),
    )

    # C1: Destroyed ship check
    if ship.is_destroyed:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ship is destroyed")

    if ship.autopilot_mode != "active":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ship must be in autopilot_mode='active' to query autopilot tick data",
        )

    # --- Target locks this ship holds ---
    locks_result = await session.exec(
        select(TargetLock).where(
            TargetLock.ship_id == ship.id,
            TargetLock.status.in_([LockStatus.locking.value, LockStatus.locked.value]),  # type: ignore[attr-defined]
        )
    )
    locks = [
        {
            "id": l.id,
            "target_ship_id": l.target_ship_id,
            "status": l.status.value if hasattr(l.status, "value") else l.status,
            "ticks_remaining": l.ticks_remaining,
        }
        for l in locks_result.all()
    ]

    # --- Ships targeting this ship (threat assessment) ---
    threat_result = await session.exec(
        select(TargetLock).where(
            TargetLock.target_ship_id == ship.id,
            TargetLock.status.in_([LockStatus.locking.value, LockStatus.locked.value]),  # type: ignore[attr-defined]
        )
    )
    ships_targeting_me = [
        {
            "lock_id": l.id,
            "ship_id": l.ship_id,
            "status": l.status.value if hasattr(l.status, "value") else l.status,
            "ticks_remaining": l.ticks_remaining,
        }
        for l in threat_result.all()
    ]

    # M4: Use scanner/detector range for visibility instead of hardcoded 1km
    visibility_range = 1_000.0  # default 1 km
    for m in ship.modules:
        if m.module_type.value == "scanner" and m.scan_range > 0:
            visibility_range = max(visibility_range, m.scan_range)
        elif m.module_type.value == "passive_detector" and m.detection_range > 0:
            visibility_range = max(visibility_range, m.detection_range)

    # C2: Bounding box filter for nearby ships — avoid full table scan
    margin = visibility_range
    nearby_ships_result = await session.exec(
        select(Spaceship).where(
            Spaceship.id != ship.id,
            Spaceship.is_destroyed == False,
            Spaceship.docked_in_id == None,
            Spaceship.pos_x.between(ship.pos_x - margin, ship.pos_x + margin),
            Spaceship.pos_y.between(ship.pos_y - margin, ship.pos_y + margin),
            Spaceship.pos_z.between(ship.pos_z - margin, ship.pos_z + margin),
        )
    )
    candidate_ships = list(nearby_ships_result.all())

    # C2: Bounding box filter for nearby celestial objects
    nearby_objects_result = await session.exec(
        select(CelestialObject).where(
            CelestialObject.pos_x.between(ship.pos_x - margin, ship.pos_x + margin),
            CelestialObject.pos_y.between(ship.pos_y - margin, ship.pos_y + margin),
            CelestialObject.pos_z.between(ship.pos_z - margin, ship.pos_z + margin),
        )
    )
    candidate_objects = list(nearby_objects_result.all())

    nearby = []
    nearby_ships_with_dist = []  # for H6 nearest_enemy/nearest_friendly computation

    for other in candidate_ships:
        # L2: docked_in_id filter already handled by query; no hasattr guard needed
        dist = _dist(
            ship.pos_x, ship.pos_y, ship.pos_z,
            other.pos_x, other.pos_y, other.pos_z,
        )
        if dist <= visibility_range:
            nearby.append({
                "type": "ship",
                "id": other.id,
                "distance": dist,
                "ship_class": other.ship_class.value,
                "name": other.name,
                # H2: Add owner info to nearby contacts
                "user_id": other.user_id,
                "pos_x": other.pos_x,
                "pos_y": other.pos_y,
                "pos_z": other.pos_z,
            })
            nearby_ships_with_dist.append((other, dist))

    for obj in candidate_objects:
        dist = _dist(
            ship.pos_x, ship.pos_y, ship.pos_z,
            obj.pos_x, obj.pos_y, obj.pos_z,
        )
        if dist <= visibility_range:
            nearby.append({
                "type": "object",
                "id": obj.id,
                "distance": dist,
                "object_type": obj.object_type.value,
                "name": obj.name,
                "pos_x": obj.pos_x,
                "pos_y": obj.pos_y,
                "pos_z": obj.pos_z,
                "ore_remaining": obj.ore_remaining,
            })

    nearby.sort(key=lambda c: c["distance"])

    # H6: Find nearest enemy and nearest friendly among nearby ships
    nearest_enemy = None
    nearest_friendly = None
    for other, dist in nearby_ships_with_dist:
        if other.user_id != ship.user_id:
            if nearest_enemy is None or dist < nearest_enemy["distance"]:
                nearest_enemy = {
                    "id": other.id,
                    "ship_class": other.ship_class.value,
                    "distance": dist,
                }
        else:
            if nearest_friendly is None or dist < nearest_friendly["distance"]:
                nearest_friendly = {
                    "id": other.id,
                    "ship_class": other.ship_class.value,
                    "distance": dist,
                }

    # H4: Scope events to ship, not just user
    events_result = await session.exec(
        select(Event)
        .where(Event.ship_id == ship.id)
        .order_by(Event.id.desc())  # type: ignore[union-attr]
        .limit(10)
    )
    events_since_last_tick = [
        {
            "id": e.id,
            "tick": e.tick,
            "event_type": e.event_type.value if hasattr(e.event_type, "value") else e.event_type,
            "message": e.message,
            "ship_id": e.ship_id,
        }
        for e in events_result.all()
    ]

    return {
        "ship": _ship_dict(ship),
        "profile": ship.autopilot_profile,
        "locks": locks,
        "nearby": nearby,
        "events_since_last_tick": events_since_last_tick,
        "threat_assessment": {
            "ships_targeting_me": ships_targeting_me,
            # H6: Add nearest enemy/friendly
            "nearest_enemy": nearest_enemy,
            "nearest_friendly": nearest_friendly,
        },
        # H6: Stub team signals and objectives
        "team_signals": [],
        "team_objectives": [],
    }
