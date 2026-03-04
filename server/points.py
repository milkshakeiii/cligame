"""
Points system helpers for Phase 9.

Points are awarded in the tick loop. This module provides the award_points()
helper and tracks damage for kill assist calculations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from server.models import Event, User

from server.models import EventType


def award_points(
    users_by_id: Dict[int, "User"],
    user_id: int,
    amount: float,
    reason: str,
    pending_events: list,
    tick: int,
    ship_id: Optional[int] = None,
) -> None:
    """Award points to a user, mutating the in-memory User object.

    Emits a points_earned event to pending_events.
    """
    from server.models import Event  # local import

    user = users_by_id.get(user_id)
    if user is None or amount <= 0:
        return
    user.points += amount
    pending_events.append(Event(
        tick=tick,
        user_id=user_id,
        ship_id=ship_id,
        event_type=EventType.points_earned,
        message=f"+{amount:.1f} pts ({reason})",
        category="points",
        amount=amount,
        reason=reason,
    ))
