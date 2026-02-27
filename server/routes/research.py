"""
Research routes (read-only views).

GET   /api/ships/{id}/research/status  — Current research progress on this ship
GET   /api/research/tech-tree          — Full tech tree with completion status
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import select

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    RESEARCH_COSTS,
    TECH_TREE,
    ResearchProgress,
    Team,
    User,
)
from server.research import (
    get_completed_tech_ids,
    get_effective_tech_tree,
)
from server.routes.common import get_owned_ship


router = APIRouter(tags=["research"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ResearchProgressOut(BaseModel):
    id: int
    tech_id: str
    tech_name: str
    status: str
    ticks_remaining: int
    total_ticks: int
    progress_pct: float
    ship_id: int
    module_id: int


class TechNodeOut(BaseModel):
    tech_id: str
    name: str
    tier: int
    prerequisites: list[str]
    unlocks_modules: list[str]
    unlocks_ships: list[str]
    ore_cost: int
    research_ticks: int
    status: str  # "available", "researching", "complete", "locked"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rp_to_out(rp: ResearchProgress) -> ResearchProgressOut:
    node = TECH_TREE.get(rp.tech_id, {})
    total = rp.total_ticks or 1
    done = total - rp.ticks_remaining
    pct = round((done / total) * 100.0, 1)
    return ResearchProgressOut(
        id=rp.id,
        tech_id=rp.tech_id,
        tech_name=node.get("name", rp.tech_id),
        status=rp.status,
        ticks_remaining=rp.ticks_remaining,
        total_ticks=rp.total_ticks,
        progress_pct=pct,
        ship_id=rp.ship_id,
        module_id=rp.module_id,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/ships/{ship_id}/research/status", response_model=list[ResearchProgressOut])
async def research_status(
    ship_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Return all research progress (active + completed) associated with this ship."""
    await get_owned_ship(ship_id, current_user, session)

    result = await session.exec(
        select(ResearchProgress).where(
            ResearchProgress.ship_id == ship_id,
            ResearchProgress.status.in_(["researching", "paused", "complete"]),
        )
    )
    return [_rp_to_out(rp) for rp in result.all()]


@router.get("/api/research/tech-tree", response_model=list[TechNodeOut])
async def tech_tree(
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Return the full tech tree with completion/research status for this user (or team)."""
    # If user is on a team, include all team research
    if current_user.team_id is not None:
        result = await session.exec(
            select(ResearchProgress).where(
                (ResearchProgress.user_id == current_user.id)
                | (ResearchProgress.team_id == current_user.team_id)
            )
        )
    else:
        result = await session.exec(
            select(ResearchProgress).where(ResearchProgress.user_id == current_user.id)
        )
    all_research = result.all()
    completed = get_completed_tech_ids(all_research)
    researching = {r.tech_id for r in all_research if r.status == "researching"}

    # Use faction-specific tech tree if user is on a team
    user_faction = None
    if current_user.team_id is not None:
        team_result = await session.exec(
            select(Team).where(Team.id == current_user.team_id)
        )
        team = team_result.first()
        if team:
            user_faction = team.faction

    effective_tree = get_effective_tech_tree(user_faction)

    nodes = []
    for tech_id, node in effective_tree.items():
        tier = node["tier"]
        costs = RESEARCH_COSTS[tier]

        if tech_id in completed:
            node_status = "complete"
        elif tech_id in researching:
            node_status = "researching"
        elif all(p in completed for p in node["prerequisites"]):
            node_status = "available"
        else:
            node_status = "locked"

        nodes.append(TechNodeOut(
            tech_id=tech_id,
            name=node["name"],
            tier=tier,
            prerequisites=node["prerequisites"],
            unlocks_modules=node["unlocks_modules"],
            unlocks_ships=node["unlocks_ships"],
            ore_cost=costs["ore"],
            research_ticks=costs["ticks"],
            status=node_status,
        ))

    return nodes
