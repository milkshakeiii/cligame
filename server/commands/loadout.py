"""Command handlers for loadout: claim_ship, reship."""

from __future__ import annotations

from sqlmodel import select

from server.commands import CommandRejected, TickContext, get_payload, register_handler
from server.models import (
    Command,
    EventType,
    HULL_POINT_COSTS,
    MODULE_FIXED_VOLUMES,
    MODULE_POINT_COSTS,
    ModuleType,
    ShipClass,
    ShipModule,
    Spaceship,
    User,
    create_default_ship,
    make_module,
    recalculate_max_armor,
    recalculate_max_capacitor,
    recalculate_max_shield,
    SOLARION_EXCLUSIVE_MODULES,
    VOIDBORN_EXCLUSIVE_MODULES,
)
from server.research import get_completed_tech_ids, is_module_unlocked, ResearchProgress


@register_handler("claim_ship")
async def handle_claim_ship(ctx: TickContext, cmd: Command) -> None:
    """Claim an unclaimed docked hull, fit modules, spend points, launch."""
    payload = get_payload(cmd)
    modules_list = payload.get("modules", [])

    # Fetch user early — needed for both auto-create and existing-hull paths
    user_result = await ctx.session.exec(select(User).where(User.id == cmd.user_id))
    user = user_result.first()
    if user is None:
        raise CommandRejected("User not found")

    if cmd.ship_id is None:
        # --- Auto-create path: ship_class in payload ---
        ship_class_str = payload.get("ship_class")
        if not ship_class_str:
            raise CommandRejected("ship_id or ship_class is required")

        # Validate it's a free hull class
        hull_cost = HULL_POINT_COSTS.get(ship_class_str)
        if hull_cost is None:
            raise CommandRejected(f"Unknown ship class: {ship_class_str}")
        if hull_cost != 0:
            raise CommandRejected(
                f"Only free hull classes can be auto-created ('{ship_class_str}' costs {hull_cost} pts)"
            )

        # Must be on a team
        if user.team_id is None:
            raise CommandRejected("You must be on a team to auto-create a ship")

        # Find team's mothership with a docking bay
        from sqlalchemy.orm import selectinload
        ms_result = await ctx.session.exec(
            select(Spaceship)
            .where(
                Spaceship.team_id == user.team_id,
                Spaceship.ship_class == ShipClass.mothership,
                Spaceship.is_destroyed == False,  # noqa: E712
            )
            .options(selectinload(Spaceship.modules), selectinload(Spaceship.team))
        )
        mothership = None
        for ms in ms_result.all():
            if any(m.module_type == ModuleType.docking_bay for m in ms.modules):
                mothership = ms
                break
        if mothership is None:
            raise CommandRejected("No team mothership with docking bay found")

        # Create the hull
        try:
            sc = ShipClass(ship_class_str)
        except ValueError:
            raise CommandRejected(f"Unknown ship class: {ship_class_str}")

        faction = None
        if mothership.team is not None:
            faction = mothership.team.faction

        hull = create_default_ship(
            name=f"{ship_class_str}",
            ship_class=sc,
            user_id=cmd.user_id,
            pos_x=mothership.pos_x,
            pos_y=mothership.pos_y,
            pos_z=mothership.pos_z,
            team_id=user.team_id,
            faction=faction,
        )
        hull.match_id = mothership.match_id
        hull.docked_in_id = mothership.id
        hull.modules = []  # prevent lazy load on relationship
        ctx.session.add(hull)
        await ctx.session.flush()
    else:
        # --- Existing hull path ---
        hull = ctx.ship_map.get(cmd.ship_id)
        if hull is None:
            raise CommandRejected(f"Ship #{cmd.ship_id} not found")
        if hull.claimed_by_user_id is not None:
            raise CommandRejected(f"Ship #{cmd.ship_id} is already claimed")
        if hull.docked_in_id is None:
            raise CommandRejected(f"Ship #{cmd.ship_id} is not docked")
        if hull.is_destroyed:
            raise CommandRejected(f"Ship #{cmd.ship_id} is destroyed")
        if hull.team_id is not None and user.team_id is not None and hull.team_id != user.team_id:
            raise CommandRejected("Ship belongs to a different team")

    # Get team research for module unlocking
    completed_techs = set()
    if user.team_id is not None:
        research_result = await ctx.session.exec(
            select(ResearchProgress).where(ResearchProgress.team_id == user.team_id)
        )
        completed_techs = get_completed_tech_ids(research_result.all())

    # Determine faction for module validation
    faction = None
    if hull.team is not None:
        faction = hull.team.faction

    # Validate and calculate module costs
    total_module_vol = 0
    total_module_cost = 0.0
    module_specs = []
    for mod_spec in modules_list:
        mod_type = mod_spec.get("module_type")
        mod_vol = mod_spec.get("volume", 0)
        if mod_type is None:
            raise CommandRejected("Each module requires module_type")

        # Validate module type exists
        try:
            mt = ModuleType(mod_type)
        except ValueError:
            raise CommandRejected(f"Unknown module type: {mod_type}")

        # Validate research
        if not is_module_unlocked(mod_type, completed_techs):
            raise CommandRejected(f"Module {mod_type} is not yet researched")

        # Faction-exclusive check
        if mod_type in SOLARION_EXCLUSIVE_MODULES and faction != "solarion":
            raise CommandRejected(f"Module {mod_type} is Solarion-exclusive")
        if mod_type in VOIDBORN_EXCLUSIVE_MODULES and faction != "voidborn":
            raise CommandRejected(f"Module {mod_type} is Voidborn-exclusive")

        # Get point cost
        mod_cost = MODULE_POINT_COSTS.get(mod_type, 0)
        total_module_cost += mod_cost

        # Track volume (use fixed volume if applicable)
        fixed_vol = MODULE_FIXED_VOLUMES.get(mod_type)
        actual_vol = fixed_vol if fixed_vol is not None else mod_vol
        total_module_vol += actual_vol

        module_specs.append((mt, actual_vol, mod_cost))

    # Validate volume fits hull
    if total_module_vol > hull.total_volume:
        raise CommandRejected(
            f"Total module volume ({total_module_vol} m³) exceeds hull capacity "
            f"({hull.total_volume} m³)"
        )

    # Calculate total cost
    hull_cost = HULL_POINT_COSTS.get(hull.ship_class.value, 0)
    total_cost = hull_cost + total_module_cost

    # Validate points
    if user.points < total_cost:
        raise CommandRejected(
            f"Insufficient points: need {total_cost:.0f}, have {user.points:.0f}"
        )

    # --- All validations passed, execute ---

    # Deduct points
    user.points -= total_cost

    # Claim the ship
    hull.claimed_by_user_id = cmd.user_id
    hull.user_id = cmd.user_id
    hull.loadout_points_spent = total_cost

    # Install all modules
    for mt, vol, _ in module_specs:
        mod = make_module(mt, vol)
        mod.ship_id = hull.id
        ctx.session.add(mod)

    await ctx.session.flush()

    # Reload modules
    mods_result = await ctx.session.exec(
        select(ShipModule).where(ShipModule.ship_id == hull.id)
    )
    hull.modules = list(mods_result.all())

    # Recalculate derived stats
    recalculate_max_capacitor(hull)
    hull.capacitor = hull.max_capacitor
    recalculate_max_shield(hull)
    hull.shield_hp = hull.max_shield_hp
    recalculate_max_armor(hull)
    hull.armor_hp = hull.max_armor_hp

    # Undock
    hull.docked_in_id = None

    # Builder kickback: 50% of hull cost to builder (if different player)
    if hull.built_by_user_id and hull.built_by_user_id != cmd.user_id and hull_cost > 0:
        kickback = hull_cost * 0.5
        builder_result = await ctx.session.exec(
            select(User).where(User.id == hull.built_by_user_id)
        )
        builder = builder_result.first()
        if builder:
            builder.points += kickback

    ctx.emit(
        EventType.ship_claimed,
        f"Claimed {hull.ship_class.value} #{hull.id} with {len(module_specs)} modules "
        f"({total_cost:.0f} pts)",
        user_id=cmd.user_id,
        ship_id=hull.id,
    )


