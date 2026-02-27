"""Command handlers for research: start_research, cancel_research."""

from __future__ import annotations

from sqlmodel import select

from server.commands import CommandRejected, TickContext, get_payload, register_handler
from server.models import (
    Command,
    ModuleType,
    ResearchProgress,
    Team,
)
from server.research import start_research


@register_handler("start_research")
async def handle_start_research(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    tech_id = payload.get("tech_id")
    module_id = payload.get("module_id")

    if not tech_id:
        raise CommandRejected("tech_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    if ship.is_destroyed:
        raise CommandRejected("Ship is destroyed")

    # Find research modules
    research_modules = [
        m for m in ship.modules if m.module_type == ModuleType.research_module
    ]
    if not research_modules:
        raise CommandRejected("Ship has no research module installed")

    if module_id is not None:
        module = next((m for m in research_modules if m.id == module_id), None)
        if module is None:
            raise CommandRejected("Research module not found on this ship")
    else:
        # Find first available
        busy_result = await ctx.session.exec(
            select(ResearchProgress).where(
                ResearchProgress.ship_id == ship.id,
                ResearchProgress.status == "researching",
            )
        )
        busy_module_ids = {rp.module_id for rp in busy_result.all()}

        module = next(
            (m for m in research_modules if m.id not in busy_module_ids),
            None,
        )
        if module is None:
            raise CommandRejected("All research modules are busy")

    # Faction lookup
    from server.models import User
    user_result = await ctx.session.exec(select(User).where(User.id == cmd.user_id))
    user = user_result.first()

    user_faction = None
    if user.team_id is not None:
        team_result = await ctx.session.exec(select(Team).where(Team.id == user.team_id))
        team = team_result.first()
        if team:
            user_faction = team.faction

    try:
        rp = await start_research(
            ctx.session, ship, module, tech_id, cmd.user_id,
            team_id=user.team_id,
            faction=user_faction,
        )
    except ValueError as exc:
        raise CommandRejected(str(exc))


@register_handler("cancel_research")
async def handle_cancel_research(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    module_id = payload.get("module_id")

    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    result = await ctx.session.exec(
        select(ResearchProgress).where(
            ResearchProgress.ship_id == ship.id,
            ResearchProgress.status.in_(["researching", "paused"]),
        )
    )
    active = result.all()

    if module_id is not None:
        active = [r for r in active if r.module_id == module_id]

    if not active:
        raise CommandRejected("No active research to cancel")

    for rp in active:
        rp.status = "cancelled"
        mod = next((m for m in ship.modules if m.id == rp.module_id), None)
        if mod:
            mod.active = False
