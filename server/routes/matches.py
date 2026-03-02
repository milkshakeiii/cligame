"""
Match management routes for Phase 8.

POST   /api/matches                    -- Create a match
GET    /api/matches                    -- List matches (optional ?status= filter)
GET    /api/matches/{id}               -- Match details
POST   /api/matches/{id}/join          -- Join as team2
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select, func

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    Match,
    MatchStatus,
    Spaceship,
    Team,
    User,
)

router = APIRouter(prefix="/api/matches", tags=["matches"])

# Max allowed team size difference when joining the larger team in an active match.
# Joining the smaller team is always allowed (improves balance).
MAX_TEAM_SIZE_DIFF = 1


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateMatchRequest(BaseModel):
    name: str
    faction: str


class JoinMatchRequest(BaseModel):
    faction: str


class MatchOut(BaseModel):
    id: int
    name: str
    status: str
    team1_id: Optional[int] = None
    team2_id: Optional[int] = None
    team1_mothership_id: Optional[int] = None
    team2_mothership_id: Optional[int] = None
    winner_team_id: Optional[int] = None
    started_at_tick: Optional[int] = None
    ended_at_tick: Optional[int] = None
    created_at: str


class MatchDetailOut(BaseModel):
    id: int
    name: str
    status: str
    team1: Optional[dict] = None
    team2: Optional[dict] = None
    team1_mothership: Optional[dict] = None
    team2_mothership: Optional[dict] = None
    winner_team_id: Optional[int] = None
    started_at_tick: Optional[int] = None
    ended_at_tick: Optional[int] = None
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_team_info(session, team_id: Optional[int], include_members: bool = False) -> Optional[dict]:
    """Fetch team info dict for a match response."""
    if team_id is None:
        return None
    result = await session.exec(select(Team).where(Team.id == team_id))
    team = result.first()
    if team is None:
        return None
    count_result = await session.exec(
        select(func.count()).where(User.team_id == team.id)
    )
    member_count = count_result.one()
    info: dict = {
        "id": team.id,
        "name": team.name,
        "faction": team.faction,
        "member_count": member_count,
    }
    if include_members:
        members_result = await session.exec(
            select(User.username).where(User.team_id == team.id)
        )
        info["members"] = list(members_result.all())
    return info


async def _get_mothership_info(session, ship_id: Optional[int]) -> Optional[dict]:
    """Fetch mothership HP summary for a match response."""
    if ship_id is None:
        return None
    result = await session.exec(select(Spaceship).where(Spaceship.id == ship_id))
    ship = result.first()
    if ship is None:
        return None
    return {
        "id": ship.id,
        "name": ship.name,
        "shield_hp": ship.shield_hp,
        "max_shield_hp": ship.max_shield_hp,
        "armor_hp": ship.armor_hp,
        "max_armor_hp": ship.max_armor_hp,
        "is_destroyed": ship.is_destroyed,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_match(
    body: CreateMatchRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Create a match. Creates match + team1 for the creator."""
    if current_user.team_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already on a team. Leave your current team first.",
        )

    faction_lower = body.faction.lower()
    if faction_lower not in ("solarion", "voidborn"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid faction '{body.faction}'. Must be 'solarion' or 'voidborn'.",
        )

    opposite_faction = "voidborn" if faction_lower == "solarion" else "solarion"

    # Create both teams upfront
    team1 = Team(name=f"{body.name} - Team 1", faction=faction_lower)
    team2 = Team(name=f"{body.name} - Team 2", faction=opposite_faction)
    session.add(team1)
    session.add(team2)
    await session.flush()

    # Assign creator to team1
    current_user.team_id = team1.id

    # Assign creator's existing ships to the team
    ship_result = await session.exec(
        select(Spaceship).where(Spaceship.user_id == current_user.id)
    )
    for ship in ship_result.all():
        ship.team_id = team1.id

    # Create the match
    match = Match(
        name=body.name,
        status=MatchStatus.pending.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    session.add(match)
    await session.commit()
    await session.refresh(match)

    return {
        "id": match.id,
        "name": match.name,
        "status": match.status,
        "team1_id": match.team1_id,
        "team2_id": match.team2_id,
        "created_at": match.created_at.isoformat(),
    }


@router.get("")
async def list_matches(
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """List matches with optional status filter."""
    query = select(Match)
    if status_filter:
        query = query.where(Match.status == status_filter)
    result = await session.exec(query)
    matches = result.all()

    # Gather all team IDs to batch-fetch info
    team_ids = set()
    for m in matches:
        if m.team1_id is not None:
            team_ids.add(m.team1_id)
        if m.team2_id is not None:
            team_ids.add(m.team2_id)

    # Fetch faction and member count for each team
    team_info: dict[int, dict] = {}
    for tid in team_ids:
        info = await _get_team_info(session, tid)
        if info:
            team_info[tid] = info

    return [
        {
            "id": m.id,
            "name": m.name,
            "status": m.status,
            "team1_id": m.team1_id,
            "team2_id": m.team2_id,
            "team1_member_count": team_info[m.team1_id]["member_count"] if m.team1_id and m.team1_id in team_info else None,
            "team2_member_count": team_info[m.team2_id]["member_count"] if m.team2_id and m.team2_id in team_info else None,
            "team1_faction": team_info[m.team1_id]["faction"] if m.team1_id and m.team1_id in team_info else None,
            "team2_faction": team_info[m.team2_id]["faction"] if m.team2_id and m.team2_id in team_info else None,
            "winner_team_id": m.winner_team_id,
            "started_at_tick": m.started_at_tick,
            "ended_at_tick": m.ended_at_tick,
            "created_at": m.created_at.isoformat(),
        }
        for m in matches
    ]


@router.get("/{match_id}")
async def get_match(
    match_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Get detailed match info including teams and mothership HP."""
    result = await session.exec(select(Match).where(Match.id == match_id))
    match = result.first()
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found.")

    team1_info = await _get_team_info(session, match.team1_id, include_members=True)
    team2_info = await _get_team_info(session, match.team2_id, include_members=True)
    ms1_info = await _get_mothership_info(session, match.team1_mothership_id)
    ms2_info = await _get_mothership_info(session, match.team2_mothership_id)

    return {
        "id": match.id,
        "name": match.name,
        "status": match.status,
        "team1": team1_info,
        "team2": team2_info,
        "team1_mothership": ms1_info,
        "team2_mothership": ms2_info,
        "winner_team_id": match.winner_team_id,
        "started_at_tick": match.started_at_tick,
        "ended_at_tick": match.ended_at_tick,
        "created_at": match.created_at.isoformat(),
    }


@router.post("/{match_id}/join")
async def join_match(
    match_id: int,
    body: JoinMatchRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Join a match by picking a faction. Works for both pending and active matches."""
    if current_user.team_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Already on a team. Leave your current team first.",
        )

    # Lock match row to prevent concurrent joins
    result = await session.exec(
        select(Match).where(Match.id == match_id).with_for_update()
    )
    match = result.first()
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found.")
    if match.status not in (MatchStatus.pending.value, MatchStatus.active.value):
        raise HTTPException(status_code=400, detail="Match is not joinable (must be pending or active).")

    faction_lower = body.faction.lower()
    if faction_lower not in ("solarion", "voidborn"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid faction '{body.faction}'. Must be 'solarion' or 'voidborn'.",
        )

    # Both teams always exist — find the one matching the requested faction
    t1_result = await session.exec(select(Team).where(Team.id == match.team1_id))
    team1 = t1_result.first()
    t2_result = await session.exec(select(Team).where(Team.id == match.team2_id))
    team2 = t2_result.first()

    if team1 is None or team2 is None:
        raise HTTPException(status_code=400, detail="Match is missing a team.")

    if team1.faction == faction_lower:
        target_team, other_team = team1, team2
    elif team2.faction == faction_lower:
        target_team, other_team = team2, team1
    else:
        raise HTTPException(status_code=400, detail=f"No team in this match has faction '{faction_lower}'.")

    # Balance check for active matches
    if match.status == MatchStatus.active.value:
        my_count_result = await session.exec(
            select(func.count()).where(User.team_id == target_team.id)
        )
        my_count = my_count_result.one()
        other_count_result = await session.exec(
            select(func.count()).where(User.team_id == other_team.id)
        )
        other_count = other_count_result.one()

        if my_count >= other_count and my_count - other_count >= MAX_TEAM_SIZE_DIFF:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot join — would make teams too unbalanced "
                       f"({my_count + 1} vs {other_count}). "
                       f"Join the other faction to help balance.",
            )

    # Add user to team
    current_user.team_id = target_team.id

    # Assign user's existing ships to the team
    ship_result = await session.exec(
        select(Spaceship).where(Spaceship.user_id == current_user.id)
    )
    for ship in ship_result.all():
        ship.team_id = target_team.id

    await session.commit()

    return {
        "message": "Joined match successfully.",
        "match_id": match.id,
        "team_id": target_team.id,
        "faction": faction_lower,
    }


@router.post("/{match_id}/switch-team")
async def switch_team(
    match_id: int,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Switch to the other team in a match (pending or active)."""
    result = await session.exec(
        select(Match).where(Match.id == match_id).with_for_update()
    )
    match = result.first()
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found.")
    if match.status not in (MatchStatus.pending.value, MatchStatus.active.value):
        raise HTTPException(status_code=400, detail="Match is not joinable.")

    # Which team is the user on?
    if current_user.team_id == match.team1_id:
        from_team_id = match.team1_id
        to_team_id = match.team2_id
    elif current_user.team_id == match.team2_id:
        from_team_id = match.team2_id
        to_team_id = match.team1_id
    else:
        raise HTTPException(status_code=400, detail="You are not in this match.")

    to_result = await session.exec(select(Team).where(Team.id == to_team_id))
    to_team = to_result.first()

    # Balance check for active matches
    if match.status == MatchStatus.active.value:
        to_count_result = await session.exec(
            select(func.count()).where(User.team_id == to_team_id)
        )
        to_count = to_count_result.one()
        from_count_result = await session.exec(
            select(func.count()).where(User.team_id == from_team_id)
        )
        from_count = from_count_result.one()
        new_to = to_count + 1
        new_from = from_count - 1
        if new_from > 0 and new_to - new_from >= MAX_TEAM_SIZE_DIFF:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot switch — would make teams too unbalanced ({new_to} vs {new_from}).",
            )

    # Move user
    current_user.team_id = to_team.id

    # Move user's ships
    ship_result = await session.exec(
        select(Spaceship).where(Spaceship.user_id == current_user.id)
    )
    for ship in ship_result.all():
        ship.team_id = to_team.id

    await session.commit()

    return {
        "message": "Switched team.",
        "match_id": match.id,
        "team_id": to_team.id,
        "faction": to_team.faction,
    }
