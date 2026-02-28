"""
Research system for Phase 5 + Phase 7 faction extensions.

Provides:
  - start_research(): validate and begin a research effort
  - tick_research(): advance active research (called from tick loop)
  - get_completed_techs(): return all completed tech IDs for a user/team
  - get_effective_tech_tree(): return tech tree with faction overrides
  - is_module_unlocked() / is_ship_unlocked(): gating checks
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from sqlmodel import select

from server.models import (
    MODULE_REQUIRED_TECH,
    RESEARCH_COSTS,
    RESEARCH_COMPLETE_POINTS,
    RESEARCH_GATED_MODULES,
    RESEARCH_GATED_SHIPS,
    SHIP_REQUIRED_TECH,
    TECH_TREE,
    Event,
    EventType,
    ResearchContributor,
    ResearchProgress,
    ShipModule,
    Spaceship,
    User,
)


# ---------------------------------------------------------------------------
# Faction-aware tech tree helper
# ---------------------------------------------------------------------------


def get_effective_tech_tree(faction: Optional[str] = None) -> Dict[str, dict]:
    """Return the tech tree filtered to nodes available for a faction.

    Faction-specific nodes have a "faction" key. Non-faction nodes are always
    included. Faction nodes are only included when they match the given faction.
    """
    tree: Dict[str, dict] = {}
    for tech_id, node in TECH_TREE.items():
        node_faction = node.get("faction")
        if node_faction is None or node_faction == faction:
            tree[tech_id] = node
    return tree


# ---------------------------------------------------------------------------
# Gating helpers (pure functions, no DB)
# ---------------------------------------------------------------------------


def get_completed_tech_ids(research_list: List[ResearchProgress]) -> Set[str]:
    """Extract set of completed tech IDs from a list of ResearchProgress rows."""
    return {r.tech_id for r in research_list if r.status == "complete"}


def is_module_unlocked(module_type: str, completed_techs: Set[str]) -> bool:
    """Check if a module type is available (either not gated or research completed)."""
    if module_type not in RESEARCH_GATED_MODULES:
        return True  # available from start
    required = MODULE_REQUIRED_TECH.get(module_type)
    if required is None:
        return True
    return required in completed_techs


def is_ship_unlocked(ship_class: str, completed_techs: Set[str]) -> bool:
    """Check if a ship class is available (either not gated or research completed)."""
    if ship_class not in RESEARCH_GATED_SHIPS:
        return True  # available from start
    required = SHIP_REQUIRED_TECH.get(ship_class)
    if required is None:
        return True
    return required in completed_techs


def check_prerequisites(
    tech_id: str,
    completed_techs: Set[str],
    faction: Optional[str] = None,
) -> Optional[str]:
    """
    Check if prerequisites for a tech are met.
    Returns None if OK, or a message describing what's missing.

    Uses the faction-effective tech tree when ``faction`` is provided,
    allowing faction-specific techs to be validated.

    Supports both "prerequisites" (all required) and "prerequisites_any"
    (at least one required).
    """
    tree = get_effective_tech_tree(faction)
    node = tree.get(tech_id)
    if node is None:
        return f"Unknown tech: {tech_id}"
    # All prerequisites must be met
    for prereq in node["prerequisites"]:
        if prereq not in completed_techs:
            prereq_node = tree.get(prereq)
            prereq_name = prereq_node["name"] if prereq_node else prereq
            return f"Prerequisite not met: {prereq_name} ({prereq})"
    # At least one of prerequisites_any must be met (if present)
    any_prereqs = node.get("prerequisites_any", [])
    if any_prereqs and not any(p in completed_techs for p in any_prereqs):
        names = []
        for p in any_prereqs:
            pn = tree.get(p)
            names.append(pn["name"] if pn else p)
        return f"Prerequisite not met: need at least one of {', '.join(names)}"
    return None


def get_tech_name(tech_id: str, faction: Optional[str] = None) -> str:
    """Return the display name for a tech ID."""
    tree = get_effective_tech_tree(faction)
    node = tree.get(tech_id)
    return node["name"] if node else tech_id


# ---------------------------------------------------------------------------
# Start research (DB-aware)
# ---------------------------------------------------------------------------


async def start_research(
    session,
    ship: Spaceship,
    module: ShipModule,
    tech_id: str,
    user_id: int,
    team_id: Optional[int] = None,
    faction: Optional[str] = None,
) -> ResearchProgress:
    """
    Begin researching a tech. Validates prerequisites, deducts ore, creates
    a ResearchProgress row.

    When ``team_id`` is provided, research completion is shared across the
    team.  ``user_id`` still tracks who initiated the research.  The
    ``faction`` parameter (derived from the ship's team) determines which
    faction-specific tech tree overrides are applied.

    Raises ValueError on validation failure.
    """
    tree = get_effective_tech_tree(faction)
    node = tree.get(tech_id)
    if node is None:
        raise ValueError(f"Unknown tech: {tech_id}")

    # Get all research for this user/team
    if team_id is not None:
        result = await session.exec(
            select(ResearchProgress).where(ResearchProgress.team_id == team_id)
        )
    else:
        result = await session.exec(
            select(ResearchProgress).where(ResearchProgress.user_id == user_id)
        )
    all_research = result.all()

    completed = get_completed_tech_ids(all_research)

    # Already researched?
    if tech_id in completed:
        raise ValueError(f"Already researched: {node['name']}")

    is_duplicable = node.get("duplicable", False)

    # Already in progress?
    in_progress = [
        r for r in all_research
        if r.tech_id == tech_id and r.status == "researching"
    ]
    if in_progress:
        if is_duplicable:
            # For duplicable techs, add as a contributor instead
            rp = in_progress[0]
            # Check research module type
            if module.module_type.value != "research_module":
                raise ValueError("Module is not a research module")
            # Check module not already researching
            existing = await session.exec(
                select(ResearchProgress).where(
                    ResearchProgress.module_id == module.id,
                    ResearchProgress.status == "researching",
                )
            )
            if existing.first() is not None:
                raise ValueError("This research module is already busy")
            # Check not already contributing
            existing_contrib = await session.exec(
                select(ResearchContributor).where(
                    ResearchContributor.research_id == rp.id,
                    ResearchContributor.module_id == module.id,
                )
            )
            if existing_contrib.first() is not None:
                raise ValueError("This module is already contributing to this research")
            # Deduct ore
            tier = node["tier"]
            costs = RESEARCH_COSTS[tier]
            if ship.ore < costs["ore"]:
                raise ValueError(
                    f"Insufficient ore: need {costs['ore']}, have {ship.ore:.0f}"
                )
            ship.ore -= costs["ore"]
            module.active = True
            contrib = ResearchContributor(
                research_id=rp.id,
                ship_id=ship.id,
                module_id=module.id,
                user_id=user_id,
            )
            session.add(contrib)
            return rp
        else:
            raise ValueError(f"Already researching: {node['name']}")

    # Check prerequisites
    prereq_error = check_prerequisites(tech_id, completed, faction=faction)
    if prereq_error:
        raise ValueError(prereq_error)

    # Check research module type
    if module.module_type.value != "research_module":
        raise ValueError("Module is not a research module")

    # Check module not already researching something
    existing = await session.exec(
        select(ResearchProgress).where(
            ResearchProgress.module_id == module.id,
            ResearchProgress.status == "researching",
        )
    )
    if existing.first() is not None:
        raise ValueError("This research module is already busy")

    # Check ore cost
    tier = node["tier"]
    costs = RESEARCH_COSTS[tier]
    if ship.ore < costs["ore"]:
        raise ValueError(
            f"Insufficient ore: need {costs['ore']}, have {ship.ore:.0f}"
        )

    # Deduct ore
    ship.ore -= costs["ore"]

    # Activate the research module
    module.active = True

    # Create research progress
    rp = ResearchProgress(
        user_id=user_id,
        team_id=team_id,
        tech_id=tech_id,
        ship_id=ship.id,
        module_id=module.id,
        status="researching",
        ticks_remaining=costs["ticks"],
        total_ticks=costs["ticks"],
        ore_cost=costs["ore"],
    )
    session.add(rp)
    await session.flush()

    # For duplicable techs, the initiator is also a contributor
    if is_duplicable:
        contrib = ResearchContributor(
            research_id=rp.id,
            ship_id=ship.id,
            module_id=module.id,
            user_id=user_id,
        )
        session.add(contrib)

    return rp


# ---------------------------------------------------------------------------
# Tick research (called from tick loop)
# ---------------------------------------------------------------------------


async def tick_research(
    session,
    ships_by_id: Dict[int, Spaceship],
    current_tick: int,
    users_by_id: Optional[Dict[int, "User"]] = None,
) -> None:
    """
    Advance all active research by one tick.
    - Drains 50 capacitor per tick per active research module.
    - Pauses if insufficient capacitor.
    - Completes when ticks_remaining reaches 0.
    - For duplicable techs, counts active contributors and decrements
      ticks_remaining by the contributor count.
    """
    result = await session.exec(
        select(ResearchProgress).where(ResearchProgress.status == "researching")
    )
    active_research = result.all()

    # Preload all contributors for active duplicable research
    active_rp_ids = [rp.id for rp in active_research]
    contributors_by_rp: Dict[int, list] = {}
    if active_rp_ids:
        contrib_result = await session.exec(
            select(ResearchContributor).where(
                ResearchContributor.research_id.in_(active_rp_ids)
            )
        )
        for c in contrib_result.all():
            contributors_by_rp.setdefault(c.research_id, []).append(c)

    for rp in active_research:
        tree = get_effective_tech_tree()
        node = tree.get(rp.tech_id)
        is_duplicable = node.get("duplicable", False) if node else False

        if is_duplicable:
            # Process each contributor's ship for cap drain
            contribs = contributors_by_rp.get(rp.id, [])
            active_count = 0
            for contrib in contribs:
                cship = ships_by_id.get(contrib.ship_id)
                if cship is None or cship.is_destroyed:
                    continue
                cmodule = next(
                    (m for m in cship.modules if m.id == contrib.module_id), None
                )
                if cmodule is None:
                    continue
                cap_cost = 50.0
                if cship.capacitor < cap_cost:
                    cmodule.active = False
                    continue
                cship.capacitor -= cap_cost
                cmodule.active = True
                active_count += 1
                # Award 1 pt/tick per contributor for duplicable research
                if users_by_id and contrib.user_id in users_by_id:
                    users_by_id[contrib.user_id].points += 1.0

            if active_count == 0:
                continue  # no progress this tick

            rp.ticks_remaining -= active_count
        else:
            # Non-duplicable: original single-researcher logic
            ship = ships_by_id.get(rp.ship_id)
            if ship is None or ship.is_destroyed:
                rp.status = "cancelled"
                continue

            module = next(
                (m for m in ship.modules if m.id == rp.module_id), None
            )
            if module is None:
                rp.status = "cancelled"
                continue

            cap_cost = 50.0
            if ship.capacitor < cap_cost:
                if rp.status != "paused":
                    rp.status = "paused"
                    module.active = False
                    session.add(Event(
                        tick=current_tick,
                        event_type=EventType.research_paused,
                        ship_id=ship.id,
                        user_id=ship.user_id,
                        message=f"Research paused ({get_tech_name(rp.tech_id)}): insufficient capacitor",
                    ))
                continue

            if rp.status == "paused":
                rp.status = "researching"
                module.active = True

            ship.capacitor -= cap_cost
            rp.ticks_remaining -= 1

        if rp.ticks_remaining <= 0:
            rp.status = "complete"
            rp.ticks_remaining = 0

            # Deactivate all contributor modules for duplicable, or just the module for non-duplicable
            if is_duplicable:
                for contrib in contributors_by_rp.get(rp.id, []):
                    cship = ships_by_id.get(contrib.ship_id)
                    if cship:
                        cmod = next((m for m in cship.modules if m.id == contrib.module_id), None)
                        if cmod:
                            cmod.active = False
            else:
                ship = ships_by_id.get(rp.ship_id)
                if ship:
                    module = next((m for m in ship.modules if m.id == rp.module_id), None)
                    if module:
                        module.active = False

            # Award research completion points
            tier = node["tier"] if node else 1
            rp_points = RESEARCH_COMPLETE_POINTS.get(tier, 200)
            if users_by_id and rp.user_id in users_by_id:
                users_by_id[rp.user_id].points += rp_points

            # Emit event for the primary researcher's ship
            rp_ship = ships_by_id.get(rp.ship_id)
            session.add(Event(
                tick=current_tick,
                event_type=EventType.research_complete,
                ship_id=rp.ship_id if rp_ship else None,
                user_id=rp.user_id,
                message=f"Research complete: {get_tech_name(rp.tech_id)} (+{rp_points} pts)",
            ))
