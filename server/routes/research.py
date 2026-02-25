"""
Research routes for Phase 5.

POST  /api/ships/{id}/research/start   — Begin researching a tech
POST  /api/ships/{id}/research/cancel  — Cancel active research on a module
GET   /api/ships/{id}/research/status  — Current research progress on this ship
GET   /api/research/tech-tree          — Full tech tree with completion status
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    RESEARCH_COSTS,
    TECH_TREE,
    ModuleType,
    ResearchProgress,
    Spaceship,
    User,
)
from server.research import (
    get_completed_tech_ids,
    start_research,
)
from server.routes.common import get_owned_ship


router = APIRouter(tags=["research"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ResearchStartRequest(BaseModel):
    tech_id: str
    module_id: Optional[int] = None  # research module ID; if None, first available


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


class ResearchCancelRequest(BaseModel):
    module_id: Optional[int] = None  # if None, cancel all research on ship


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


@router.post(
    "/api/ships/{ship_id}/research/start",
    response_model=ResearchProgressOut,
    status_code=status.HTTP_201_CREATED,
)
async def research_start(
    ship_id: int,
    body: ResearchStartRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Begin researching a tech using a research module on this ship."""
    ship = await get_owned_ship(
        ship_id, current_user, session,
        selectinload(Spaceship.modules),
    )

    if ship.is_destroyed:
        raise HTTPException(status_code=422, detail="Ship is destroyed")

    # Find the research module
    research_modules = [
        m for m in ship.modules
        if m.module_type == ModuleType.research_module
    ]
    if not research_modules:
        raise HTTPException(
            status_code=422,
            detail="Ship has no research module installed",
        )

    if body.module_id is not None:
        module = next((m for m in research_modules if m.id == body.module_id), None)
        if module is None:
            raise HTTPException(status_code=404, detail="Research module not found on this ship")
    else:
        # Find first available (not currently researching)
        busy_module_ids = set()
        busy_result = await session.exec(
            select(ResearchProgress).where(
                ResearchProgress.ship_id == ship.id,
                ResearchProgress.status == "researching",
            )
        )
        for rp in busy_result.all():
            busy_module_ids.add(rp.module_id)

        module = next(
            (m for m in research_modules if m.id not in busy_module_ids),
            None,
        )
        if module is None:
            raise HTTPException(
                status_code=422,
                detail="All research modules are busy",
            )

    try:
        rp = await start_research(
            session, ship, module, body.tech_id, current_user.id,
            team_id=current_user.team_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    await session.commit()
    await session.refresh(rp)
    return _rp_to_out(rp)


@router.post("/api/ships/{ship_id}/research/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def research_cancel(
    ship_id: int,
    body: ResearchCancelRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Cancel active research on this ship. Ore is not refunded."""
    ship = await get_owned_ship(
        ship_id, current_user, session,
        selectinload(Spaceship.modules),
    )

    result = await session.exec(
        select(ResearchProgress).where(
            ResearchProgress.ship_id == ship.id,
            ResearchProgress.status.in_(["researching", "paused"]),
        )
    )
    active = result.all()

    if body.module_id is not None:
        active = [r for r in active if r.module_id == body.module_id]

    if not active:
        raise HTTPException(status_code=404, detail="No active research to cancel")

    for rp in active:
        rp.status = "cancelled"
        # Deactivate the research module
        mod = next((m for m in ship.modules if m.id == rp.module_id), None)
        if mod:
            mod.active = False

    await session.commit()


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

    nodes = []
    for tech_id, node in TECH_TREE.items():
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
