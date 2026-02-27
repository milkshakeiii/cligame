"""
View endpoint.

GET /api/view — player's world state snapshot
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import select

from server.auth import get_current_user
from server.database import get_session
from server.models import GameState, User
from server.views import compute_player_view

router = APIRouter(prefix="/api", tags=["view"])


@router.get("/view")
async def get_view(
    ship_id: Optional[int] = Query(None, description="Filter to a single ship"),
    since_tick: Optional[int] = Query(None, description="Events since this tick"),
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Return the player's complete world state snapshot."""
    gs_result = await session.exec(select(GameState))
    gs = gs_result.first()
    current_tick = gs.current_tick if gs else 0

    return await compute_player_view(
        session, current_user, current_tick,
        ship_id=ship_id, since_tick=since_tick,
    )
