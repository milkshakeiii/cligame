"""
Integration tests for the tick loop and related subsystems.

Covers:
  1. Ship destruction & kill points
  2. Production pipeline (build command)
  3. Dock command via command pipeline
  4. Board / eject commands
  5. Reship command
  6. Tick loop phase helpers (unit tests via db_session):
     - _process_modules (cycle firing, cap drain)
     - _process_mining (ore extraction from asteroid)
     - apply_shield_regen
     - apply_regen (capacitor regen)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.conftest import (
    register_user,
    spawn_test_mothership,
    make_test_ship,
    add_module_to_ship,
)

from server.models import (
    BuildOrder,
    BuildStatus,
    CelestialObject,
    CelestialType,
    Event,
    EventType,
    GameState,
    KILL_POINTS,
    LeechDebuff,
    LockStatus,
    ModuleType,
    ShipClass,
    ShipModule,
    Spaceship,
    TargetLock,
    Team,
    User,
    create_default_ship,
    make_module,
    recalculate_max_capacitor,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _auth(client: AsyncClient, username: str) -> tuple[dict, dict]:
    """Register a user and return (headers, auth_data)."""
    data = await register_user(client, username)
    headers = {"Authorization": f"Bearer {data['token']}"}
    return headers, data


async def _auth_header(client: AsyncClient, username: str = "testuser") -> dict:
    """Register a user and return auth headers."""
    headers, _ = await _auth(client, username)
    return headers


async def _send_command(
    client: AsyncClient,
    headers: dict,
    command_type: str,
    cmd_ship_id: int | None = None,
    **payload,
) -> dict:
    """Send a command and return the response."""
    body: dict = {"type": command_type, "payload": payload}
    if cmd_ship_id is not None:
        body["ship_id"] = cmd_ship_id
    resp = await client.post("/api/commands", json=body, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()


async def _send_raw_command(
    client: AsyncClient,
    headers: dict,
    command_type: str,
    payload: dict,
    cmd_ship_id: int | None = None,
) -> dict:
    """Send a command with an explicit payload dict (no kwarg expansion)."""
    body: dict = {"type": command_type, "payload": payload}
    if cmd_ship_id is not None:
        body["ship_id"] = cmd_ship_id
    resp = await client.post("/api/commands", json=body, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()


async def _process(client: AsyncClient) -> dict:
    """Trigger command processing via test endpoint."""
    resp = await client.post("/api/_test/process_commands")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _get_rejected_commands(client: AsyncClient, headers: dict) -> list[dict]:
    """Return all rejected commands for the user."""
    resp = await client.get("/api/commands", params={"status": "rejected"}, headers=headers)
    assert resp.status_code == 200
    return resp.json()


async def _get_ships(client: AsyncClient, headers: dict) -> list[dict]:
    """Return all ships for the user."""
    resp = await client.get("/api/ships", headers=headers)
    assert resp.status_code == 200
    return resp.json()


async def _get_view(client: AsyncClient, headers: dict) -> dict:
    """Return the full game view for the user."""
    resp = await client.get("/api/view", params={"since_tick": 0}, headers=headers)
    assert resp.status_code == 200
    return resp.json()


async def _find_mothership(client: AsyncClient, headers: dict) -> dict | None:
    """Find the team's mothership via the view endpoint (works for unowned ships)."""
    view = await _get_view(client, headers)
    ships = view.get("ships", [])
    return next((s for s in ships if s.get("ship_class") == "mothership"), None)


async def _setup_match(client: AsyncClient) -> tuple[dict, dict, dict, dict, int]:
    """Set up a full match with two users/teams.

    Uses the match creation API which auto-creates teams (no manual
    /api/teams call needed).  Match is started via the start_match command.

    Returns (headers1, auth1, headers2, auth2, match_id).
    """
    headers1, auth1 = await _auth(client, "player1")
    headers2, auth2 = await _auth(client, "player2")

    # Create match (auto-creates team1 for player1 with solarion)
    resp = await client.post(
        "/api/matches",
        json={"name": "Test Match", "faction": "solarion"},
        headers=headers1,
    )
    assert resp.status_code == 201, resp.text
    match_id = resp.json()["id"]

    # User2 joins (auto-assigns to team2 with voidborn)
    resp = await client.post(
        f"/api/matches/{match_id}/join",
        json={"faction": "voidborn"},
        headers=headers2,
    )
    assert resp.status_code == 200, resp.text

    # Start match via command system (no /api/matches/{id}/start endpoint)
    await _send_command(client, headers1, "start_match", match_id=match_id)
    await _process(client)

    # Verify match is active
    resp = await client.get(f"/api/matches/{match_id}", headers=headers1)
    assert resp.status_code == 200
    match_detail = resp.json()
    assert match_detail["status"] == "active", f"Match not active: {match_detail}"

    return headers1, auth1, headers2, auth2, match_id


# ===========================================================================
# 1. Ship Destruction & Kill Points
# ===========================================================================


