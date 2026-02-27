"""
The game tick loop.

Runs as an asyncio background task started by FastAPI's lifespan context.
Each tick (default 1 real second) executes the following phases in order:

  1. Increment GameState.current_tick
  2. Energy phase      — capacitor regen for all ships
  3. Module phase      — advance cycle timers, fire cycles, drain cap
  4. Mining phase      — ore extraction for ships with active mining lasers
  5. Production phase  — advance build orders, spawn completed ships
  6. Physics phase     — apply movement behaviors, integrate positions
  6.5 Target lock phase  — advance lock timers, complete/break locks
  6.55 Solar Lance phase — charge / fire / cooldown the Solarion superweapon
  6.6 Weapon fire phase  — turret tracking, hit/miss, damage application
  6.65 Leech phase       — tick leech debuffs (damage + cap drain)
  6.7 Shield regen phase — passive shield regeneration
  6.7b Repair modules    — shield boosters + armor repairers
  6.72 Voidborn armor regen — passive armor regen for Voidborn ships
  6.73 Bio-Repair Swarm  — AoE armor repair for friendly ships
  6.8 Missile phase      — resolve in-flight missiles (delayed damage)
  6.9 Destruction phase  — destroy ships at 0 armor, create wrecks
  7. Detection phase     — passive detectors + scan-reveal alerts
  8. Generate Event records for noteworthy occurrences
  9. Commit once

The loop is resilient: per-tick exceptions are caught, logged, and the loop
continues rather than crashing the server.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
from typing import Optional

from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.config import settings
from server.database import async_session
from server.models import (
    BuildStatus,
    CelestialType,
    CLASS_ORDER,
    CelestialObject,
    Event,
    EventType,
    GameState,
    LeechDebuff,
    LockStatus,
    Match,
    MatchStatus,
    MAX_LOCKS,
    ModuleType,
    MovementOrder,
    OrderStatus,
    OrderType,
    PendingMissile,
    SHIP_CLASSES,
    Spaceship,
    ShipModule,
    BuildOrder,
    TargetLock,
    Team,
    User,
    TURRET_TYPES,
    MISSILE_TYPES,
    WEAPON_TYPES,
    SHIELD_BOOSTER_TYPES,
    ARMOR_REPAIRER_TYPES,
    LEECH_PROJECTOR_TYPES,
    STEALTH_FIELD_TYPES,
    VOIDBORN_MODULE_PARAMS,
    SOLARION_MODULE_PARAMS,
    SHARED_MODULE_PARAMS,
    VOIDBORN_SHIELD_BOOSTER_TYPES,
    SOLARION_ARMOR_REPAIRER_TYPES,
    SOLARION_BEAM_TURRET_TYPES,
    WeaponAssignment,
)
from server.energy import apply_regen, check_depletion, drain_module
from server.mining import tick_mining_laser, tick_ore_transfer
from server.production import tick_build_order, FACTORY_CAP_PER_TICK, get_next_queued_order
from server.physics import (
    DT,
    DOCK_TICKS,
    Vec3,
    behavior_approach,
    behavior_dock,
    behavior_keep_at_range,
    behavior_orbit,
    behavior_stop,
    integrate,
    resolve_target_position,
)
from server.scanning import (
    tick_active_scanner,
    tick_passive_detector,
    get_ships_that_detect_scan,
    DETAIL_CLASSIFICATION,
)
from server.match import cleanup_match_assignments
from server.combat import (
    apply_armor_regen,
    apply_damage,
    apply_shield_regen,
    compute_angular_velocity,
    compute_final_hit_chance,
    compute_lock_time,
    compute_missile_damage,
    compute_transversal_velocity,
    compute_turret_damage,
)
from server.research import tick_research

logger = logging.getLogger(__name__)

# Wrecks despawn after this many ticks
WRECK_LIFETIME_TICKS = 300

# ---------------------------------------------------------------------------
# In-memory state for detection deduplication (BUG-04)
# ---------------------------------------------------------------------------

# Maps module_id -> set of contact keys (type:id strings) seen on the previous
# detector cycle.  Not persisted — resets on server restart, which is fine
# because players only need "new contact" events going forward.
_detection_previous_contacts: dict[int, set[str]] = {}

# ---------------------------------------------------------------------------
# In-memory state for mining out-of-range suppression (MISS-05)
# ---------------------------------------------------------------------------

# Maps ship_id -> set of module IDs that are currently in an "out of range"
# state for the mining laser.  An event is only emitted on the *first* cycle
# where no asteroid is found, not on every subsequent cycle.
_mining_out_of_range: dict[int, set[int]] = {}

# ---------------------------------------------------------------------------
# In-memory state for match mothership HP warning cooldowns (Phase 8)
# ---------------------------------------------------------------------------

# Maps (match_id, ship_id) -> last tick a warning was emitted.
# Prevents spamming mothership_under_attack / mothership_critical every tick.
_mothership_warning_last_tick: dict[tuple[int, int], int] = {}
_MOTHERSHIP_WARNING_COOLDOWN = 30  # ticks between repeated warnings

# ---------------------------------------------------------------------------
# Public control API (called from FastAPI lifespan)
# ---------------------------------------------------------------------------

_tick_task: Optional[asyncio.Task] = None


async def start_tick_loop() -> None:
    """Start the background tick loop task."""
    global _tick_task
    if _tick_task is None or _tick_task.done():
        _tick_task = asyncio.create_task(_tick_loop())
        logger.info("Tick loop started")


async def stop_tick_loop() -> None:
    """Cancel the background tick loop task and wait for it to finish."""
    global _tick_task
    if _tick_task is not None and not _tick_task.done():
        _tick_task.cancel()
        try:
            await _tick_task
        except asyncio.CancelledError:
            pass
        logger.info("Tick loop stopped")


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


async def _tick_loop() -> None:
    """
    Infinite loop that runs one game tick per ``settings.tick_interval`` seconds.
    Errors within a single tick are caught and logged; the loop continues.
    """
    while True:
        try:
            await _run_tick()
        except asyncio.CancelledError:
            raise  # re-raise so the task ends cleanly
        except Exception:
            logger.exception("Unhandled error during tick — continuing")

        await asyncio.sleep(settings.tick_interval)


# ---------------------------------------------------------------------------
# Single tick
# ---------------------------------------------------------------------------


async def _run_tick() -> None:
    """Execute one complete game tick."""
    async with async_session() as session:
        # ------------------------------------------------------------------
        # Load game state
        # ------------------------------------------------------------------
        gs_result = await session.exec(select(GameState))
        game_state = gs_result.first()
        if game_state is None:
            # Server not fully initialised yet — skip
            return

        game_state.current_tick += 1
        current_tick = game_state.current_tick

        # ------------------------------------------------------------------
        # Load all active ships with their modules, orders, build orders
        # ------------------------------------------------------------------
        ships_result = await session.exec(
            select(Spaceship)
            .where(Spaceship.is_destroyed == False)  # noqa: E712
            .options(
                selectinload(Spaceship.modules),
                selectinload(Spaceship.movement_orders),
                selectinload(Spaceship.build_orders),
                selectinload(Spaceship.target_locks),
                selectinload(Spaceship.team),
            )
        )
        ships: list[Spaceship] = list(ships_result.all())

        # Load all celestial objects
        objects_result = await session.exec(select(CelestialObject))
        celestial_objects: list[CelestialObject] = list(objects_result.all())

        # Load weapon assignments and pending missiles for combat
        wa_result = await session.exec(select(WeaponAssignment))
        weapon_assignments: list[WeaponAssignment] = list(wa_result.all())

        pm_result = await session.exec(select(PendingMissile))
        pending_missiles: list[PendingMissile] = list(pm_result.all())

        # Load active leech debuffs for faction mechanics
        leech_result = await session.exec(select(LeechDebuff))
        active_leeches: list[LeechDebuff] = list(leech_result.all())

        # Collect events to bulk-insert at the end
        pending_events: list[Event] = []

        def emit(
            event_type: EventType,
            message: str,
            user_id: int,
            ship_id: Optional[int] = None,
        ) -> None:
            pending_events.append(
                Event(
                    tick=current_tick,
                    user_id=user_id,
                    ship_id=ship_id,
                    event_type=event_type,
                    message=message,
                )
            )

        # ------------------------------------------------------------------
        # Phase 0: Process command queue
        # ------------------------------------------------------------------
        from server.commands import TickContext, process_commands
        ctx = TickContext(
            session=session,
            ships=ships,
            celestial_objects=celestial_objects,
            weapon_assignments=weapon_assignments,
            pending_missiles=pending_missiles,
            active_leeches=active_leeches,
            current_tick=current_tick,
            pending_events=pending_events,
        )
        await process_commands(ctx)
        # Commands may have modified lists (new ships, new weapon assignments)
        ships = ctx.ships
        weapon_assignments = ctx.weapon_assignments

        # ------------------------------------------------------------------
        # Phase 1: Energy — capacitor regen
        # ------------------------------------------------------------------
        for ship in ships:
            if ship.is_docked():
                continue
            apply_regen(ship)

        # ------------------------------------------------------------------
        # Phase 2: Module cycling
        # ------------------------------------------------------------------
        # fired_modules_by_ship maps ship.id -> set of module IDs that fired
        fired_modules_by_ship: dict[int, set[int]] = {}
        for ship in ships:
            if ship.is_docked():
                continue
            fired_modules_by_ship[ship.id] = _process_modules(ship, current_tick, emit)

        # ------------------------------------------------------------------
        # Phase 3: Mining
        # ------------------------------------------------------------------
        _asteroid_map = {obj.id: obj for obj in celestial_objects}
        for ship in ships:
            if ship.is_docked():
                continue
            _process_mining(
                ship,
                _asteroid_map,
                current_tick,
                emit,
                fired_modules_by_ship.get(ship.id, set()),
            )

        # ------------------------------------------------------------------
        # Phase 4: Production
        # ------------------------------------------------------------------
        new_ships: list[Spaceship] = []
        for ship in ships:
            if ship.is_docked():
                continue
            _process_production(ship, current_tick, emit, new_ships)

        # Add newly spawned ships to the session
        for new_ship in new_ships:
            session.add(new_ship)

        # ------------------------------------------------------------------
        # Phase 4b: Research
        # ------------------------------------------------------------------
        _ship_map_pre = {s.id: s for s in ships}
        await tick_research(session, _ship_map_pre, current_tick)

        # ------------------------------------------------------------------
        # Phase 5: Physics
        # ------------------------------------------------------------------
        _ship_map = {s.id: s for s in ships}
        for ship in ships:
            if ship.is_docked():
                continue
            _process_physics(ship, _ship_map, _asteroid_map, current_tick, emit, session)

        # Clean up leeches on ships that are now docked (dock may have occurred in physics)
        for ship in ships:
            if ship.is_docked():
                leeches_on_docked = [lch for lch in active_leeches if lch.target_ship_id == ship.id]
                for lch in leeches_on_docked:
                    session.delete(lch)
                    active_leeches.remove(lch)

        # ------------------------------------------------------------------
        # Phase 6.5: Target Lock Processing
        # ------------------------------------------------------------------
        for ship in ships:
            if ship.is_docked() or ship.is_destroyed:
                continue
            _process_target_locks(ship, _ship_map, current_tick, emit)

        # ------------------------------------------------------------------
        # Phase 6.55: Solar Lance Processing
        # ------------------------------------------------------------------
        for ship in ships:
            if ship.is_docked() or ship.is_destroyed:
                continue
            _process_solar_lance(ship, _ship_map, current_tick, emit)

        # ------------------------------------------------------------------
        # Phase 6.6: Weapon Fire
        # ------------------------------------------------------------------
        _module_map: dict[int, ShipModule] = {}
        for ship in ships:
            for m in ship.modules:
                _module_map[m.id] = m

        # Build weapon assignment lookup: module_id -> WeaponAssignment
        _wa_by_module: dict[int, WeaponAssignment] = {
            wa.module_id: wa for wa in weapon_assignments
        }

        for ship in ships:
            if ship.is_docked() or ship.is_destroyed:
                continue
            _process_weapon_fire(
                ship, _ship_map, _wa_by_module,
                fired_modules_by_ship.get(ship.id, set()),
                current_tick, emit, session, pending_missiles,
                active_leeches,
            )

        # ------------------------------------------------------------------
        # Phase 6.65: Leech Processing
        # ------------------------------------------------------------------
        _process_leeches(active_leeches, _ship_map, current_tick, session, emit)

        # ------------------------------------------------------------------
        # Phase 6.7: Shield Regen
        # ------------------------------------------------------------------
        for ship in ships:
            if ship.is_docked() or ship.is_destroyed:
                continue
            apply_shield_regen(ship)

        # ------------------------------------------------------------------
        # Phase 6.7b: Shield Boosters + Armor Repairers + Shield Purge
        # ------------------------------------------------------------------
        for ship in ships:
            if ship.is_docked() or ship.is_destroyed:
                continue
            _process_repair_modules(
                ship, fired_modules_by_ship.get(ship.id, set()),
            )
            _process_shield_purge(
                ship, fired_modules_by_ship.get(ship.id, set()),
                active_leeches, emit, session,
            )

        # ------------------------------------------------------------------
        # Phase 6.72: Voidborn Passive Armor Regen
        # ------------------------------------------------------------------
        for ship in ships:
            if ship.is_docked() or ship.is_destroyed:
                continue
            if ship.faction == "voidborn":
                apply_armor_regen(ship)

        # ------------------------------------------------------------------
        # Phase 6.73: Bio-Repair Swarm Processing
        # ------------------------------------------------------------------
        for ship in ships:
            if ship.is_docked() or ship.is_destroyed:
                continue
            _process_bio_repair_swarm(
                ship, ships, fired_modules_by_ship.get(ship.id, set()),
                current_tick, emit,
            )

        # ------------------------------------------------------------------
        # Phase 6.8: Missile Resolution
        # ------------------------------------------------------------------
        _process_pending_missiles(
            pending_missiles, _ship_map, current_tick, emit, session,
        )

        # ------------------------------------------------------------------
        # Phase 6.9: Destruction
        # ------------------------------------------------------------------
        _process_destruction(ships, _ship_map, current_tick, emit, session, active_leeches)

        # ------------------------------------------------------------------
        # Phase 6.9b: Wreck cleanup (expired wrecks despawn)
        # ------------------------------------------------------------------
        _cleanup_expired_wrecks(celestial_objects, current_tick, session)

        # ------------------------------------------------------------------
        # Phase 6.9c: Match win condition check
        # ------------------------------------------------------------------
        await _check_match_win_conditions(
            session, ships, _ship_map, current_tick, emit,
        )

        # ------------------------------------------------------------------
        # Phase 7: Detection
        # ------------------------------------------------------------------
        for ship in ships:
            if ship.is_docked():
                continue
            _process_detection(
                ship,
                ships,
                celestial_objects,
                current_tick,
                emit,
                fired_modules_by_ship.get(ship.id, set()),
            )

        # ------------------------------------------------------------------
        # Persist everything
        # ------------------------------------------------------------------
        for event in pending_events:
            session.add(event)

        await session.commit()


# ---------------------------------------------------------------------------
# Phase helpers
# ---------------------------------------------------------------------------


def _process_modules(
    ship: Spaceship,
    current_tick: int,
    emit,
) -> set[int]:
    """
    Advance cycle timers for all active non-passive modules.
    Drain cap when a cycle fires.  Handle cap depletion.

    Returns a set of module IDs whose cycles fired this tick.
    """
    fired_module_ids: set[int] = set()

    for module in ship.modules:
        # Count down stealth cooldown even if module is inactive
        if module.module_type.value in STEALTH_FIELD_TYPES and module.stealth_cooldown_remaining > 0:
            module.stealth_cooldown_remaining -= 1

        if not module.active:
            continue
        if module.is_passive:
            continue  # passive modules don't cycle

        # Count down
        module.ticks_until_cycle = max(0, module.ticks_until_cycle - 1)

        if module.ticks_until_cycle > 0:
            continue  # not yet time to cycle

        # Cycle fires — drain cap
        success = drain_module(ship, module)
        if not success:
            # Insufficient cap — don't fire the cycle; deactivate non-engine modules
            if module.module_type != ModuleType.engine:
                module.active = False
                if ship.user_id is not None:
                    emit(
                        EventType.cap_depleted,
                        f"{module.module_type.value.replace('_', ' ').title()} "
                        f"deactivated: insufficient capacitor",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )
            continue

        # Reset cycle timer and record that this module fired
        module.ticks_until_cycle = module.cycle_time
        fired_module_ids.add(module.id)

    # Check for cap depletion after module drain
    depleted = check_depletion(ship)
    if depleted and ship.user_id is not None:
        emit(
            EventType.cap_depleted,
            "Capacitor depleted, all modules offline",
            user_id=ship.user_id,
            ship_id=ship.id,
        )

    return fired_module_ids


def _find_nearest_asteroid(
    ship: Spaceship,
    asteroid_map: dict[int, CelestialObject],
    laser_range: float,
) -> Optional[CelestialObject]:
    """Return the nearest non-depleted asteroid within laser_range, or None."""
    from server.models import CelestialType

    best: Optional[CelestialObject] = None
    best_dist = float("inf")
    for obj in asteroid_map.values():
        if obj.object_type != CelestialType.asteroid:
            continue
        if obj.ore_remaining <= 0.0:
            continue
        dx = ship.pos_x - obj.pos_x
        dy = ship.pos_y - obj.pos_y
        dz = ship.pos_z - obj.pos_z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist <= laser_range and dist < best_dist:
            best = obj
            best_dist = dist
    return best


def _process_mining(
    ship: Spaceship,
    asteroid_map: dict[int, CelestialObject],
    current_tick: int,
    emit,
    fired_module_ids: set[int],
) -> None:
    """
    Fire mining laser cycles for all active mining lasers that fired this tick.

    ``fired_module_ids`` is the set of module IDs returned by ``_process_modules``
    for this ship — it contains exactly the modules whose cycles completed this tick.
    """
    cargo_full_emitted = False

    for module in ship.modules:
        if module.module_type not in (ModuleType.mining_laser, ModuleType.strip_miner):
            continue
        if not module.active:
            continue

        # Only process lasers whose cycle fired this tick
        if module.id not in fired_module_ids:
            continue  # not a cycle-fire tick

        asteroid = _find_nearest_asteroid(ship, asteroid_map, module.mining_range)
        result = tick_mining_laser(ship, module, asteroid)

        if result["no_asteroid"] or result["out_of_range"]:
            # MISS-05: emit an event the first time the laser fires with nothing
            # in range, then suppress repeats until a successful cycle resets it.
            ship_oor_set = _mining_out_of_range.setdefault(ship.id, set())
            if module.id not in ship_oor_set:
                ship_oor_set.add(module.id)
                if ship.user_id is not None:
                    emit(
                        EventType.mining,
                        "Mining Laser: no asteroid within range",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )
            continue

        if result["asteroid_done"]:
            module.active = False
            if ship.user_id is not None:
                target_id = asteroid.id if asteroid else "?"
                emit(
                    EventType.asteroid_depleted,
                    f"Asteroid #{target_id} depleted",
                    user_id=ship.user_id,
                    ship_id=ship.id,
                )
            continue

        if result["ore_mined"] > 0 and ship.user_id is not None:
            asteroid_id = asteroid.id if asteroid else "?"
            emit(
                EventType.mining,
                f"Mined {result['ore_mined']:.0f} ore from asteroid #{asteroid_id}",
                user_id=ship.user_id,
                ship_id=ship.id,
            )
            # MISS-05: successful cycle clears the "out of range" flag so the
            # next out-of-range period will emit a fresh event.
            _mining_out_of_range.get(ship.id, set()).discard(module.id)

        # Cargo-full check (emit once per tick per ship)
        cargo_cap = ship.cargo_capacity()
        if not cargo_full_emitted and cargo_cap > 0 and ship.ore >= cargo_cap:
            cargo_full_emitted = True
            if ship.user_id is not None:
                emit(
                    EventType.cargo_full,
                    f"Cargo bay full ({ship.ore:.0f}/{cargo_cap:.0f} ore) — "
                    f"asteroid ore preserved, stop mining to avoid wasting capacitor",
                    user_id=ship.user_id,
                    ship_id=ship.id,
                )


def _process_production(
    ship: Spaceship,
    current_tick: int,
    emit,
    new_ships: list[Spaceship],
) -> None:
    """
    Advance all active/paused build orders on this ship.
    Spawn new ships when builds complete.

    Queued orders are promoted to 'building' when their factory has no active
    or paused order (i.e., the factory just became free or was never busy).
    """
    # Collect factory module IDs that have an active (building/paused) order
    active_factory_ids: set[int] = {
        o.factory_module_id
        for o in ship.build_orders
        if o.status in (BuildStatus.building, BuildStatus.paused)
    }

    # Promote the next queued order for each factory that is now free
    for order in ship.build_orders:
        if order.status != BuildStatus.queued:
            continue
        if order.factory_module_id in active_factory_ids:
            continue  # factory is still busy
        # Promote this queued order to building
        order.status = BuildStatus.building
        active_factory_ids.add(order.factory_module_id)

    for order in ship.build_orders:
        if order.status not in (BuildStatus.building, BuildStatus.paused):
            continue

        result = tick_build_order(ship, order)

        if result["paused"] and ship.user_id is not None:
            emit(
                EventType.build_paused,
                f"Construction of {order.blueprint.value} paused: capacitor depleted",
                user_id=ship.user_id,
                ship_id=ship.id,
            )

        if result["completed"] and ship.user_id is not None:
            new_ship: Optional[Spaceship] = result["new_ship"]
            if new_ship is not None:
                new_ship.user_id = ship.user_id
                new_ships.append(new_ship)
                emit(
                    EventType.build_complete,
                    f"{order.blueprint.value.replace('_', ' ').title()} construction "
                    f"complete, spawned nearby",
                    user_id=ship.user_id,
                    ship_id=ship.id,
                )


def _process_physics(
    ship: Spaceship,
    ship_map: dict[int, Spaceship],
    asteroid_map: dict[int, CelestialObject],
    current_tick: int,
    emit,
    session,
) -> None:
    """
    Process all active movement orders for a ship and integrate position/velocity.
    """
    position: Vec3 = (ship.pos_x, ship.pos_y, ship.pos_z)
    velocity: Vec3 = (ship.vel_x, ship.vel_y, ship.vel_z)
    max_speed = ship.effective_max_speed()
    accel_mag = ship.effective_acceleration()

    # Find the first active order
    active_order: Optional[MovementOrder] = None
    for order in ship.movement_orders:
        if order.status == OrderStatus.active:
            active_order = order
            break

    if active_order is None:
        # BUG-02: ships with nonzero velocity still drift even without an order.
        speed_sq = ship.vel_x ** 2 + ship.vel_y ** 2 + ship.vel_z ** 2
        if speed_sq > 0.0:
            ship.pos_x += ship.vel_x * DT
            ship.pos_y += ship.vel_y * DT
            ship.pos_z += ship.vel_z * DT
        return

    # Resolve target
    target_ship = ship_map.get(active_order.target_ship_id) if active_order.target_ship_id else None
    target_object = asteroid_map.get(active_order.target_object_id) if active_order.target_object_id else None

    target_pos, target_vel = resolve_target_position(
        order_target_ship=target_ship,
        order_target_object=target_object,
        order_target_x=active_order.target_x,
        order_target_y=active_order.target_y,
        order_target_z=active_order.target_z,
    )

    # Dispatch behavior
    completed = False
    accel_vec: Vec3 = (0.0, 0.0, 0.0)
    dock_initiated = False

    if active_order.order_type == OrderType.approach:
        res = behavior_approach(
            position=position,
            velocity=velocity,
            target_pos=target_pos,
            target_vel=target_vel,
            max_speed=max_speed,
            acceleration_mag=accel_mag,
        )
        accel_vec = res.acceleration
        completed = res.completed

    elif active_order.order_type == OrderType.orbit:
        res = behavior_orbit(
            position=position,
            velocity=velocity,
            target_pos=target_pos,
            target_vel=target_vel,
            orbit_radius=active_order.orbit_radius,
            max_speed=max_speed,
            acceleration_mag=accel_mag,
        )
        accel_vec = res.acceleration

    elif active_order.order_type == OrderType.keep_distance:
        res = behavior_keep_at_range(
            position=position,
            velocity=velocity,
            target_pos=target_pos,
            target_vel=target_vel,
            desired_range=active_order.desired_distance,
            max_speed=max_speed,
            acceleration_mag=accel_mag,
        )
        accel_vec = res.acceleration

    elif active_order.order_type == OrderType.stop:
        res = behavior_stop(
            velocity=velocity,
            acceleration_mag=accel_mag,
        )
        accel_vec = res.acceleration
        if res.completed:
            ship.vel_x = 0.0
            ship.vel_y = 0.0
            ship.vel_z = 0.0
            completed = True

    elif active_order.order_type == OrderType.dock:
        res = behavior_dock(
            position=position,
            velocity=velocity,
            target_pos=target_pos,
            target_vel=target_vel,
            max_speed=max_speed,
            acceleration_mag=accel_mag,
            docking_ticks_remaining=active_order.docking_ticks_remaining,
        )
        accel_vec = res.acceleration
        dock_initiated = res.docking_initiated

        # Manage docking countdown
        if dock_initiated and active_order.docking_ticks_remaining == 0:
            active_order.docking_ticks_remaining = DOCK_TICKS
        elif active_order.docking_ticks_remaining > 0:
            active_order.docking_ticks_remaining -= 1
            if active_order.docking_ticks_remaining <= 0:
                # Docking complete — re-validate class and capacity before docking
                dock_valid = True
                if target_ship is None:
                    dock_valid = False
                else:
                    # C1: Class check
                    ship_class_idx = CLASS_ORDER.index(ship.ship_class.value)
                    target_class_idx = CLASS_ORDER.index(target_ship.ship_class.value)
                    if ship_class_idx >= target_class_idx:
                        dock_valid = False
                        if ship.user_id is not None:
                            emit(
                                EventType.order_complete,
                                (
                                    f"Docking failed: ship class '{ship.ship_class.value}' "
                                    f"must be smaller than target '{target_ship.ship_class.value}'"
                                ),
                                user_id=ship.user_id,
                                ship_id=ship.id,
                            )
                    else:
                        # C1: Capacity check — sum volumes of ships already docked
                        used_capacity = sum(
                            s.total_volume
                            for s in ship_map.values()
                            if s.docked_in_id == target_ship.id
                        )
                        remaining_capacity = target_ship.docking_capacity() - used_capacity
                        if ship.total_volume > remaining_capacity:
                            dock_valid = False
                            if ship.user_id is not None:
                                emit(
                                    EventType.order_complete,
                                    (
                                        f"Docking failed: insufficient capacity in "
                                        f"ship #{target_ship.id} "
                                        f"(need {ship.total_volume} m³, "
                                        f"available {remaining_capacity:.0f} m³)"
                                    ),
                                    user_id=ship.user_id,
                                    ship_id=ship.id,
                                )

                if dock_valid and target_ship is not None and ship.user_id is not None:
                    ship.docked_in_id = target_ship.id
                    completed = True
                    emit(
                        EventType.dock_complete,
                        f"Docked with ship #{target_ship.id} ({target_ship.name})",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )
                elif not dock_valid:
                    # MISS-06: emit a cancellation event for every case where
                    # the simulation cancels a dock order.  The class/capacity
                    # failure branches above already emit a specific reason; the
                    # target-not-found branch (target_ship is None) does not, so
                    # we cover it here with a generic message.
                    if target_ship is None and ship.user_id is not None:
                        emit(
                            EventType.order_complete,
                            "Docking cancelled: target ship no longer exists",
                            user_id=ship.user_id,
                            ship_id=ship.id,
                        )
                    # Cancel the order so it doesn't loop
                    active_order.status = OrderStatus.cancelled

    # Integrate position and velocity
    new_pos, new_vel = integrate(
        position=position,
        velocity=velocity,
        acceleration_vec=accel_vec,
        max_speed=max_speed,
        dt=DT,
    )

    # Write back (but not if docking just completed — ship is now "inside")
    if not ship.is_docked():
        ship.pos_x, ship.pos_y, ship.pos_z = new_pos
        ship.vel_x, ship.vel_y, ship.vel_z = new_vel

    # Mark order complete
    if completed:
        active_order.status = OrderStatus.completed
        if ship.user_id is not None and active_order.order_type != OrderType.dock:
            emit(
                EventType.order_complete,
                f"{active_order.order_type.value.replace('_', ' ').title()} order completed",
                user_id=ship.user_id,
                ship_id=ship.id,
            )


def _process_detection(
    ship: Spaceship,
    all_ships: list[Spaceship],
    all_objects: list[CelestialObject],
    current_tick: int,
    emit,
    fired_module_ids: set[int],
) -> None:
    """
    Run passive detectors and active scanners for one tick.

    ``fired_module_ids`` is the set of module IDs returned by ``_process_modules``
    for this ship — only modules in this set had their cycles fire this tick.
    """
    for module in ship.modules:
        if not module.active:
            continue

        # Passive detector — fires when its module ID is in fired_module_ids
        if module.module_type == ModuleType.passive_detector:
            if module.id not in fired_module_ids:
                continue  # not a cycle-fire tick
            result = tick_passive_detector(ship, module, all_ships, all_objects)

            # BUG-04: build the set of contact keys seen this cycle, then only
            # emit events for contacts that weren't present last cycle.
            current_keys: set[str] = set()
            for contact in result.new_contacts:
                key = f"{contact['type']}:{contact['id']}"
                current_keys.add(key)

            previous_keys = _detection_previous_contacts.get(module.id, set())

            for contact in result.new_contacts:
                key = f"{contact['type']}:{contact['id']}"
                if key in previous_keys:
                    continue  # already reported — skip to suppress flood
                if ship.user_id is not None:
                    dist_km = contact["distance"] / 1000.0
                    pos = (contact["pos_x"], contact["pos_y"], contact["pos_z"])
                    msg = (
                        f"Unknown contact detected at "
                        f"({pos[0]:.0f}, {pos[1]:.0f}, {pos[2]:.0f}), "
                        f"range {dist_km:.1f} km"
                    )
                    emit(
                        EventType.detection,
                        msg,
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )

            # Update the previous-contacts registry for next cycle
            _detection_previous_contacts[module.id] = current_keys

        # Active scanner — fires when its module ID is in fired_module_ids
        elif module.module_type == ModuleType.scanner:
            if module.id not in fired_module_ids:
                continue  # not a cycle-fire tick
            scan_result = tick_active_scanner(ship, module, all_ships, all_objects)
            contact_count = len(scan_result.contacts)
            if ship.user_id is not None:
                emit(
                    EventType.scan_complete,
                    f"Scan complete: {contact_count} contact(s) found",
                    user_id=ship.user_id,
                    ship_id=ship.id,
                )

            # Notify ships with passive detectors that they were scanned
            detecting_ships = get_ships_that_detect_scan(ship, all_ships)
            for other_ship in detecting_ships:
                if other_ship.user_id is not None:
                    dist_km = math.sqrt(
                        (ship.pos_x - other_ship.pos_x) ** 2
                        + (ship.pos_y - other_ship.pos_y) ** 2
                        + (ship.pos_z - other_ship.pos_z) ** 2
                    ) / 1000.0
                    emit(
                        EventType.scan_detected,
                        f"Scan detected from "
                        f"({ship.pos_x:.0f}, {ship.pos_y:.0f}, {ship.pos_z:.0f}), "
                        f"range {dist_km:.1f} km",
                        user_id=other_ship.user_id,
                        ship_id=other_ship.id,
                    )


# ---------------------------------------------------------------------------
# Combat phase helpers
# ---------------------------------------------------------------------------


def _process_target_locks(
    ship: Spaceship,
    ship_map: dict[int, Spaceship],
    current_tick: int,
    emit,
) -> None:
    """Advance target lock timers, complete or break locks."""
    for lock in ship.target_locks:
        if lock.status == LockStatus.broken:
            continue

        target = ship_map.get(lock.target_ship_id)

        # Break lock if target is gone, destroyed, or out of range
        if target is None or target.is_destroyed:
            lock.status = LockStatus.broken
            if ship.user_id is not None:
                emit(
                    EventType.target_lost,
                    f"Target lock lost: target destroyed or gone",
                    user_id=ship.user_id,
                    ship_id=ship.id,
                )
            continue

        # Check range: lock breaks at 1.25x the lock acquisition range
        # Scanner → 200km acquire / 250km break; no scanner → 1km / 1.25km
        has_scanner = any(
            m.module_type == ModuleType.scanner for m in ship.modules
        )
        lock_break_range = 250_000.0 if has_scanner else 1_250.0
        dx = target.pos_x - ship.pos_x
        dy = target.pos_y - ship.pos_y
        dz = target.pos_z - ship.pos_z
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist > lock_break_range:
            lock.status = LockStatus.broken
            if ship.user_id is not None:
                emit(
                    EventType.target_lost,
                    f"Target lock lost on Ship #{target.id}: out of range ({dist/1000:.1f} km)",
                    user_id=ship.user_id,
                    ship_id=ship.id,
                )
            continue

        if lock.status == LockStatus.locking:
            lock.ticks_remaining -= 1
            if lock.ticks_remaining <= 0:
                lock.status = LockStatus.locked
                if ship.user_id is not None:
                    emit(
                        EventType.target_locked,
                        f"Target lock acquired on Ship #{target.id} "
                        f"({target.ship_class.value.replace('_', ' ')}, {dist/1000:.1f} km)",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )
                # Notify the target they're being locked
                if target.user_id is not None:
                    emit(
                        EventType.incoming_lock,
                        f"Warning: locked by Ship #{ship.id} "
                        f"({ship.ship_class.value.replace('_', ' ')})",
                        user_id=target.user_id,
                        ship_id=target.id,
                    )


def _process_weapon_fire(
    ship: Spaceship,
    ship_map: dict[int, Spaceship],
    wa_by_module: dict[int, WeaponAssignment],
    fired_module_ids: set[int],
    current_tick: int,
    emit,
    session,
    pending_missiles_list: list[PendingMissile],
    active_leeches: list[LeechDebuff],
) -> None:
    """
    Fire weapons that cycled this tick.
    Only fires if the weapon's assigned target has a completed lock.
    """
    # Build set of locked target IDs for this ship
    locked_targets: set[int] = set()
    for lock in ship.target_locks:
        if lock.status == LockStatus.locked:
            locked_targets.add(lock.target_ship_id)

    # Check if this ship has any weapon that will fire this tick
    will_fire_weapon = False
    for module in ship.modules:
        mt = module.module_type.value
        if mt not in WEAPON_TYPES:
            continue
        if not module.active:
            continue
        if module.id not in fired_module_ids:
            continue
        wa = wa_by_module.get(module.id)
        if wa is None:
            continue
        if wa.target_ship_id not in locked_targets:
            continue
        target = ship_map.get(wa.target_ship_id)
        if target is None or target.is_destroyed:
            continue
        will_fire_weapon = True
        break

    # Stealth deactivation: if the ship will fire a weapon, deactivate stealth
    if will_fire_weapon:
        for m in ship.modules:
            if m.module_type.value in STEALTH_FIELD_TYPES and m.active:
                m.active = False
                m.stealth_cooldown_remaining = VOIDBORN_MODULE_PARAMS.get(
                    m.module_type.value, {}
                ).get("decloak_cooldown", 10)
                if ship.user_id is not None:
                    emit(
                        EventType.stealth_deactivated,
                        "Stealth field deactivated: weapon fire",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )

    for module in ship.modules:
        mt = module.module_type.value
        if mt not in WEAPON_TYPES:
            continue
        if not module.active:
            continue
        if module.id not in fired_module_ids:
            continue

        # Check weapon assignment
        wa = wa_by_module.get(module.id)
        if wa is None:
            continue
        if wa.target_ship_id not in locked_targets:
            continue

        target = ship_map.get(wa.target_ship_id)
        if target is None or target.is_destroyed:
            continue

        attacker_pos = (ship.pos_x, ship.pos_y, ship.pos_z)
        attacker_vel = (ship.vel_x, ship.vel_y, ship.vel_z)
        target_pos = (target.pos_x, target.pos_y, target.pos_z)
        target_vel = (target.vel_x, target.vel_y, target.vel_z)

        # --- TURRETS (including Solarion beam turrets) ---
        if mt in TURRET_TYPES:
            hit_chance = compute_final_hit_chance(
                attacker_pos, attacker_vel,
                target_pos, target_vel,
                module.tracking_speed,
                module.sig_resolution,
                target.effective_signature_radius(),
                module.optimal_range,
                module.falloff_range,
            )

            roll = random.random()
            if roll > hit_chance:
                # Miss
                if ship.user_id is not None:
                    emit(
                        EventType.weapon_miss,
                        f"{mt.replace('_', ' ').title()} missed Ship #{target.id} "
                        f"(chance: {hit_chance*100:.0f}%)",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )
                continue

            # Hit — apply sig ratio damage reduction
            applied = compute_turret_damage(
                module.damage_per_cycle,
                module.sig_resolution,
                target.effective_signature_radius(),
            )

            dmg_result = apply_damage(target, applied, module.damage_type or "kinetic")

            if ship.user_id is not None:
                layer = "shield" if dmg_result["shield_damage"] > 0 else "armor"
                emit(
                    EventType.weapon_hit,
                    f"{mt.replace('_', ' ').title()} hit Ship #{target.id} "
                    f"for {dmg_result['total_applied']:.0f} {module.damage_type} damage ({layer})",
                    user_id=ship.user_id,
                    ship_id=ship.id,
                )

            _emit_damage_events(target, dmg_result, ship.id, emit)

        # --- LEECH PROJECTORS ---
        elif mt in LEECH_PROJECTOR_TYPES:
            params = VOIDBORN_MODULE_PARAMS.get(mt, {})
            leech_range = params.get("range", 8_000)
            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(attacker_pos, target_pos)))

            if dist > leech_range:
                if ship.user_id is not None:
                    emit(
                        EventType.weapon_miss,
                        f"{mt.replace('_', ' ').title()}: target out of range "
                        f"({dist/1000:.1f} km)",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )
                continue

            # Check stacking limit: max 2 same-type leeches from same source on same target
            max_stacks = params.get("max_stacks_per_source", 2)
            leech_type_val = params.get("leech_type", mt)
            same_type_leeches = [
                lch for lch in active_leeches
                if lch.source_ship_id == ship.id
                and lch.target_ship_id == target.id
                and lch.leech_type == leech_type_val
            ]

            if len(same_type_leeches) >= max_stacks:
                # Refresh the oldest one's duration
                oldest = min(same_type_leeches, key=lambda lch: lch.created_at_tick)
                oldest.ticks_remaining = params.get("leech_duration", 30)
                oldest.created_at_tick = current_tick
            else:
                # Create new leech debuff
                new_leech = LeechDebuff(
                    source_ship_id=ship.id,
                    target_ship_id=target.id,
                    leech_type=params.get("leech_type", mt),
                    damage_per_tick=params.get("leech_damage_per_tick", 3),
                    damage_type=params.get("leech_damage_type", "kinetic"),
                    cap_drain_per_tick=params.get("leech_cap_drain_per_tick", 5),
                    ticks_remaining=params.get("leech_duration", 30),
                    created_at_tick=current_tick,
                )
                session.add(new_leech)
                active_leeches.append(new_leech)

            # Emit events
            if ship.user_id is not None:
                emit(
                    EventType.leech_applied,
                    f"{mt.replace('_', ' ').title()} applied to Ship #{target.id}",
                    user_id=ship.user_id,
                    ship_id=ship.id,
                )
            if target.user_id is not None:
                emit(
                    EventType.leech_incoming,
                    f"Leech debuff applied by Ship #{ship.id}",
                    user_id=target.user_id,
                    ship_id=target.id,
                )

        # --- MISSILES ---
        elif mt in MISSILE_TYPES:
            dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(attacker_pos, target_pos)))

            # Check if target is in range and missile can reach
            if dist > module.optimal_range:
                if ship.user_id is not None:
                    emit(
                        EventType.weapon_miss,
                        f"{mt.replace('_', ' ').title()}: target out of range "
                        f"({dist/1000:.1f} km)",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )
                continue

            # Check if target is moving away faster than missile
            direction = tuple((t - a) for a, t in zip(attacker_pos, target_pos))
            dir_mag = max(1e-6, math.sqrt(sum(d * d for d in direction)))
            dir_unit = tuple(d / dir_mag for d in direction)
            relative_vel = tuple(tv - av for av, tv in zip(attacker_vel, target_vel))
            radial_speed = sum(rv * du for rv, du in zip(relative_vel, dir_unit))

            if radial_speed > module.missile_speed:
                if ship.user_id is not None:
                    emit(
                        EventType.weapon_miss,
                        f"{mt.replace('_', ' ').title()}: target outrunning missile",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )
                continue

            # Calculate flight time
            flight_time = int(dist / max(1, module.missile_speed))
            if flight_time > module.missile_flight_time:
                if ship.user_id is not None:
                    emit(
                        EventType.weapon_miss,
                        f"{mt.replace('_', ' ').title()}: target too far for missile flight time",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )
                continue

            # Create pending missile (delayed damage)
            missile = PendingMissile(
                source_ship_id=ship.id,
                target_ship_id=target.id,
                damage=module.damage_per_cycle,
                damage_type=module.damage_type or "explosive",
                explosion_radius=module.explosion_radius,
                explosion_velocity=module.explosion_velocity,
                ticks_remaining=max(1, flight_time),
                source_user_id=ship.user_id or 0,
            )
            session.add(missile)
            pending_missiles_list.append(missile)


def _emit_damage_events(
    target: Spaceship,
    dmg_result: dict,
    attacker_id: int,
    emit,
) -> None:
    """Emit incoming_damage, shield_depleted, armor_critical events on the target."""
    if target.user_id is None:
        return

    if dmg_result["total_applied"] > 0:
        if dmg_result["shield_damage"] > 0:
            layer_info = f"shield: {target.shield_hp:.0f}/{target.max_shield_hp:.0f}"
        else:
            layer_info = f"armor: {target.armor_hp:.0f}/{target.max_armor_hp:.0f}"
        emit(
            EventType.incoming_damage,
            f"Hit by Ship #{attacker_id} for {dmg_result['total_applied']:.0f} damage "
            f"({layer_info})",
            user_id=target.user_id,
            ship_id=target.id,
        )

    if dmg_result["shields_broken"]:
        emit(
            EventType.shield_depleted,
            "Shields depleted! Armor taking damage.",
            user_id=target.user_id,
            ship_id=target.id,
        )

    if dmg_result["armor_critical"]:
        emit(
            EventType.armor_critical,
            f"Armor critical: {target.armor_hp:.0f}/{target.max_armor_hp:.0f} HP remaining",
            user_id=target.user_id,
            ship_id=target.id,
        )


def _process_repair_modules(
    ship: Spaceship,
    fired_module_ids: set[int],
) -> None:
    """Apply shield booster and armor repairer effects for modules that cycled."""
    for module in ship.modules:
        if not module.active:
            continue
        if module.id not in fired_module_ids:
            continue

        mt = module.module_type.value

        if mt in SHIELD_BOOSTER_TYPES or mt in VOIDBORN_SHIELD_BOOSTER_TYPES:
            ship.shield_hp = min(
                ship.max_shield_hp,
                ship.shield_hp + module.shield_repair_per_cycle,
            )
        elif mt in ARMOR_REPAIRER_TYPES or mt in SOLARION_ARMOR_REPAIRER_TYPES:
            ship.armor_hp = min(
                ship.max_armor_hp,
                ship.armor_hp + module.armor_repair_per_cycle,
            )


def _process_pending_missiles(
    pending_missiles: list[PendingMissile],
    ship_map: dict[int, Spaceship],
    current_tick: int,
    emit,
    session,
) -> None:
    """Advance missile flight timers and apply damage on arrival."""
    for missile in pending_missiles:
        missile.ticks_remaining -= 1
        if missile.ticks_remaining > 0:
            continue

        target = ship_map.get(missile.target_ship_id)
        if target is None or target.is_destroyed:
            # Target gone — missile wasted
            await_delete = missile
            session.delete(await_delete)
            continue

        # Apply missile damage with sig/speed reduction
        applied = compute_missile_damage(
            missile.damage,
            missile.explosion_radius,
            missile.explosion_velocity,
            target.effective_signature_radius(),
            target.speed(),
        )

        dmg_result = apply_damage(target, applied, missile.damage_type)

        # Emit events for the attacker
        source = ship_map.get(missile.source_ship_id)
        if source and source.user_id is not None:
            emit(
                EventType.weapon_hit,
                f"Missile hit Ship #{target.id} for {dmg_result['total_applied']:.0f} "
                f"{missile.damage_type} damage",
                user_id=source.user_id,
                ship_id=source.id,
            )

        _emit_damage_events(target, dmg_result, missile.source_ship_id, emit)

        session.delete(missile)


def _process_destruction(
    ships: list[Spaceship],
    ship_map: dict[int, Spaceship],
    current_tick: int,
    emit,
    session,
    active_leeches: list[LeechDebuff],
) -> None:
    """Handle ships whose armor has reached 0."""
    for ship in ships:
        if not ship.is_destroyed:
            continue
        if ship.armor_hp > 0:
            continue  # Not actually destroyed (shouldn't happen, but safe)

        # Emit destruction event to owner
        if ship.user_id is not None:
            emit(
                EventType.you_destroyed,
                f"Ship #{ship.id} ({ship.name}) destroyed! "
                f"Wreck at ({ship.pos_x:.0f}, {ship.pos_y:.0f}, {ship.pos_z:.0f})",
                user_id=ship.user_id,
                ship_id=ship.id,
            )

        # Notify attackers (anyone with a lock on this ship)
        for other in ships:
            if other.id == ship.id:
                continue
            for lock in other.target_locks:
                if lock.target_ship_id == ship.id and lock.status == LockStatus.locked:
                    if other.user_id is not None:
                        emit(
                            EventType.ship_destroyed,
                            f"Ship #{ship.id} ({ship.name}) destroyed!",
                            user_id=other.user_id,
                            ship_id=other.id,
                        )
                    lock.status = LockStatus.broken

        # Eject docked ships
        for other in ships:
            if other.docked_in_id == ship.id:
                other.docked_in_id = None
                other.pos_x = ship.pos_x
                other.pos_y = ship.pos_y
                other.pos_z = ship.pos_z
                other.vel_x = 0.0
                other.vel_y = 0.0
                other.vel_z = 0.0

        # Create wreck with 25% of cargo
        wreck = CelestialObject(
            name=f"Wreck of {ship.name}",
            object_type=CelestialType.wreck,
            pos_x=ship.pos_x,
            pos_y=ship.pos_y,
            pos_z=ship.pos_z,
            ore_remaining=ship.ore * 0.25,
            ore_initial=ship.ore * 0.25,
            created_tick=current_tick,
        )
        session.add(wreck)

        # Clean up leeches sourced from this destroyed ship
        leeches_to_remove = [
            lch for lch in active_leeches
            if lch.source_ship_id == ship.id
        ]
        for lch in leeches_to_remove:
            target = ship_map.get(lch.target_ship_id)
            if target and target.user_id is not None:
                emit(
                    EventType.leech_cleansed,
                    f"Leech debuff removed: source Ship #{ship.id} destroyed",
                    user_id=target.user_id,
                    ship_id=target.id,
                )
            session.delete(lch)
            active_leeches.remove(lch)


def _cleanup_expired_wrecks(
    celestial_objects: list[CelestialObject],
    current_tick: int,
    session,
) -> None:
    """Remove wrecks that have exceeded WRECK_LIFETIME_TICKS."""
    for obj in celestial_objects:
        if obj.object_type != CelestialType.wreck:
            continue
        if obj.created_tick is None:
            continue
        if current_tick - obj.created_tick >= WRECK_LIFETIME_TICKS:
            session.delete(obj)


# ---------------------------------------------------------------------------
# Phase 8: Match win condition check
# ---------------------------------------------------------------------------


async def _check_match_win_conditions(
    session,
    ships: list[Spaceship],
    ship_map: dict[int, Spaceship],
    current_tick: int,
    emit,
) -> None:
    """
    After destruction processing, check if any match mothership was destroyed.
    If so, end the match with the opposing team as winner.

    Also checks for mothership HP thresholds and emits warning events.
    """
    active_matches_result = await session.exec(
        select(Match).where(Match.status == MatchStatus.active.value)
    )
    active_matches = active_matches_result.all()

    for match in active_matches:
        t1_ms = ship_map.get(match.team1_mothership_id)
        t2_ms = ship_map.get(match.team2_mothership_id)

        winner_team_id = None

        if t1_ms and t1_ms.is_destroyed:
            winner_team_id = match.team2_id
        elif t2_ms and t2_ms.is_destroyed:
            winner_team_id = match.team1_id

        if winner_team_id is not None:
            match.status = MatchStatus.completed.value
            match.winner_team_id = winner_team_id
            match.ended_at_tick = current_tick

            # Emit match_ended events to all players in both teams (before cleanup clears team_id)
            for tid in [match.team1_id, match.team2_id]:
                if tid is None:
                    continue
                user_result = await session.exec(
                    select(User.id).where(User.team_id == tid)
                )
                for uid in user_result.all():
                    emit(
                        EventType.match_ended,
                        f"Match '{match.name}' ended! Mothership destroyed.",
                        user_id=uid,
                    )

            # Cleanup so players can join new matches
            await cleanup_match_assignments(session, match)
            continue

        # Mothership warning events (under attack / critical) with cooldown
        for ms, team_id in [(t1_ms, match.team1_id), (t2_ms, match.team2_id)]:
            if ms is None or ms.is_destroyed or team_id is None:
                continue
            total_hp = ms.max_shield_hp + ms.max_armor_hp
            current_hp = ms.shield_hp + ms.armor_hp
            if total_hp <= 0:
                continue
            hp_pct = current_hp / total_hp

            warning_type = None
            if hp_pct < 0.25:
                warning_type = EventType.mothership_critical
            elif hp_pct < 0.75:
                warning_type = EventType.mothership_under_attack

            if warning_type is None:
                continue

            # Cooldown: only emit every _MOTHERSHIP_WARNING_COOLDOWN ticks
            cooldown_key = (match.id, ms.id)
            last_tick = _mothership_warning_last_tick.get(cooldown_key, -999)
            if current_tick - last_tick < _MOTHERSHIP_WARNING_COOLDOWN:
                continue
            _mothership_warning_last_tick[cooldown_key] = current_tick

            prefix = "CRITICAL" if warning_type == EventType.mothership_critical else "WARNING"
            user_result = await session.exec(
                select(User.id).where(User.team_id == team_id)
            )
            for uid in user_result.all():
                emit(
                    warning_type,
                    f"{prefix}: Mothership '{ms.name}' at {hp_pct*100:.0f}% HP!",
                    user_id=uid,
                    ship_id=ms.id,
                )


# ---------------------------------------------------------------------------
# Phase 7: Faction mechanic helpers
# ---------------------------------------------------------------------------


def _process_solar_lance(
    ship: Spaceship,
    ship_map: dict[int, Spaceship],
    current_tick: int,
    emit,
) -> None:
    """Process Solar Lance charging, firing, and cooldown for a single ship."""
    for module in ship.modules:
        if module.module_type.value != "solar_lance":
            continue
        if not module.active:
            continue

        lance_params = SOLARION_MODULE_PARAMS.get("solar_lance", {})

        if module.lance_state == "charging":
            module.lance_charge_remaining -= 1

            # Emit progress event every 10 ticks
            if module.lance_charge_remaining > 0 and module.lance_charge_remaining % 10 == 0:
                if ship.user_id is not None:
                    emit(
                        EventType.solar_lance_charging,
                        f"Solar Lance charging: {module.lance_charge_remaining} ticks remaining",
                        user_id=ship.user_id,
                        ship_id=ship.id,
                    )

            if module.lance_charge_remaining <= 0:
                # Charge complete — attempt to fire
                target = ship_map.get(module.lance_target_ship_id) if module.lance_target_ship_id else None
                fire_cap_cost = lance_params.get("cap_cost", 10_000)
                can_fire = True
                reason = ""

                # Check target exists and is not destroyed
                if target is None or target.is_destroyed:
                    can_fire = False
                    reason = "target lost"

                # Check lock still held
                if can_fire:
                    has_lock = any(
                        lock.target_ship_id == module.lance_target_ship_id
                        and lock.status == LockStatus.locked
                        for lock in ship.target_locks
                    )
                    if not has_lock:
                        can_fire = False
                        reason = "lock lost"

                # Check distance
                if can_fire and target is not None:
                    dx = target.pos_x - ship.pos_x
                    dy = target.pos_y - ship.pos_y
                    dz = target.pos_z - ship.pos_z
                    dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                    max_range = lance_params.get("range", 100_000)
                    if dist > max_range:
                        can_fire = False
                        reason = f"out of range ({dist/1000:.1f} km)"

                # Check angular velocity
                if can_fire and target is not None:
                    attacker_pos = (ship.pos_x, ship.pos_y, ship.pos_z)
                    attacker_vel = (ship.vel_x, ship.vel_y, ship.vel_z)
                    target_pos = (target.pos_x, target.pos_y, target.pos_z)
                    target_vel = (target.vel_x, target.vel_y, target.vel_z)
                    transversal = compute_transversal_velocity(
                        attacker_pos, attacker_vel, target_pos, target_vel
                    )
                    distance = math.sqrt(
                        (target.pos_x - ship.pos_x) ** 2
                        + (target.pos_y - ship.pos_y) ** 2
                        + (target.pos_z - ship.pos_z) ** 2
                    )
                    angular_vel = compute_angular_velocity(transversal, distance)
                    max_angular = lance_params.get("max_angular_velocity", 0.001)
                    if angular_vel > max_angular:
                        can_fire = False
                        reason = "target angular velocity too high"

                # Check capacitor
                if can_fire and ship.capacitor < fire_cap_cost:
                    can_fire = False
                    reason = "insufficient capacitor"

                # Fire or fizzle
                if can_fire and target is not None:
                    # Consume cap
                    ship.capacitor = max(0, ship.capacitor - fire_cap_cost)
                    # Apply massive damage
                    lance_damage = lance_params.get("damage", 50_000)
                    lance_dmg_type = lance_params.get("damage_type", "thermal")
                    apply_damage(target, lance_damage, lance_dmg_type)
                    if ship.user_id is not None:
                        emit(
                            EventType.solar_lance_fired,
                            f"Solar Lance fired on Ship #{target.id} "
                            f"for {lance_damage} {lance_dmg_type} damage!",
                            user_id=ship.user_id,
                            ship_id=ship.id,
                        )
                    if target.user_id is not None:
                        emit(
                            EventType.incoming_damage,
                            f"Solar Lance hit by Ship #{ship.id} "
                            f"for {lance_damage} {lance_dmg_type} damage!",
                            user_id=target.user_id,
                            ship_id=target.id,
                        )
                else:
                    # Fizzle — still consume cap (or whatever's available)
                    cap_consumed = min(ship.capacitor, fire_cap_cost)
                    ship.capacitor = max(0, ship.capacitor - cap_consumed)
                    if ship.user_id is not None:
                        emit(
                            EventType.solar_lance_fizzled,
                            f"Solar Lance fizzled: {reason}",
                            user_id=ship.user_id,
                            ship_id=ship.id,
                        )

                # Enter cooldown
                cooldown = lance_params.get("cooldown", 300)
                module.lance_state = "cooldown"
                module.lance_cooldown_remaining = cooldown
                module.lance_target_ship_id = None

        elif module.lance_state == "cooldown":
            module.lance_cooldown_remaining -= 1
            if module.lance_cooldown_remaining <= 0:
                module.lance_state = "idle"
                module.active = False


def _process_leeches(
    active_leeches: list[LeechDebuff],
    ship_map: dict[int, Spaceship],
    current_tick: int,
    session,
    emit,
) -> None:
    """Tick all active leech debuffs: apply damage, drain cap, expire."""
    leeches_to_remove: list[LeechDebuff] = []

    for leech in active_leeches:
        target = ship_map.get(leech.target_ship_id)

        # Skip if target destroyed — mark for deletion
        if target is None or target.is_destroyed:
            leeches_to_remove.append(leech)
            continue

        # Compute stacking diminishment: sort same-type leeches on same target
        same_type_on_target = sorted(
            [lch for lch in active_leeches if lch.target_ship_id == leech.target_ship_id and lch.leech_type == leech.leech_type],
            key=lambda lch: lch.created_at_tick,
        )
        rank = next((i for i, lch in enumerate(same_type_on_target) if lch is leech), 0)
        # First 5 at full power, then diminishing
        effectiveness = 0.85 ** max(0, rank - 4)

        # Apply effective damage
        effective_damage = leech.damage_per_tick * effectiveness
        apply_damage(target, effective_damage, leech.damage_type)

        # Drain cap
        effective_drain = leech.cap_drain_per_tick * effectiveness
        target.capacitor = max(0, target.capacitor - effective_drain)

        # Decrement ticks remaining
        leech.ticks_remaining -= 1
        if leech.ticks_remaining <= 0:
            leeches_to_remove.append(leech)
            if target.user_id is not None:
                emit(
                    EventType.leech_expired,
                    f"Leech debuff ({leech.leech_type.replace('_', ' ')}) expired",
                    user_id=target.user_id,
                    ship_id=target.id,
                )

        # Periodic summary every 10 ticks
        if current_tick % 10 == 0 and target.user_id is not None and leech.ticks_remaining > 0:
            emit(
                EventType.leech_tick,
                f"Leech debuff active: {effective_damage:.1f} {leech.damage_type} dmg/tick, "
                f"{effective_drain:.1f} cap drain/tick, {leech.ticks_remaining} ticks left",
                user_id=target.user_id,
                ship_id=target.id,
            )

    # Remove expired/invalid leeches
    for leech in leeches_to_remove:
        session.delete(leech)
        if leech in active_leeches:
            active_leeches.remove(leech)


def _process_shield_purge(
    ship: Spaceship,
    fired_module_ids: set[int],
    active_leeches: list[LeechDebuff],
    emit,
    session,
) -> None:
    """Process shield purge module: remove all leeches on this ship at a shield HP cost."""
    for module in ship.modules:
        if module.module_type.value != "shield_purge":
            continue
        if not module.active:
            continue
        if module.id not in fired_module_ids:
            continue

        # Find leeches targeting this ship
        leeches_on_ship = [lch for lch in active_leeches if lch.target_ship_id == ship.id]
        if not leeches_on_ship:
            continue

        # Cost: 10% of current shield HP
        shield_cost = ship.shield_hp * SHARED_MODULE_PARAMS.get("shield_purge", {}).get("shield_hp_cost_percent", 0.10)
        ship.shield_hp = max(0, ship.shield_hp - shield_cost)

        # Remove all leeches
        for lch in leeches_on_ship:
            session.delete(lch)
            if lch in active_leeches:
                active_leeches.remove(lch)

        if ship.user_id is not None:
            emit(
                EventType.leech_cleansed,
                f"Shield Purge activated: {len(leeches_on_ship)} leech debuff(s) removed "
                f"(cost: {shield_cost:.0f} shield HP)",
                user_id=ship.user_id,
                ship_id=ship.id,
            )


def _process_bio_repair_swarm(
    ship: Spaceship,
    all_ships: list[Spaceship],
    fired_module_ids: set[int],
    current_tick: int,
    emit,
) -> None:
    """Process Bio-Repair Swarm: AoE armor repair for friendly ships in range."""
    for module in ship.modules:
        if module.module_type.value != "bio_repair_swarm":
            continue
        if not module.active:
            continue
        if module.id not in fired_module_ids:
            continue

        params = VOIDBORN_MODULE_PARAMS.get("bio_repair_swarm", {})
        repair_range = params.get("range", 30_000)
        repair_percent = params.get("repair_percent_per_tick", 0.02)
        repaired_count = 0

        for other in all_ships:
            if other.is_destroyed or other.is_docked():
                continue
            if other.id == ship.id:
                continue
            # Only repair ships on the same team
            if ship.team_id is None or other.team_id != ship.team_id:
                continue

            # Check range
            dx = other.pos_x - ship.pos_x
            dy = other.pos_y - ship.pos_y
            dz = other.pos_z - ship.pos_z
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist > repair_range:
                continue

            # Repair 2% of max armor
            repair_amount = other.max_armor_hp * repair_percent
            if other.armor_hp < other.max_armor_hp:
                other.armor_hp = min(other.max_armor_hp, other.armor_hp + repair_amount)
                repaired_count += 1

        if repaired_count > 0 and ship.user_id is not None:
            emit(
                EventType.bio_repair_swarm_active,
                f"Bio-Repair Swarm repaired {repaired_count} friendly ship(s)",
                user_id=ship.user_id,
                ship_id=ship.id,
            )
