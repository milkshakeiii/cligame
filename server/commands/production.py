"""Command handlers for production: build."""

from __future__ import annotations

from sqlmodel import select, or_

from server.commands import CommandRejected, TickContext, get_payload, register_handler
from server.models import (
    BuildStatus,
    Command,
    ModuleType,
    ResearchProgress,
    SHIP_REQUIRED_TECH,
    ShipClass,
)
from server.production import can_factory_build, start_build
from server.research import get_completed_tech_ids, get_tech_name, is_ship_unlocked


@register_handler("build")
async def handle_build(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    blueprint_str = payload.get("blueprint")
    factory_module_id = payload.get("factory_module_id")

    if not blueprint_str:
        raise CommandRejected("blueprint is required")
    try:
        blueprint = ShipClass(blueprint_str)
    except ValueError:
        raise CommandRejected(f"Invalid blueprint: {blueprint_str}")

    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    # Research gating
    from server.models import User
    user_result = await ctx.session.exec(select(User).where(User.id == cmd.user_id))
    user = user_result.first()

    research_conditions = [ResearchProgress.user_id == cmd.user_id]
    if user.team_id is not None:
        research_conditions.append(ResearchProgress.team_id == user.team_id)
    rp_result = await ctx.session.exec(
        select(ResearchProgress).where(or_(*research_conditions))
    )
    completed_techs = get_completed_tech_ids(rp_result.all())
    if not is_ship_unlocked(blueprint_str, completed_techs):
        tech_id = SHIP_REQUIRED_TECH.get(blueprint_str, "?")
        raise CommandRejected(f"Research required: {get_tech_name(tech_id)} ({tech_id})")

    # Find factory module
    factory_modules = [m for m in ship.modules if m.module_type == ModuleType.factory]
    if not factory_modules:
        raise CommandRejected("Ship has no factory module installed")

    if factory_module_id is not None:
        factory = next((m for m in factory_modules if m.id == factory_module_id), None)
        if factory is None:
            raise CommandRejected("Factory module not found on this ship")
    else:
        factory = None
        for m in factory_modules:
            ok, _ = can_factory_build(m, blueprint)
            if ok:
                factory = m
                break
        if factory is None:
            raise CommandRejected(f"No factory module capable of building {blueprint_str}")

    # Check factory not already building
    active_for_factory = [
        o for o in (ship.build_orders if hasattr(ship, 'build_orders') and ship.build_orders else [])
        if o.factory_module_id == factory.id
        and o.status in (BuildStatus.building, BuildStatus.paused)
    ]
    if active_for_factory:
        raise CommandRejected(
            f"Factory module #{factory.id} is already building "
            f"{active_for_factory[0].blueprint.value}"
        )

    try:
        order = start_build(ship, factory, blueprint, faction=ship.faction if hasattr(ship, 'faction') else None)
    except ValueError as exc:
        raise CommandRejected(str(exc))

    ctx.session.add(order)
    await ctx.session.flush()

    if hasattr(ship, 'build_orders') and ship.build_orders is not None:
        ship.build_orders.append(order)
