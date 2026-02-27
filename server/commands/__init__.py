"""
Intent-based command processing infrastructure.

The tick loop is the sole writer of game state. Request handlers enqueue
commands via POST /api/commands.  At the start of each tick the loop drains
the queue and dispatches to registered handlers.

Public API:
    TickContext      — wraps all in-memory state for a single tick
    CommandRejected  — raised by handlers when a precondition fails
    process_commands — drain + dispatch (called from tick loop)
    COMMAND_HANDLERS — registry populated by @register_handler
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from server.models import (
    CelestialObject,
    Command,
    CommandStatus,
    Event,
    EventType,
    LeechDebuff,
    PendingMissile,
    Spaceship,
    WeaponAssignment,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TickContext — passed to every handler
# ---------------------------------------------------------------------------


@dataclass
class TickContext:
    """All in-memory state for the current tick, shared across handlers."""

    session: AsyncSession
    ships: list[Spaceship]
    celestial_objects: list[CelestialObject]
    weapon_assignments: list[WeaponAssignment]
    pending_missiles: list[PendingMissile]
    active_leeches: list[LeechDebuff]
    current_tick: int
    pending_events: list[Event]

    # Lazy-built lookup caches (populated on first access)
    _ship_map: dict[int, Spaceship] = field(default_factory=dict, repr=False)
    _ship_map_dirty: bool = field(default=True, repr=False)

    @property
    def ship_map(self) -> dict[int, Spaceship]:
        if self._ship_map_dirty or not self._ship_map:
            self._ship_map = {s.id: s for s in self.ships}
            self._ship_map_dirty = False
        return self._ship_map

    def invalidate_ship_map(self) -> None:
        """Call after adding/removing ships from ctx.ships."""
        self._ship_map_dirty = True

    def find_ship(self, ship_id: int, user_id: int) -> Spaceship:
        """Find ship in in-memory list, verify ownership. Raises CommandRejected."""
        ship = self.ship_map.get(ship_id)
        if ship is None:
            raise CommandRejected(f"Ship #{ship_id} not found or destroyed")
        if ship.user_id != user_id:
            raise CommandRejected(f"Ship #{ship_id} is not yours")
        return ship

    def find_any_ship(self, ship_id: int) -> Spaceship:
        """Find ship in in-memory list without ownership check."""
        ship = self.ship_map.get(ship_id)
        if ship is None:
            raise CommandRejected(f"Ship #{ship_id} not found or destroyed")
        return ship

    def emit(
        self,
        event_type: EventType,
        message: str,
        user_id: int,
        ship_id: Optional[int] = None,
    ) -> None:
        """Append event to pending_events."""
        self.pending_events.append(
            Event(
                tick=self.current_tick,
                user_id=user_id,
                ship_id=ship_id,
                event_type=event_type,
                message=message,
            )
        )


# ---------------------------------------------------------------------------
# CommandRejected exception
# ---------------------------------------------------------------------------


class CommandRejected(Exception):
    """Raised by a command handler when a precondition fails."""
    pass


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

COMMAND_HANDLERS: dict[str, Callable] = {}


def register_handler(command_type: str):
    """Decorator to register a command handler function.

    Usage::

        @register_handler("install_module")
        async def handle_install_module(ctx: TickContext, cmd: Command) -> None:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        if command_type in COMMAND_HANDLERS:
            raise ValueError(f"Duplicate handler for {command_type!r}")
        COMMAND_HANDLERS[command_type] = fn
        return fn
    return decorator


def get_payload(cmd: Command) -> dict[str, Any]:
    """Parse the JSON payload of a command."""
    try:
        return json.loads(cmd.payload) if cmd.payload else {}
    except json.JSONDecodeError:
        raise CommandRejected("Malformed command payload")


# ---------------------------------------------------------------------------
# process_commands — called once per tick
# ---------------------------------------------------------------------------


async def process_commands(ctx: TickContext) -> None:
    """Drain pending commands, dispatch to handlers, mark processed/rejected."""
    result = await ctx.session.exec(
        select(Command)
        .where(Command.status == CommandStatus.pending.value)
        .order_by(Command.id)  # FIFO
    )
    commands = result.all()

    for cmd in commands:
        # Cache attributes before handler runs — avoids lazy-load issues after
        # a handler crash leaves the session in a broken state.
        cmd_id = cmd.id
        cmd_type = cmd.command_type
        cmd_user_id = cmd.user_id
        cmd_ship_id = cmd.ship_id

        handler = COMMAND_HANDLERS.get(cmd_type)
        if handler is None:
            cmd.status = CommandStatus.rejected.value
            cmd.rejection_reason = f"Unknown command type: {cmd_type}"
            cmd.processed_at_tick = ctx.current_tick
            ctx.emit(
                EventType.command_rejected,
                f"Unknown command: {cmd_type}",
                user_id=cmd_user_id,
                ship_id=cmd_ship_id,
            )
            continue

        try:
            await handler(ctx, cmd)
            cmd.status = CommandStatus.processed.value
            cmd.processed_at_tick = ctx.current_tick
        except CommandRejected as e:
            cmd.status = CommandStatus.rejected.value
            cmd.rejection_reason = str(e)
            cmd.processed_at_tick = ctx.current_tick
            ctx.emit(
                EventType.command_rejected,
                str(e),
                user_id=cmd_user_id,
                ship_id=cmd_ship_id,
            )
        except Exception as e:
            # Rollback the broken transaction so we can continue processing
            await ctx.session.rollback()
            logger.exception("Unexpected error processing command #%s (%s)", cmd_id, cmd_type)
            # Re-fetch the command after rollback (it was detached)
            refetch = await ctx.session.exec(
                select(Command).where(Command.id == cmd_id)
            )
            cmd = refetch.first()
            if cmd:
                cmd.status = CommandStatus.rejected.value
                cmd.rejection_reason = f"Internal error: {type(e).__name__}"
                cmd.processed_at_tick = ctx.current_tick
                await ctx.session.flush()
            ctx.emit(
                EventType.command_rejected,
                f"Internal error processing {cmd_type}",
                user_id=cmd_user_id,
                ship_id=cmd_ship_id,
            )


# ---------------------------------------------------------------------------
# Auto-import all handler modules so decorators execute on import
# ---------------------------------------------------------------------------

from server.commands import (  # noqa: E402, F401
    ships,
    movement,
    modules,
    combat,
    production,
    resources,
    research,
    autopilot,
    matches,
)
