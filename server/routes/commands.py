"""
Command endpoints.

POST /api/commands  — enqueue a command (returns 202)
GET  /api/commands  — list player's commands (with optional status filter)
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import select

from server.auth import get_current_user
from server.database import get_session
from server.models import Command, CommandStatus, CommandType, User

router = APIRouter(prefix="/api/commands", tags=["commands"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CommandRequest(BaseModel):
    type: str
    ship_id: Optional[int] = None
    payload: dict = {}


class CommandOut(BaseModel):
    command_id: int
    type: str
    ship_id: Optional[int]
    status: str
    message: str
    rejection_reason: Optional[str] = None
    processed_at_tick: Optional[int] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_command(
    body: CommandRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """Enqueue a command for processing by the tick loop."""
    # Validate command type
    try:
        CommandType(body.type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown command type: {body.type}",
        )

    cmd = Command(
        user_id=current_user.id,
        ship_id=body.ship_id,
        command_type=body.type,
        payload=json.dumps(body.payload),
    )
    session.add(cmd)
    await session.commit()
    await session.refresh(cmd)

    return CommandOut(
        command_id=cmd.id,
        type=cmd.command_type,
        ship_id=cmd.ship_id,
        status=cmd.status,
        message="Command queued. Check view next tick for results.",
    )


@router.get("")
async def list_commands(
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """List player's commands with optional status filter."""
    query = (
        select(Command)
        .where(Command.user_id == current_user.id)
        .order_by(Command.id.desc())
        .limit(limit)
    )
    if status_filter:
        query = query.where(Command.status == status_filter)

    result = await session.exec(query)
    commands = result.all()

    return [
        CommandOut(
            command_id=cmd.id,
            type=cmd.command_type,
            ship_id=cmd.ship_id,
            status=cmd.status,
            message=(
                cmd.rejection_reason
                if cmd.status == CommandStatus.rejected.value and cmd.rejection_reason
                else f"Command {cmd.status}"
            ),
            rejection_reason=cmd.rejection_reason,
            processed_at_tick=cmd.processed_at_tick,
        )
        for cmd in commands
    ]
