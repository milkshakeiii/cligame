"""
View computation for the intent-based architecture.

compute_player_view() builds the complete world state visible to a player,
reading only committed DB state (which is always consistent since only the
tick loop writes).
"""

from __future__ import annotations

import math
from typing import Optional

from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.models import (
    BuildStatus,
    CelestialObject,
    Command,
    CommandStatus,
    Event,
    GameState,
    HULL_POINT_COSTS,
    Match,
    MatchStatus,
    ModuleType,
    OrderStatus,
    Spaceship,
    Team,
    User,
    WeaponAssignment,
)
from server.scanning import default_visibility_level, DETAIL_CLASSIFICATION, DETAIL_IDENTIFICATION


def _dist(ax, ay, az, bx, by, bz) -> float:
    dx, dy, dz = ax - bx, ay - by, az - bz
    return math.sqrt(dx * dx + dy * dy + dz * dz)


async def compute_player_view(
    session,
    user: User,
    current_tick: int,
    *,
    ship_id: Optional[int] = None,
    since_tick: Optional[int] = None,
) -> dict:
    """Build the complete world state visible to a player."""

    # --- Player's ships (team-shared when on a team) ---
    on_team = user.team_id is not None
    ship_owner_filter = (
        Spaceship.team_id == user.team_id if on_team else Spaceship.user_id == user.id
    )
    ship_query = (
        select(Spaceship)
        .where(ship_owner_filter)
        .options(
            selectinload(Spaceship.modules),
            selectinload(Spaceship.movement_orders),
            selectinload(Spaceship.build_orders),
            selectinload(Spaceship.target_locks),
            selectinload(Spaceship.team),
        )
    )
    if ship_id is not None:
        ship_query = ship_query.where(Spaceship.id == ship_id)

    ships_result = await session.exec(ship_query)
    ships = list(ships_result.all())

    # Fetch weapon assignments for all player ships (Fix 12)
    ship_ids = [s.id for s in ships]
    all_wa: list[WeaponAssignment] = []
    if ship_ids:
        wa_result = await session.exec(
            select(WeaponAssignment).where(
                WeaponAssignment.ship_id.in_(ship_ids)
            )
        )
        all_wa = list(wa_result.all())

    ship_views = []
    for ship in ships:
        faction = None
        try:
            faction = ship.faction
        except Exception:
            pass

        used_volume = sum(m.volume for m in ship.modules)
        modules = [
            {
                "id": m.id,
                "module_type": m.module_type.value,
                "volume": m.volume,
                "active": m.active,
                "cycle_time": m.cycle_time,
                "ticks_until_cycle": m.ticks_until_cycle,
                "capacitor_per_cycle": m.capacitor_per_cycle,
            }
            for m in ship.modules
        ]

        active_orders = [
            {
                "id": o.id,
                "order_type": o.order_type.value,
                "status": o.status.value,
                "target_ship_id": o.target_ship_id,
                "target_object_id": o.target_object_id,
                "target_x": o.target_x,
                "target_y": o.target_y,
                "target_z": o.target_z,
                "desired_distance": o.desired_distance,
                "orbit_radius": o.orbit_radius,
            }
            for o in ship.movement_orders
            if o.status == OrderStatus.active
        ]

        locks = [
            {
                "id": l.id,
                "target_ship_id": l.target_ship_id,
                "status": l.status.value if hasattr(l.status, "value") else l.status,
                "ticks_remaining": l.ticks_remaining,
            }
            for l in ship.target_locks
            if l.status in ("locking", "locked")
            or (hasattr(l.status, "value") and l.status.value in ("locking", "locked"))
        ]

        build_orders = [
            {
                "id": bo.id,
                "blueprint": bo.blueprint.value if hasattr(bo.blueprint, "value") else bo.blueprint,
                "status": bo.status.value if hasattr(bo.status, "value") else bo.status,
                "ore_cost": bo.ore_cost,
                "ticks_remaining": bo.ticks_remaining,
                "total_ticks": bo.total_ticks,
                "factory_module_id": bo.factory_module_id,
            }
            for bo in ship.build_orders
            if bo.status in (BuildStatus.building, BuildStatus.paused, BuildStatus.queued)
        ]

        ship_wa = [
            {"module_id": wa.module_id, "target_ship_id": wa.target_ship_id}
            for wa in all_wa if wa.ship_id == ship.id
        ]

        ship_views.append({
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
            "total_volume": ship.total_volume,
            "used_volume": used_volume,
            "cargo_capacity": ship.cargo_capacity(),
            "max_speed": ship.max_speed(),
            "acceleration": ship.acceleration(),
            "shield_hp": ship.shield_hp,
            "max_shield_hp": ship.max_shield_hp,
            "armor_hp": ship.armor_hp,
            "max_armor_hp": ship.max_armor_hp,
            "is_destroyed": ship.is_destroyed,
            "signature_radius": ship.signature_radius,
            "docked_in_id": ship.docked_in_id,
            "team_id": ship.team_id,
            "match_id": ship.match_id,
            "faction": faction,
            "modules": modules,
            "active_orders": active_orders,
            "locks": locks,
            "build_orders": build_orders,
            "weapon_assignments": ship_wa,
        })

    # --- Nearby contacts ---
    nearby = []
    if ships:
        # Collect all target IDs locked by the player's ships
        locked_target_ids: set[int] = set()
        for ship in ships:
            for l in ship.target_locks:
                status = l.status.value if hasattr(l.status, "value") else l.status
                if status == "locked":
                    locked_target_ids.add(l.target_ship_id)

        # Hoist queries outside per-ship loop to avoid N+1 (Fix 11)
        other_filter = (
            Spaceship.team_id != user.team_id if on_team else Spaceship.user_id != user.id
        )
        other_ships_result = await session.exec(
            select(Spaceship).where(
                other_filter,
                Spaceship.is_destroyed == False,
                Spaceship.docked_in_id == None,
            )
        )
        all_other_ships = list(other_ships_result.all())

        objects_result = await session.exec(select(CelestialObject))
        all_celestial_objects = list(objects_result.all())

        # Use scanner/detector range for visibility
        for ship in ships:
            if ship.is_destroyed or ship.is_docked():
                continue

            visibility_range = 1_000.0
            for m in ship.modules:
                if m.module_type == ModuleType.scanner and m.scan_range and m.scan_range > 0:
                    visibility_range = max(visibility_range, m.scan_range)
                elif m.module_type == ModuleType.passive_detector and m.detection_range and m.detection_range > 0:
                    visibility_range = max(visibility_range, m.detection_range)

            # Other ships
            for other in all_other_ships:
                dist = _dist(ship.pos_x, ship.pos_y, ship.pos_z,
                           other.pos_x, other.pos_y, other.pos_z)
                if dist <= visibility_range:
                    detail = default_visibility_level(dist)
                    if detail == 0:
                        detail = 1  # at least contact-level within range
                    contact = {
                        "type": "ship",
                        "id": other.id,
                        "distance": dist,
                        "detail": detail,
                        "pos_x": other.pos_x,
                        "pos_y": other.pos_y,
                        "pos_z": other.pos_z,
                    }
                    if detail >= DETAIL_CLASSIFICATION:
                        contact["ship_class"] = other.ship_class.value
                    if detail >= DETAIL_IDENTIFICATION:
                        contact["name"] = other.name
                    if other.id in locked_target_ids:
                        contact["shield_hp"] = other.shield_hp
                        contact["max_shield_hp"] = other.max_shield_hp
                        contact["armor_hp"] = other.armor_hp
                        contact["max_armor_hp"] = other.max_armor_hp
                    # Avoid duplicates
                    if not any(c["type"] == "ship" and c["id"] == other.id for c in nearby):
                        nearby.append(contact)

            # Celestial objects
            for obj in all_celestial_objects:
                dist = _dist(ship.pos_x, ship.pos_y, ship.pos_z,
                           obj.pos_x, obj.pos_y, obj.pos_z)
                if dist <= visibility_range:
                    detail = default_visibility_level(dist)
                    if detail == 0:
                        detail = 1
                    contact = {
                        "type": "object",
                        "id": obj.id,
                        "distance": dist,
                        "detail": detail,
                        "pos_x": obj.pos_x,
                        "pos_y": obj.pos_y,
                        "pos_z": obj.pos_z,
                        "object_type": obj.object_type.value,
                    }
                    if detail >= DETAIL_CLASSIFICATION:
                        contact["ore_remaining"] = obj.ore_remaining
                    if not any(c["type"] == "object" and c["id"] == obj.id for c in nearby):
                        nearby.append(contact)

    nearby.sort(key=lambda c: c["distance"])

    # --- Recent events (team-shared when on a team) ---
    event_since = since_tick if since_tick is not None else max(0, current_tick - 20)
    team_ship_ids = [s.id for s in ships]
    if on_team and team_ship_ids:
        event_owner_filter = Event.ship_id.in_(team_ship_ids)
    else:
        event_owner_filter = Event.user_id == user.id
    events_result = await session.exec(
        select(Event)
        .where(event_owner_filter, Event.tick >= event_since)
        .order_by(Event.tick.desc(), Event.id.desc())
        .limit(100)
    )
    events = [
        {
            "id": e.id,
            "tick": e.tick,
            "type": e.event_type.value if hasattr(e.event_type, "value") else e.event_type,
            "message": e.message,
            "ship_id": e.ship_id,
        }
        for e in events_result.all()
    ]

    # --- Pending/recent commands ---
    cmd_result = await session.exec(
        select(Command)
        .where(Command.user_id == user.id)
        .order_by(Command.id.desc())
        .limit(20)
    )
    pending_commands = [
        {
            "id": c.id,
            "type": c.command_type,
            "ship_id": c.ship_id,
            "status": c.status,
            "rejection_reason": c.rejection_reason,
            "processed_at_tick": c.processed_at_tick,
        }
        for c in cmd_result.all()
    ]

    # --- Team info ---
    team_info = None
    if user.team_id is not None:
        team_result = await session.exec(select(Team).where(Team.id == user.team_id))
        team = team_result.first()
        if team:
            team_info = {
                "id": team.id,
                "name": team.name,
                "faction": team.faction,
            }

    # --- Match info ---
    match_info = None
    if user.team_id is not None:
        match_result = await session.exec(
            select(Match).where(
                Match.status.in_([MatchStatus.pending.value, MatchStatus.active.value]),
                (Match.team1_id == user.team_id) | (Match.team2_id == user.team_id),
            )
        )
        match = match_result.first()
        if match:
            match_info = {
                "id": match.id,
                "name": match.name,
                "status": match.status,
                "team1_id": match.team1_id,
                "team2_id": match.team2_id,
                "started_at_tick": match.started_at_tick,
                "winner_team_id": match.winner_team_id,
            }

    # --- Available unclaimed hulls ---
    available_hulls = []
    if on_team:
        hull_query = select(Spaceship).where(
            Spaceship.team_id == user.team_id,
            Spaceship.claimed_by_user_id == None,  # noqa: E711
            Spaceship.docked_in_id != None,  # noqa: E711
            Spaceship.is_destroyed == False,  # noqa: E712
        )
        hull_result = await session.exec(hull_query)
        for h in hull_result.all():
            available_hulls.append({
                "ship_id": h.id,
                "ship_class": h.ship_class.value,
                "docked_at_ship_id": h.docked_in_id,
                "hull_point_cost": HULL_POINT_COSTS.get(h.ship_class.value, 0),
            })

    # Free hull classes that can be auto-created without building
    free_hull_classes = [cls for cls, cost in HULL_POINT_COSTS.items() if cost == 0]

    return {
        "tick": current_tick,
        "points": user.points,
        "ships": ship_views,
        "available_hulls": available_hulls,
        "free_hull_classes": free_hull_classes,
        "nearby": nearby,
        "events": events,
        "pending_commands": pending_commands,
        "team": team_info,
        "match": match_info,
    }
