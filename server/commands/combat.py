"""Command handlers for combat: lock, unlock, assign weapon, fire all, hold fire."""

from __future__ import annotations

import math

from sqlmodel import select

from server.combat import compute_lock_time
from server.commands import CommandRejected, TickContext, get_payload, register_handler
from server.models import (
    Command,
    LockStatus,
    ModuleType,
    STEALTH_FIELD_TYPES,
    TargetLock,
    VOIDBORN_MODULE_PARAMS,
    WEAPON_TYPES,
    WeaponAssignment,
    get_max_locks,
    get_ship_classes,
)


@register_handler("lock_target")
async def handle_lock_target(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    target_ship_id = payload.get("target_ship_id")
    if target_ship_id is None:
        raise CommandRejected("target_ship_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    if ship.is_destroyed:
        raise CommandRejected("Ship is destroyed")
    if ship.is_docked():
        raise CommandRejected("Ship is currently docked")

    # Can't lock yourself
    if target_ship_id == cmd.ship_id:
        raise CommandRejected("Cannot lock your own ship")

    # Check max locks
    active_locks = [
        l for l in (ship.target_locks if hasattr(ship, 'target_locks') and ship.target_locks else [])
        if l.status in (LockStatus.locking, LockStatus.locked)
    ]
    max_locks = get_max_locks(ship.faction if hasattr(ship, 'faction') else None, ship.ship_class.value)
    if len(active_locks) >= max_locks:
        raise CommandRejected(f"Maximum target locks reached ({max_locks})")

    # Already locking this target?
    for l in active_locks:
        if l.target_ship_id == target_ship_id:
            raise CommandRejected(f"Already locking/locked Ship #{target_ship_id}")

    # Target must exist
    target = ctx.find_any_ship(target_ship_id)
    if target.is_destroyed:
        raise CommandRejected("Target ship is destroyed")

    # Range check
    has_scanner = any(m.module_type == ModuleType.scanner for m in ship.modules)
    lock_range = 200_000.0 if has_scanner else 1_000.0
    dx = ship.pos_x - target.pos_x
    dy = ship.pos_y - target.pos_y
    dz = ship.pos_z - target.pos_z
    distance = math.sqrt(dx * dx + dy * dy + dz * dz)
    if distance > lock_range:
        raise CommandRejected(
            f"Target out of range: {distance/1000:.1f} km (max {lock_range/1000:.0f} km)"
        )

    # Match isolation
    if ship.match_id is not None or target.match_id is not None:
        if ship.match_id != target.match_id:
            raise CommandRejected("Cannot lock targets outside your match")

    # Deactivate stealth fields (decloak)
    for m in ship.modules:
        if m.module_type.value in STEALTH_FIELD_TYPES and m.active:
            m.active = False
            m.stealth_cooldown_remaining = VOIDBORN_MODULE_PARAMS.get(
                m.module_type.value, {}
            ).get("decloak_cooldown", 10)

    # Compute lock time
    consts = get_ship_classes(ship.faction if hasattr(ship, 'faction') else None)[ship.ship_class.value]
    lock_time = compute_lock_time(
        ship.scan_resolution,
        target.effective_signature_radius(),
        consts["base_lock_time"],
    )

    lock = TargetLock(
        ship_id=ship.id,
        target_ship_id=target_ship_id,
        status=LockStatus.locking,
        ticks_remaining=lock_time,
    )
    ctx.session.add(lock)
    await ctx.session.flush()

    if hasattr(ship, 'target_locks') and ship.target_locks is not None:
        ship.target_locks.append(lock)


@register_handler("unlock_target")
async def handle_unlock_target(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    target_ship_id = payload.get("target_ship_id")
    if target_ship_id is None:
        raise CommandRejected("target_ship_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    lock = next(
        (l for l in (ship.target_locks if hasattr(ship, 'target_locks') and ship.target_locks else [])
         if l.target_ship_id == target_ship_id
         and l.status in (LockStatus.locking, LockStatus.locked)),
        None,
    )
    if lock is None:
        raise CommandRejected("No active lock on that target")

    lock.status = LockStatus.broken

    # Remove weapon assignments for this target
    wa_result = await ctx.session.exec(
        select(WeaponAssignment).where(
            WeaponAssignment.ship_id == ship.id,
            WeaponAssignment.target_ship_id == target_ship_id,
        )
    )
    for wa in wa_result.all():
        await ctx.session.delete(wa)
        if wa in ctx.weapon_assignments:
            ctx.weapon_assignments.remove(wa)


@register_handler("assign_weapon")
async def handle_assign_weapon(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    module_id = payload.get("module_id")
    target_ship_id = payload.get("target_ship_id")
    if module_id is None:
        raise CommandRejected("module_id is required")
    if target_ship_id is None:
        raise CommandRejected("target_ship_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)
    if ship.is_docked():
        raise CommandRejected("Ship is currently docked")

    module = next((m for m in ship.modules if m.id == module_id), None)
    if module is None:
        raise CommandRejected("Module not found on this ship")
    if module.module_type.value not in WEAPON_TYPES:
        raise CommandRejected("Module is not a weapon")

    # Verify target is locked
    locked = any(
        l.target_ship_id == target_ship_id and l.status == LockStatus.locked
        for l in (ship.target_locks if hasattr(ship, 'target_locks') and ship.target_locks else [])
    )
    if not locked:
        raise CommandRejected(f"Ship #{target_ship_id} is not locked")

    # Upsert weapon assignment
    existing = next((wa for wa in ctx.weapon_assignments if wa.module_id == module_id), None)
    if existing:
        existing.target_ship_id = target_ship_id
    else:
        wa = WeaponAssignment(
            module_id=module_id,
            ship_id=ship.id,
            target_ship_id=target_ship_id,
        )
        ctx.session.add(wa)
        await ctx.session.flush()
        ctx.weapon_assignments.append(wa)

    module.active = True


@register_handler("fire_all")
async def handle_fire_all(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    target_ship_id = payload.get("target_ship_id")
    if target_ship_id is None:
        raise CommandRejected("target_ship_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)
    if ship.is_docked():
        raise CommandRejected("Ship is currently docked")

    # Verify target is locked
    locked = any(
        l.target_ship_id == target_ship_id and l.status == LockStatus.locked
        for l in (ship.target_locks if hasattr(ship, 'target_locks') and ship.target_locks else [])
    )
    if not locked:
        raise CommandRejected(f"Ship #{target_ship_id} is not locked")

    for module in ship.modules:
        if module.module_type.value not in WEAPON_TYPES:
            continue

        existing = next((wa for wa in ctx.weapon_assignments if wa.module_id == module.id), None)
        if existing:
            existing.target_ship_id = target_ship_id
        else:
            wa = WeaponAssignment(
                module_id=module.id,
                ship_id=ship.id,
                target_ship_id=target_ship_id,
            )
            ctx.session.add(wa)
            await ctx.session.flush()
            ctx.weapon_assignments.append(wa)

        module.active = True


@register_handler("hold_fire")
async def handle_hold_fire(ctx: TickContext, cmd: Command) -> None:
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    for module in ship.modules:
        if module.module_type.value in WEAPON_TYPES:
            module.active = False

    # Clear weapon assignments
    to_remove = [wa for wa in ctx.weapon_assignments if wa.ship_id == ship.id]
    for wa in to_remove:
        await ctx.session.delete(wa)
        ctx.weapon_assignments.remove(wa)
