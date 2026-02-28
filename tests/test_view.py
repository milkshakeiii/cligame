"""
Tests for the GET /api/view endpoint.

Covers:
- Basic view returns correct structure
- Ship data in view
- Nearby contacts
- Events
- Ship filtering
- Command status in view
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import register_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _auth_header(client: AsyncClient, username: str = "testuser") -> dict:
    data = await register_user(client, username)
    return {"Authorization": f"Bearer {data['token']}"}


async def _send_command(
    client: AsyncClient,
    headers: dict,
    command_type: str,
    ship_id: int | None = None,
    **payload,
) -> dict:
    body: dict = {"type": command_type, "payload": payload}
    if ship_id is not None:
        body["ship_id"] = ship_id
    resp = await client.post("/api/commands", json=body, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()


async def _process(client: AsyncClient) -> dict:
    resp = await client.post("/api/_test/process_commands")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_ship(client: AsyncClient, headers: dict, ship_class: str = "strike_craft") -> dict:
    """Create a ship via the command system and return its data."""
    await _send_command(client, headers, "create_ship", ship_class=ship_class)
    await _process(client)
    resp = await client.get("/api/ships", headers=headers)
    ships = resp.json()
    matches = [s for s in ships if s["ship_class"] == ship_class]
    assert matches, f"No {ship_class} ship found after create_ship command"
    return matches[-1]  # return the most recently created one


# ---------------------------------------------------------------------------
# View endpoint tests
# ---------------------------------------------------------------------------


class TestViewEndpoint:

    @pytest.mark.anyio
    async def test_view_basic_structure(self, client: AsyncClient):
        headers = await _auth_header(client)
        resp = await client.get("/api/view", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "tick" in data
        assert "ships" in data
        assert "nearby" in data
        assert "events" in data
        assert "pending_commands" in data

    @pytest.mark.anyio
    async def test_view_shows_ships(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        resp = await client.get("/api/view", headers=headers)
        data = resp.json()
        # Registration auto-creates a mothership, so expect at least 2 ships
        assert len(data["ships"]) >= 2
        ship_ids = [s["id"] for s in data["ships"]]
        assert ship["id"] in ship_ids
        # The newly created strike_craft should be present
        strike_craft = [s for s in data["ships"] if s["ship_class"] == "strike_craft"]
        assert len(strike_craft) == 1

    @pytest.mark.anyio
    async def test_view_ship_has_modules(self, client: AsyncClient):
        headers = await _auth_header(client)
        await _create_ship(client, headers)

        resp = await client.get("/api/view", headers=headers)
        data = resp.json()
        ship_view = data["ships"][0]
        assert "modules" in ship_view
        # Default ship has at least an engine module
        assert len(ship_view["modules"]) >= 1

    @pytest.mark.anyio
    async def test_view_ship_filter(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship1 = await _create_ship(client, headers)

        # Filter to ship1
        resp = await client.get(
            "/api/view",
            params={"ship_id": ship1["id"]},
            headers=headers,
        )
        data = resp.json()
        assert len(data["ships"]) == 1
        assert data["ships"][0]["id"] == ship1["id"]

    @pytest.mark.anyio
    async def test_view_default_mothership(self, client: AsyncClient):
        """Registration auto-creates a mothership — verify it appears in view."""
        headers = await _auth_header(client)
        resp = await client.get("/api/view", headers=headers)
        data = resp.json()
        # Registration creates a default mothership
        assert len(data["ships"]) == 1
        assert data["ships"][0]["ship_class"] == "mothership"

    @pytest.mark.anyio
    async def test_view_ship_details(self, client: AsyncClient):
        """Verify ship view includes all expected fields."""
        headers = await _auth_header(client)
        await _create_ship(client, headers)

        resp = await client.get("/api/view", headers=headers)
        ship = resp.json()["ships"][0]

        expected_fields = [
            "id", "name", "ship_class",
            "pos_x", "pos_y", "pos_z",
            "vel_x", "vel_y", "vel_z",
            "ore", "capacitor", "max_capacitor",
            "total_volume", "used_volume",
            "cargo_capacity", "max_speed", "acceleration",
            "shield_hp", "max_shield_hp",
            "armor_hp", "max_armor_hp",
            "is_destroyed", "signature_radius",
            "modules", "active_orders", "locks", "build_orders",
            "match_id", "weapon_assignments",
        ]
        for field in expected_fields:
            assert field in ship, f"Missing field: {field}"

    @pytest.mark.anyio
    async def test_view_events_since_tick(self, client: AsyncClient):
        headers = await _auth_header(client)
        resp = await client.get(
            "/api/view",
            params={"since_tick": 0},
            headers=headers,
        )
        data = resp.json()
        assert "events" in data

    @pytest.mark.anyio
    async def test_view_pending_commands(self, client: AsyncClient):
        headers = await _auth_header(client)
        # Enqueue a command
        resp = await client.post(
            "/api/commands",
            json={"type": "create_ship", "payload": {"ship_class": "strike_craft"}},
            headers=headers,
        )
        assert resp.status_code == 202

        # Check view shows the pending command
        resp = await client.get("/api/view", headers=headers)
        data = resp.json()
        pending = data.get("pending_commands", [])
        assert len(pending) >= 1
        assert any(c["status"] == "pending" for c in pending)

    @pytest.mark.anyio
    async def test_view_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/view")
        assert resp.status_code in (401, 403)
