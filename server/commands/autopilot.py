"""Command handlers for autopilot: assume_control, release_to_autopilot, set_autopilot_profile."""

from __future__ import annotations

from sqlmodel import select

from server.commands import CommandRejected, TickContext, get_payload, register_handler
from server.models import (
    AutopilotProfile,
    Command,
    DEFAULT_AUTOPILOT_PROFILES,
    MovementOrder,
    OrderStatus,
)

VALID_PROFILES = {p.value for p in AutopilotProfile}


@register_handler("assume_control")
async def handle_assume_control(ctx: TickContext, cmd: Command) -> None:
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    if ship.is_destroyed:
        raise CommandRejected("Ship is destroyed")
    if ship.autopilot_mode == "off":
        raise CommandRejected("Ship is already under player control")

    ship.autopilot_mode = "off"

    # Cancel active orders
    orders_result = await ctx.session.exec(
        select(MovementOrder).where(
            MovementOrder.ship_id == ship.id,
            MovementOrder.status == OrderStatus.active,
        )
    )
    for order in orders_result.all():
        order.status = OrderStatus.cancelled


@register_handler("release_to_autopilot")
async def handle_release_to_autopilot(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    profile = payload.get("profile")

    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    if ship.is_destroyed:
        raise CommandRejected("Ship is destroyed")
    if ship.autopilot_mode != "off":
        raise CommandRejected(f"Ship is already autopiloted (mode='{ship.autopilot_mode}')")

    if profile is not None:
        if profile not in VALID_PROFILES:
            raise CommandRejected(f"Invalid profile '{profile}'. Valid: {sorted(VALID_PROFILES)}")
        ship.autopilot_profile = profile
    elif ship.autopilot_profile is None:
        ship.autopilot_profile = DEFAULT_AUTOPILOT_PROFILES.get(
            ship.ship_class.value, "mining"
        )

    ship.autopilot_mode = "active"


@register_handler("set_autopilot_profile")
async def handle_set_autopilot_profile(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    profile = payload.get("profile")

    if not profile:
        raise CommandRejected("profile is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    if ship.is_destroyed:
        raise CommandRejected("Ship is destroyed")
    if ship.autopilot_mode != "active":
        raise CommandRejected("Ship must be in autopilot mode to change profile")
    if profile not in VALID_PROFILES:
        raise CommandRejected(f"Invalid profile '{profile}'. Valid: {sorted(VALID_PROFILES)}")

    ship.autopilot_profile = profile
