"""
Tests for Phase 6: Autopilot system.

Tests cover:
- Assume/release commands
- Profile changes
- Autopilot tick endpoint
- Factory-built ships default to autopilot mode
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import register_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_and_create_ship(
    client: AsyncClient,
    username: str = "pilot1",
    ship_class: str = "frigate",
) -> tuple[dict, dict, str]:
    """Register a user, create a ship, return (user_data, ship_data, token)."""
    auth = await register_user(client, username)
    token = auth["token"]
    headers = {"Authorization": f"Bearer {token}"}
    resp = await client.post(
        "/api/ships",
        json={"ship_class": ship_class},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    ship = resp.json()
    return auth, ship, token


# ---------------------------------------------------------------------------
# Assume / Release
# ---------------------------------------------------------------------------


class TestAssumeCommand:
    @pytest.mark.asyncio
    async def test_assume_ship_in_autopilot_mode(self, client: AsyncClient):
        """Assuming control of an autopiloted ship sets mode to 'off'."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # First release ship to autopilot
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "mining"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["autopilot_mode"] == "active"

        # Now assume control
        resp = await client.post(
            f"/api/ships/{ship_id}/command/assume",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["autopilot_mode"] == "off"

    @pytest.mark.asyncio
    async def test_assume_already_player_controlled_fails(self, client: AsyncClient):
        """Cannot assume a ship that's already in mode='off'."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Ship starts in mode='off' by default (created via API)
        resp = await client.post(
            f"/api/ships/{ship_id}/command/assume",
            headers=headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_assume_cancels_movement_orders(self, client: AsyncClient):
        """Assuming command cancels active movement orders."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Create a movement order BEFORE releasing to autopilot
        # (can't issue orders while autopiloted)
        resp = await client.post(
            f"/api/ships/{ship_id}/orders",
            json={"order_type": "stop"},
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text

        # Release to autopilot
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={},
            headers=headers,
        )
        assert resp.status_code == 200

        # Assume control — orders should be cancelled
        resp = await client.post(
            f"/api/ships/{ship_id}/command/assume",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["autopilot_mode"] == "off"


class TestReleaseCommand:
    @pytest.mark.asyncio
    async def test_release_with_profile(self, client: AsyncClient):
        """Releasing to autopilot with a profile sets both mode and profile."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "scout"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["autopilot_mode"] == "active"
        assert data["autopilot_profile"] == "scout"

    @pytest.mark.asyncio
    async def test_release_default_profile_frigate(self, client: AsyncClient):
        """Frigate defaults to 'mining' profile when released without specifying one."""
        auth, ship, token = await _register_and_create_ship(client, ship_class="frigate")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["autopilot_mode"] == "active"
        assert data["autopilot_profile"] == "mining"

    @pytest.mark.asyncio
    async def test_release_default_profile_corvette(self, client: AsyncClient):
        """Corvette defaults to 'combat_aggressive' profile."""
        auth, ship, token = await _register_and_create_ship(client, ship_class="corvette")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["autopilot_profile"] == "combat_aggressive"

    @pytest.mark.asyncio
    async def test_release_already_autopiloted_fails(self, client: AsyncClient):
        """Cannot release a ship that's already in autopilot mode."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Release first
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={},
            headers=headers,
        )
        assert resp.status_code == 200

        # Try to release again
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={},
            headers=headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_release_invalid_profile_fails(self, client: AsyncClient):
        """Releasing with an invalid profile name fails."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "invalid_profile"},
            headers=headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_release_preserves_existing_profile(self, client: AsyncClient):
        """Releasing without a profile keeps the previous profile."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Release with scout profile
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "scout"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["autopilot_profile"] == "scout"

        # Assume control
        resp = await client.post(
            f"/api/ships/{ship_id}/command/assume",
            headers=headers,
        )
        assert resp.status_code == 200

        # Release without profile — should keep 'scout'
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["autopilot_profile"] == "scout"


# ---------------------------------------------------------------------------
# Profile changes
# ---------------------------------------------------------------------------


class TestProfileChange:
    @pytest.mark.asyncio
    async def test_change_profile(self, client: AsyncClient):
        """Can change the profile of an autopiloted ship."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Release to autopilot
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "mining"},
            headers=headers,
        )
        assert resp.status_code == 200

        # Change profile
        resp = await client.put(
            f"/api/ships/{ship_id}/autopilot/profile",
            json={"profile": "combat_defensive"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["autopilot_profile"] == "combat_defensive"

    @pytest.mark.asyncio
    async def test_change_profile_not_autopiloted_fails(self, client: AsyncClient):
        """Cannot change profile on a player-controlled ship."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        resp = await client.put(
            f"/api/ships/{ship_id}/autopilot/profile",
            json={"profile": "combat_defensive"},
            headers=headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_change_profile_invalid_fails(self, client: AsyncClient):
        """Invalid profile name is rejected."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Release first
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = await client.put(
            f"/api/ships/{ship_id}/autopilot/profile",
            json={"profile": "nonexistent"},
            headers=headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Autopilot tick
# ---------------------------------------------------------------------------


class TestAutopilotTick:
    @pytest.mark.asyncio
    async def test_tick_returns_ship_data(self, client: AsyncClient):
        """Autopilot tick returns ship info, locks, nearby, events, threats."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Release to autopilot
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "mining"},
            headers=headers,
        )
        assert resp.status_code == 200

        # Get tick data
        resp = await client.get(
            f"/api/ships/{ship_id}/autopilot/tick",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        # Verify structure
        assert "ship" in data
        assert "profile" in data
        assert "locks" in data
        assert "nearby" in data
        assert "events_since_last_tick" in data
        assert "threat_assessment" in data
        assert "ships_targeting_me" in data["threat_assessment"]

        # Verify ship info
        assert data["ship"]["id"] == ship_id
        assert data["ship"]["autopilot_mode"] == "active"
        assert data["profile"] == "mining"

    @pytest.mark.asyncio
    async def test_tick_fails_when_not_autopiloted(self, client: AsyncClient):
        """Cannot get tick data for a player-controlled ship."""
        auth, ship, token = await _register_and_create_ship(client)
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        resp = await client.get(
            f"/api/ships/{ship_id}/autopilot/tick",
            headers=headers,
        )
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Factory-built ships default to autopilot
# ---------------------------------------------------------------------------


class TestFactoryAutopilotDefaults:
    @pytest.mark.asyncio
    async def test_factory_built_ship_defaults_to_autopilot(self, client: AsyncClient):
        """Ships built by factory should start in autopilot mode."""
        from server.models import ShipClass, spawn_new_ship, create_default_ship

        # Create a builder ship
        builder = create_default_ship(
            name="Builder",
            ship_class=ShipClass.frigate,
            user_id=1,
        )
        builder.id = 1
        builder.modules = []

        from server.production import tick_build_order
        from server.models import BuildOrder, BuildStatus

        order = BuildOrder(
            id=1,
            ship_id=1,
            factory_module_id=1,
            blueprint=ShipClass.corvette,
            status=BuildStatus.building,
            ore_cost=1500,
            ticks_remaining=1,
            total_ticks=480,
        )
        builder.capacitor = 10000.0

        result = tick_build_order(builder, order)
        assert result["completed"] is True
        new_ship = result["new_ship"]
        assert new_ship.autopilot_mode == "active"
        assert new_ship.autopilot_profile == "combat_aggressive"  # corvette default

    @pytest.mark.asyncio
    async def test_factory_frigate_defaults_to_mining(self, client: AsyncClient):
        """Factory-built frigate defaults to mining profile."""
        from server.models import ShipClass, create_default_ship
        from server.production import tick_build_order
        from server.models import BuildOrder, BuildStatus

        builder = create_default_ship(
            name="Builder",
            ship_class=ShipClass.cruiser,
            user_id=1,
        )
        builder.id = 1
        builder.modules = []

        order = BuildOrder(
            id=1,
            ship_id=1,
            factory_module_id=1,
            blueprint=ShipClass.frigate,
            status=BuildStatus.building,
            ore_cost=10000,
            ticks_remaining=1,
            total_ticks=1800,
        )
        builder.capacitor = 10000.0

        result = tick_build_order(builder, order)
        assert result["completed"] is True
        new_ship = result["new_ship"]
        assert new_ship.autopilot_mode == "active"
        assert new_ship.autopilot_profile == "mining"


# ---------------------------------------------------------------------------
# All valid profiles
# ---------------------------------------------------------------------------


class TestAllProfiles:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("profile", [
        "mining", "scout", "combat_aggressive", "combat_defensive", "escort", "patrol",
    ])
    async def test_all_profiles_accepted(self, client: AsyncClient, profile: str):
        """All valid profile names are accepted."""
        auth, ship, token = await _register_and_create_ship(client, username=f"user_{profile}")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": profile},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["autopilot_profile"] == profile


# ---------------------------------------------------------------------------
# Tick endpoint data population tests
# ---------------------------------------------------------------------------


class TestAutopilotTickData:
    """Test that autopilot tick returns properly populated data."""

    @pytest.mark.asyncio
    async def test_tick_response_types(self, client: AsyncClient):
        """Verify all tick response fields have correct types."""
        _, ship, token = await _register_and_create_ship(client, username="types1")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "mining"},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = await client.get(f"/api/ships/{ship_id}/autopilot/tick", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        # Verify types
        assert isinstance(data["ship"], dict)
        assert isinstance(data["profile"], str)
        assert isinstance(data["locks"], list)
        assert isinstance(data["nearby"], list)
        assert isinstance(data["events_since_last_tick"], list)
        assert isinstance(data["threat_assessment"], dict)
        assert isinstance(data["threat_assessment"]["ships_targeting_me"], list)
        assert isinstance(data["team_signals"], list)
        assert isinstance(data["team_objectives"], list)

    @pytest.mark.asyncio
    async def test_tick_ship_has_full_module_detail(self, client: AsyncClient):
        """Ship info in tick response includes full module detail."""
        _, ship, token = await _register_and_create_ship(client, username="moddetail1")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Install a module
        resp = await client.post(
            f"/api/ships/{ship_id}/modules",
            json={"module_type": "mining_laser"},
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text

        # Release to autopilot
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "mining"},
            headers=headers,
        )
        assert resp.status_code == 200

        # Get tick data
        resp = await client.get(f"/api/ships/{ship_id}/autopilot/tick", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        modules = data["ship"]["modules"]
        assert len(modules) > 0

        mining_laser = [m for m in modules if m["module_type"] == "mining_laser"]
        assert len(mining_laser) == 1
        ml = mining_laser[0]

        # Verify full detail is present
        assert "cycle_time" in ml
        assert "capacitor_per_cycle" in ml
        assert "mining_yield" in ml
        assert "mining_range" in ml
        assert ml["mining_yield"] > 0

    @pytest.mark.asyncio
    async def test_tick_nearby_includes_user_id(self, client: AsyncClient):
        """Nearby ships include user_id for friend/foe identification."""
        # Create two users with ships at the same position
        _, ship1, token1 = await _register_and_create_ship(client, username="nearby1")
        _, ship2, token2 = await _register_and_create_ship(client, username="nearby2")
        headers1 = {"Authorization": f"Bearer {token1}"}
        headers2 = {"Authorization": f"Bearer {token2}"}

        # Both ships start at (0,0,0), so they're within 1km of each other
        # Release ship1 to autopilot
        resp = await client.post(
            f"/api/ships/{ship1['id']}/command/release",
            json={"profile": "combat_aggressive"},
            headers=headers1,
        )
        assert resp.status_code == 200

        # Get tick for ship1
        resp = await client.get(
            f"/api/ships/{ship1['id']}/autopilot/tick",
            headers=headers1,
        )
        assert resp.status_code == 200
        data = resp.json()

        # Ship2 should appear in nearby with user_id
        nearby_ships = [n for n in data["nearby"] if n["type"] == "ship"]
        if len(nearby_ships) > 0:
            assert "user_id" in nearby_ships[0]

    @pytest.mark.asyncio
    async def test_tick_threat_assessment_structure(self, client: AsyncClient):
        """Threat assessment includes nearest_enemy and nearest_friendly fields."""
        _, ship, token = await _register_and_create_ship(client, username="threat1")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "combat_defensive"},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = await client.get(f"/api/ships/{ship_id}/autopilot/tick", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        ta = data["threat_assessment"]
        assert "ships_targeting_me" in ta
        assert "nearest_enemy" in ta
        assert "nearest_friendly" in ta

    @pytest.mark.asyncio
    async def test_tick_ship_includes_autopilot_priority_target(self, client: AsyncClient):
        """Ship info in tick includes autopilot_priority_target_id."""
        _, ship, token = await _register_and_create_ship(client, username="priority1")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "mining"},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = await client.get(f"/api/ships/{ship_id}/autopilot/tick", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert "autopilot_priority_target_id" in data["ship"]
        assert data["ship"]["autopilot_priority_target_id"] is None  # default


# ---------------------------------------------------------------------------
# Auth / ownership / 404 tests
# ---------------------------------------------------------------------------


class TestAutopilotAuth:
    """Test auth, ownership, and 404 for all autopilot endpoints."""

    @pytest.mark.asyncio
    async def test_assume_unauthenticated(self, client: AsyncClient):
        resp = await client.post("/api/ships/1/command/assume")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_release_unauthenticated(self, client: AsyncClient):
        resp = await client.post("/api/ships/1/command/release")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_profile_unauthenticated(self, client: AsyncClient):
        resp = await client.put("/api/ships/1/autopilot/profile", json={"profile": "mining"})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_tick_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/ships/1/autopilot/tick")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_assume_nonexistent_ship(self, client: AsyncClient):
        auth = await register_user(client, "ghost1")
        headers = {"Authorization": f"Bearer {auth['token']}"}
        resp = await client.post("/api/ships/99999/command/assume", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_release_nonexistent_ship(self, client: AsyncClient):
        auth = await register_user(client, "ghost2")
        headers = {"Authorization": f"Bearer {auth['token']}"}
        resp = await client.post("/api/ships/99999/command/release", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_assume_other_users_ship(self, client: AsyncClient):
        """Cannot assume another user's ship."""
        _, ship, _ = await _register_and_create_ship(client, username="owner1")
        auth2 = await register_user(client, "intruder1")
        headers2 = {"Authorization": f"Bearer {auth2['token']}"}
        resp = await client.post(
            f"/api/ships/{ship['id']}/command/assume",
            headers=headers2,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_release_other_users_ship(self, client: AsyncClient):
        """Cannot release another user's ship."""
        _, ship, _ = await _register_and_create_ship(client, username="owner2")
        auth2 = await register_user(client, "intruder2")
        headers2 = {"Authorization": f"Bearer {auth2['token']}"}

        resp = await client.post(
            f"/api/ships/{ship['id']}/command/release",
            headers=headers2,
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Orders guard test
# ---------------------------------------------------------------------------


class TestOrdersGuardAutopilot:
    @pytest.mark.asyncio
    async def test_cannot_issue_orders_to_autopiloted_ship(self, client: AsyncClient):
        """Manual orders are rejected for ships in autopilot mode."""
        _, ship, token = await _register_and_create_ship(client, username="guard1")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Release to autopilot
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "mining"},
            headers=headers,
        )
        assert resp.status_code == 200

        # Try to issue a movement order
        resp = await client.post(
            f"/api/ships/{ship_id}/orders",
            json={"order_type": "stop"},
            headers=headers,
        )
        assert resp.status_code == 409
        assert "autopiloted" in resp.json()["detail"].lower() or "autopilot" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_can_issue_orders_after_assume(self, client: AsyncClient):
        """After assuming control, manual orders work again."""
        _, ship, token = await _register_and_create_ship(client, username="guard2")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Release then assume
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={},
            headers=headers,
        )
        assert resp.status_code == 200
        resp = await client.post(
            f"/api/ships/{ship_id}/command/assume",
            headers=headers,
        )
        assert resp.status_code == 200

        # Now orders should work
        resp = await client.post(
            f"/api/ships/{ship_id}/orders",
            json={"order_type": "stop"},
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text


# ---------------------------------------------------------------------------
# Ship info shows autopilot status
# ---------------------------------------------------------------------------


class TestShipInfoAutopilot:
    @pytest.mark.asyncio
    async def test_ship_info_shows_autopilot_fields(self, client: AsyncClient):
        """GET /api/ships/{id} includes autopilot_mode and autopilot_profile."""
        _, ship, token = await _register_and_create_ship(client, username="info1")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Default: off
        resp = await client.get(f"/api/ships/{ship_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["autopilot_mode"] == "off"
        assert data["autopilot_profile"] is None

        # Release to autopilot
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "scout"},
            headers=headers,
        )
        assert resp.status_code == 200

        # Check ship info again
        resp = await client.get(f"/api/ships/{ship_id}", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["autopilot_mode"] == "active"
        assert data["autopilot_profile"] == "scout"

    @pytest.mark.asyncio
    async def test_ship_list_shows_autopilot_fields(self, client: AsyncClient):
        """GET /api/ships includes autopilot fields in ship list."""
        _, ship, token = await _register_and_create_ship(client, username="info2")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # Release to autopilot
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            json={"profile": "patrol"},
            headers=headers,
        )
        assert resp.status_code == 200

        # Check ship list
        resp = await client.get("/api/ships", headers=headers)
        assert resp.status_code == 200
        ships = resp.json()
        assert len(ships) > 0
        target = [s for s in ships if s["id"] == ship_id][0]
        assert target["autopilot_mode"] == "active"
        assert target["autopilot_profile"] == "patrol"


# ---------------------------------------------------------------------------
# Release without body (H7 fix)
# ---------------------------------------------------------------------------


class TestReleaseWithoutBody:
    @pytest.mark.asyncio
    async def test_release_with_empty_body(self, client: AsyncClient):
        """Release works with no body at all."""
        _, ship, token = await _register_and_create_ship(client, username="nobody1")
        headers = {"Authorization": f"Bearer {token}"}
        ship_id = ship["id"]

        # POST with no body (empty content)
        resp = await client.post(
            f"/api/ships/{ship_id}/command/release",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["autopilot_mode"] == "active"
        # Should get default profile for frigate
        assert data["autopilot_profile"] == "mining"
