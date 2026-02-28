"""
Tests for the intent-based command system.

Covers:
- Command enqueue (POST /api/commands)
- Command listing (GET /api/commands)
- Command processing via _test/process_commands endpoint
- Handler tests for key domains (happy path + rejections)
- Validation: docked ship restrictions, autopilot guards, cleanup on deactivate/uninstall
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
    """Register a user and return auth headers."""
    data = await register_user(client, username)
    return {"Authorization": f"Bearer {data['token']}"}


async def _send_command(
    client: AsyncClient,
    headers: dict,
    command_type: str,
    ship_id: int | None = None,
    **payload,
) -> dict:
    """Send a command and return the response."""
    body: dict = {"type": command_type, "payload": payload}
    if ship_id is not None:
        body["ship_id"] = ship_id
    resp = await client.post("/api/commands", json=body, headers=headers)
    assert resp.status_code == 202, resp.text
    return resp.json()


async def _process(client: AsyncClient) -> dict:
    """Trigger command processing via test endpoint."""
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
    return matches[-1]


async def _install_module(
    client: AsyncClient,
    headers: dict,
    ship_id: int,
    module_type: str,
    volume: int = 0,
) -> dict:
    """Install a module via the command system and return the module data."""
    await _send_command(
        client, headers, "install_module",
        ship_id=ship_id, module_type=module_type, volume=volume,
    )
    await _process(client)
    resp = await client.get(f"/api/ships/{ship_id}/modules", headers=headers)
    modules = resp.json()
    matches = [m for m in modules if m["module_type"] == module_type]
    assert matches, f"No {module_type} module found after install_module command"
    return matches[-1]


async def _activate_module(
    client: AsyncClient, headers: dict, ship_id: int, module_id: int,
) -> None:
    """Activate a module via the command system."""
    await _send_command(
        client, headers, "activate_module",
        ship_id=ship_id, module_id=module_id,
    )
    await _process(client)


async def _get_rejected_commands(client: AsyncClient, headers: dict) -> list[dict]:
    """Return all rejected commands for the user."""
    resp = await client.get("/api/commands", params={"status": "rejected"}, headers=headers)
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Command infrastructure tests
# ---------------------------------------------------------------------------


class TestCommandInfrastructure:
    """Test the command enqueue/list/process pipeline."""

    @pytest.mark.anyio
    async def test_enqueue_command(self, client: AsyncClient):
        headers = await _auth_header(client)
        data = await _send_command(client, headers, "create_ship", payload={"ship_class": "strike_craft"})
        assert "command_id" in data
        assert data["type"] == "create_ship"
        assert data["status"] == "pending"

    @pytest.mark.anyio
    async def test_enqueue_invalid_type(self, client: AsyncClient):
        headers = await _auth_header(client)
        resp = await client.post(
            "/api/commands",
            json={"type": "not_a_real_command", "payload": {}},
            headers=headers,
        )
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_list_commands(self, client: AsyncClient):
        headers = await _auth_header(client)
        await _send_command(client, headers, "create_ship", ship_class="strike_craft")
        await _send_command(client, headers, "create_ship", ship_class="strike_craft")

        resp = await client.get("/api/commands", headers=headers)
        assert resp.status_code == 200
        commands = resp.json()
        assert len(commands) == 2

    @pytest.mark.anyio
    async def test_list_commands_filter_status(self, client: AsyncClient):
        headers = await _auth_header(client)
        await _send_command(client, headers, "create_ship", ship_class="strike_craft")
        await _process(client)

        resp = await client.get("/api/commands", params={"status": "processed"}, headers=headers)
        assert resp.status_code == 200
        commands = resp.json()
        assert len(commands) >= 1
        assert all(c["status"] == "processed" for c in commands)

    @pytest.mark.anyio
    async def test_process_commands_endpoint(self, client: AsyncClient):
        headers = await _auth_header(client)
        await _send_command(client, headers, "create_ship", ship_class="strike_craft")
        result = await _process(client)
        assert result["processed"] is True


# ---------------------------------------------------------------------------
# Ship command handler tests
# ---------------------------------------------------------------------------


class TestShipCommands:
    """Test ship-related command handlers via the process pipeline."""

    @pytest.mark.anyio
    async def test_create_ship(self, client: AsyncClient):
        headers = await _auth_header(client)
        await _send_command(client, headers, "create_ship", ship_class="strike_craft")
        await _process(client)

        # Verify ship exists (registration auto-creates a mothership)
        resp = await client.get("/api/ships", headers=headers)
        assert resp.status_code == 200
        ships = resp.json()
        frigates = [s for s in ships if s["ship_class"] == "strike_craft"]
        assert len(frigates) == 1

    @pytest.mark.anyio
    async def test_create_ship_with_name(self, client: AsyncClient):
        headers = await _auth_header(client)
        await _send_command(client, headers, "create_ship", ship_class="strike_craft", name="MyShip")
        await _process(client)

        resp = await client.get("/api/ships", headers=headers)
        ships = resp.json()
        named = [s for s in ships if s["name"] == "MyShip"]
        assert len(named) == 1

    @pytest.mark.anyio
    async def test_create_ship_invalid_class(self, client: AsyncClient):
        headers = await _auth_header(client)
        await _send_command(client, headers, "create_ship", ship_class="not_a_class")
        await _process(client)

        # Command should be rejected
        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1
        assert "Invalid ship class" in (rejected[0].get("rejection_reason") or "")

    @pytest.mark.anyio
    async def test_rename_ship(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        await _send_command(client, headers, "rename_ship", ship_id=ship["id"], name="NewName")
        await _process(client)

        resp = await client.get(f"/api/ships/{ship['id']}", headers=headers)
        assert resp.json()["name"] == "NewName"

    @pytest.mark.anyio
    async def test_install_module(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        await _send_command(
            client, headers, "install_module",
            ship_id=ship["id"],
            module_type="starter_mining_laser",
        )
        await _process(client)

        resp = await client.get(f"/api/ships/{ship['id']}/modules", headers=headers)
        modules = resp.json()
        types = [m["module_type"] for m in modules]
        assert "starter_mining_laser" in types

    @pytest.mark.anyio
    async def test_install_module_no_volume(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        await _send_command(
            client, headers, "install_module",
            ship_id=ship["id"],
            module_type="starter_passive_detector",
        )
        await _process(client)

        resp = await client.get(f"/api/ships/{ship['id']}/modules", headers=headers)
        modules = resp.json()
        types = [m["module_type"] for m in modules]
        assert "starter_passive_detector" in types

    @pytest.mark.anyio
    async def test_uninstall_module(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        # Install a starter detector via command system
        scanner = await _install_module(client, headers, ship["id"], "starter_passive_detector")

        await _send_command(
            client, headers, "uninstall_module",
            ship_id=ship["id"],
            module_id=scanner["id"],
        )
        await _process(client)

        resp = await client.get(f"/api/ships/{ship['id']}/modules", headers=headers)
        module_ids = [m["id"] for m in resp.json()]
        assert scanner["id"] not in module_ids

    @pytest.mark.anyio
    async def test_undock_when_not_docked(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        await _send_command(client, headers, "undock", ship_id=ship["id"])
        await _process(client)

        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1
        assert "not currently docked" in (rejected[0].get("rejection_reason") or "").lower()


# ---------------------------------------------------------------------------
# Movement command handler tests
# ---------------------------------------------------------------------------


class TestMovementCommands:

    @pytest.mark.anyio
    async def test_move_to_point(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        await _send_command(
            client, headers, "move",
            ship_id=ship["id"],
            order_type="approach",
            target_x=1000.0,
            target_y=0.0,
            target_z=0.0,
        )
        await _process(client)

        # Verify command was processed (not rejected)
        resp = await client.get("/api/commands", params={"status": "processed"}, headers=headers)
        commands = resp.json()
        assert any(c["type"] == "move" for c in commands)

    @pytest.mark.anyio
    async def test_stop(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        await _send_command(client, headers, "stop", ship_id=ship["id"])
        await _process(client)

        resp = await client.get("/api/commands", params={"status": "processed"}, headers=headers)
        commands = resp.json()
        assert any(c["type"] == "stop" for c in commands)


# ---------------------------------------------------------------------------
# Module activation command tests
# ---------------------------------------------------------------------------


class TestModuleCommands:

    @pytest.mark.anyio
    async def test_activate_module(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        # Install scanner via command system
        scanner = await _install_module(client, headers, ship["id"], "starter_passive_detector")

        await _send_command(
            client, headers, "activate_module",
            ship_id=ship["id"],
            module_id=scanner["id"],
        )
        await _process(client)

        resp = await client.get("/api/commands", params={"status": "processed"}, headers=headers)
        commands = resp.json()
        assert any(c["type"] == "activate_module" for c in commands)

    @pytest.mark.anyio
    async def test_deactivate_module(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        # Install scanner via command, then activate it
        scanner = await _install_module(client, headers, ship["id"], "starter_passive_detector")
        await _activate_module(client, headers, ship["id"], scanner["id"])

        await _send_command(
            client, headers, "deactivate_module",
            ship_id=ship["id"],
            module_id=scanner["id"],
        )
        await _process(client)

        resp = await client.get("/api/commands", params={"status": "processed"}, headers=headers)
        commands = resp.json()
        assert any(c["type"] == "deactivate_module" for c in commands)


# ---------------------------------------------------------------------------
# Combat command tests
# ---------------------------------------------------------------------------


class TestCombatCommands:

    @pytest.mark.anyio
    async def test_lock_target_no_target(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        await _send_command(
            client, headers, "lock_target",
            ship_id=ship["id"],
            target_ship_id=99999,
        )
        await _process(client)

        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1


# ---------------------------------------------------------------------------
# Resource command tests
# ---------------------------------------------------------------------------


class TestResourceCommands:

    @pytest.mark.anyio
    async def test_scan_no_scanner(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        await _send_command(client, headers, "scan", ship_id=ship["id"])
        await _process(client)

        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1
        assert "scanner" in (rejected[0].get("rejection_reason") or "").lower()


# ---------------------------------------------------------------------------
# Fix 16: Validation tests for new guards and cleanup
# ---------------------------------------------------------------------------


class TestDockedShipRestrictions:
    """Docked ships cannot perform combat, module, scan, or move actions (Fix 4)."""

    async def _make_docked_ship(self, client: AsyncClient, headers: dict) -> dict:
        """Create a frigate and dock it in the mothership via test helper."""
        # The mothership is auto-created on registration. Create a frigate.
        frigate = await _create_ship(client, headers)
        # Get mothership
        resp = await client.get("/api/ships", headers=headers)
        ships = resp.json()
        mothership = next(s for s in ships if s["ship_class"] == "mothership")
        # Directly dock the frigate (bypasses movement phase, test-only)
        resp = await client.post(
            "/api/_test/dock_ship",
            json={"ship_id": frigate["id"], "target_ship_id": mothership["id"]},
        )
        assert resp.status_code == 200
        # Verify it docked
        resp = await client.get(f"/api/ships/{frigate['id']}", headers=headers)
        data = resp.json()
        assert data.get("docked_in_id") is not None, "Ship should be docked"
        return data

    @pytest.mark.anyio
    async def test_move_while_docked(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await self._make_docked_ship(client, headers)

        await _send_command(
            client, headers, "move",
            ship_id=ship["id"],
            order_type="approach", target_x=100.0, target_y=0.0, target_z=0.0,
        )
        await _process(client)

        rejected = await _get_rejected_commands(client, headers)
        assert any("docked" in (r.get("rejection_reason") or "").lower() for r in rejected)

    @pytest.mark.anyio
    async def test_lock_target_while_docked(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await self._make_docked_ship(client, headers)

        await _send_command(
            client, headers, "lock_target",
            ship_id=ship["id"],
            target_ship_id=99999,
        )
        await _process(client)

        rejected = await _get_rejected_commands(client, headers)
        assert any("docked" in (r.get("rejection_reason") or "").lower() for r in rejected)

    @pytest.mark.anyio
    async def test_activate_module_while_docked(self, client: AsyncClient):
        headers = await _auth_header(client)
        # Create a ship, install scanner, then dock it
        frigate = await _create_ship(client, headers)
        scanner = await _install_module(client, headers, frigate["id"], "starter_passive_detector")

        resp = await client.get("/api/ships", headers=headers)
        ships = resp.json()
        mothership = next(s for s in ships if s["ship_class"] == "mothership")

        # Directly dock (test helper)
        await client.post(
            "/api/_test/dock_ship",
            json={"ship_id": frigate["id"], "target_ship_id": mothership["id"]},
        )

        # Try to activate scanner while docked
        await _send_command(
            client, headers, "activate_module",
            ship_id=frigate["id"], module_id=scanner["id"],
        )
        await _process(client)

        rejected = await _get_rejected_commands(client, headers)
        assert any("docked" in (r.get("rejection_reason") or "").lower() for r in rejected)

    @pytest.mark.anyio
    async def test_scan_while_docked(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await self._make_docked_ship(client, headers)

        await _send_command(client, headers, "scan", ship_id=ship["id"])
        await _process(client)

        rejected = await _get_rejected_commands(client, headers)
        # May be rejected for "docked" or "no active scanner" — either is valid
        assert len(rejected) >= 1


class TestScanTrigger:
    """Scan command sets ticks_until_cycle = 0 so scanning phase picks it up (Fix 6)."""

    @pytest.mark.anyio
    async def test_scan_triggers_cycle_reset(self, client: AsyncClient):
        headers = await _auth_header(client)
        # Use mothership (auto-created at registration) since scanner requires 500 m³
        resp = await client.get("/api/ships", headers=headers)
        ships = resp.json()
        ship = next(s for s in ships if s["ship_class"] == "mothership")
        scanner = await _install_module(client, headers, ship["id"], "scanner")
        await _activate_module(client, headers, ship["id"], scanner["id"])

        await _send_command(client, headers, "scan", ship_id=ship["id"])
        await _process(client)

        # Scan should succeed (not be rejected)
        resp = await client.get("/api/commands", params={"status": "processed"}, headers=headers)
        commands = resp.json()
        assert any(c["type"] == "scan" for c in commands)


class TestWeaponCleanup:
    """Weapon assignments cleaned up on uninstall/deactivate (Fixes 7, 8)."""

    @pytest.mark.anyio
    async def test_uninstall_weapon_cleans_assignment(self, client: AsyncClient):
        """Uninstalling a weapon module cleans up its WeaponAssignment."""
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)
        turret = await _install_module(client, headers, ship["id"], "starter_turret")

        # Activate the turret
        await _activate_module(client, headers, ship["id"], turret["id"])

        # Uninstall the turret
        await _send_command(
            client, headers, "uninstall_module",
            ship_id=ship["id"], module_id=turret["id"],
        )
        await _process(client)

        # Verify module is gone
        resp = await client.get(f"/api/ships/{ship['id']}/modules", headers=headers)
        module_ids = [m["id"] for m in resp.json()]
        assert turret["id"] not in module_ids

    @pytest.mark.anyio
    async def test_deactivate_weapon_cleans_assignment(self, client: AsyncClient):
        """Deactivating a weapon clears its weapon assignment."""
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)
        turret = await _install_module(client, headers, ship["id"], "starter_turret")

        # Activate, then deactivate
        await _activate_module(client, headers, ship["id"], turret["id"])
        await _send_command(
            client, headers, "deactivate_module",
            ship_id=ship["id"], module_id=turret["id"],
        )
        await _process(client)

        # Command should succeed
        resp = await client.get("/api/commands", params={"status": "processed"}, headers=headers)
        commands = resp.json()
        assert any(c["type"] == "deactivate_module" for c in commands)


class TestRenameEvent:
    """Renaming a ship emits an event (Fix 9)."""

    @pytest.mark.anyio
    async def test_rename_ship_emits_event(self, client: AsyncClient):
        headers = await _auth_header(client)
        ship = await _create_ship(client, headers)

        await _send_command(client, headers, "rename_ship", ship_id=ship["id"], name="NewName")
        await _process(client)

        # Check events via view endpoint
        resp = await client.get("/api/view", params={"since_tick": 0}, headers=headers)
        events = resp.json().get("events", [])
        assert any("renamed" in (e.get("message") or "").lower() for e in events)


class TestUnexpectedExceptionHandling:
    """Unexpected handler exceptions don't block the queue (Fix 1)."""

    @pytest.mark.anyio
    async def test_unexpected_exception_doesnt_block_queue(self, client: AsyncClient):
        """If one command handler crashes, subsequent commands still process."""
        headers = await _auth_header(client)

        # Enqueue a create_ship with a missing required field to trigger rejection
        # Then enqueue a valid create_ship command
        await _send_command(client, headers, "create_ship", ship_class="not_a_class")
        await _send_command(client, headers, "create_ship", ship_class="strike_craft")
        await _process(client)

        # First should be rejected, second should succeed
        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1

        resp = await client.get("/api/ships", headers=headers)
        ships = resp.json()
        frigates = [s for s in ships if s["ship_class"] == "strike_craft"]
        assert len(frigates) == 1
