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
    RESEARCH_GATED_MODULES,
    RESEARCH_GATED_SHIPS,
    SHIP_REQUIRED_TECH,
    SOLARION_TECH_TREE_OVERRIDES,
    TECH_TREE,
    VOIDBORN_TECH_TREE_OVERRIDES,
    Event,
    EventType,
    ResearchProgress,
    ShipModule,
    Spaceship,
)


# ---------------------------------------------------------------------------
# Faction-aware tech tree helper
# ---------------------------------------------------------------------------


def get_effective_tech_tree(faction: Optional[str] = None) -> Dict[str, dict]:
    """Return the tech tree with faction-specific overrides applied."""
    tree = dict(TECH_TREE)  # shallow copy
    if faction == "solarion":
        tree.update(SOLARION_TECH_TREE_OVERRIDES)
    elif faction == "voidborn":
        tree.update(VOIDBORN_TECH_TREE_OVERRIDES)
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
    """
    tree = get_effective_tech_tree(faction)
    node = tree.get(tech_id)
    if node is None:
        return f"Unknown tech: {tech_id}"
    for prereq in node["prerequisites"]:
        if prereq not in completed_techs:
            prereq_node = tree.get(prereq)
            prereq_name = prereq_node["name"] if prereq_node else prereq
            return f"Prerequisite not met: {prereq_name} ({prereq})"
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

    # Already in progress?
    in_progress = [
        r for r in all_research
        if r.tech_id == tech_id and r.status == "researching"
    ]
    if in_progress:
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
    return rp


# ---------------------------------------------------------------------------
# Tick research (called from tick loop)
# ---------------------------------------------------------------------------


async def tick_research(session, ships_by_id: Dict[int, Spaceship], current_tick: int) -> None:
    """
    Advance all active research by one tick.
    - Drains 50 capacitor per tick per active research module.
    - Pauses if insufficient capacitor.
    - Completes when ticks_remaining reaches 0.
    """
    result = await session.exec(
        select(ResearchProgress).where(ResearchProgress.status == "researching")
    )
    active_research = result.all()

    for rp in active_research:
        ship = ships_by_id.get(rp.ship_id)
        if ship is None or ship.is_destroyed:
            rp.status = "cancelled"
            continue

        # Find the research module
        module = next(
            (m for m in ship.modules if m.id == rp.module_id),
            None,
        )
        if module is None:
            rp.status = "cancelled"
            continue

        # Check capacitor (research module drains 50 cap/tick)
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

        # If was paused and now has cap, resume
        if rp.status == "paused":
            rp.status = "researching"
            module.active = True

        # Drain capacitor
        ship.capacitor -= cap_cost

        # Advance research
        rp.ticks_remaining -= 1

        if rp.ticks_remaining <= 0:
            rp.status = "complete"
            rp.ticks_remaining = 0
            module.active = False

            session.add(Event(
                tick=current_tick,
                event_type=EventType.research_complete,
                ship_id=ship.id,
                user_id=ship.user_id,
                message=f"Research complete: {get_tech_name(rp.tech_id)}",
            ))
