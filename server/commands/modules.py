"""Command handlers for module activation/deactivation."""

from __future__ import annotations

from sqlmodel import select

from server.commands import CommandRejected, TickContext, get_payload, register_handler
from server.models import (
    Command,
    LockStatus,
    MODULE_REGISTRY,
    STEALTH_FIELD_TYPES,
    TargetLock,
)


@register_handler("activate_module")
async def handle_activate_module(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    module_id = payload.get("module_id")
    if module_id is None:
        raise CommandRejected("module_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)
    if ship.is_docked():
        raise CommandRejected("Ship is currently docked")

    module = next((m for m in ship.modules if m.id == module_id), None)
    if module is None:
        raise CommandRejected("Module not found on this ship")

    # Stealth cooldown check
    if module.module_type.value in STEALTH_FIELD_TYPES:
        if module.stealth_cooldown_remaining > 0:
            raise CommandRejected(
                f"Stealth field on cooldown ({module.stealth_cooldown_remaining} ticks remaining)"
            )

    # Solar lance requires target
    if module.module_type.value == "solar_lance":
        target_id = payload.get("target_ship_id")
        if target_id is None:
            raise CommandRejected("Solar lance requires a target_ship_id")
        # Verify target is locked
        lock_result = await ctx.session.exec(
            select(TargetLock).where(
                TargetLock.ship_id == ship.id,
                TargetLock.target_ship_id == target_id,
                TargetLock.status == LockStatus.locked,
            )
        )
        if lock_result.first() is None:
            raise CommandRejected(f"Ship #{target_id} is not locked — lock target first")
        module.lance_state = "charging"
        module.lance_charge_remaining = MODULE_REGISTRY["solar_lance"].lance_charge_time
        module.lance_target_ship_id = target_id

    module.active = True
    if module.cycle_time > 0:
        module.ticks_until_cycle = module.cycle_time


@register_handler("deactivate_module")
async def handle_deactivate_module(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    module_id = payload.get("module_id")
    if module_id is None:
        raise CommandRejected("module_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    module = next((m for m in ship.modules if m.id == module_id), None)
    if module is None:
        raise CommandRejected("Module not found on this ship")

    module.active = False

    # Clean up weapon assignment if this is a weapon module
    from server.models import WEAPON_TYPES, WeaponAssignment
    if module.module_type.value in WEAPON_TYPES:
        wa = next((w for w in ctx.weapon_assignments if w.module_id == module.id), None)
        if wa:
            await ctx.session.delete(wa)
            ctx.weapon_assignments.remove(wa)

    # Clear solar lance state
    if module.module_type.value == "solar_lance":
        module.lance_state = None
        module.lance_charge_remaining = 0
        module.lance_target_ship_id = None
