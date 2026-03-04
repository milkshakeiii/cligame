"""
Chat and notifications endpoints.

POST /api/chat            — send a team chat message
GET  /api/notifications   — unified read for action/points/chat events
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import select

from server.auth import get_current_user
from server.database import get_session
from server.models import Event, EventType, GameState, User

router = APIRouter(prefix="/api", tags=["chat"])


class ChatMessage(BaseModel):
    message: str


@router.post("/chat")
async def send_chat(
    body: ChatMessage,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Send a team chat message."""
    if current_user.team_id is None:
        return {"error": "You must be on a team to chat"}

    gs_result = await session.exec(select(GameState))
    gs = gs_result.first()
    current_tick = gs.current_tick if gs else 0

    event = Event(
        tick=current_tick,
        user_id=current_user.id,
        event_type=EventType.command_processed,
        message=body.message,
        category="chat",
        team_id=current_user.team_id,
        username=current_user.username,
    )
    session.add(event)
    await session.commit()

    return {"status": "sent", "tick": current_tick}


@router.get("/notifications")
async def get_notifications(
    since_tick: Optional[int] = Query(None, description="Events since this tick"),
    category: Optional[str] = Query(None, description="Filter: action|points|chat"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Unified notification read endpoint for all event categories."""
    gs_result = await session.exec(select(GameState))
    gs = gs_result.first()
    current_tick = gs.current_tick if gs else 0

    tick_filter = since_tick if since_tick is not None else max(0, current_tick - 100)

    query = select(Event).where(Event.tick >= tick_filter)

    # Scope: own events + team chat
    from sqlalchemy import or_
    if current_user.team_id is not None:
        query = query.where(
            or_(
                Event.user_id == current_user.id,
                (Event.category == "chat") & (Event.team_id == current_user.team_id),
            )
        )
    else:
        query = query.where(Event.user_id == current_user.id)

    if category is not None:
        query = query.where(Event.category == category)

    query = query.order_by(Event.tick.desc(), Event.id.desc()).limit(limit)

    result = await session.exec(query)
    events = []
    for e in result.all():
        entry = {
            "id": e.id,
            "tick": e.tick,
            "category": getattr(e, 'category', 'action') or 'action',
            "type": e.event_type.value if hasattr(e.event_type, "value") else e.event_type,
            "message": e.message,
            "ship_id": e.ship_id,
        }
        cat = entry["category"]
        if cat == "points":
            entry["amount"] = e.amount
            entry["reason"] = e.reason
        elif cat == "chat":
            entry["username"] = e.username
            entry["team_id"] = e.team_id
        events.append(entry)

    return events
