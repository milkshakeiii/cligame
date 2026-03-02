"""
Shared helpers for route files.

Provides a reusable ``get_owned_ship`` function that handles ship lookup,
ownership verification, and optional eager-loading of related models.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.models import Spaceship, User


async def get_owned_ship(
    ship_id: int,
    user: User,
    session,
    *load_options,
) -> Spaceship:
    """
    Fetch a ship by ID and verify it belongs to the given user.

    Pass SQLAlchemy ``selectinload`` options as positional arguments after
    ``session`` to eager-load relationships.  For example::

        ship = await get_owned_ship(
            ship_id, user, session,
            selectinload(Spaceship.modules),
            selectinload(Spaceship.movement_orders),
        )

    Raises HTTP 404 if the ship does not exist, HTTP 403 if it is not owned
    by the user.
    """
    q = select(Spaceship).where(Spaceship.id == ship_id)
    if load_options:
        q = q.options(*load_options)

    result = await session.exec(q)
    ship = result.first()

    if ship is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ship not found")
    is_owner = ship.user_id == user.id or ship.claimed_by_user_id == user.id
    is_teammate = ship.team_id is not None and ship.team_id == user.team_id
    if not is_owner and not is_teammate:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your ship")

    return ship
