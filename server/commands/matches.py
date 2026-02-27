"""Command handlers for matches: start_match, surrender."""

from __future__ import annotations

from sqlmodel import select
from sqlalchemy.orm import selectinload

from server.commands import CommandRejected, TickContext, get_payload, register_handler
from server.match import cleanup_match_assignments, create_match_mothership, generate_match_map
from server.models import (
    Command,
    EventType,
    GameState,
    Match,
    MatchStatus,
    Team,
    User,
)


@register_handler("start_match")
async def handle_start_match(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    match_id = payload.get("match_id")
    if match_id is None:
        raise CommandRejected("match_id is required")

    result = await ctx.session.exec(select(Match).where(Match.id == match_id))
    match = result.first()
    if match is None:
        raise CommandRejected("Match not found")
    if match.status != MatchStatus.pending.value:
        raise CommandRejected("Match is not in pending state")
    if match.team1_id is None or match.team2_id is None:
        raise CommandRejected("Match needs two teams before starting")

    # Load user to check participation
    user_result = await ctx.session.exec(select(User).where(User.id == cmd.user_id))
    user = user_result.first()
    if user.team_id not in (match.team1_id, match.team2_id):
        raise CommandRejected("Only match participants can start the match")

    # Load teams with users
    t1_result = await ctx.session.exec(
        select(Team).where(Team.id == match.team1_id).options(selectinload(Team.users))
    )
    team1 = t1_result.first()
    t2_result = await ctx.session.exec(
        select(Team).where(Team.id == match.team2_id).options(selectinload(Team.users))
    )
    team2 = t2_result.first()

    if not team1 or not team1.users:
        raise CommandRejected("Team 1 has no players")
    if not team2 or not team2.users:
        raise CommandRejected("Team 2 has no players")

    current_tick = ctx.current_tick

    # Generate match map
    await generate_match_map(ctx.session, match, team1, team2, current_tick)

    # Create motherships
    ms1 = await create_match_mothership(
        ctx.session, team1, (-800_000.0, 0.0, 0.0), match.id, current_tick,
    )
    ms2 = await create_match_mothership(
        ctx.session, team2, (800_000.0, 0.0, 0.0), match.id, current_tick,
    )

    match.status = MatchStatus.active.value
    match.started_at_tick = current_tick
    match.team1_mothership_id = ms1.id
    match.team2_mothership_id = ms2.id

    # Initialize relationship collections for motherships so tick phases
    # don't trigger lazy-loads (MissingGreenlet) in async context.
    # Note: do NOT use hasattr() to check — it triggers the lazy load itself.
    for ms in (ms1, ms2):
        ms.movement_orders = []
        ms.build_orders = []
        ms.target_locks = []

    # Add motherships to ctx
    ctx.ships.append(ms1)
    ctx.ships.append(ms2)
    ctx.invalidate_ship_map()

    # Emit events
    for u in team1.users + team2.users:
        ctx.emit(EventType.match_started, f"Match '{match.name}' has started!",
                 user_id=u.id)


@register_handler("surrender")
async def handle_surrender(ctx: TickContext, cmd: Command) -> None:
    payload = get_payload(cmd)
    match_id = payload.get("match_id")
    if match_id is None:
        raise CommandRejected("match_id is required")

    result = await ctx.session.exec(select(Match).where(Match.id == match_id))
    match = result.first()
    if match is None:
        raise CommandRejected("Match not found")
    if match.status != MatchStatus.active.value:
        raise CommandRejected("Match is not active")

    # Which team?
    user_result = await ctx.session.exec(select(User).where(User.id == cmd.user_id))
    user = user_result.first()
    user_team_id = user.team_id
    if user_team_id == match.team1_id:
        team_side = 1
    elif user_team_id == match.team2_id:
        team_side = 2
    else:
        raise CommandRejected("You are not in this match")

    # Parse existing votes
    if team_side == 1:
        existing_votes = set(filter(None, match.surrender_votes_team1.split(",")))
    else:
        existing_votes = set(filter(None, match.surrender_votes_team2.split(",")))

    user_id_str = str(cmd.user_id)
    if user_id_str in existing_votes:
        raise CommandRejected("Already voted to surrender")

    existing_votes.add(user_id_str)

    if team_side == 1:
        match.surrender_votes_team1 = ",".join(existing_votes)
    else:
        match.surrender_votes_team2 = ",".join(existing_votes)

    # Count team members
    team_users_result = await ctx.session.exec(
        select(User.id).where(User.team_id == user_team_id)
    )
    team_user_ids = list(team_users_result.all())
    total_members = len(team_user_ids)
    needed = (total_members // 2) + 1
    vote_count = len(existing_votes)

    if vote_count >= needed:
        # Surrender — other team wins
        match.status = MatchStatus.completed.value
        match.ended_at_tick = ctx.current_tick
        match.winner_team_id = match.team2_id if team_side == 1 else match.team1_id

        # Get all user IDs for events
        all_t1 = await ctx.session.exec(select(User.id).where(User.team_id == match.team1_id))
        all_t2 = await ctx.session.exec(select(User.id).where(User.team_id == match.team2_id))
        all_user_ids = list(all_t1.all()) + list(all_t2.all())

        winner_result = await ctx.session.exec(
            select(Team).where(Team.id == match.winner_team_id)
        )
        winner_team = winner_result.first()
        winner_name = winner_team.name if winner_team else "Unknown"

        for uid in all_user_ids:
            ctx.emit(
                EventType.match_ended,
                f"Match '{match.name}' ended! Winner: {winner_name} (surrender)",
                user_id=uid,
            )

        await cleanup_match_assignments(ctx.session, match)
        # Sync ctx: remove destroyed match ships so later tick phases see consistent state
        ctx.ships = [s for s in ctx.ships if not s.is_destroyed]
        ctx.invalidate_ship_map()
    else:
        ctx.emit(
            EventType.surrender_vote,
            f"Surrender vote cast ({vote_count}/{needed} needed)",
            user_id=cmd.user_id,
        )