@register_handler("reship")
async def handle_reship(ctx: TickContext, cmd: Command) -> None:
    """Dock current ship, strip modules, refund 75% of loadout cost."""
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    if not ship.is_docked():
        raise CommandRejected("Ship must be docked to reship")
    if ship.claimed_by_user_id != cmd.user_id:
        raise CommandRejected("You don't control this ship")

    # Calculate refund
    refund = ship.loadout_points_spent * 0.75

    # Fetch user
    user_result = await ctx.session.exec(select(User).where(User.id == cmd.user_id))
    user = user_result.first()
    if user is None:
        raise CommandRejected("User not found")

    # Refund points
    user.points += refund

    # Strip all modules
    mods_result = await ctx.session.exec(
        select(ShipModule).where(ShipModule.ship_id == ship.id)
    )
    for mod in mods_result.all():
        await ctx.session.delete(mod)
    ship.modules = []

    # Reset to base hull stats
    recalculate_max_capacitor(ship)
    ship.capacitor = ship.max_capacitor
    recalculate_max_shield(ship)
    ship.shield_hp = ship.max_shield_hp
    recalculate_max_armor(ship)
    ship.armor_hp = ship.max_armor_hp

    # Mark unclaimed
    ship.claimed_by_user_id = None
    ship.loadout_points_spent = 0.0

    ctx.emit(
        EventType.reship_complete,
        f"Reshipped from {ship.ship_class.value} #{ship.id}, "
        f"refunded {refund:.0f} pts",
        user_id=cmd.user_id,
        ship_id=ship.id,
    )
