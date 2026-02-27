"""Command handlers for resources: transfer_ore, scan."""

from __future__ import annotations

from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.commands import CommandRejected, TickContext, get_payload, register_handler
from server.mining import tick_ore_transfer
from server.models import (
    Command,
    EventType,
    ModuleType,
    Spaceship,
)


@register_handler("transfer_ore")
async def handle_transfer_ore(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    target_ship_id = payload.get("target_ship_id")
    if target_ship_id is None:
        raise CommandRejected("target_ship_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")
    if cmd.ship_id == target_ship_id:
        raise CommandRejected("Cannot transfer ore to the same ship")

    source = ctx.find_ship(cmd.ship_id, cmd.user_id)
    target = ctx.find_any_ship(target_ship_id)

    # Run transfer loop
    total_transferred = 0.0
    while True:
        result = tick_ore_transfer(source, target)
        if result["error"]:
            if total_transferred == 0:
                raise CommandRejected(result["error"])
            break
        total_transferred += result["transferred"]
        if result["complete"] or result["transferred"] == 0:
            break

    if total_transferred > 0:
        ctx.emit(
            EventType.transfer_complete,
            f"Transferred {total_transferred:.0f} ore to ship #{target.id} ({target.name})",
            user_id=cmd.user_id,
            ship_id=source.id,
        )


@register_handler("scan")
async def handle_scan(ctx: TickContext, cmd: Command) -> None:
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)
    if ship.is_docked():
        raise CommandRejected("Ship is currently docked")

    # Find active scanner
    scanner = next(
        (m for m in ship.modules if m.module_type == ModuleType.scanner and m.active),
        None,
    )
    if scanner is None:
        any_scanner = next(
            (m for m in ship.modules if m.module_type == ModuleType.scanner), None
        )
        if any_scanner is None:
            raise CommandRejected("Ship has no scanner module installed")
        raise CommandRejected("Scanner module is not active — activate it first")

    if ship.capacitor < scanner.capacitor_per_cycle:
        raise CommandRejected(
            f"Insufficient capacitor: need {scanner.capacitor_per_cycle:.0f}, "
            f"have {ship.capacitor:.0f}"
        )

    # Drain cap and trigger scan on next tick's scanning phase
    ship.capacitor -= scanner.capacitor_per_cycle
    scanner.ticks_until_cycle = 0

    ctx.emit(
        EventType.scan_complete,
        "Active scan triggered — results will appear next tick",
        user_id=cmd.user_id,
        ship_id=ship.id,
    )
