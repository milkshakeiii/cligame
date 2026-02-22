"""
Resource transfer route.

POST /api/ships/{id}/transfer — initiate an ore transfer to another ship.

The tick loop handles continuous per-tick transfer; this endpoint validates
preconditions and records a TransferOrder as an active movement order targeting
the destination ship.  Since the transfer logic is driven by the tick loop's
``tick_ore_transfer`` function (called when ships are within 100 m), this
endpoint simply validates the request and queues an approach-to-transfer
movement order, or performs an immediate single-tick transfer if already in range.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.auth import get_current_user
from server.database import get_session
from server.models import (
    Event,
    EventType,
    GameState,
    Spaceship,
    User,
)
from server.mining import tick_ore_transfer
from server.routes.common import get_owned_ship as _get_owned_ship_common

router = APIRouter(prefix="/api/ships", tags=["resources"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TransferRequest(BaseModel):
    target_ship_id: int


class TransferResponse(BaseModel):
    transferred: float
    source_ore: float
    target_ore: float
    complete: bool
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_owned_ship_with_modules(ship_id: int, user: User, session) -> Spaceship:
    return await _get_owned_ship_common(
        ship_id,
        user,
        session,
        selectinload(Spaceship.modules),
    )


async def _get_current_tick(session) -> int:
    result = await session.exec(select(GameState))
    gs = result.first()
    return gs.current_tick if gs else 0


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/{ship_id}/transfer", response_model=TransferResponse)
async def transfer_ore(
    ship_id: int,
    body: TransferRequest,
    current_user: User = Depends(get_current_user),
    session=Depends(get_session),
):
    """
    Attempt to transfer ore from this ship to the target ship.

    Calls ``tick_ore_transfer`` from the mining module for a single-tick
    transfer burst.  The tick loop will also run transfers automatically
    each tick as long as the ships remain in range.

    Requirements:
    - Target ship must have a Resource Drop-off module.
    - Both ships must be within 100 m of each other.
    - Source ship must have ore.
    - Target ship must have cargo capacity available.
    """
    if ship_id == body.target_ship_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot transfer ore to the same ship",
        )

    source = await _get_owned_ship_with_modules(ship_id, current_user, session)

    # Load target (any ship, not necessarily owned by current user)
    target_result = await session.exec(
        select(Spaceship)
        .where(Spaceship.id == body.target_ship_id)
        .options(selectinload(Spaceship.modules))
    )
    target = target_result.first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target ship not found")

    # I9: Loop until all ore is transferred (up to cargo capacity) in one request
    total_transferred = 0.0
    last_result: dict = {"transferred": 0.0, "complete": False, "error": None}
    while True:
        last_result = tick_ore_transfer(source, target)
        if last_result["error"]:
            if total_transferred == 0:
                # Only raise if nothing was transferred at all
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail=last_result["error"],
                )
            break
        total_transferred += last_result["transferred"]
        if last_result["complete"] or last_result["transferred"] == 0:
            break

    if total_transferred > 0:
        tick = await _get_current_tick(session)
        event = Event(
            tick=tick,
            user_id=current_user.id,
            ship_id=source.id,
            event_type=EventType.transfer_complete,
            message=(
                f"Transferred {total_transferred:.0f} ore to ship "
                f"#{target.id} ({target.name})"
            ),
        )
        session.add(event)

    await session.commit()

    return TransferResponse(
        transferred=total_transferred,
        source_ore=source.ore,
        target_ore=target.ore,
        complete=last_result["complete"],
        message=(
            f"Transferred {total_transferred:.0f} ore to {target.name}"
            if total_transferred > 0
            else "No ore transferred"
        ),
    )
