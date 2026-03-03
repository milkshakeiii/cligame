"""Command handlers for ship management: create, rename, install/uninstall module, undock."""

from __future__ import annotations

import math
import random

from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.commands import CommandRejected, TickContext, get_payload, register_handler
from server.models import (
    ARMOR_PLATE_TYPES,
    Command,
    EventType,
    FACTION_SHIP_NAMES,
    MODULE_REQUIRED_TECH,
    ModuleType,
    REFERENCE_ENGINE_FRACTION,
    ResearchProgress,
    SHIELD_EXTENDER_TYPES,
    SHIP_REQUIRED_TECH,
    ShipClass,
    EJECT_ALLOWED_CLASSES,
    SOLARION_EXCLUSIVE_MODULES,
    Team,
    VOIDBORN_EXCLUSIVE_MODULES,
    create_default_ship,
    make_module,
    recalculate_max_armor,
    recalculate_max_capacitor,
    recalculate_max_shield,
)
from server.research import get_completed_tech_ids, get_tech_name, is_module_unlocked, is_ship_unlocked


@register_handler("create_ship")
async def handle_create_ship(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    ship_class_str = payload.get("ship_class")
    name = payload.get("name")

    if not ship_class_str:
        raise CommandRejected("ship_class is required")
    try:
        ship_class = ShipClass(ship_class_str)
    except ValueError:
        raise CommandRejected(f"Invalid ship class: {ship_class_str}")

    # Load user for team info
    from server.models import User
    user_result = await ctx.session.exec(select(User).where(User.id == cmd.user_id))
    user = user_result.first()
    if user is None:
        raise CommandRejected("User not found")

    # Research gating
    if user.team_id is not None:
        rp_result = await ctx.session.exec(
            select(ResearchProgress).where(
                (ResearchProgress.user_id == cmd.user_id)
                | (ResearchProgress.team_id == user.team_id)
            )
        )
    else:
        rp_result = await ctx.session.exec(
            select(ResearchProgress).where(ResearchProgress.user_id == cmd.user_id)
        )
    completed_techs = get_completed_tech_ids(rp_result.all())
    if not is_ship_unlocked(ship_class_str, completed_techs):
        tech_id = SHIP_REQUIRED_TECH.get(ship_class_str, "?")
        raise CommandRejected(f"Research required: {get_tech_name(tech_id)} ({tech_id})")

    # Spawn position near existing ships
    user_ships = [s for s in ctx.ships if s.user_id == cmd.user_id]
    pos_x, pos_y, pos_z = 0.0, 0.0, 0.0
    if user_ships:
        ref = user_ships[0]
        theta = random.uniform(0, 2 * math.pi)
        phi = random.uniform(0, math.pi)
        dx = math.sin(phi) * math.cos(theta)
        dy = math.sin(phi) * math.sin(theta)
        dz = math.cos(phi)
        pos_x = ref.pos_x + dx * 100.0
        pos_y = ref.pos_y + dy * 100.0
        pos_z = ref.pos_z + dz * 100.0

    # Faction info
    user_team_id = user.team_id
    user_faction = None
    if user_team_id is not None:
        team_result = await ctx.session.exec(select(Team).where(Team.id == user_team_id))
        team = team_result.first()
        if team:
            user_faction = team.faction

    # Auto-generate name
    ship_name = name
    if not ship_name:
        same_class_count = sum(1 for s in user_ships if s.ship_class == ship_class)
        if user_faction and user_faction in FACTION_SHIP_NAMES:
            faction_name = FACTION_SHIP_NAMES[user_faction].get(ship_class_str)
            if faction_name:
                ship_name = f"{faction_name}-{same_class_count + 1}"
        if not ship_name:
            class_label = ship_class_str.replace("_", " ").title()
            ship_name = f"{class_label}-{same_class_count + 1}"

    ship = create_default_ship(
        name=ship_name,
        ship_class=ship_class,
        user_id=cmd.user_id,
        pos_x=pos_x, pos_y=pos_y, pos_z=pos_z,
        team_id=user_team_id,
        faction=user_faction,
    )
    # Pre-initialize relationship collections to avoid lazy-load in async context
    ship.modules = []
    ship.movement_orders = []
    ship.build_orders = []
    ship.target_locks = []
    ctx.session.add(ship)
    await ctx.session.flush()

    # Add default engine module
    engine_volume = max(1, int(ship.total_volume * REFERENCE_ENGINE_FRACTION))
    engine = make_module(ModuleType.engine, engine_volume)
    engine.ship_id = ship.id
    ctx.session.add(engine)
    await ctx.session.flush()

    ship.modules.append(engine)
    ctx.ships.append(ship)
    ctx.invalidate_ship_map()

    ctx.emit(
        EventType.command_processed,
        f"Ship '{ship_name}' ({ship_class_str}) created",
        user_id=cmd.user_id,
        ship_id=ship.id,
    )


@register_handler("rename_ship")
async def handle_rename_ship(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    new_name = payload.get("name")
    if not new_name:
        raise CommandRejected("name is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)
    ship.name = new_name
    ctx.emit(EventType.command_processed, f"Ship renamed to '{new_name}'",
             user_id=cmd.user_id, ship_id=ship.id)


@register_handler("install_module")
async def handle_install_module(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    module_type_str = payload.get("module_type")
    volume = payload.get("volume", 0)

    if not module_type_str:
        raise CommandRejected("module_type is required")
    try:
        module_type = ModuleType(module_type_str)
    except ValueError:
        raise CommandRejected(f"Invalid module type: {module_type_str}")

    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")
    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    # Block during combat
    from server.models import LockStatus, TargetLock
    lock_result = await ctx.session.exec(
        select(TargetLock).where(
            ((TargetLock.ship_id == ship.id) | (TargetLock.target_ship_id == ship.id)),
            TargetLock.status.in_([LockStatus.locking.value, LockStatus.locked.value]),
        )
    )
    if lock_result.first() is not None:
        raise CommandRejected("Cannot modify modules while in combat (active target locks)")

    # Variable-size modules need positive volume
    VARIABLE_SIZE_MODULES = {
        ModuleType.engine, ModuleType.reactor, ModuleType.cargo_bay,
        ModuleType.docking_bay, ModuleType.factory, ModuleType.enhanced_docking_bay,
    }
    if module_type in VARIABLE_SIZE_MODULES and volume <= 0:
        raise CommandRejected(f"module_type '{module_type_str}' requires a positive volume")

    # Research gating
    from server.models import User
    user_result = await ctx.session.exec(select(User).where(User.id == cmd.user_id))
    user = user_result.first()

    if user.team_id is not None:
        rp_result = await ctx.session.exec(
            select(ResearchProgress).where(
                (ResearchProgress.user_id == cmd.user_id)
                | (ResearchProgress.team_id == user.team_id)
            )
        )
    else:
        rp_result = await ctx.session.exec(
            select(ResearchProgress).where(ResearchProgress.user_id == cmd.user_id)
        )
    completed_techs = get_completed_tech_ids(rp_result.all())
    if not is_module_unlocked(module_type_str, completed_techs):
        tech_id = MODULE_REQUIRED_TECH.get(module_type_str, "?")
        raise CommandRejected(f"Research required: {get_tech_name(tech_id)} ({tech_id})")

    # Faction exclusivity
    if module_type_str in SOLARION_EXCLUSIVE_MODULES or module_type_str in VOIDBORN_EXCLUSIVE_MODULES:
        ship_faction = None
        if ship.team_id is not None:
            team_result = await ctx.session.exec(select(Team).where(Team.id == ship.team_id))
            team_obj = team_result.first()
            if team_obj:
                ship_faction = team_obj.faction
        if module_type_str in SOLARION_EXCLUSIVE_MODULES and ship_faction != "solarion":
            raise CommandRejected(f"Module '{module_type_str}' requires Solarion faction")
        if module_type_str in VOIDBORN_EXCLUSIVE_MODULES and ship_faction != "voidborn":
            raise CommandRejected(f"Module '{module_type_str}' requires Voidborn faction")

    # Volume check
    used = sum(m.volume for m in ship.modules)
    module = make_module(module_type, volume)
    if used + module.volume > ship.total_volume:
        raise CommandRejected(
            f"Not enough volume: {module.volume} m³ needed, "
            f"only {ship.total_volume - used} m³ available"
        )

    module.ship_id = ship.id
    ctx.session.add(module)
    await ctx.session.flush()
    ship.modules.append(module)

    # Recalculate derived stats
    if module_type == ModuleType.reactor:
        recalculate_max_capacitor(ship)
    if module_type_str in SHIELD_EXTENDER_TYPES:
        old_max = ship.max_shield_hp
        recalculate_max_shield(ship)
        bonus = ship.max_shield_hp - old_max
        ship.shield_hp = min(ship.shield_hp + bonus, ship.max_shield_hp)
    if module_type_str in ARMOR_PLATE_TYPES:
        old_max = ship.max_armor_hp
        recalculate_max_armor(ship)
        bonus = ship.max_armor_hp - old_max
        ship.armor_hp = min(ship.armor_hp + bonus, ship.max_armor_hp)


@register_handler("uninstall_module")
async def handle_uninstall_module(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    module_id = payload.get("module_id")
    if module_id is None:
        raise CommandRejected("module_id is required")
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")

    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)

    # Block during combat
    from server.models import LockStatus, TargetLock
    lock_result = await ctx.session.exec(
        select(TargetLock).where(
            ((TargetLock.ship_id == ship.id) | (TargetLock.target_ship_id == ship.id)),
            TargetLock.status.in_([LockStatus.locking.value, LockStatus.locked.value]),
        )
    )
    if lock_result.first() is not None:
        raise CommandRejected("Cannot modify modules while in combat (active target locks)")

    module = next((m for m in ship.modules if m.id == module_id), None)
    if module is None:
        raise CommandRejected("Module not found on this ship")

    # Clean up weapon assignment if this is a weapon module
    from server.models import WEAPON_TYPES, WeaponAssignment
    if module.module_type.value in WEAPON_TYPES:
        wa = next((w for w in ctx.weapon_assignments if w.module_id == module.id), None)
        if wa:
            await ctx.session.delete(wa)
            ctx.weapon_assignments.remove(wa)

    ship.modules.remove(module)
    await ctx.session.delete(module)

    if module.module_type == ModuleType.reactor:
        recalculate_max_capacitor(ship)
        ship.capacitor = min(ship.capacitor, ship.max_capacitor)
    if module.module_type.value in SHIELD_EXTENDER_TYPES:
        recalculate_max_shield(ship)
        ship.shield_hp = min(ship.shield_hp, ship.max_shield_hp)
    if module.module_type.value in ARMOR_PLATE_TYPES:
        recalculate_max_armor(ship)
        ship.armor_hp = min(ship.armor_hp, ship.max_armor_hp)


@register_handler("undock")
async def handle_undock(ctx: TickContext, cmd: Command) -> None:
    if cmd.ship_id is None:
        raise CommandRejected("ship_id is required")
    ship = ctx.find_ship(cmd.ship_id, cmd.user_id)
    if not ship.is_docked():
        raise CommandRejected("Ship is not currently docked")
    # Non-ejectable ships must be claimed before undocking
    if ship.ship_class.value not in EJECT_ALLOWED_CLASSES and ship.claimed_by_user_id is None:
        raise CommandRejected("Ship must be claimed before undocking")
    ship.docked_in_id = None