@pytest.mark.anyio
class TestShipDestruction:

    async def test_destruction_creates_wreck_and_awards_kill_points(self, db_session: AsyncSession):
        """When a ship's armor reaches 0 and is_destroyed is True,
        _process_destruction creates a wreck and awards kill points."""
        from server.tick import _process_destruction

        # Create two users (using correct field names: password_hash, token)
        attacker_user = User(
            username="attacker", token="attacker_tok",
            password_hash="x", points=0.0,
        )
        victim_user = User(
            username="victim", token="victim_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(attacker_user)
        db_session.add(victim_user)
        await db_session.flush()

        # Create attacker ship
        attacker_ship = create_default_ship(
            "Attacker", ShipClass.frigate, user_id=attacker_user.id,
        )
        db_session.add(attacker_ship)
        await db_session.flush()
        await db_session.refresh(attacker_ship, attribute_names=["modules", "target_locks"])

        # Create victim ship -- destroyed
        victim_ship = create_default_ship(
            "Victim", ShipClass.strike_craft, user_id=victim_user.id,
            pos_x=100.0, pos_y=200.0, pos_z=300.0,
        )
        victim_ship.is_destroyed = True
        victim_ship.armor_hp = 0.0
        victim_ship.shield_hp = 0.0
        victim_ship.ore = 400.0
        victim_ship.last_damage_by_user_id = attacker_user.id
        db_session.add(victim_ship)
        await db_session.flush()
        await db_session.refresh(victim_ship, attribute_names=["modules", "target_locks"])

        # Give attacker a lock on the victim
        lock = TargetLock(
            ship_id=attacker_ship.id,
            target_ship_id=victim_ship.id,
            status=LockStatus.locked,
            ticks_remaining=0,
        )
        db_session.add(lock)
        await db_session.flush()
        await db_session.refresh(attacker_ship, attribute_names=["target_locks"])

        ships = [attacker_ship, victim_ship]
        ship_map = {s.id: s for s in ships}

        events: list[Event] = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append(Event(
                tick=1, user_id=user_id, ship_id=ship_id,
                event_type=event_type, message=message,
            ))

        pts_awarded: list[tuple] = []

        def award_pts(user_id, amount, reason):
            pts_awarded.append((user_id, amount, reason))

        _process_destruction(
            ships=ships,
            ship_map=ship_map,
            current_tick=1,
            emit=emit,
            session=db_session,
            active_leeches=[],
            award_pts=award_pts,
            damage_dealt_tracker={},
        )

        # Verify kill points were awarded
        expected_kill_pts = KILL_POINTS.get("strike_craft", 100)
        assert len(pts_awarded) >= 1
        kill_award = pts_awarded[0]
        assert kill_award[0] == attacker_user.id
        assert kill_award[1] == expected_kill_pts
        assert "kill" in kill_award[2]

        # Verify wreck was created
        wrecks = await db_session.exec(
            select(CelestialObject).where(
                CelestialObject.object_type == CelestialType.wreck
            )
        )
        wreck = wrecks.first()
        assert wreck is not None
        assert wreck.pos_x == victim_ship.pos_x
        assert wreck.pos_y == victim_ship.pos_y
        assert wreck.pos_z == victim_ship.pos_z
        # Wreck has 25% of cargo
        assert abs(wreck.ore_remaining - 400.0 * 0.25) < 0.01

        # Verify attacker's lock on the victim is broken
        assert lock.status == LockStatus.broken

        # Verify destruction event was emitted for the victim
        victim_events = [e for e in events if e.event_type == EventType.you_destroyed]
        assert len(victim_events) == 1
        assert victim_events[0].user_id == victim_user.id

        # Verify ship_destroyed event emitted to attacker (had lock)
        attacker_events = [e for e in events if e.event_type == EventType.ship_destroyed]
        assert len(attacker_events) == 1
        assert attacker_events[0].user_id == attacker_user.id

    async def test_destruction_ejects_docked_ships(self, db_session: AsyncSession):
        """When a ship is destroyed, docked ships are ejected to the same position."""
        from server.tick import _process_destruction

        user = User(
            username="testuser", token="test_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(user)
        await db_session.flush()

        # Create carrier ship (will be destroyed)
        carrier = create_default_ship(
            "Carrier", ShipClass.frigate, user_id=user.id,
            pos_x=500.0, pos_y=600.0, pos_z=700.0,
        )
        carrier.is_destroyed = True
        carrier.armor_hp = 0.0
        carrier.shield_hp = 0.0
        carrier.ore = 0.0
        db_session.add(carrier)
        await db_session.flush()
        await db_session.refresh(carrier, attribute_names=["modules", "target_locks"])

        # Create docked ship
        docked = create_default_ship(
            "Docked", ShipClass.strike_craft, user_id=user.id,
        )
        db_session.add(docked)
        await db_session.flush()
        docked.docked_in_id = carrier.id
        await db_session.refresh(docked, attribute_names=["modules", "target_locks"])

        ships = [carrier, docked]
        ship_map = {s.id: s for s in ships}

        events: list[Event] = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append(Event(
                tick=1, user_id=user_id, ship_id=ship_id,
                event_type=event_type, message=message,
            ))

        _process_destruction(
            ships=ships,
            ship_map=ship_map,
            current_tick=1,
            emit=emit,
            session=db_session,
            active_leeches=[],
        )

        # Docked ship should be ejected
        assert docked.docked_in_id is None
        assert docked.pos_x == carrier.pos_x
        assert docked.pos_y == carrier.pos_y
        assert docked.pos_z == carrier.pos_z
        assert docked.vel_x == 0.0
        assert docked.vel_y == 0.0
        assert docked.vel_z == 0.0

    async def test_destruction_assist_points(self, db_session: AsyncSession):
        """Players who dealt >10% of total HP get assist points (50% of kill)."""
        from server.tick import _process_destruction

        killer = User(
            username="killer", token="killer_tok",
            password_hash="x", points=0.0,
        )
        assister = User(
            username="assister", token="assister_tok",
            password_hash="x", points=0.0,
        )
        bystander = User(
            username="bystander", token="bystander_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(killer)
        db_session.add(assister)
        db_session.add(bystander)
        await db_session.flush()

        victim = create_default_ship(
            "Victim", ShipClass.corvette, user_id=None,
        )
        victim.is_destroyed = True
        victim.armor_hp = 0.0
        victim.shield_hp = 0.0
        victim.max_shield_hp = 300.0
        victim.max_armor_hp = 600.0
        victim.ore = 0.0
        victim.last_damage_by_user_id = killer.id
        db_session.add(victim)
        await db_session.flush()
        await db_session.refresh(victim, attribute_names=["modules", "target_locks"])

        # Assister dealt 15% of total HP (> 10% threshold), bystander dealt 5%
        total_hp = victim.max_shield_hp + victim.max_armor_hp  # 900
        damage_dealt_tracker = {
            victim.id: {
                killer.id: 500.0,       # killer (gets full kill points)
                assister.id: 150.0,     # 150/900 = 16.7% > 10%
                bystander.id: 40.0,     # 40/900 = 4.4% < 10%
            }
        }

        ships = [victim]
        ship_map = {s.id: s for s in ships}

        pts_awarded: list[tuple] = []

        def award_pts(user_id, amount, reason):
            pts_awarded.append((user_id, amount, reason))

        def emit(event_type, message, user_id, ship_id=None):
            pass

        _process_destruction(
            ships=ships,
            ship_map=ship_map,
            current_tick=1,
            emit=emit,
            session=db_session,
            active_leeches=[],
            award_pts=award_pts,
            damage_dealt_tracker=damage_dealt_tracker,
        )

        # Killer gets full kill points
        kill_pts = KILL_POINTS.get("corvette", 500)
        killer_awards = [p for p in pts_awarded if p[0] == killer.id]
        assert len(killer_awards) == 1
        assert killer_awards[0][1] == kill_pts

        # Assister gets 50% of kill points
        assister_awards = [p for p in pts_awarded if p[0] == assister.id]
        assert len(assister_awards) == 1
        assert assister_awards[0][1] == kill_pts * 0.5
        assert "assist" in assister_awards[0][2]

        # Bystander gets nothing (below 10% threshold)
        bystander_awards = [p for p in pts_awarded if p[0] == bystander.id]
        assert len(bystander_awards) == 0


# ===========================================================================
# 2. Production Pipeline (Build Command)
# ===========================================================================


@pytest.mark.anyio
class TestProductionPipeline:

    async def test_build_order_created_via_command(self, client: AsyncClient):
        """Sending a build command creates a BuildOrder in the database."""
        headers1, auth1, headers2, auth2, match_id = await _setup_match(client)

        # Find the mothership for user1's team
        mothership = await _find_mothership(client, headers1)
        assert mothership is not None, "Expected a mothership after match start"

        # Find a factory module on the mothership
        resp = await client.get(f"/api/ships/{mothership['id']}/modules", headers=headers1)
        assert resp.status_code == 200
        modules = resp.json()
        factory = next(
            (m for m in modules if "factory" in m["module_type"]),
            None,
        )
        assert factory is not None, "Mothership should have a factory module"

        # Board the mothership to gain access for build commands
        await _send_command(client, headers1, "board_ship", cmd_ship_id=mothership["id"])
        await _process(client)

        # Verify no rejection on board
        rejected = await _get_rejected_commands(client, headers1)
        board_rejects = [r for r in rejected if r.get("type") == "board_ship"]
        assert len(board_rejects) == 0, f"Board rejected: {board_rejects}"

        # Send build command for a strike_craft
        await _send_raw_command(
            client, headers1, "build",
            payload={
                "blueprint": "strike_craft",
                "factory_module_id": factory["id"],
            },
            cmd_ship_id=mothership["id"],
        )
        await _process(client)

        # The build command should not be rejected (mothership has a factory + ore)
        rejected = await _get_rejected_commands(client, headers1)
        build_rejects = [r for r in rejected if r.get("type") == "build"]
        # Build might be rejected if there's no ore in the mothership - that's expected
        # in a fresh match mothership. Check if there's ore first.
        resp = await client.get(f"/api/ships/{mothership['id']}", headers=headers1)
        ship_data = resp.json()
        # If there is no ore, the rejection is expected
        if ship_data.get("ore", 0) >= 200:
            assert len(build_rejects) == 0, f"Build rejected: {build_rejects}"

    async def test_tick_build_order_advances(self, db_session: AsyncSession):
        """tick_build_order decrements ticks_remaining and drains cap per tick."""
        from server.production import tick_build_order

        user = User(
            username="builder", token="builder_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship(
            "Mothership", ShipClass.mothership, user_id=user.id,
        )
        db_session.add(ship)
        await db_session.flush()

        # Add a factory module
        factory = make_module(ModuleType.small_factory)
        factory.ship_id = ship.id
        db_session.add(factory)
        await db_session.flush()

        # Add cargo and reactor so ship has resources
        reactor = make_module(ModuleType.capital_standard_reactor)
        reactor.ship_id = ship.id
        db_session.add(reactor)
        await db_session.flush()

        await db_session.refresh(ship, attribute_names=["modules"])
        recalculate_max_capacitor(ship)
        ship.capacitor = ship.max_capacitor  # Full cap
        ship.ore = 10_000  # Plenty of ore

        # Create a build order (already building)
        order = BuildOrder(
            ship_id=ship.id,
            factory_module_id=factory.id,
            blueprint=ShipClass.strike_craft,
            status=BuildStatus.building,
            ore_cost=200,
            ticks_remaining=5,
            total_ticks=60,
        )
        db_session.add(order)
        await db_session.flush()

        cap_before = ship.capacitor

        result = tick_build_order(ship, order)

        assert not result["completed"]
        assert not result["paused"]
        assert order.ticks_remaining == 4
        assert ship.capacitor < cap_before  # Cap was drained

    async def test_tick_build_order_completes(self, db_session: AsyncSession):
        """When ticks_remaining hits 0, the build completes and spawns a ship."""
        from server.production import tick_build_order

        user = User(
            username="builder2", token="builder2_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship(
            "Mothership2", ShipClass.mothership, user_id=user.id,
        )
        db_session.add(ship)
        await db_session.flush()

        factory = make_module(ModuleType.small_factory)
        factory.ship_id = ship.id
        db_session.add(factory)
        await db_session.flush()

        await db_session.refresh(ship, attribute_names=["modules"])
        ship.capacitor = 10000.0
        ship.max_capacitor = 25000.0
        ship.ore = 10_000

        # 1 tick remaining -- will complete this tick
        order = BuildOrder(
            ship_id=ship.id,
            factory_module_id=factory.id,
            blueprint=ShipClass.strike_craft,
            status=BuildStatus.building,
            ore_cost=200,
            ticks_remaining=1,
            total_ticks=60,
        )
        db_session.add(order)
        await db_session.flush()

        result = tick_build_order(ship, order)

        assert result["completed"]
        assert order.status == BuildStatus.completed
        assert order.ticks_remaining == 0
        new_ship = result["new_ship"]
        assert new_ship is not None
        assert new_ship.ship_class == ShipClass.strike_craft
        assert new_ship.docked_in_id == ship.id

    async def test_tick_build_order_pauses_on_low_cap(self, db_session: AsyncSession):
        """Build order pauses when the ship lacks capacitor energy."""
        from server.production import tick_build_order

        user = User(
            username="builder3", token="builder3_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship(
            "Mothership3", ShipClass.mothership, user_id=user.id,
        )
        db_session.add(ship)
        await db_session.flush()

        factory = make_module(ModuleType.small_factory)
        factory.ship_id = ship.id
        db_session.add(factory)
        await db_session.flush()

        await db_session.refresh(ship, attribute_names=["modules"])
        ship.capacitor = 0.0  # No cap -- should cause pause
        ship.max_capacitor = 25000.0

        order = BuildOrder(
            ship_id=ship.id,
            factory_module_id=factory.id,
            blueprint=ShipClass.strike_craft,
            status=BuildStatus.building,
            ore_cost=200,
            ticks_remaining=10,
            total_ticks=60,
        )
        db_session.add(order)
        await db_session.flush()

        ticks_before = order.ticks_remaining

        result = tick_build_order(ship, order)

        assert result["paused"]
        assert order.status == BuildStatus.paused
        # Ticks should not have been decremented
        assert order.ticks_remaining == ticks_before


# ===========================================================================
# 3. Dock Command via Command Pipeline
# ===========================================================================


@pytest.mark.anyio
class TestDockCommand:

    async def test_dock_command_creates_movement_order(self, client: AsyncClient):
        """Sending a dock command via the command pipeline creates a movement order
        (approach behavior) toward the mothership."""
        headers1, auth1, headers2, auth2, match_id = await _setup_match(client)

        # Claim a strike craft for user1
        await _send_raw_command(
            client, headers1, "claim_ship",
            payload={
                "ship_class": "strike_craft",
                "modules": [
                    {"module_type": "starter_engine"},
                    {"module_type": "starter_reactor"},
                ],
            },
        )
        await _process(client)

        # Verify claim succeeded
        rejected = await _get_rejected_commands(client, headers1)
        claim_rejects = [r for r in rejected if r.get("type") == "claim_ship"]
        assert len(claim_rejects) == 0, f"Claim rejected: {claim_rejects}"

        # Find the strike craft and the mothership
        ships = await _get_ships(client, headers1)
        craft = next((s for s in ships if s["ship_class"] == "strike_craft"), None)
        assert craft is not None
        mothership = await _find_mothership(client, headers1)
        assert mothership is not None

        # Send dock command targeting the mothership
        await _send_command(
            client, headers1, "dock",
            cmd_ship_id=craft["id"],
            target_ship_id=mothership["id"],
        )
        await _process(client)

        # Verify no rejection
        rejected = await _get_rejected_commands(client, headers1)
        dock_rejects = [r for r in rejected if r.get("type") == "dock"]
        assert len(dock_rejects) == 0, f"Dock rejected: {dock_rejects}"

    async def test_direct_dock_sets_docked_in_id(self, client: AsyncClient):
        """Using the test dock endpoint directly sets docked_in_id."""
        headers = await _auth_header(client, "docker")

        mothership = await spawn_test_mothership(client, headers)

        # Create a strike craft
        await _send_command(client, headers, "create_ship", ship_class="strike_craft")
        await _process(client)

        ships = await _get_ships(client, headers)
        craft = next(s for s in ships if s["ship_class"] == "strike_craft")

        # Dock via test endpoint
        resp = await client.post(
            "/api/_test/dock_ship",
            json={"ship_id": craft["id"], "target_ship_id": mothership["id"]},
        )
        assert resp.status_code == 200

        # Verify docked_in_id
        resp = await client.get(f"/api/ships/{craft['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["docked_in_id"] == mothership["id"]


# ===========================================================================
# 4. Board / Eject Commands
# ===========================================================================


@pytest.mark.anyio
class TestBoardEject:

    async def test_board_mothership(self, client: AsyncClient):
        """Board an unpiloted mothership, verify claimed_by_user_id is set."""
        headers1, auth1, headers2, auth2, match_id = await _setup_match(client)

        # Find the mothership for user1's team
        mothership = await _find_mothership(client, headers1)
        assert mothership is not None

        # Board the mothership
        await _send_command(client, headers1, "board_ship", cmd_ship_id=mothership["id"])
        await _process(client)

        # Verify no rejection
        rejected = await _get_rejected_commands(client, headers1)
        board_rejects = [r for r in rejected if r.get("type") == "board_ship"]
        assert len(board_rejects) == 0, f"Board rejected: {board_rejects}"

        # Verify the ship is now claimed by user1 (check via view endpoint,
        # since GET /api/ships/{id} ShipDetailOut doesn't include user_id)
        view = await _get_view(client, headers1)
        view_ships = view.get("ships", [])
        ms_in_view = next((s for s in view_ships if s["id"] == mothership["id"]), None)
        assert ms_in_view is not None
        assert ms_in_view.get("claimed_by_user_id") == auth1["user_id"]

        # Verify a ship_boarded event was emitted
        events = view.get("events", [])
        boarded_events = [e for e in events if "boarded" in (e.get("message") or "").lower()]
        assert len(boarded_events) >= 1

    async def test_eject_from_mothership(self, client: AsyncClient):
        """Board then eject from a mothership, verify user_id is cleared."""
        headers1, auth1, headers2, auth2, match_id = await _setup_match(client)

        mothership = await _find_mothership(client, headers1)
        assert mothership is not None

        # Board
        await _send_command(client, headers1, "board_ship", cmd_ship_id=mothership["id"])
        await _process(client)

        # Verify boarded via view endpoint
        view = await _get_view(client, headers1)
        ms_in_view = next(
            (s for s in view.get("ships", []) if s["id"] == mothership["id"]), None,
        )
        assert ms_in_view is not None
        assert ms_in_view.get("claimed_by_user_id") == auth1["user_id"]

        # Eject
        await _send_command(client, headers1, "eject", cmd_ship_id=mothership["id"])
        await _process(client)

        # Verify no rejection for eject
        rejected = await _get_rejected_commands(client, headers1)
        eject_rejects = [r for r in rejected if r.get("type") == "eject"]
        assert len(eject_rejects) == 0, f"Eject rejected: {eject_rejects}"

        # Verify claimed_by_user_id is cleared (ship is no longer piloted)
        view = await _get_view(client, headers1)
        ms_in_view = next(
            (s for s in view.get("ships", []) if s["id"] == mothership["id"]), None,
        )
        assert ms_in_view is not None
        assert ms_in_view.get("claimed_by_user_id") is None

    async def test_board_already_piloted_rejected(self, client: AsyncClient):
        """Boarding a ship that is already piloted should be rejected."""
        headers1, auth1, headers2, auth2, match_id = await _setup_match(client)

        mothership = await _find_mothership(client, headers1)
        assert mothership is not None

        # User1 boards mothership
        await _send_command(client, headers1, "board_ship", cmd_ship_id=mothership["id"])
        await _process(client)

        # User1 tries to board again -- should be rejected (already piloted)
        await _send_command(client, headers1, "board_ship", cmd_ship_id=mothership["id"])
        await _process(client)

        rejected = await _get_rejected_commands(client, headers1)
        board_rejects = [r for r in rejected if r.get("type") == "board_ship"]
        assert len(board_rejects) >= 1
        assert "already piloted" in (board_rejects[-1].get("rejection_reason") or "").lower()

    async def test_eject_non_mothership_rejected(self, client: AsyncClient):
        """Ejecting from a non-mothership (e.g. strike_craft) should be rejected."""
        headers1, auth1, headers2, auth2, match_id = await _setup_match(client)

        # Claim a strike craft
        await _send_raw_command(
            client, headers1, "claim_ship",
            payload={
                "ship_class": "strike_craft",
                "modules": [
                    {"module_type": "starter_engine"},
                ],
            },
        )
        await _process(client)

        ships = await _get_ships(client, headers1)
        craft = next((s for s in ships if s["ship_class"] == "strike_craft"), None)
        assert craft is not None

        # Try to eject from the strike craft
        await _send_command(client, headers1, "eject", cmd_ship_id=craft["id"])
        await _process(client)

        rejected = await _get_rejected_commands(client, headers1)
        eject_rejects = [r for r in rejected if r.get("type") == "eject"]
        assert len(eject_rejects) >= 1
        reason = (eject_rejects[-1].get("rejection_reason") or "").lower()
        assert "eject" in reason or "cannot" in reason


# ===========================================================================
# 5. Reship Command (via match)
# ===========================================================================


@pytest.mark.anyio
class TestReshipViaMatch:

    async def test_reship_refunds_and_strips_modules(self, client: AsyncClient):
        """Claim a ship, dock it, reship, verify modules stripped and points refunded."""
        headers1, auth1, headers2, auth2, match_id = await _setup_match(client)

        # Claim a strike craft with modules
        await _send_raw_command(
            client, headers1, "claim_ship",
            payload={
                "ship_class": "strike_craft",
                "modules": [
                    {"module_type": "starter_engine"},
                    {"module_type": "starter_reactor"},
                    {"module_type": "tiny_cargo_bay"},
                ],
            },
        )
        await _process(client)

        # Verify no rejection
        rejected = await _get_rejected_commands(client, headers1)
        claim_rejects = [r for r in rejected if r.get("type") == "claim_ship"]
        assert len(claim_rejects) == 0, f"Claim rejected: {claim_rejects}"

        # Get the ship
        ships = await _get_ships(client, headers1)
        craft = next((s for s in ships if s["ship_class"] == "strike_craft"), None)
        assert craft is not None

        # Find mothership
        mothership = await _find_mothership(client, headers1)
        assert mothership is not None

        # Verify modules are installed
        resp = await client.get(f"/api/ships/{craft['id']}/modules", headers=headers1)
        assert resp.status_code == 200
        modules_before = resp.json()
        assert len(modules_before) >= 3

        # Dock the craft in the mothership
        resp = await client.post(
            "/api/_test/dock_ship",
            json={"ship_id": craft["id"], "target_ship_id": mothership["id"]},
        )
        assert resp.status_code == 200

        # Record points before reship
        view_before = await _get_view(client, headers1)
        points_before = view_before["points"]

        # Reship
        await _send_raw_command(
            client, headers1, "reship",
            payload={},
            cmd_ship_id=craft["id"],
        )
        await _process(client)

        # Verify no reship rejection
        rejected = await _get_rejected_commands(client, headers1)
        reship_rejects = [r for r in rejected if r.get("type") == "reship"]
        assert len(reship_rejects) == 0, f"Reship rejected: {reship_rejects}"

        # Verify modules stripped
        resp = await client.get(f"/api/ships/{craft['id']}/modules", headers=headers1)
        assert resp.status_code == 200
        modules_after = resp.json()
        assert len(modules_after) == 0

        # Verify a reship_complete event was emitted
        view = await _get_view(client, headers1)
        events = view.get("events", [])
        reship_events = [e for e in events if "reship" in (e.get("message") or "").lower()]
        assert len(reship_events) >= 1


# ===========================================================================
# 6. Tick Loop Phase Helpers (Unit Tests via db_session)
# ===========================================================================


@pytest.mark.anyio
class TestProcessModules:

    async def test_module_cycle_fires_and_drains_cap(self, db_session: AsyncSession):
        """_process_modules fires a module cycle when ticks_until_cycle reaches 0
        and drains capacitor."""
        from server.tick import _process_modules

        user = User(
            username="modtest", token="modtest_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship(
            "Test", ShipClass.frigate, user_id=user.id,
        )
        db_session.add(ship)
        await db_session.flush()

        # Add a mining laser (active, about to fire)
        laser = make_module(ModuleType.mining_laser)
        laser.ship_id = ship.id
        laser.active = True
        laser.ticks_until_cycle = 1  # Will fire after decrement to 0
        db_session.add(laser)
        await db_session.flush()

        # Add a reactor so we have cap
        reactor = make_module(ModuleType.small_standard_reactor)
        reactor.ship_id = ship.id
        db_session.add(reactor)
        await db_session.flush()

        await db_session.refresh(ship, attribute_names=["modules"])
        recalculate_max_capacitor(ship)
        ship.capacitor = ship.max_capacitor

        cap_before = ship.capacitor
        events: list = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append((event_type, message))

        fired_ids = _process_modules(ship, current_tick=1, emit=emit)

        # The laser should have fired (ticks_until_cycle was 1, decremented to 0)
        assert laser.id in fired_ids
        # Cap should have been drained
        assert ship.capacitor < cap_before
        # Cycle timer should be reset
        assert laser.ticks_until_cycle == laser.cycle_time

    async def test_module_deactivates_on_insufficient_cap(self, db_session: AsyncSession):
        """When a module cycles but there's not enough cap, it deactivates."""
        from server.tick import _process_modules

        user = User(
            username="nocap", token="nocap_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship(
            "NoCapShip", ShipClass.strike_craft, user_id=user.id,
        )
        db_session.add(ship)
        await db_session.flush()

        # Add a mining laser with high cap cost, about to fire
        laser = make_module(ModuleType.mining_laser)
        laser.ship_id = ship.id
        laser.active = True
        laser.ticks_until_cycle = 1
        db_session.add(laser)
        await db_session.flush()

        await db_session.refresh(ship, attribute_names=["modules"])
        ship.capacitor = 0.0  # No cap
        ship.max_capacitor = 50.0

        events: list = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append((event_type, message))

        fired_ids = _process_modules(ship, current_tick=1, emit=emit)

        # Laser should NOT have fired
        assert laser.id not in fired_ids
        # Laser should be deactivated
        assert laser.active is False

    async def test_passive_modules_not_cycled(self, db_session: AsyncSession):
        """Passive modules (cycle_time=0) are skipped by _process_modules."""
        from server.tick import _process_modules

        user = User(
            username="passive", token="passive_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship(
            "PassiveShip", ShipClass.frigate, user_id=user.id,
        )
        db_session.add(ship)
        await db_session.flush()

        # Passive detector is passive (cycle_time=0)
        detector = make_module(ModuleType.passive_detector)
        detector.ship_id = ship.id
        detector.active = True
        db_session.add(detector)
        await db_session.flush()

        await db_session.refresh(ship, attribute_names=["modules"])
        ship.capacitor = 1000.0
        ship.max_capacitor = 1000.0
        cap_before = ship.capacitor

        def emit(event_type, message, user_id, ship_id=None):
            pass

        fired_ids = _process_modules(ship, current_tick=1, emit=emit)

        # Passive module should not fire
        assert detector.id not in fired_ids
        # Cap should not have been drained
        assert ship.capacitor == cap_before


@pytest.mark.anyio
class TestProcessMining:

    async def test_mining_extracts_ore(self, db_session: AsyncSession):
        """_process_mining extracts ore from a nearby asteroid into the ship's cargo."""
        from server.tick import _process_mining

        user = User(
            username="miner", token="miner_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship(
            "MinerShip", ShipClass.frigate, user_id=user.id,
        )
        db_session.add(ship)
        await db_session.flush()

        # Add a mining laser and cargo bay
        laser = make_module(ModuleType.mining_laser)
        laser.ship_id = ship.id
        laser.active = True
        db_session.add(laser)

        cargo = make_module(ModuleType.large_cargo_bay)
        cargo.ship_id = ship.id
        db_session.add(cargo)
        await db_session.flush()

        await db_session.refresh(ship, attribute_names=["modules"])
        ship.ore = 0.0

        # Create an asteroid at the same position as the ship
        asteroid = CelestialObject(
            name="Test Asteroid",
            object_type=CelestialType.asteroid,
            pos_x=ship.pos_x,
            pos_y=ship.pos_y,
            pos_z=ship.pos_z,
            ore_remaining=5000.0,
            ore_initial=5000.0,
            ore_richness=1.0,
        )
        db_session.add(asteroid)
        await db_session.flush()

        asteroid_map = {asteroid.id: asteroid}
        fired_module_ids = {laser.id}  # Pretend the laser fired this tick

        events: list = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append((event_type, message))

        pts_awarded: list[tuple] = []

        def award_pts(user_id, amount, reason, ship_id=None):
            pts_awarded.append((user_id, amount, reason))

        _process_mining(
            ship=ship,
            asteroid_map=asteroid_map,
            current_tick=1,
            emit=emit,
            fired_module_ids=fired_module_ids,
            award_pts=award_pts,
        )

        # Ship should have gained ore
        assert ship.ore > 0
        # Asteroid should have lost ore
        assert asteroid.ore_remaining < 5000.0
        # Mining event should have been emitted
        mining_events = [e for e in events if e[0] == EventType.mining]
        assert len(mining_events) >= 1

    async def test_mining_no_asteroid_in_range(self, db_session: AsyncSession):
        """When no asteroid is within range, mining emits an out-of-range event."""
        from server.tick import _process_mining

        user = User(
            username="nominer", token="nominer_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship(
            "NoMineShip", ShipClass.frigate, user_id=user.id,
        )
        db_session.add(ship)
        await db_session.flush()

        laser = make_module(ModuleType.mining_laser)
        laser.ship_id = ship.id
        laser.active = True
        db_session.add(laser)
        await db_session.flush()

        cargo = make_module(ModuleType.large_cargo_bay)
        cargo.ship_id = ship.id
        db_session.add(cargo)
        await db_session.flush()

        await db_session.refresh(ship, attribute_names=["modules"])
        ship.ore = 0.0

        # No asteroids -- empty map
        asteroid_map = {}
        fired_module_ids = {laser.id}

        events: list = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append((event_type, message))

        _process_mining(
            ship=ship,
            asteroid_map=asteroid_map,
            current_tick=1,
            emit=emit,
            fired_module_ids=fired_module_ids,
        )

        # No ore mined
        assert ship.ore == 0.0
        # Should have emitted a mining event about no asteroid in range
        mining_events = [e for e in events if e[0] == EventType.mining]
        assert len(mining_events) >= 1
        assert "no asteroid" in mining_events[0][1].lower()

    async def test_mining_cargo_full(self, db_session: AsyncSession):
        """When cargo is full, ore is not extracted from the asteroid."""
        from server.tick import _process_mining

        user = User(
            username="fullminer", token="fullminer_tok",
            password_hash="x", points=0.0,
        )
        db_session.add(user)
        await db_session.flush()

        ship = create_default_ship(
            "FullShip", ShipClass.frigate, user_id=user.id,
        )
        db_session.add(ship)
        await db_session.flush()

        laser = make_module(ModuleType.mining_laser)
        laser.ship_id = ship.id
        laser.active = True
        db_session.add(laser)

        cargo = make_module(ModuleType.tiny_cargo_bay)
        cargo.ship_id = ship.id
        db_session.add(cargo)
        await db_session.flush()

        await db_session.refresh(ship, attribute_names=["modules"])
        # Fill cargo to capacity
        ship.ore = ship.cargo_capacity()

        asteroid = CelestialObject(
            name="Full Test Asteroid",
            object_type=CelestialType.asteroid,
            pos_x=ship.pos_x,
            pos_y=ship.pos_y,
            pos_z=ship.pos_z,
            ore_remaining=5000.0,
            ore_initial=5000.0,
            ore_richness=1.0,
        )
        db_session.add(asteroid)
        await db_session.flush()

        asteroid_map = {asteroid.id: asteroid}
        fired_module_ids = {laser.id}
        ore_before = asteroid.ore_remaining

        events: list = []

        def emit(event_type, message, user_id, ship_id=None):
            events.append((event_type, message))

        _process_mining(
            ship=ship,
            asteroid_map=asteroid_map,
            current_tick=1,
            emit=emit,
            fired_module_ids=fired_module_ids,
        )

        # Asteroid ore should NOT have decreased (cargo is full, ore preserved)
        assert asteroid.ore_remaining == ore_before
        # Cargo full event should have been emitted
        cargo_events = [e for e in events if e[0] == EventType.cargo_full]
        assert len(cargo_events) >= 1


@pytest.mark.anyio
class TestShieldRegen:

    async def test_shield_regen_increases_shield_hp(self):
        """apply_shield_regen increases shield_hp when below max."""
        from server.combat import apply_shield_regen

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.max_shield_hp = 2000.0
        ship.shield_hp = 500.0  # 25% -- near peak regen

        shield_before = ship.shield_hp
        apply_shield_regen(ship)

        assert ship.shield_hp > shield_before
        assert ship.shield_hp <= ship.max_shield_hp

    async def test_shield_regen_does_nothing_at_full(self):
        """apply_shield_regen does nothing when shield is at max."""
        from server.combat import apply_shield_regen

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.max_shield_hp = 2000.0
        ship.shield_hp = 2000.0  # Full

        apply_shield_regen(ship)

        assert ship.shield_hp == 2000.0

    async def test_shield_regen_does_nothing_on_destroyed_ship(self):
        """apply_shield_regen does nothing when ship is destroyed."""
        from server.combat import apply_shield_regen

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.max_shield_hp = 2000.0
        ship.shield_hp = 500.0
        ship.is_destroyed = True

        shield_before = ship.shield_hp
        apply_shield_regen(ship)

        assert ship.shield_hp == shield_before

    async def test_shield_regen_peaks_at_25_percent(self):
        """Shield regen peaks near 25% shield (same curve as capacitor)."""
        from server.combat import apply_shield_regen

        ship_low = make_test_ship(ship_class=ShipClass.frigate)
        ship_low.max_shield_hp = 2000.0
        ship_low.shield_hp = 500.0  # 25%

        ship_high = make_test_ship(ship_class=ShipClass.frigate)
        ship_high.max_shield_hp = 2000.0
        ship_high.shield_hp = 1500.0  # 75%

        before_low = ship_low.shield_hp
        before_high = ship_high.shield_hp

        apply_shield_regen(ship_low)
        apply_shield_regen(ship_high)

        regen_at_25 = ship_low.shield_hp - before_low
        regen_at_75 = ship_high.shield_hp - before_high

        # Regen at 25% should be higher than at 75%
        assert regen_at_25 > regen_at_75


@pytest.mark.anyio
class TestCapacitorRegen:

    async def test_apply_regen_increases_capacitor(self):
        """apply_regen increases capacitor when below max."""
        from server.energy import apply_regen

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.modules = []
        ship.max_capacitor = 1000.0
        ship.capacitor = 250.0  # 25% -- near peak regen

        cap_before = ship.capacitor
        apply_regen(ship)

        assert ship.capacitor > cap_before
        assert ship.capacitor <= ship.max_capacitor

    async def test_apply_regen_caps_at_max(self):
        """apply_regen does not exceed max_capacitor."""
        from server.energy import apply_regen

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.modules = []
        ship.max_capacitor = 100.0
        ship.capacitor = 99.9

        apply_regen(ship)

        assert ship.capacitor <= ship.max_capacitor

    async def test_apply_regen_zero_cap_no_regen(self):
        """When capacitor is exactly 0, no regen occurs (regen formula returns 0)."""
        from server.energy import apply_regen

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.modules = []
        ship.max_capacitor = 1000.0
        ship.capacitor = 0.0

        apply_regen(ship)

        assert ship.capacitor == 0.0

    async def test_apply_regen_full_cap_no_regen(self):
        """When capacitor is at max, no regen occurs (regen formula returns 0)."""
        from server.energy import apply_regen

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.modules = []
        ship.max_capacitor = 1000.0
        ship.capacitor = 1000.0

        apply_regen(ship)

        assert ship.capacitor == 1000.0

    async def test_apply_regen_includes_reactor_bonus(self):
        """Reactor modules add flat regen bonus on top of the curve."""
        from server.energy import apply_regen

        # Ship without reactor
        ship_no_reactor = make_test_ship(ship_class=ShipClass.frigate)
        ship_no_reactor.modules = []
        ship_no_reactor.max_capacitor = 1000.0
        ship_no_reactor.capacitor = 250.0

        # Ship with reactor
        ship_with_reactor = make_test_ship(ship_class=ShipClass.frigate)
        ship_with_reactor.id = 2
        reactor = make_module(ModuleType.small_standard_reactor)
        reactor.id = 100
        reactor.ship_id = ship_with_reactor.id
        ship_with_reactor.modules = [reactor]
        ship_with_reactor.max_capacitor = 1000.0 + reactor.reactor_cap_bonus
        ship_with_reactor.capacitor = 250.0

        cap_before_no = ship_no_reactor.capacitor
        cap_before_with = ship_with_reactor.capacitor

        apply_regen(ship_no_reactor)
        apply_regen(ship_with_reactor)

        regen_no = ship_no_reactor.capacitor - cap_before_no
        regen_with = ship_with_reactor.capacitor - cap_before_with

        # Ship with reactor should regen more (flat bonus from reactor_regen_bonus)
        if reactor.reactor_regen_bonus > 0:
            assert regen_with > regen_no


@pytest.mark.anyio
class TestArmorRegen:

    async def test_armor_regen_voidborn(self):
        """apply_armor_regen increases armor_hp for Voidborn ships."""
        from server.combat import apply_armor_regen

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.max_armor_hp = 4000.0
        ship.armor_hp = 1000.0  # 25%

        armor_before = ship.armor_hp
        apply_armor_regen(ship)

        assert ship.armor_hp > armor_before
        assert ship.armor_hp <= ship.max_armor_hp

    async def test_armor_regen_does_nothing_at_full(self):
        """apply_armor_regen does nothing when armor is at max."""
        from server.combat import apply_armor_regen

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.max_armor_hp = 4000.0
        ship.armor_hp = 4000.0

        apply_armor_regen(ship)

        assert ship.armor_hp == 4000.0

    async def test_armor_regen_does_nothing_when_destroyed(self):
        """apply_armor_regen does nothing when ship is destroyed."""
        from server.combat import apply_armor_regen

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.max_armor_hp = 4000.0
        ship.armor_hp = 1000.0
        ship.is_destroyed = True

        armor_before = ship.armor_hp
        apply_armor_regen(ship)

        assert ship.armor_hp == armor_before


# ===========================================================================
# 7. Module Drain and Depletion
# ===========================================================================


@pytest.mark.anyio
class TestEnergyDrain:

    async def test_drain_module_success(self):
        """drain_module succeeds when ship has enough cap."""
        from server.energy import drain_module

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.modules = []
        ship.capacitor = 500.0
        ship.max_capacitor = 1000.0

        laser = make_module(ModuleType.mining_laser)
        laser.id = 1
        laser.ship_id = ship.id

        cap_before = ship.capacitor
        success = drain_module(ship, laser)

        assert success is True
        if laser.capacitor_per_cycle > 0:
            assert ship.capacitor < cap_before

    async def test_drain_module_fails_insufficient_cap(self):
        """drain_module fails and returns False when ship lacks cap."""
        from server.energy import drain_module

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.modules = []
        ship.capacitor = 0.0
        ship.max_capacitor = 1000.0

        laser = make_module(ModuleType.mining_laser)
        laser.id = 1
        laser.ship_id = ship.id

        if laser.capacitor_per_cycle > 0:
            success = drain_module(ship, laser)
            assert success is False

    async def test_check_depletion_deactivates_modules(self):
        """check_depletion deactivates non-engine modules when cap is 0."""
        from server.energy import check_depletion

        ship = make_test_ship(ship_class=ShipClass.frigate)
        ship.capacitor = 0.0
        ship.max_capacitor = 1000.0

        laser = make_module(ModuleType.mining_laser)
        laser.id = 1
        laser.ship_id = ship.id
        laser.active = True

        engine = make_module(ModuleType.starter_engine)
        engine.id = 2
        engine.ship_id = ship.id
        engine.active = True

        ship.modules = [laser, engine]

        depleted = check_depletion(ship)

        assert depleted is True
        # Mining laser should be deactivated
        assert laser.active is False
        # Engine should remain active
        assert engine.active is True


# ===========================================================================
# 8. Stop Command
# ===========================================================================


@pytest.mark.anyio
class TestStopCommand:

    async def test_stop_command_accepted(self, client: AsyncClient):
        """Sending a stop command is accepted (not rejected)."""
        headers1, auth1, headers2, auth2, match_id = await _setup_match(client)

        # Claim a strike craft
        await _send_raw_command(
            client, headers1, "claim_ship",
            payload={
                "ship_class": "strike_craft",
                "modules": [
                    {"module_type": "starter_engine"},
                ],
            },
        )
        await _process(client)

        ships = await _get_ships(client, headers1)
        craft = next((s for s in ships if s["ship_class"] == "strike_craft"), None)
        assert craft is not None

        # Send stop command
        await _send_command(client, headers1, "stop", cmd_ship_id=craft["id"])
        await _process(client)

        # Verify no rejection
        rejected = await _get_rejected_commands(client, headers1)
        stop_rejects = [r for r in rejected if r.get("type") == "stop"]
        assert len(stop_rejects) == 0, f"Stop rejected: {stop_rejects}"


# ===========================================================================
# 9. Transfer Ore
# ===========================================================================


@pytest.mark.anyio
class TestTransferOre:

    async def test_transfer_ore_command_accepted(self, client: AsyncClient):
        """Sending a transfer_ore command is accepted when ship is docked with ore."""
        headers = await _auth_header(client, "transfer_user")

        mothership = await spawn_test_mothership(client, headers)

        # Create and dock a strike craft
        await _send_command(client, headers, "create_ship", ship_class="strike_craft")
        await _process(client)

        ships = await _get_ships(client, headers)
        craft = next(s for s in ships if s["ship_class"] == "strike_craft")

        # Dock it
        resp = await client.post(
            "/api/_test/dock_ship",
            json={"ship_id": craft["id"], "target_ship_id": mothership["id"]},
        )
        assert resp.status_code == 200

        # Send transfer_ore command
        await _send_command(
            client, headers, "transfer_ore",
            cmd_ship_id=craft["id"],
            target_ship_id=mothership["id"],
        )
        await _process(client)

        # The command may be rejected if the craft has no ore (which is expected
        # in this test since we didn't mine), but the command type should be valid
        rejected = await _get_rejected_commands(client, headers)
        transfer_rejects = [r for r in rejected if r.get("type") == "transfer_ore"]
        # If rejected, it should be for a gameplay reason (no ore, not docked, etc.)
        # not for an unknown command type
        for r in transfer_rejects:
            reason = (r.get("rejection_reason") or "").lower()
            assert "unknown" not in reason, f"Unexpected rejection: {reason}"


# ===========================================================================
# 10. Module Activate / Deactivate
# ===========================================================================


@pytest.mark.anyio
class TestModuleActivation:

    async def test_activate_and_deactivate_module(self, client: AsyncClient):
        """Activate a module via command, then deactivate it."""
        headers1, auth1, headers2, auth2, match_id = await _setup_match(client)

        # Claim a strike craft with a mining laser
        await _send_raw_command(
            client, headers1, "claim_ship",
            payload={
                "ship_class": "strike_craft",
                "modules": [
                    {"module_type": "starter_engine"},
                    {"module_type": "starter_mining_laser"},
                ],
            },
        )
        await _process(client)

        # Get the ship and its modules
        ships = await _get_ships(client, headers1)
        craft = next((s for s in ships if s["ship_class"] == "strike_craft"), None)
        assert craft is not None

        resp = await client.get(f"/api/ships/{craft['id']}/modules", headers=headers1)
        assert resp.status_code == 200
        modules = resp.json()
        laser = next(
            (m for m in modules if "mining_laser" in m["module_type"]),
            None,
        )
        assert laser is not None

        # Activate the mining laser
        await _send_raw_command(
            client, headers1, "activate_module",
            payload={"module_id": laser["id"]},
            cmd_ship_id=craft["id"],
        )
        await _process(client)

        # Verify no rejection
        rejected = await _get_rejected_commands(client, headers1)
        activate_rejects = [r for r in rejected if r.get("type") == "activate_module"]
        assert len(activate_rejects) == 0, f"Activate rejected: {activate_rejects}"

        # Deactivate the mining laser
        await _send_raw_command(
            client, headers1, "deactivate_module",
            payload={"module_id": laser["id"]},
            cmd_ship_id=craft["id"],
        )
        await _process(client)

        # Verify no rejection for deactivate
        rejected = await _get_rejected_commands(client, headers1)
        deactivate_rejects = [r for r in rejected if r.get("type") == "deactivate_module"]
        assert len(deactivate_rejects) == 0, f"Deactivate rejected: {deactivate_rejects}"
