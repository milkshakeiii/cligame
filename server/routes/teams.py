"""
Team management routes for Phase 7.

POST   /api/teams                    -- Create a team
POST   /api/teams/{team_id}/join     -- Join a team
POST   /api/teams/leave              -- Leave current team
GET    /api/teams/{team_id}          -- Get team info
GET    /api/teams                    -- List all teams
GET    /api/teams/{team_id}/research -- Get team research status
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select, func
from sqlalchemy.orm import selectinload

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    Faction,
    Match,
    MatchStatus,
    ResearchProgress,
    Spaceship,
    Team,
    User,
)

router = APIRouter(prefix="/api/teams", tags=["teams"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateTeamRequest(BaseModel):
    name: str
    faction: str


class TeamOut(BaseModel):
    id: int
    name: str
    faction: str
    member_count: int
    created_at: str


class TeamJoinOut(BaseModel):
    message: str
    team_id: int
    team_name: str
    faction: str


class TeamResearchOut(BaseModel):
    id: int
    tech_id: str
    status: str
    ticks_remaining: int
    total_ticks: int
    user_id: int
    ship_id: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(
    body: CreateTeamRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Create a new team with a faction alignment."""
    # Validate faction
    faction_lower = body.faction.lower()
    if faction_lower not in ("solarion", "voidborn"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid faction '{body.faction}'. Must be 'solarion' or 'voidborn'.",
        )

    # Check name uniqueness
    existing = await session.exec(
        select(Team).where(Team.name == body.name)
    )
    if existing.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team name '{body.name}' is already taken.",
        )

    team = Team(name=body.name, faction=faction_lower)
    session.add(team)
    await session.commit()
    await session.refresh(team)

    return TeamOut(
        id=team.id,
        name=team.name,
        faction=team.faction,
        member_count=0,
        created_at=team.created_at.isoformat(),
    )


@router.post("/{team_id}/join", response_model=TeamJoinOut)
async def join_team(
    team_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Join a team. A user can only be on one team at a time."""
    if current_user.team_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Already on a team (team_id={current_user.team_id}). Leave your current team first.",
        )

    # Verify team exists
    result = await session.exec(
        select(Team).where(Team.id == team_id)
    )
    team = result.first()
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found.",
        )

    # Assign user to team (ships are assigned at match start, not here)
    current_user.team_id = team.id

    await session.commit()

    return TeamJoinOut(
        message="Joined team successfully.",
        team_id=team.id,
        team_name=team.name,
        faction=team.faction,
    )


@router.post("/leave")
async def leave_team(
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Leave the current team. Cannot leave if in an active match."""
    if current_user.team_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Not on a team.",
        )

    # Unassign user's ships from the team
    ship_result = await session.exec(
        select(Spaceship).where(
            Spaceship.user_id == current_user.id,
            Spaceship.team_id == current_user.team_id,
        )
    )
    for ship in ship_result.all():
        ship.team_id = None
        ship.match_id = None

    current_user.team_id = None
    await session.commit()

    return {"message": "Left team successfully."}


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(
    team_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Get team info including member count."""
    result = await session.exec(
        select(Team).where(Team.id == team_id)
    )
    team = result.first()
    if team is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found.",
        )

    # Count members
    count_result = await session.exec(
        select(func.count()).where(User.team_id == team.id)
    )
    member_count = count_result.one()

    return TeamOut(
        id=team.id,
        name=team.name,
        faction=team.faction,
        member_count=member_count,
        created_at=team.created_at.isoformat(),
    )


@router.get("", response_model=list[TeamOut])
async def list_teams(
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """List all teams."""
    result = await session.exec(select(Team))
    teams = result.all()

    out = []
    for team in teams:
        count_result = await session.exec(
            select(func.count()).where(User.team_id == team.id)
        )
        member_count = count_result.one()
        out.append(TeamOut(
            id=team.id,
            name=team.name,
            faction=team.faction,
            member_count=member_count,
            created_at=team.created_at.isoformat(),
        ))
    return out


@router.get("/{team_id}/research", response_model=list[TeamResearchOut])
async def team_research(
    team_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Get all research progress for a team."""
    # Verify team exists
    team_result = await session.exec(
        select(Team).where(Team.id == team_id)
    )
    if team_result.first() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found.",
        )

    result = await session.exec(
        select(ResearchProgress).where(
            ResearchProgress.team_id == team_id,
            ResearchProgress.status.in_(["researching", "paused", "complete"]),
        )
    )

    return [
        TeamResearchOut(
            id=rp.id,
            tech_id=rp.tech_id,
            status=rp.status,
            ticks_remaining=rp.ticks_remaining,
            total_ticks=rp.total_ticks,
            user_id=rp.user_id,
            ship_id=rp.ship_id,
        )
        for rp in result.all()
    ]
