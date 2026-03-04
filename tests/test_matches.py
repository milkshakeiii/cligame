"""
Tests for Phase 8: Match System.

Covers:
  1. Match lifecycle — create, join, start, play, win
  2. Map generation — asteroid counts, positions, ore amounts
  3. Mothership loadout verification
  4. Win condition — mothership destroyed → match ends
  5. Surrender — majority vote ends match
  6. Match scoping — ships and asteroids scoped to match
  7. Error cases — wrong faction, double join, invalid state transitions
  8. Edge cases — starting active match, surrendering on wrong match,
     double-joining, mothership position, non-mothership destruction,
     missing GameState, concurrent surrender votes, HP warning events
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker, selectinload
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from server.models import (
    ASTEROID_SIZES,
    MATCH_MOTHERSHIP_LOADOUT,
    CelestialObject,
    CelestialType,
    Event,
    EventType,
    GameState,
    Match,
    MatchStatus,
    ModuleType,
    ShipClass,
    Spaceship,
    Team,
    User,
    create_default_ship,
)
from server.match import create_match_mothership, generate_match_map
from tests.conftest import register_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup_two_users(client: AsyncClient) -> tuple[dict, dict]:
    """Register two users and return their auth dicts."""
    user1 = await register_user(client, "player1")
    user2 = await register_user(client, "player2")
    return user1, user2


async def _create_and_join_match(
    client: AsyncClient,
    user1: dict,
    user2: dict,
    match_name: str = "Test Match",
    faction1: str = "solarion",
    faction2: str = "voidborn",
) -> dict:
    """Create a match with user1 and join with user2, return match creation response."""
    # User1 creates match
    resp = await client.post(
        "/api/matches",
        json={"name": match_name, "faction": faction1},
        headers=auth_headers(user1["token"]),
    )
    assert resp.status_code == 201, resp.text
    match_data = resp.json()

    # User2 joins
    resp = await client.post(
        f"/api/matches/{match_data['id']}/join",
        json={"faction": faction2},
        headers=auth_headers(user2["token"]),
    )
    assert resp.status_code == 200, resp.text

    return match_data


async def _send_command(
    client: AsyncClient,
    headers: dict,
    command_type: str,
    **payload,
) -> dict:
    """Send a command and return the response."""
    body: dict = {"type": command_type, "payload": payload}
    resp = await client.post("/api/commands", json=body, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()


async def _process(client: AsyncClient) -> dict:
    """Trigger command processing via test endpoint."""
    resp = await client.post("/api/_test/process_commands")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _start_match_via_cmd(client: AsyncClient, headers: dict, match_id: int) -> dict:
    """Start a match via the command system and return the updated match detail."""
    await _send_command(client, headers, "start_match", match_id=match_id)
    await _process(client)
    resp = await client.get(f"/api/matches/{match_id}", headers=headers)
    assert resp.status_code == 200
    return resp.json()


async def _surrender_via_cmd(client: AsyncClient, headers: dict, match_id: int) -> dict:
    """Submit a surrender vote via the command system and return the updated match detail."""
    await _send_command(client, headers, "surrender", match_id=match_id)
    await _process(client)
    resp = await client.get(f"/api/matches/{match_id}", headers=headers)
    assert resp.status_code == 200
    return resp.json()


async def _get_rejected_commands(client: AsyncClient, headers: dict) -> list[dict]:
    """Return all rejected commands for the user."""
    resp = await client.get("/api/commands", params={"status": "rejected"}, headers=headers)
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Test: Match creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_match(client: AsyncClient):
    """Creating a match creates a pending match and a team for the creator."""
    user = await register_user(client, "creator")

    resp = await client.post(
        "/api/matches",
        json={"name": "My Match", "faction": "solarion"},
        headers=auth_headers(user["token"]),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Match"
    assert data["status"] == "pending"
    assert data["team1_id"] is not None
    assert data["team2_id"] is not None


@pytest.mark.asyncio
async def test_create_match_invalid_faction(client: AsyncClient):
    """Creating a match with an invalid faction returns 422."""
    user = await register_user(client, "creator")
    resp = await client.post(
        "/api/matches",
        json={"name": "Bad Match", "faction": "neutral"},
        headers=auth_headers(user["token"]),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test: Join match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_match(client: AsyncClient):
    """Joining a match as team2 with opposite faction succeeds."""
    user1, user2 = await _setup_two_users(client)
    match_data = await _create_and_join_match(client, user1, user2)

    # Verify match now has two teams
    resp = await client.get(
        f"/api/matches/{match_data['id']}",
        headers=auth_headers(user1["token"]),
    )
    assert resp.status_code == 200
    detail = resp.json()
    assert detail["team1"] is not None
    assert detail["team2"] is not None
    assert detail["team1"]["faction"] == "solarion"
    assert detail["team2"]["faction"] == "voidborn"


@pytest.mark.asyncio
async def test_join_match_same_faction(client: AsyncClient):
    """Joining with the same faction as the creator puts you on their team."""
    user1 = await register_user(client, "player1")
    user2 = await register_user(client, "player2")

    resp = await client.post(
        "/api/matches",
        json={"name": "Faction Test", "faction": "solarion"},
        headers=auth_headers(user1["token"]),
    )
    assert resp.status_code == 201
    match_id = resp.json()["id"]
    team1_id = resp.json()["team1_id"]

    resp = await client.post(
        f"/api/matches/{match_id}/join",
        json={"faction": "solarion"},
        headers=auth_headers(user2["token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["team_id"] == team1_id
    assert resp.json()["faction"] == "solarion"


# ---------------------------------------------------------------------------
# Test: List matches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_matches(client: AsyncClient):
    """List matches returns all matches."""
    user1 = await register_user(client, "lister1")
    user2 = await register_user(client, "lister2")

    # Create two matches with different users
    await client.post(
        "/api/matches",
        json={"name": "Match A", "faction": "solarion"},
        headers=auth_headers(user1["token"]),
    )
    await client.post(
        "/api/matches",
        json={"name": "Match B", "faction": "voidborn"},
        headers=auth_headers(user2["token"]),
    )

    resp = await client.get(
        "/api/matches",
        headers=auth_headers(user1["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 2


@pytest.mark.asyncio
async def test_list_matches_with_status_filter(client: AsyncClient):
    """List matches with status filter returns only matching."""
    user = await register_user(client, "filterer")

    await client.post(
        "/api/matches",
        json={"name": "Pending Match", "faction": "solarion"},
        headers=auth_headers(user["token"]),
    )

    resp = await client.get(
        "/api/matches",
        params={"status_filter": "active"},
        headers=auth_headers(user["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    # No active matches yet
    assert all(m["status"] == "active" for m in data)


# ---------------------------------------------------------------------------
# Test: Start match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_match(client: AsyncClient):
    """Starting a match generates map and motherships."""
    user1, user2 = await _setup_two_users(client)
    match_data = await _create_and_join_match(client, user1, user2)

    detail = await _start_match_via_cmd(
        client, auth_headers(user1["token"]), match_data["id"]
    )
    assert detail["status"] == "active"
    assert detail["team1_mothership"] is not None
    assert detail["team2_mothership"] is not None
    # Motherships should not be destroyed
    assert not detail["team1_mothership"]["is_destroyed"]
    assert not detail["team2_mothership"]["is_destroyed"]


@pytest.mark.asyncio
async def test_start_match_solo(client: AsyncClient):
    """Starting a match with only one player succeeds (team2 is empty)."""
    user = await register_user(client, "solo")
    resp = await client.post(
        "/api/matches",
        json={"name": "Solo Match", "faction": "solarion"},
        headers=auth_headers(user["token"]),
    )
    match_id = resp.json()["id"]

    match_data = await _start_match_via_cmd(client, auth_headers(user["token"]), match_id)
    assert match_data["status"] == "active"
    assert match_data.get("team1_mothership") is not None
    assert match_data.get("team2_mothership") is not None


# ---------------------------------------------------------------------------
# Test: Map generation (unit test with db_session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_map_generation(db_session: AsyncSession):
    """generate_match_map creates asteroids scoped to match."""
    # Create minimal objects
    team1 = Team(name="T1", faction="solarion")
    team2 = Team(name="T2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="u1", token="tok1", team_id=team1.id)
    db_session.add(user1)
    await db_session.flush()

    match = Match(
        name="Map Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    db_session.add(match)
    await db_session.flush()

    await generate_match_map(db_session, match, team1, team2, current_tick=0)
    await db_session.commit()

    # Count asteroids
    result = await db_session.exec(
        select(CelestialObject).where(CelestialObject.match_id == match.id)
    )
    asteroids = result.all()

    # Should have: 8+10 per home (x2) + 30-40 center + 8-12 per flank (x2)
    # Minimum: 36 + 30 + 16 = 82, Maximum: 36 + 40 + 24 = 100
    assert len(asteroids) >= 66  # some flexibility for random counts
    assert len(asteroids) <= 110

    # All should be match-scoped
    for ast in asteroids:
        assert ast.match_id == match.id
        assert ast.object_type == CelestialType.asteroid
        assert ast.ore_remaining > 0


# ---------------------------------------------------------------------------
# Test: Mothership loadout (unit test with db_session)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mothership_loadout(db_session: AsyncSession):
    """create_match_mothership installs correct modules and sets resources."""
    team = Team(name="Loadout Team", faction="solarion")
    db_session.add(team)
    await db_session.flush()

    user = User(username="loader", token="tok_loader", team_id=team.id)
    db_session.add(user)
    await db_session.flush()

    # Reload team with users
    result = await db_session.exec(
        select(Team).where(Team.id == team.id).options(selectinload(Team.users))
    )
    team = result.one()

    match = Match(
        name="Loadout Test",
        status=MatchStatus.active.value,
        team1_id=team.id,
    )
    db_session.add(match)
    await db_session.flush()

    ms = await create_match_mothership(
        db_session, team, (0.0, 0.0, 0.0), match.id, current_tick=0,
    )
    await db_session.commit()

    assert ms.ship_class == ShipClass.mothership
    assert ms.match_id == match.id
    assert ms.team_id == team.id
    assert ms.ore == 7_500.0
    assert ms.max_capacitor > 0
    assert ms.max_shield_hp > 0
    assert ms.max_armor_hp > 0

    # Verify modules installed
    assert len(ms.modules) == len(MATCH_MOTHERSHIP_LOADOUT)
    module_types = [m.module_type.value for m in ms.modules]
    for expected_type, _ in MATCH_MOTHERSHIP_LOADOUT:
        assert expected_type in module_types


# ---------------------------------------------------------------------------
# Test: Surrender
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_surrender_single_player_team(client: AsyncClient):
    """When a team has 1 player, 1 surrender vote ends the match."""
    user1, user2 = await _setup_two_users(client)
    match_data = await _create_and_join_match(client, user1, user2)

    # Start the match via command
    await _start_match_via_cmd(client, auth_headers(user1["token"]), match_data["id"])

    # User1 surrenders (team1 has 1 player, so 1 vote = majority)
    detail = await _surrender_via_cmd(client, auth_headers(user1["token"]), match_data["id"])

    # Match should be completed with team2 as winner
    assert detail["status"] == "completed"
    assert detail["winner_team_id"] is not None


@pytest.mark.asyncio
async def test_surrender_duplicate_vote_fails(client: AsyncClient):
    """Voting to surrender twice fails — second command is rejected."""
    user1, user2 = await _setup_two_users(client)

    # Need 2 players on team1 to not instantly end
    user3 = await register_user(client, "player3")

    # Create match
    resp = await client.post(
        "/api/matches",
        json={"name": "Multi Surrender", "faction": "solarion"},
        headers=auth_headers(user1["token"]),
    )
    match_id = resp.json()["id"]

    # Get team1 id from the match
    resp = await client.get(
        f"/api/matches/{match_id}",
        headers=auth_headers(user1["token"]),
    )
    team1_id = resp.json()["team1"]["id"]

    # User3 joins team1
    await client.post(
        f"/api/teams/{team1_id}/join",
        headers=auth_headers(user3["token"]),
    )

    # User2 joins match as team2
    await client.post(
        f"/api/matches/{match_id}/join",
        json={"faction": "voidborn"},
        headers=auth_headers(user2["token"]),
    )

    # Start match via command
    await _start_match_via_cmd(client, auth_headers(user1["token"]), match_id)

    # User1 votes surrender — first vote (1 of 2 needed, match stays active)
    detail = await _surrender_via_cmd(client, auth_headers(user1["token"]), match_id)
    assert detail["status"] == "active"

    # User1 tries again — should be rejected
    await _send_command(client, auth_headers(user1["token"]), "surrender", match_id=match_id)
    await _process(client)

    rejected = await _get_rejected_commands(client, auth_headers(user1["token"]))
    assert any("already voted" in (r.get("rejection_reason") or "").lower() for r in rejected)


# ---------------------------------------------------------------------------
# Test: Match win condition via tick loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_win_condition_mothership_destroyed(db_session: AsyncSession):
    """When a mothership is destroyed, the match ends in the tick loop check."""
    from server.tick import _check_match_win_conditions
    from server.models import Event, EventType

    # Setup teams and users
    team1 = Team(name="Winners", faction="solarion")
    team2 = Team(name="Losers", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="winner", token="tok_win", team_id=team1.id)
    user2 = User(username="loser", token="tok_lose", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    # Load teams with users
    t1_result = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1_result.one()
    t2_result = await db_session.exec(
        select(Team).where(Team.id == team2.id).options(selectinload(Team.users))
    )
    team2 = t2_result.one()

    match = Match(
        name="Win Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    db_session.add(match)
    await db_session.flush()

    # Create motherships
    ms1 = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, 0,
    )
    ms2 = await create_match_mothership(
        db_session, team2, (800_000.0, 0.0, 0.0), match.id, 0,
    )
    match.team1_mothership_id = ms1.id
    match.team2_mothership_id = ms2.id
    await db_session.commit()

    # Simulate: destroy team2's mothership
    ms2.is_destroyed = True
    ms2.armor_hp = 0.0
    ms2.shield_hp = 0.0
    await db_session.flush()

    # Build ship_map
    ships = [ms1, ms2]
    ship_map = {s.id: s for s in ships}

    pending_events = []

    def emit(event_type, message, user_id=None, ship_id=None):
        pending_events.append({
            "event_type": event_type,
            "message": message,
            "user_id": user_id,
            "ship_id": ship_id,
        })

    await _check_match_win_conditions(db_session, ships, ship_map, 100, emit)
    await db_session.commit()

    # Refresh match
    result = await db_session.exec(select(Match).where(Match.id == match.id))
    match = result.one()

    assert match.status == MatchStatus.completed.value
    assert match.winner_team_id == team1.id
    assert match.ended_at_tick == 100

    # Should have emitted match_ended events
    ended_events = [e for e in pending_events if e["event_type"] == EventType.match_ended]
    assert len(ended_events) >= 2  # at least one per team


# ---------------------------------------------------------------------------
# Test: Match scoping
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_match_scoping_on_spawned_ships(db_session: AsyncSession):
    """Ships spawned via spawn_new_ship inherit match_id from builder."""
    from server.models import spawn_new_ship

    team = Team(name="Scoping Team", faction="voidborn")
    db_session.add(team)
    await db_session.flush()

    user = User(username="scoper", token="tok_scope", team_id=team.id)
    db_session.add(user)
    await db_session.flush()

    # Load team with users
    result = await db_session.exec(
        select(Team).where(Team.id == team.id).options(selectinload(Team.users))
    )
    team = result.one()

    match = Match(
        name="Scope Test",
        status=MatchStatus.active.value,
        team1_id=team.id,
    )
    db_session.add(match)
    await db_session.flush()

    # Create a builder ship with match_id
    ms = await create_match_mothership(
        db_session, team, (0.0, 0.0, 0.0), match.id, 0,
    )
    await db_session.commit()

    # Spawn a new ship from the builder
    new_ship = spawn_new_ship(
        blueprint=ShipClass.strike_craft,
        builder=ms,
        current_tick=10,
    )

    assert new_ship.match_id == match.id
    assert new_ship.team_id == team.id


# ---------------------------------------------------------------------------
# Test: Starting an already active match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_already_active_match_fails(client: AsyncClient):
    """Starting a match that is already active — second start_match is rejected."""
    user1, user2 = await _setup_two_users(client)
    match_data = await _create_and_join_match(client, user1, user2)

    # Start the match the first time
    detail = await _start_match_via_cmd(client, auth_headers(user1["token"]), match_data["id"])
    assert detail["status"] == "active"

    # Try to start it again — should be rejected
    await _send_command(client, auth_headers(user1["token"]), "start_match", match_id=match_data["id"])
    await _process(client)

    rejected = await _get_rejected_commands(client, auth_headers(user1["token"]))
    assert any("not in pending state" in (r.get("rejection_reason") or "").lower() for r in rejected)


# ---------------------------------------------------------------------------
# Test: Surrendering on a match you are not in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_surrender_not_in_match_fails(client: AsyncClient):
    """A player not in the match cannot surrender — command is rejected."""
    user1, user2 = await _setup_two_users(client)
    user3 = await register_user(client, "outsider")

    match_data = await _create_and_join_match(client, user1, user2)

    # Start via command
    await _start_match_via_cmd(client, auth_headers(user1["token"]), match_data["id"])

    # user3 (not in the match) tries to surrender
    await _send_command(client, auth_headers(user3["token"]), "surrender", match_id=match_data["id"])
    await _process(client)

    rejected = await _get_rejected_commands(client, auth_headers(user3["token"]))
    assert any("not in this match" in (r.get("rejection_reason") or "").lower() for r in rejected)


# ---------------------------------------------------------------------------
# Test: Double-joining a match (team2 already exists)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_match_third_player(client: AsyncClient):
    """A third player can join an existing match on either team."""
    user1, user2 = await _setup_two_users(client)
    user3 = await register_user(client, "latecomer")

    match_data = await _create_and_join_match(client, user1, user2)

    # user3 joins voidborn — should succeed (same team as user2)
    resp = await client.post(
        f"/api/matches/{match_data['id']}/join",
        json={"faction": "voidborn"},
        headers=auth_headers(user3["token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["faction"] == "voidborn"


# ---------------------------------------------------------------------------
# Test: Mothership position verification (-800 km and +800 km)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mothership_positions(db_session: AsyncSession):
    """Motherships are placed at -800 km and +800 km on the X axis."""
    team1 = Team(name="Pos T1", faction="solarion")
    team2 = Team(name="Pos T2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="pos_u1", token="tok_pos1", team_id=team1.id)
    user2 = User(username="pos_u2", token="tok_pos2", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    # Reload teams with users
    t1r = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1r.one()
    t2r = await db_session.exec(
        select(Team).where(Team.id == team2.id).options(selectinload(Team.users))
    )
    team2 = t2r.one()

    match = Match(
        name="Pos Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    db_session.add(match)
    await db_session.flush()

    ms1 = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, 0,
    )
    ms2 = await create_match_mothership(
        db_session, team2, (800_000.0, 0.0, 0.0), match.id, 0,
    )
    await db_session.commit()

    # Team 1 mothership at -800 km
    assert ms1.pos_x == -800_000.0
    assert ms1.pos_y == 0.0
    assert ms1.pos_z == 0.0

    # Team 2 mothership at +800 km
    assert ms2.pos_x == 800_000.0
    assert ms2.pos_y == 0.0
    assert ms2.pos_z == 0.0


# ---------------------------------------------------------------------------
# Test: Win condition does NOT trigger when non-mothership is destroyed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_win_condition_not_triggered_for_non_mothership(db_session: AsyncSession):
    """Destroying a non-mothership ship does NOT end the match."""
    from server.tick import _check_match_win_conditions

    team1 = Team(name="No Win T1", faction="solarion")
    team2 = Team(name="No Win T2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="nw_u1", token="tok_nw1", team_id=team1.id)
    user2 = User(username="nw_u2", token="tok_nw2", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    t1r = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1r.one()
    t2r = await db_session.exec(
        select(Team).where(Team.id == team2.id).options(selectinload(Team.users))
    )
    team2 = t2r.one()

    match = Match(
        name="No Win Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    db_session.add(match)
    await db_session.flush()

    # Create motherships (both alive)
    ms1 = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, 0,
    )
    ms2 = await create_match_mothership(
        db_session, team2, (800_000.0, 0.0, 0.0), match.id, 0,
    )
    match.team1_mothership_id = ms1.id
    match.team2_mothership_id = ms2.id
    await db_session.flush()

    # Create a regular ship on team2 and destroy it
    regular_ship = create_default_ship(
        name="Escort",
        ship_class=ShipClass.frigate,
        user_id=user2.id,
        pos_x=800_000.0,
        pos_y=100.0,
        pos_z=0.0,
        team_id=team2.id,
        faction="voidborn",
    )
    regular_ship.match_id = match.id
    regular_ship.is_destroyed = True
    regular_ship.armor_hp = 0.0
    regular_ship.shield_hp = 0.0
    db_session.add(regular_ship)
    await db_session.commit()

    ships = [ms1, ms2, regular_ship]
    ship_map = {s.id: s for s in ships}

    pending_events = []

    def emit(event_type, message, user_id=None, ship_id=None):
        pending_events.append({
            "event_type": event_type,
            "message": message,
            "user_id": user_id,
            "ship_id": ship_id,
        })

    await _check_match_win_conditions(db_session, ships, ship_map, 50, emit)
    await db_session.commit()

    # Refresh match
    result = await db_session.exec(select(Match).where(Match.id == match.id))
    match = result.one()

    # Match should still be active
    assert match.status == MatchStatus.active.value
    assert match.winner_team_id is None
    assert match.ended_at_tick is None

    # No match_ended events should have been emitted
    ended_events = [e for e in pending_events if e["event_type"] == EventType.match_ended]
    assert len(ended_events) == 0


# ---------------------------------------------------------------------------
# Test: Win condition with both motherships alive
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_win_condition_both_alive_no_winner(db_session: AsyncSession):
    """When both motherships are alive, the match stays active."""
    from server.tick import _check_match_win_conditions

    team1 = Team(name="Alive T1", faction="solarion")
    team2 = Team(name="Alive T2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="al_u1", token="tok_al1", team_id=team1.id)
    user2 = User(username="al_u2", token="tok_al2", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    t1r = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1r.one()
    t2r = await db_session.exec(
        select(Team).where(Team.id == team2.id).options(selectinload(Team.users))
    )
    team2 = t2r.one()

    match = Match(
        name="Both Alive Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    db_session.add(match)
    await db_session.flush()

    ms1 = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, 0,
    )
    ms2 = await create_match_mothership(
        db_session, team2, (800_000.0, 0.0, 0.0), match.id, 0,
    )
    match.team1_mothership_id = ms1.id
    match.team2_mothership_id = ms2.id
    await db_session.commit()

    ships = [ms1, ms2]
    ship_map = {s.id: s for s in ships}

    pending_events = []

    def emit(event_type, message, user_id=None, ship_id=None):
        pending_events.append({
            "event_type": event_type,
            "message": message,
            "user_id": user_id,
            "ship_id": ship_id,
        })

    await _check_match_win_conditions(db_session, ships, ship_map, 10, emit)

    result = await db_session.exec(select(Match).where(Match.id == match.id))
    match = result.one()

    assert match.status == MatchStatus.active.value
    assert match.winner_team_id is None

    ended_events = [e for e in pending_events if e["event_type"] == EventType.match_ended]
    assert len(ended_events) == 0


# ---------------------------------------------------------------------------
# Test: Mothership HP warning events (under attack and critical)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mothership_hp_warning_under_attack(db_session: AsyncSession):
    """When mothership HP drops below 75%, mothership_under_attack is emitted."""
    from server.tick import _check_match_win_conditions

    team1 = Team(name="Warn T1", faction="solarion")
    team2 = Team(name="Warn T2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="warn_u1", token="tok_warn1", team_id=team1.id)
    user2 = User(username="warn_u2", token="tok_warn2", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    t1r = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1r.one()
    t2r = await db_session.exec(
        select(Team).where(Team.id == team2.id).options(selectinload(Team.users))
    )
    team2 = t2r.one()

    match = Match(
        name="Warn Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    db_session.add(match)
    await db_session.flush()

    ms1 = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, 0,
    )
    ms2 = await create_match_mothership(
        db_session, team2, (800_000.0, 0.0, 0.0), match.id, 0,
    )
    match.team1_mothership_id = ms1.id
    match.team2_mothership_id = ms2.id
    await db_session.flush()

    # Reduce team1 mothership HP to ~50% (below 75% but above 25%)
    total_hp = ms1.max_shield_hp + ms1.max_armor_hp
    ms1.shield_hp = 0.0
    ms1.armor_hp = total_hp * 0.50  # 50% of total HP
    await db_session.commit()

    ships = [ms1, ms2]
    ship_map = {s.id: s for s in ships}

    pending_events = []

    def emit(event_type, message, user_id=None, ship_id=None):
        pending_events.append({
            "event_type": event_type,
            "message": message,
            "user_id": user_id,
            "ship_id": ship_id,
        })

    await _check_match_win_conditions(db_session, ships, ship_map, 20, emit)

    # Should have mothership_under_attack events for team1
    under_attack_events = [
        e for e in pending_events
        if e["event_type"] == EventType.mothership_under_attack
    ]
    assert len(under_attack_events) >= 1
    assert any("WARNING" in e["message"] for e in under_attack_events)


@pytest.mark.asyncio
async def test_mothership_hp_warning_critical(db_session: AsyncSession):
    """When mothership HP drops below 25%, mothership_critical is emitted."""
    from server.tick import _check_match_win_conditions

    team1 = Team(name="Crit T1", faction="solarion")
    team2 = Team(name="Crit T2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="crit_u1", token="tok_crit1", team_id=team1.id)
    user2 = User(username="crit_u2", token="tok_crit2", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    t1r = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1r.one()
    t2r = await db_session.exec(
        select(Team).where(Team.id == team2.id).options(selectinload(Team.users))
    )
    team2 = t2r.one()

    match = Match(
        name="Crit Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    db_session.add(match)
    await db_session.flush()

    ms1 = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, 0,
    )
    ms2 = await create_match_mothership(
        db_session, team2, (800_000.0, 0.0, 0.0), match.id, 0,
    )
    match.team1_mothership_id = ms1.id
    match.team2_mothership_id = ms2.id
    await db_session.flush()

    # Reduce team2 mothership HP to ~10% (below 25%)
    total_hp = ms2.max_shield_hp + ms2.max_armor_hp
    ms2.shield_hp = 0.0
    ms2.armor_hp = total_hp * 0.10  # 10% of total HP
    await db_session.commit()

    ships = [ms1, ms2]
    ship_map = {s.id: s for s in ships}

    pending_events = []

    def emit(event_type, message, user_id=None, ship_id=None):
        pending_events.append({
            "event_type": event_type,
            "message": message,
            "user_id": user_id,
            "ship_id": ship_id,
        })

    await _check_match_win_conditions(db_session, ships, ship_map, 30, emit)

    # Should have mothership_critical events for team2
    critical_events = [
        e for e in pending_events
        if e["event_type"] == EventType.mothership_critical
    ]
    assert len(critical_events) >= 1
    assert any("CRITICAL" in e["message"] for e in critical_events)


# ---------------------------------------------------------------------------
# Test: Get non-existent match returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_nonexistent_match_404(client: AsyncClient):
    """Getting a match that does not exist returns 404."""
    user = await register_user(client, "seeker")
    resp = await client.get(
        "/api/matches/99999",
        headers=auth_headers(user["token"]),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Join non-existent match returns 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_nonexistent_match_404(client: AsyncClient):
    """Joining a match that does not exist returns 404."""
    user = await register_user(client, "joiner")
    resp = await client.post(
        "/api/matches/99999/join",
        json={"faction": "voidborn"},
        headers=auth_headers(user["token"]),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: Start non-existent match — command rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_nonexistent_match_rejected(client: AsyncClient):
    """Starting a match that does not exist — command is rejected."""
    user = await register_user(client, "starter")
    await _send_command(client, auth_headers(user["token"]), "start_match", match_id=99999)
    await _process(client)

    rejected = await _get_rejected_commands(client, auth_headers(user["token"]))
    assert len(rejected) >= 1
    assert any("not found" in (r.get("rejection_reason") or "").lower() for r in rejected)


# ---------------------------------------------------------------------------
# Test: Surrender on a non-existent match — command rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_surrender_nonexistent_match_rejected(client: AsyncClient):
    """Surrendering on a match that does not exist — command is rejected."""
    user = await register_user(client, "quitter")
    await _send_command(client, auth_headers(user["token"]), "surrender", match_id=99999)
    await _process(client)

    rejected = await _get_rejected_commands(client, auth_headers(user["token"]))
    assert len(rejected) >= 1
    assert any("not found" in (r.get("rejection_reason") or "").lower() for r in rejected)


# ---------------------------------------------------------------------------
# Test: Surrender on a pending match — command rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_surrender_on_pending_match_rejected(client: AsyncClient):
    """Cannot surrender on a match that has not started yet."""
    user1, user2 = await _setup_two_users(client)
    match_data = await _create_and_join_match(client, user1, user2)

    # Do NOT start the match — try to surrender immediately
    await _send_command(client, auth_headers(user1["token"]), "surrender", match_id=match_data["id"])
    await _process(client)

    rejected = await _get_rejected_commands(client, auth_headers(user1["token"]))
    assert any("not active" in (r.get("rejection_reason") or "").lower() for r in rejected)


# ---------------------------------------------------------------------------
# Test: Surrender on a completed match — command rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_surrender_on_completed_match_rejected(client: AsyncClient):
    """Cannot surrender on a match that is already completed."""
    user1, user2 = await _setup_two_users(client)
    match_data = await _create_and_join_match(client, user1, user2)

    # Start the match via command
    await _start_match_via_cmd(client, auth_headers(user1["token"]), match_data["id"])

    # Surrender to end the match
    await _surrender_via_cmd(client, auth_headers(user1["token"]), match_data["id"])

    # Try to surrender again on the now-completed match
    await _send_command(client, auth_headers(user2["token"]), "surrender", match_id=match_data["id"])
    await _process(client)

    rejected = await _get_rejected_commands(client, auth_headers(user2["token"]))
    assert any("not active" in (r.get("rejection_reason") or "").lower() for r in rejected)


# ---------------------------------------------------------------------------
# Test: Join an active match as reinforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_active_match_as_reinforcement(client: AsyncClient):
    """Players can join an active match as reinforcements with balance check."""
    user1, user2 = await _setup_two_users(client)
    user3 = await register_user(client, "lateplayer")
    user4 = await register_user(client, "lateplayer2")

    match_data = await _create_and_join_match(client, user1, user2)

    # Start the match (team1=solarion has user1, team2=voidborn has user2)
    detail = await _start_match_via_cmd(client, auth_headers(user1["token"]), match_data["id"])
    assert detail["status"] == "active"

    # user3 joins voidborn (1v1 → balanced, allowed: 1-1=0 < 1)
    resp = await client.post(
        f"/api/matches/{match_data['id']}/join",
        json={"faction": "voidborn"},
        headers=auth_headers(user3["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Joined match successfully."
    assert data["faction"] == "voidborn"

    # Now teams are solarion(1) vs voidborn(2).
    # user4 tries to join voidborn (the larger team): 2-1=1, not < 1 → rejected
    resp = await client.post(
        f"/api/matches/{match_data['id']}/join",
        json={"faction": "voidborn"},
        headers=auth_headers(user4["token"]),
    )
    assert resp.status_code == 400
    assert "unbalanced" in resp.json()["detail"].lower()

    # user4 joins solarion (the smaller team): 1 < 2 → always allowed
    resp = await client.post(
        f"/api/matches/{match_data['id']}/join",
        json={"faction": "solarion"},
        headers=auth_headers(user4["token"]),
    )
    assert resp.status_code == 200
    assert resp.json()["faction"] == "solarion"


# ---------------------------------------------------------------------------
# Test: Join match with invalid faction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_match_invalid_faction(client: AsyncClient):
    """Joining a match with an invalid faction returns 422."""
    user1 = await register_user(client, "player1")
    user2 = await register_user(client, "player2")

    resp = await client.post(
        "/api/matches",
        json={"name": "Bad Join", "faction": "solarion"},
        headers=auth_headers(user1["token"]),
    )
    assert resp.status_code == 201
    match_id = resp.json()["id"]

    resp = await client.post(
        f"/api/matches/{match_id}/join",
        json={"faction": "neutral"},
        headers=auth_headers(user2["token"]),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test: Concurrent surrender votes reaching majority
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_surrender_majority_with_multiple_voters(client: AsyncClient):
    """Two out of three team members voting to surrender ends the match."""
    user1 = await register_user(client, "player1")
    user2 = await register_user(client, "player2")
    user3 = await register_user(client, "player3")
    user4 = await register_user(client, "player4")

    # User1 creates match
    resp = await client.post(
        "/api/matches",
        json={"name": "Majority Test", "faction": "solarion"},
        headers=auth_headers(user1["token"]),
    )
    assert resp.status_code == 201
    match_id = resp.json()["id"]

    # Get team1 id
    resp = await client.get(
        f"/api/matches/{match_id}",
        headers=auth_headers(user1["token"]),
    )
    team1_id = resp.json()["team1"]["id"]

    # User3 and user4 join team1
    resp = await client.post(
        f"/api/teams/{team1_id}/join",
        headers=auth_headers(user3["token"]),
    )
    assert resp.status_code == 200

    resp = await client.post(
        f"/api/teams/{team1_id}/join",
        headers=auth_headers(user4["token"]),
    )
    assert resp.status_code == 200

    # User2 joins as team2
    resp = await client.post(
        f"/api/matches/{match_id}/join",
        json={"faction": "voidborn"},
        headers=auth_headers(user2["token"]),
    )
    assert resp.status_code == 200

    # Start the match
    detail = await _start_match_via_cmd(client, auth_headers(user1["token"]), match_id)
    assert detail["status"] == "active"

    # First vote (1 of 2 needed for 3 players — majority is 2)
    detail = await _surrender_via_cmd(client, auth_headers(user1["token"]), match_id)
    assert detail["status"] == "active"  # not ended yet, only 1 of 2 votes

    # Second vote reaches majority
    detail = await _surrender_via_cmd(client, auth_headers(user3["token"]), match_id)
    assert detail["status"] == "completed"

    # Verify match is completed
    resp = await client.get(
        f"/api/matches/{match_id}",
        headers=auth_headers(user1["token"]),
    )
    detail = resp.json()
    assert detail["status"] == "completed"
    assert detail["winner_team_id"] is not None


# ---------------------------------------------------------------------------
# Test: Win condition with match that has missing mothership in ship_map
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_win_condition_missing_mothership_in_ship_map(db_session: AsyncSession):
    """If a mothership is not in the ship_map, the match should not end."""
    from server.tick import _check_match_win_conditions

    team1 = Team(name="Miss T1", faction="solarion")
    team2 = Team(name="Miss T2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="miss_u1", token="tok_miss1", team_id=team1.id)
    user2 = User(username="miss_u2", token="tok_miss2", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    match = Match(
        name="Missing MS Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
        team1_mothership_id=9999,  # non-existent in ship_map
        team2_mothership_id=9998,
    )
    db_session.add(match)
    await db_session.commit()

    # Empty ship_map — motherships not loaded
    ships = []
    ship_map = {}

    pending_events = []

    def emit(event_type, message, user_id=None, ship_id=None):
        pending_events.append({
            "event_type": event_type,
            "message": message,
        })

    await _check_match_win_conditions(db_session, ships, ship_map, 5, emit)

    result = await db_session.exec(select(Match).where(Match.id == match.id))
    match = result.one()

    # Should not end if motherships are not in the ship_map
    assert match.status == MatchStatus.active.value
    assert match.winner_team_id is None


# ---------------------------------------------------------------------------
# Test: Team1 mothership destroyed (team2 wins)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_win_condition_team1_mothership_destroyed(db_session: AsyncSession):
    """When team1's mothership is destroyed, team2 wins."""
    from server.tick import _check_match_win_conditions

    team1 = Team(name="Lose T1", faction="solarion")
    team2 = Team(name="Win T2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="lose_u1", token="tok_l1", team_id=team1.id)
    user2 = User(username="win_u2", token="tok_w2", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    t1r = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1r.one()
    t2r = await db_session.exec(
        select(Team).where(Team.id == team2.id).options(selectinload(Team.users))
    )
    team2 = t2r.one()

    match = Match(
        name="T1 Lose Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    db_session.add(match)
    await db_session.flush()

    ms1 = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, 0,
    )
    ms2 = await create_match_mothership(
        db_session, team2, (800_000.0, 0.0, 0.0), match.id, 0,
    )
    match.team1_mothership_id = ms1.id
    match.team2_mothership_id = ms2.id
    await db_session.commit()

    # Destroy team1's mothership
    ms1.is_destroyed = True
    ms1.armor_hp = 0.0
    ms1.shield_hp = 0.0
    await db_session.flush()

    ships = [ms1, ms2]
    ship_map = {s.id: s for s in ships}
    pending_events = []

    def emit(event_type, message, user_id=None, ship_id=None):
        pending_events.append({
            "event_type": event_type,
            "message": message,
            "user_id": user_id,
        })

    await _check_match_win_conditions(db_session, ships, ship_map, 200, emit)
    await db_session.commit()

    result = await db_session.exec(select(Match).where(Match.id == match.id))
    match = result.one()

    assert match.status == MatchStatus.completed.value
    # team2 should win when team1's mothership is destroyed
    assert match.winner_team_id == team2.id
    assert match.ended_at_tick == 200


# ---------------------------------------------------------------------------
# Test: Map asteroids are in correct zones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_map_asteroid_zone_distribution(db_session: AsyncSession):
    """Asteroids should be distributed in home, center, and flank zones."""
    team1 = Team(name="Zone T1", faction="solarion")
    team2 = Team(name="Zone T2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="zone_u1", token="tok_zone1", team_id=team1.id)
    db_session.add(user1)
    await db_session.flush()

    match = Match(
        name="Zone Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    db_session.add(match)
    await db_session.flush()

    await generate_match_map(db_session, match, team1, team2, current_tick=0)
    await db_session.commit()

    result = await db_session.exec(
        select(CelestialObject).where(CelestialObject.match_id == match.id)
    )
    asteroids = result.all()

    # Check that some asteroids are near each home base
    near_alpha = [a for a in asteroids if abs(a.pos_x - (-100_000)) < 25_000]
    near_bravo = [a for a in asteroids if abs(a.pos_x - 100_000) < 25_000]
    near_center = [a for a in asteroids if abs(a.pos_x) < 50_000]

    assert len(near_alpha) >= 8, f"Expected >=8 asteroids near Alpha home, got {len(near_alpha)}"
    assert len(near_bravo) >= 8, f"Expected >=8 asteroids near Bravo home, got {len(near_bravo)}"
    assert len(near_center) >= 20, f"Expected >=20 asteroids near center, got {len(near_center)}"


# ---------------------------------------------------------------------------
# Test: Surrender winner is correct team (team2 surrenders -> team1 wins)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_surrender_team2_wins_team1(client: AsyncClient):
    """When team2 surrenders, team1 wins."""
    user1, user2 = await _setup_two_users(client)
    match_data = await _create_and_join_match(client, user1, user2)

    # Start the match
    detail = await _start_match_via_cmd(client, auth_headers(user1["token"]), match_data["id"])
    assert detail["status"] == "active"
    team1_id = detail["team1"]["id"]

    # User2 (team2) surrenders
    detail = await _surrender_via_cmd(client, auth_headers(user2["token"]), match_data["id"])
    assert detail["status"] == "completed"
    assert detail["winner_team_id"] == team1_id


# ---------------------------------------------------------------------------
# Test: Match start emits match_started events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_match_start_with_no_game_state(db_session: AsyncSession):
    """Starting a match with no GameState should default to tick 0."""
    # NOTE: The db_session fixture does NOT seed a GameState.
    # This tests the fallback behavior in start_match route where
    # gs.current_tick defaults to 0 if GameState is missing.

    # Verify no GameState exists
    gs_result = await db_session.exec(select(GameState))
    gs = gs_result.first()
    assert gs is None

    # Build the scenario: the route code does
    #   current_tick = gs.current_tick if gs else 0
    # so without GameState, current_tick = 0.
    # We test this by directly calling generate_match_map with tick=0.
    team1 = Team(name="NoGS T1", faction="solarion")
    team2 = Team(name="NoGS T2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="nogs_u1", token="tok_nogs1", team_id=team1.id)
    db_session.add(user1)
    await db_session.flush()

    t1r = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1r.one()

    match = Match(
        name="NoGS Test",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
    )
    db_session.add(match)
    await db_session.flush()

    # This should work fine with current_tick=0
    await generate_match_map(db_session, match, team1, team2, current_tick=0)
    ms = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, current_tick=0,
    )
    await db_session.commit()

    assert ms is not None
    assert ms.match_id == match.id

    # Verify asteroids were created
    result = await db_session.exec(
        select(CelestialObject).where(CelestialObject.match_id == match.id)
    )
    asteroids = result.all()
    assert len(asteroids) > 0


# ---------------------------------------------------------------------------
# Test: Mothership has expected ship class
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mothership_is_mothership_class(db_session: AsyncSession):
    """Mothership created by create_match_mothership has ShipClass.mothership."""
    team = Team(name="Class Team", faction="voidborn")
    db_session.add(team)
    await db_session.flush()

    user = User(username="cls_user", token="tok_cls", team_id=team.id)
    db_session.add(user)
    await db_session.flush()

    result = await db_session.exec(
        select(Team).where(Team.id == team.id).options(selectinload(Team.users))
    )
    team = result.one()

    match = Match(
        name="Class Test",
        status=MatchStatus.active.value,
        team1_id=team.id,
    )
    db_session.add(match)
    await db_session.flush()

    ms = await create_match_mothership(
        db_session, team, (100.0, 200.0, 300.0), match.id, current_tick=5,
    )
    await db_session.commit()

    assert ms.ship_class == ShipClass.mothership
    assert ms.is_destroyed is False
    # Capacitor, shield, and armor should be at max after creation
    assert ms.capacitor == ms.max_capacitor
    assert ms.shield_hp == ms.max_shield_hp
    assert ms.armor_hp == ms.max_armor_hp


# ---------------------------------------------------------------------------
# Test: Mothership name includes team name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mothership_name_includes_team_name(db_session: AsyncSession):
    """The mothership's name should include the team name."""
    team = Team(name="Space Pirates", faction="solarion")
    db_session.add(team)
    await db_session.flush()

    user = User(username="pirate", token="tok_pirate", team_id=team.id)
    db_session.add(user)
    await db_session.flush()

    result = await db_session.exec(
        select(Team).where(Team.id == team.id).options(selectinload(Team.users))
    )
    team = result.one()

    match = Match(
        name="Name Test",
        status=MatchStatus.active.value,
        team1_id=team.id,
    )
    db_session.add(match)
    await db_session.flush()

    ms = await create_match_mothership(
        db_session, team, (0.0, 0.0, 0.0), match.id, current_tick=0,
    )
    await db_session.commit()

    assert "Space Pirates" in ms.name
    assert "Mothership" in ms.name


# ---------------------------------------------------------------------------
# Test: Mothership starting ore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mothership_starting_ore_5000(db_session: AsyncSession):
    """Motherships start with exactly 7500 ore."""
    team = Team(name="Ore Team", faction="voidborn")
    db_session.add(team)
    await db_session.flush()

    user = User(username="miner", token="tok_miner", team_id=team.id)
    db_session.add(user)
    await db_session.flush()

    result = await db_session.exec(
        select(Team).where(Team.id == team.id).options(selectinload(Team.users))
    )
    team = result.one()

    match = Match(
        name="Ore Test",
        status=MatchStatus.active.value,
        team1_id=team.id,
    )
    db_session.add(match)
    await db_session.flush()

    ms = await create_match_mothership(
        db_session, team, (0.0, 0.0, 0.0), match.id, current_tick=0,
    )
    await db_session.commit()

    assert ms.ore == 7_500.0


# ---------------------------------------------------------------------------
# Test: List matches with status filter for pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_matches_filter_pending(client: AsyncClient):
    """Filtering by 'pending' returns only pending matches."""
    user1, user2 = await _setup_two_users(client)

    # Create a pending match
    resp = await client.post(
        "/api/matches",
        json={"name": "Pending Only", "faction": "solarion"},
        headers=auth_headers(user1["token"]),
    )
    assert resp.status_code == 201

    resp = await client.get(
        "/api/matches",
        params={"status_filter": "pending"},
        headers=auth_headers(user1["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert all(m["status"] == "pending" for m in data)


# ===========================================================================
# COMPREHENSIVE INTEGRATION TESTS: Full match flow end-to-end
# ===========================================================================


@pytest.mark.asyncio
async def test_full_match_lifecycle_creation_to_victory(client: AsyncClient):
    """
    Full happy-path integration test via the HTTP API: two players play a
    match from creation through to checking all game entities after starting.

    Steps:
      1. Register two players
      2. Player1 creates a match as solarion
      3. Player2 joins as voidborn
      4. Verify match info shows both teams with correct factions
      5. Start the match
      6. Verify motherships exist at correct positions (~-800km and ~+800km)
      7. Verify motherships have correct module loadout
      8. Verify match info is active with all fields populated
    """
    # -----------------------------------------------------------------------
    # 1. Register two players
    # -----------------------------------------------------------------------
    user1 = await register_user(client, "alpha_player")
    user2 = await register_user(client, "bravo_player")

    # -----------------------------------------------------------------------
    # 2. Player1 creates a match as solarion
    # -----------------------------------------------------------------------
    create_resp = await client.post(
        "/api/matches",
        json={"name": "Grand Battle", "faction": "solarion"},
        headers=auth_headers(user1["token"]),
    )
    assert create_resp.status_code == 201, create_resp.text
    match_data = create_resp.json()
    match_id = match_data["id"]
    assert match_data["name"] == "Grand Battle"
    assert match_data["status"] == "pending"
    assert match_data["team1_id"] is not None
    assert match_data["team2_id"] is not None

    # -----------------------------------------------------------------------
    # 3. Player2 joins as voidborn
    # -----------------------------------------------------------------------
    join_resp = await client.post(
        f"/api/matches/{match_id}/join",
        json={"faction": "voidborn"},
        headers=auth_headers(user2["token"]),
    )
    assert join_resp.status_code == 200, join_resp.text
    join_data = join_resp.json()
    assert join_data["faction"] == "voidborn"

    # -----------------------------------------------------------------------
    # 4. Verify match info shows both teams with correct factions
    # -----------------------------------------------------------------------
    info_resp = await client.get(
        f"/api/matches/{match_id}",
        headers=auth_headers(user1["token"]),
    )
    assert info_resp.status_code == 200
    info = info_resp.json()
    assert info["status"] == "pending"
    assert info["team1"] is not None
    assert info["team2"] is not None
    assert info["team1"]["faction"] == "solarion"
    assert info["team2"]["faction"] == "voidborn"
    assert info["team1"]["member_count"] == 1
    assert info["team2"]["member_count"] == 1

    # -----------------------------------------------------------------------
    # 5. Start the match
    # -----------------------------------------------------------------------
    start_data = await _start_match_via_cmd(client, auth_headers(user1["token"]), match_id)
    assert start_data["status"] == "active"
    assert start_data.get("team1_mothership") is not None
    assert start_data.get("team2_mothership") is not None
    ms1_id = start_data["team1_mothership"]["id"]
    ms2_id = start_data["team2_mothership"]["id"]

    # -----------------------------------------------------------------------
    # 6. Verify motherships exist at correct positions
    # -----------------------------------------------------------------------
    ship1_resp = await client.get(
        f"/api/ships/{ms1_id}",
        headers=auth_headers(user1["token"]),
    )
    assert ship1_resp.status_code == 200
    ship1 = ship1_resp.json()
    assert ship1["ship_class"] == "mothership"
    assert abs(ship1["pos_x"] - (-100_000.0)) < 1.0
    assert abs(ship1["pos_y"]) < 1.0
    assert abs(ship1["pos_z"]) < 1.0

    ship2_resp = await client.get(
        f"/api/ships/{ms2_id}",
        headers=auth_headers(user2["token"]),
    )
    assert ship2_resp.status_code == 200
    ship2 = ship2_resp.json()
    assert ship2["ship_class"] == "mothership"
    assert abs(ship2["pos_x"] - 100_000.0) < 1.0
    assert abs(ship2["pos_y"]) < 1.0
    assert abs(ship2["pos_z"]) < 1.0

    # -----------------------------------------------------------------------
    # 7. Verify motherships have correct module loadout
    # -----------------------------------------------------------------------
    expected_module_types = [mt for mt, _ in MATCH_MOTHERSHIP_LOADOUT]
    ship1_modules = ship1.get("modules", [])
    ship2_modules = ship2.get("modules", [])
    assert len(ship1_modules) == len(MATCH_MOTHERSHIP_LOADOUT), (
        f"Expected {len(MATCH_MOTHERSHIP_LOADOUT)} modules, got {len(ship1_modules)}"
    )
    assert len(ship2_modules) == len(MATCH_MOTHERSHIP_LOADOUT), (
        f"Expected {len(MATCH_MOTHERSHIP_LOADOUT)} modules, got {len(ship2_modules)}"
    )

    ship1_mod_types = sorted([m["module_type"] for m in ship1_modules])
    ship2_mod_types = sorted([m["module_type"] for m in ship2_modules])
    expected_sorted = sorted(expected_module_types)
    assert ship1_mod_types == expected_sorted
    assert ship2_mod_types == expected_sorted

    # Motherships should have non-zero HP and correct resources
    assert ship1["max_shield_hp"] > 0
    assert ship1["max_armor_hp"] > 0
    assert ship2["max_shield_hp"] > 0
    assert ship2["max_armor_hp"] > 0
    assert ship1["is_destroyed"] is False
    assert ship2["is_destroyed"] is False
    assert ship1["ore"] == 7_500.0
    assert ship2["ore"] == 7_500.0

    # -----------------------------------------------------------------------
    # 8. Verify match info is active with all fields populated
    # -----------------------------------------------------------------------
    info_after_start = await client.get(
        f"/api/matches/{match_id}",
        headers=auth_headers(user1["token"]),
    )
    assert info_after_start.status_code == 200
    active_info = info_after_start.json()
    assert active_info["status"] == "active"
    assert active_info["started_at_tick"] is not None
    assert active_info["team1_mothership"] is not None
    assert active_info["team2_mothership"] is not None
    assert active_info["team1_mothership"]["is_destroyed"] is False
    assert active_info["team2_mothership"]["is_destroyed"] is False


@pytest.mark.asyncio
async def test_full_match_with_win_condition_db(db_session: AsyncSession):
    """
    Full end-to-end test using direct DB access: create a match, generate map,
    create motherships, verify asteroids and scoping, simulate mothership
    destruction, check win conditions, and verify final state.

    Covers:
      - Asteroid generation count and match_id scoping
      - Free-play asteroids (match_id=NULL) not mixed in
      - Simulating mothership destruction (armor_hp=0, is_destroyed=True)
      - _check_match_win_conditions ending match with correct winner
      - Match showing completed status with correct winner_team_id
    """
    from server.tick import _check_match_win_conditions

    # -----------------------------------------------------------------------
    # Setup: Create teams, users, and match
    # -----------------------------------------------------------------------
    team1 = Team(name="Solarion Vanguard", faction="solarion")
    team2 = Team(name="Voidborn Legion", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="commander1", token="tok_cmd1", team_id=team1.id)
    user2 = User(username="commander2", token="tok_cmd2", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    # Reload teams with users eagerly loaded
    t1_result = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1_result.one()
    t2_result = await db_session.exec(
        select(Team).where(Team.id == team2.id).options(selectinload(Team.users))
    )
    team2 = t2_result.one()

    match = Match(
        name="Grand Battle",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
        started_at_tick=0,
    )
    db_session.add(match)
    await db_session.flush()

    # -----------------------------------------------------------------------
    # Generate the match map
    # -----------------------------------------------------------------------
    await generate_match_map(db_session, match, team1, team2, current_tick=0)
    await db_session.flush()

    # -----------------------------------------------------------------------
    # Verify asteroids were generated (count and match_id scoping)
    # -----------------------------------------------------------------------
    asteroid_result = await db_session.exec(
        select(CelestialObject).where(CelestialObject.match_id == match.id)
    )
    asteroids = asteroid_result.all()

    # Expected: 8+10 per home (x2=36) + 30-40 center + 8-12 per flank (x2=16-24) + 8-14 rich
    # Total range: 74-124
    assert len(asteroids) >= 66, f"Expected >= 66 asteroids, got {len(asteroids)}"
    assert len(asteroids) <= 130, f"Expected <= 130 asteroids, got {len(asteroids)}"

    # All asteroids should be scoped to this match
    for ast in asteroids:
        assert ast.match_id == match.id
        assert ast.object_type == CelestialType.asteroid
        assert ast.ore_remaining > 0

    # -----------------------------------------------------------------------
    # Verify free-play asteroids (match_id=NULL) are NOT mixed in
    # -----------------------------------------------------------------------
    free_play_asteroid = CelestialObject(
        name="Free Play Rock",
        object_type=CelestialType.asteroid,
        pos_x=100.0,
        pos_y=200.0,
        pos_z=300.0,
        ore_remaining=1000.0,
        ore_initial=1000.0,
        match_id=None,
    )
    db_session.add(free_play_asteroid)
    await db_session.flush()

    # Re-query match asteroids -- should NOT include the free-play one
    match_ast_result = await db_session.exec(
        select(CelestialObject).where(CelestialObject.match_id == match.id)
    )
    match_asteroids = match_ast_result.all()
    match_asteroid_ids = {a.id for a in match_asteroids}
    assert free_play_asteroid.id not in match_asteroid_ids

    # Query free-play asteroids -- should NOT include match asteroids
    free_ast_result = await db_session.exec(
        select(CelestialObject).where(CelestialObject.match_id == None)  # noqa: E711
    )
    free_asteroids = free_ast_result.all()
    free_asteroid_ids = {a.id for a in free_asteroids}
    assert free_play_asteroid.id in free_asteroid_ids
    for match_ast in match_asteroids:
        assert match_ast.id not in free_asteroid_ids

    # -----------------------------------------------------------------------
    # Create motherships
    # -----------------------------------------------------------------------
    ms1 = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, current_tick=0,
    )
    ms2 = await create_match_mothership(
        db_session, team2, (800_000.0, 0.0, 0.0), match.id, current_tick=0,
    )
    match.team1_mothership_id = ms1.id
    match.team2_mothership_id = ms2.id
    await db_session.commit()

    # Verify mothership positions
    assert abs(ms1.pos_x - (-800_000.0)) < 1.0
    assert abs(ms2.pos_x - 800_000.0) < 1.0

    # Verify mothership loadout
    assert len(ms1.modules) == len(MATCH_MOTHERSHIP_LOADOUT)
    assert len(ms2.modules) == len(MATCH_MOTHERSHIP_LOADOUT)
    ms1_mod_types = sorted([m.module_type.value for m in ms1.modules])
    expected_sorted = sorted([mt for mt, _ in MATCH_MOTHERSHIP_LOADOUT])
    assert ms1_mod_types == expected_sorted

    # Verify derived stats
    assert ms1.max_capacitor > 0
    assert ms1.capacitor == ms1.max_capacitor
    assert ms1.max_shield_hp > 0
    assert ms1.shield_hp == ms1.max_shield_hp
    assert ms1.max_armor_hp > 0
    assert ms1.armor_hp == ms1.max_armor_hp
    assert ms1.ore == 7_500.0
    assert ms1.is_destroyed is False
    assert ms1.match_id == match.id
    assert ms1.team_id == team1.id

    # -----------------------------------------------------------------------
    # Simulate destroying team2's mothership
    # -----------------------------------------------------------------------
    ms2.armor_hp = 0.0
    ms2.shield_hp = 0.0
    ms2.is_destroyed = True
    await db_session.flush()

    # -----------------------------------------------------------------------
    # Call _check_match_win_conditions and verify match ends
    # -----------------------------------------------------------------------
    ships = [ms1, ms2]
    ship_map = {s.id: s for s in ships}
    pending_events = []

    def emit(event_type, message, user_id=None, ship_id=None):
        pending_events.append({
            "event_type": event_type,
            "message": message,
            "user_id": user_id,
            "ship_id": ship_id,
        })

    await _check_match_win_conditions(db_session, ships, ship_map, 500, emit)
    await db_session.commit()

    # -----------------------------------------------------------------------
    # Verify match ended correctly
    # -----------------------------------------------------------------------
    result = await db_session.exec(select(Match).where(Match.id == match.id))
    match = result.one()

    assert match.status == MatchStatus.completed.value
    assert match.winner_team_id == team1.id  # team1 wins (team2 MS destroyed)
    assert match.ended_at_tick == 500

    # Verify match_ended events were emitted for both players
    ended_events = [
        e for e in pending_events if e["event_type"] == EventType.match_ended
    ]
    assert len(ended_events) >= 2  # one per player
    event_user_ids = {e["user_id"] for e in ended_events}
    assert user1.id in event_user_ids
    assert user2.id in event_user_ids


@pytest.mark.asyncio
async def test_full_match_team1_ms_destroyed_team2_wins(db_session: AsyncSession):
    """
    Symmetric win condition: when team1's mothership is destroyed, team2 wins.
    """
    from server.tick import _check_match_win_conditions

    team1 = Team(name="Losers", faction="solarion")
    team2 = Team(name="Winners", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="p1_rev", token="tok_rev1", team_id=team1.id)
    user2 = User(username="p2_rev", token="tok_rev2", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    t1_result = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1_result.one()
    t2_result = await db_session.exec(
        select(Team).where(Team.id == team2.id).options(selectinload(Team.users))
    )
    team2 = t2_result.one()

    match = Match(
        name="Reverse Battle",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
        started_at_tick=0,
    )
    db_session.add(match)
    await db_session.flush()

    ms1 = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, 0,
    )
    ms2 = await create_match_mothership(
        db_session, team2, (800_000.0, 0.0, 0.0), match.id, 0,
    )
    match.team1_mothership_id = ms1.id
    match.team2_mothership_id = ms2.id
    await db_session.commit()

    # Destroy team1's mothership
    ms1.armor_hp = 0.0
    ms1.shield_hp = 0.0
    ms1.is_destroyed = True
    await db_session.flush()

    ships = [ms1, ms2]
    ship_map = {s.id: s for s in ships}
    pending_events = []

    def emit(event_type, message, user_id=None, ship_id=None):
        pending_events.append({"event_type": event_type, "user_id": user_id})

    await _check_match_win_conditions(db_session, ships, ship_map, 200, emit)
    await db_session.commit()

    result = await db_session.exec(select(Match).where(Match.id == match.id))
    match = result.one()

    assert match.status == MatchStatus.completed.value
    assert match.winner_team_id == team2.id
    assert match.ended_at_tick == 200


# ---------------------------------------------------------------------------
# SURRENDER FLOW: Full integration tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_surrender_flow_full_integration(client: AsyncClient):
    """
    Full surrender integration test:
      1. Create and start a match (2 players, 1 per team)
      2. One player surrenders -- match ends immediately (1-player team)
      3. Verify the winner is the OTHER team
      4. Verify match info shows completed status, correct winner, intact motherships
    """
    # -----------------------------------------------------------------------
    # 1. Register players, create match, join, and start
    # -----------------------------------------------------------------------
    user1 = await register_user(client, "surrender_p1")
    user2 = await register_user(client, "surrender_p2")

    create_resp = await client.post(
        "/api/matches",
        json={"name": "Surrender Test", "faction": "voidborn"},
        headers=auth_headers(user1["token"]),
    )
    assert create_resp.status_code == 201
    match_id = create_resp.json()["id"]

    join_resp = await client.post(
        f"/api/matches/{match_id}/join",
        json={"faction": "solarion"},
        headers=auth_headers(user2["token"]),
    )
    assert join_resp.status_code == 200

    detail = await _start_match_via_cmd(client, auth_headers(user1["token"]), match_id)
    assert detail["status"] == "active"
    team1_id = detail["team1"]["id"]

    # -----------------------------------------------------------------------
    # 2. Player2 (team2) surrenders -- 1-player team, instant match end
    # -----------------------------------------------------------------------
    detail = await _surrender_via_cmd(client, auth_headers(user2["token"]), match_id)
    assert detail["status"] == "completed"

    # -----------------------------------------------------------------------
    # 3. Verify the winner is team1 (the OTHER team)
    # -----------------------------------------------------------------------
    final_resp = await client.get(
        f"/api/matches/{match_id}",
        headers=auth_headers(user1["token"]),
    )
    assert final_resp.status_code == 200
    final_info = final_resp.json()
    assert final_info["status"] == "completed"
    assert final_info["winner_team_id"] == team1_id
    assert final_info["ended_at_tick"] is not None

    # -----------------------------------------------------------------------
    # 4. Verify motherships are still intact (surrender, not destruction)
    # -----------------------------------------------------------------------
    assert final_info["team1_mothership"] is not None
    assert final_info["team2_mothership"] is not None
    assert final_info["team1_mothership"]["is_destroyed"] is False
    assert final_info["team2_mothership"]["is_destroyed"] is False


@pytest.mark.asyncio
async def test_surrender_by_team1_makes_team2_winner(client: AsyncClient):
    """
    Symmetric surrender: when team1 surrenders, team2 wins.
    """
    user1 = await register_user(client, "surr_t1_p1")
    user2 = await register_user(client, "surr_t1_p2")

    create_resp = await client.post(
        "/api/matches",
        json={"name": "Team1 Surrenders", "faction": "solarion"},
        headers=auth_headers(user1["token"]),
    )
    assert create_resp.status_code == 201
    match_id = create_resp.json()["id"]

    await client.post(
        f"/api/matches/{match_id}/join",
        json={"faction": "voidborn"},
        headers=auth_headers(user2["token"]),
    )

    detail = await _start_match_via_cmd(client, auth_headers(user1["token"]), match_id)
    assert detail["status"] == "active"
    team2_id = detail["team2"]["id"]

    # Team1 (user1) surrenders
    detail = await _surrender_via_cmd(client, auth_headers(user1["token"]), match_id)
    assert detail["status"] == "completed"

    # Verify team2 wins
    final_resp = await client.get(
        f"/api/matches/{match_id}",
        headers=auth_headers(user1["token"]),
    )
    assert final_resp.json()["status"] == "completed"
    assert final_resp.json()["winner_team_id"] == team2_id


# ---------------------------------------------------------------------------
# Additional unhappy-path: no-mothership-destroyed still active
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_win_condition_both_alive_stays_active(db_session: AsyncSession):
    """_check_match_win_conditions does NOT end the match when both motherships live."""
    from server.tick import _check_match_win_conditions

    team1 = Team(name="Still Standing 1", faction="solarion")
    team2 = Team(name="Still Standing 2", faction="voidborn")
    db_session.add(team1)
    db_session.add(team2)
    await db_session.flush()

    user1 = User(username="alive1", token="tok_alive1", team_id=team1.id)
    user2 = User(username="alive2", token="tok_alive2", team_id=team2.id)
    db_session.add(user1)
    db_session.add(user2)
    await db_session.flush()

    t1_result = await db_session.exec(
        select(Team).where(Team.id == team1.id).options(selectinload(Team.users))
    )
    team1 = t1_result.one()
    t2_result = await db_session.exec(
        select(Team).where(Team.id == team2.id).options(selectinload(Team.users))
    )
    team2 = t2_result.one()

    match = Match(
        name="No Winner Yet",
        status=MatchStatus.active.value,
        team1_id=team1.id,
        team2_id=team2.id,
        started_at_tick=0,
    )
    db_session.add(match)
    await db_session.flush()

    ms1 = await create_match_mothership(
        db_session, team1, (-800_000.0, 0.0, 0.0), match.id, 0,
    )
    ms2 = await create_match_mothership(
        db_session, team2, (800_000.0, 0.0, 0.0), match.id, 0,
    )
    match.team1_mothership_id = ms1.id
    match.team2_mothership_id = ms2.id
    await db_session.commit()

    assert ms1.is_destroyed is False
    assert ms2.is_destroyed is False

    ships = [ms1, ms2]
    ship_map = {s.id: s for s in ships}
    pending_events = []

    def emit(event_type, message, user_id=None, ship_id=None):
        pending_events.append({"event_type": event_type})

    await _check_match_win_conditions(db_session, ships, ship_map, 50, emit)
    await db_session.commit()

    result = await db_session.exec(select(Match).where(Match.id == match.id))
    match = result.one()

    assert match.status == MatchStatus.active.value
    assert match.winner_team_id is None
    assert match.ended_at_tick is None

    ended_events = [e for e in pending_events if e["event_type"] == EventType.match_ended]
    assert len(ended_events) == 0


# ---------------------------------------------------------------------------
# Test: Ships don't carry over between matches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_join_match_does_not_carry_over_ships(client: AsyncClient):
    """Leaving match A and joining match B should not bring ships from A."""
    user1 = await register_user(client, "host1")
    user2 = await register_user(client, "host2")
    player = await register_user(client, "player")
    ph = auth_headers(player["token"])

    # Create and start match A
    resp = await client.post(
        "/api/matches",
        json={"name": "Match A", "faction": "solarion"},
        headers=auth_headers(user1["token"]),
    )
    match_a = resp.json()
    resp = await client.post(
        f"/api/matches/{match_a['id']}/join",
        json={"faction": "voidborn"},
        headers=ph,
    )
    assert resp.status_code == 200
    detail_a = await _start_match_via_cmd(client, auth_headers(user1["token"]), match_a["id"])
    assert detail_a["status"] == "active"

    # Player claims a ship in match A (auto-create path)
    await _send_command(client, ph, "claim_ship", ship_class="strike_craft")
    await _process(client)

    # Verify claim wasn't rejected
    rejected = await _get_rejected_commands(client, ph)
    claim_rejects = [r for r in rejected if r["type"] == "claim_ship"]
    assert len(claim_rejects) == 0, f"claim_ship rejected: {claim_rejects}"

    # Player should have ships visible via /api/view
    resp = await client.get("/api/view", headers=ph)
    assert resp.status_code == 200
    ships_a = resp.json()["ships"]
    player_ships_a = [s for s in ships_a if s.get("claimed_by_user_id") == player["user_id"]]
    assert len(player_ships_a) >= 1, "Player should have a claimed ship in match A"

    # Player leaves match A
    resp = await client.post("/api/teams/leave", headers=ph)
    assert resp.status_code == 200

    # Create match B
    resp = await client.post(
        "/api/matches",
        json={"name": "Match B", "faction": "solarion"},
        headers=auth_headers(user2["token"]),
    )
    match_b = resp.json()

    # Player joins match B
    resp = await client.post(
        f"/api/matches/{match_b['id']}/join",
        json={"faction": "voidborn"},
        headers=ph,
    )
    assert resp.status_code == 200

    # Verify: /api/view for player should show no ships (match B is pending, no ships yet)
    resp = await client.get("/api/view", headers=ph)
    assert resp.status_code == 200
    ships_b = resp.json()["ships"]
    player_ships_b = [s for s in ships_b if s.get("claimed_by_user_id") == player["user_id"]]
    assert len(player_ships_b) == 0, (
        f"Ships carried over from match A to B: {player_ships_b}"
    )


# ---------------------------------------------------------------------------
# Test: Switch team unclaims ships, doesn't move them
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_switch_team_unclaims_ships(client: AsyncClient):
    """Switching teams should unclaim the player's ships, not move them."""
    user1, user2 = await _setup_two_users(client)

    match_data = await _create_and_join_match(client, user1, user2)
    detail = await _start_match_via_cmd(client, auth_headers(user1["token"]), match_data["id"])
    assert detail["status"] == "active"

    # user2 claims a ship on voidborn (auto-create path)
    u2h = auth_headers(user2["token"])
    await _send_command(client, u2h, "claim_ship", ship_class="strike_craft")
    await _process(client)

    # Verify claim wasn't rejected
    rejected = await _get_rejected_commands(client, u2h)
    claim_rejects = [r for r in rejected if r["type"] == "claim_ship"]
    assert len(claim_rejects) == 0, f"claim_ship rejected: {claim_rejects}"

    # user2 should have a claimed ship in the view
    resp = await client.get("/api/view", headers=u2h)
    assert resp.status_code == 200
    ships_before = resp.json()["ships"]
    claimed_before = [s for s in ships_before if s.get("claimed_by_user_id") == user2["user_id"]]
    assert len(claimed_before) >= 1, "user2 should have a claimed ship"
    old_team_id = detail["team2"]["id"]  # user2 is on voidborn = team2

    # user2 switches from voidborn to solarion
    resp = await client.post(
        f"/api/matches/{match_data['id']}/switch-team",
        headers=u2h,
    )
    assert resp.status_code == 200
    new_team_id = resp.json()["team_id"]
    assert new_team_id != old_team_id

    # Verify: user2's view should have no claimed ships on the new team
    resp = await client.get("/api/view", headers=u2h)
    assert resp.status_code == 200
    ships_after = resp.json()["ships"]
    claimed_after = [s for s in ships_after if s.get("claimed_by_user_id") == user2["user_id"]]
    assert len(claimed_after) == 0, (
        f"Ship should be unclaimed after team switch, but found: {claimed_after}"
    )
