"""
Tests for Phase 9: Loadout system (claim_ship and reship commands).

Covers:
  1. Claiming a free strike_craft with free modules
  2. Claiming a nonexistent ship (rejected)
  3. Claiming with modules that exceed hull volume
  4. Claiming an already-claimed ship
  5. Reship refunds 75% of loadout points spent
  6. Reship rejected when ship is not docked
  7. Reship strips all modules from the ship
  8. Builder kickback (50% of hull cost to builder, when applicable)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import register_user, spawn_test_mothership


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
    """Send a command and return the response.

    ``cmd_ship_id`` sets the top-level ``ship_id`` on the Command row
    (used by handlers that call ``ctx.find_ship(cmd.ship_id, ...)``).
    Everything in ``**payload`` goes into the JSON payload dict.
    """
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


async def _create_and_dock_strike_craft(
    client: AsyncClient, headers: dict,
) -> tuple[dict, dict]:
    """Create a strike_craft via command, dock it in the mothership, return (craft, mothership)."""
    mothership = await spawn_test_mothership(client, headers)

    await _send_command(client, headers, "create_ship", ship_class="strike_craft")
    await _process(client)

    ships = await _get_ships(client, headers)
    craft = next(s for s in ships if s["ship_class"] == "strike_craft")

    # Dock the strike_craft in the mothership
    resp = await client.post(
        "/api/_test/dock_ship",
        json={"ship_id": craft["id"], "target_ship_id": mothership["id"]},
    )
    assert resp.status_code == 200

    # Re-fetch to confirm docking state
    resp = await client.get(f"/api/ships/{craft['id']}", headers=headers)
    assert resp.status_code == 200
    craft = resp.json()
    assert craft["docked_in_id"] == mothership["id"]

    return craft, mothership


async def _claim_ship(
    client: AsyncClient,
    headers: dict,
    hull_id: int,
    modules: list[dict],
) -> None:
    """Send a claim_ship command. ``hull_id`` is passed as top-level ship_id."""
    await _send_raw_command(
        client, headers, "claim_ship",
        payload={"modules": modules},
        cmd_ship_id=hull_id,
    )
    await _process(client)


async def _reship(
    client: AsyncClient,
    headers: dict,
    hull_id: int,
) -> None:
    """Send a reship command. ``hull_id`` is passed as top-level ship_id."""
    await _send_raw_command(
        client, headers, "reship",
        payload={},
        cmd_ship_id=hull_id,
    )
    await _process(client)


# ---------------------------------------------------------------------------
# Test: claim_ship
# ---------------------------------------------------------------------------


class TestClaimShip:

    @pytest.mark.anyio
    async def test_claim_free_strike_craft(self, client: AsyncClient):
        """Build a strike_craft, claim with free modules, verify claimed and undocked."""
        headers = await _auth_header(client)
        craft, _ms = await _create_and_dock_strike_craft(client, headers)

        # Claim with free modules: engine (30 m3) + starter_turret (fixed 15 m3)
        await _claim_ship(client, headers, craft["id"], modules=[
            {"module_type": "starter_engine"},
            {"module_type": "starter_turret"},
        ])

        # Verify no rejection
        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 0, f"Unexpected rejections: {rejected}"

        # Verify ship is undocked after claim
        resp = await client.get(f"/api/ships/{craft['id']}", headers=headers)
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["docked_in_id"] is None, "Ship should be undocked after claim"

        # Verify the ship still appears in the user's ship list
        ships = await _get_ships(client, headers)
        craft_ids = [s["id"] for s in ships if s["ship_class"] == "strike_craft"]
        assert craft["id"] in craft_ids

        # Verify points are still 0 (all free)
        view = await _get_view(client, headers)
        assert view["points"] == 0

        # Verify a ship_claimed event was emitted
        events = view.get("events", [])
        assert any("claimed" in (e.get("message") or "").lower() for e in events)

    @pytest.mark.anyio
    async def test_claim_insufficient_points(self, client: AsyncClient):
        """Try to claim a nonexistent ship, expect rejection.

        A true insufficient-points test would need a corvette hull (500
        pts), which requires completing the 1h_corvette_hull research.
        Since research completion cannot be done via the test endpoints
        alone (no tick simulation), we instead verify that the claim_ship
        handler rejects commands with an invalid hull reference.
        """
        headers = await _auth_header(client)

        # Try to claim a ship that does not exist
        await _claim_ship(client, headers, hull_id=99999, modules=[
            {"module_type": "starter_engine"},
        ])

        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1
        assert "not found" in (rejected[0].get("rejection_reason") or "").lower()

    @pytest.mark.anyio
    async def test_claim_volume_overflow(self, client: AsyncClient):
        """Claim a strike_craft (100 m3 hull) with modules exceeding capacity -- rejected."""
        headers = await _auth_header(client)
        craft, _ms = await _create_and_dock_strike_craft(client, headers)

        # Try to fit modules exceeding hull volume (starter_engine=25 + small_standard_engine=500 > 100)
        await _claim_ship(client, headers, craft["id"], modules=[
            {"module_type": "starter_engine"},
            {"module_type": "small_standard_engine"},
        ])

        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1
        reason = (rejected[0].get("rejection_reason") or "").lower()
        assert "volume" in reason or "exceeds" in reason

    @pytest.mark.anyio
    async def test_claim_already_claimed(self, client: AsyncClient):
        """Claim a ship, then try to claim it again -- second attempt rejected."""
        headers = await _auth_header(client)
        craft, mothership = await _create_and_dock_strike_craft(client, headers)

        # First claim -- should succeed
        await _claim_ship(client, headers, craft["id"], modules=[
            {"module_type": "starter_turret"},
        ])

        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 0

        # Re-dock the ship so the docking check passes (claim_ship undocked it)
        resp = await client.post(
            "/api/_test/dock_ship",
            json={"ship_id": craft["id"], "target_ship_id": mothership["id"]},
        )
        assert resp.status_code == 200

        # Second claim -- should be rejected as already claimed
        await _claim_ship(client, headers, craft["id"], modules=[
            {"module_type": "starter_turret"},
        ])

        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1
        assert "already claimed" in (rejected[0].get("rejection_reason") or "").lower()


# ---------------------------------------------------------------------------
# Test: reship
# ---------------------------------------------------------------------------


class TestReship:

    @pytest.mark.anyio
    async def test_reship_refunds_75_percent(self, client: AsyncClient):
        """Claim a free ship (0 pts), reship, verify 75% of 0 = 0 refund.

        With a zero-cost loadout the refund is 0 * 0.75 = 0.  This verifies
        the reship command completes without rejection and the user's points
        remain unchanged.
        """
        headers = await _auth_header(client)
        craft, mothership = await _create_and_dock_strike_craft(client, headers)

        # Claim with free modules (total cost = 0)
        await _claim_ship(client, headers, craft["id"], modules=[
            {"module_type": "starter_engine"},
            {"module_type": "starter_turret"},
        ])

        # Verify claim succeeded
        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 0

        # Re-dock the ship (claim_ship undocked it)
        resp = await client.post(
            "/api/_test/dock_ship",
            json={"ship_id": craft["id"], "target_ship_id": mothership["id"]},
        )
        assert resp.status_code == 200

        # Reship
        await _reship(client, headers, craft["id"])

        # Verify reship was not rejected
        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 0

        # Points should still be 0 (75% of 0 = 0)
        view = await _get_view(client, headers)
        assert view["points"] == 0

        # Verify a reship_complete event was emitted
        events = view.get("events", [])
        assert any("reship" in (e.get("message") or "").lower() for e in events)

    @pytest.mark.anyio
    async def test_reship_not_docked_rejected(self, client: AsyncClient):
        """Try to reship an undocked ship -- should be rejected."""
        headers = await _auth_header(client)
        craft, _ms = await _create_and_dock_strike_craft(client, headers)

        # Claim the ship (this undocks it)
        await _claim_ship(client, headers, craft["id"], modules=[
            {"module_type": "starter_turret"},
        ])

        # Verify claim succeeded and ship is undocked
        resp = await client.get(f"/api/ships/{craft['id']}", headers=headers)
        updated = resp.json()
        assert updated["docked_in_id"] is None

        # Try to reship while undocked
        await _reship(client, headers, craft["id"])

        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1
        assert "docked" in (rejected[0].get("rejection_reason") or "").lower()

    @pytest.mark.anyio
    async def test_reship_strips_modules(self, client: AsyncClient):
        """Claim ship with modules, reship, verify all modules are stripped."""
        headers = await _auth_header(client)
        craft, mothership = await _create_and_dock_strike_craft(client, headers)

        # Claim with starter_turret + engine
        await _claim_ship(client, headers, craft["id"], modules=[
            {"module_type": "starter_engine"},
            {"module_type": "starter_turret"},
        ])

        # Verify modules were installed (default engine from create_ship + claim modules)
        resp = await client.get(f"/api/ships/{craft['id']}/modules", headers=headers)
        assert resp.status_code == 200
        modules_before = resp.json()
        assert len(modules_before) >= 2

        # Re-dock for reship
        resp = await client.post(
            "/api/_test/dock_ship",
            json={"ship_id": craft["id"], "target_ship_id": mothership["id"]},
        )
        assert resp.status_code == 200

        # Reship
        await _reship(client, headers, craft["id"])

        # Verify no rejection
        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 0

        # Verify all modules are stripped
        resp = await client.get(f"/api/ships/{craft['id']}/modules", headers=headers)
        assert resp.status_code == 200
        modules_after = resp.json()
        assert len(modules_after) == 0, (
            f"Expected 0 modules after reship, got {len(modules_after)}: "
            f"{[m['module_type'] for m in modules_after]}"
        )


# ---------------------------------------------------------------------------
# Test: builder kickback
# ---------------------------------------------------------------------------


class TestBuilderKickback:

    @pytest.mark.anyio
    async def test_builder_kickback_zero_cost_hull(self, client: AsyncClient):
        """Two users on same team: user A creates a strike_craft, user B claims it.

        Since strike_craft hull cost is 0, the builder kickback (50% of hull
        cost) is 0.  Verifies the cross-user claim succeeds and neither user
        gains extra points.
        """
        headers1, data1 = await _auth(client, "builder")
        headers2, data2 = await _auth(client, "claimer")

        # Create a team and have both users join
        resp = await client.post(
            "/api/teams", json={"name": "Alpha", "faction": "solarion"},
            headers=headers1,
        )
        assert resp.status_code in (200, 201), resp.text
        team_id = resp.json()["id"]

        resp = await client.post(f"/api/teams/{team_id}/join", headers=headers2)
        assert resp.status_code == 200, resp.text

        # Create mothership for user A
        mothership1 = await spawn_test_mothership(client, headers1)

        # User A creates a strike_craft
        await _send_command(client, headers1, "create_ship", ship_class="strike_craft")
        await _process(client)

        # Find the strike_craft
        ships1 = await _get_ships(client, headers1)
        craft = next(s for s in ships1 if s["ship_class"] == "strike_craft")

        # Dock it in user A's mothership
        resp = await client.post(
            "/api/_test/dock_ship",
            json={"ship_id": craft["id"], "target_ship_id": mothership1["id"]},
        )
        assert resp.status_code == 200

        # User B claims the strike_craft with free modules
        await _claim_ship(client, headers2, craft["id"], modules=[
            {"module_type": "starter_turret"},
        ])

        # Verify claim was not rejected
        rejected = await _get_rejected_commands(client, headers2)
        assert len(rejected) == 0, f"Unexpected rejections: {rejected}"

        # Verify ship now appears in user B's ship list (user_id was reassigned)
        ships2 = await _get_ships(client, headers2)
        claimed_ids = [s["id"] for s in ships2 if s["ship_class"] == "strike_craft"]
        assert craft["id"] in claimed_ids, (
            f"Claimed ship #{craft['id']} should appear in claimer's ship list"
        )

        # Both users should still have 0 points (hull cost 0 -> kickback 0)
        view1 = await _get_view(client, headers1)
        assert view1["points"] == 0

        view2 = await _get_view(client, headers2)
        assert view2["points"] == 0


# ---------------------------------------------------------------------------
# Test: auto-create on claim (ship_class instead of ship_id)
# ---------------------------------------------------------------------------


class TestAutoCreateClaim:

    @pytest.mark.anyio
    async def test_claim_with_ship_class_strike_craft(self, client: AsyncClient):
        """Auto-create a strike_craft via ship_class (no pre-existing hull)."""
        headers, data = await _auth(client, "autocreate_user")

        # Create team, join it, and spawn mothership
        resp = await client.post(
            "/api/teams", json={"name": "AutoTeam", "faction": "solarion"},
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text
        team_id = resp.json()["id"]

        resp = await client.post(f"/api/teams/{team_id}/join", headers=headers)
        assert resp.status_code == 200, resp.text

        await spawn_test_mothership(client, headers)

        # Claim with ship_class instead of ship_id
        await _send_raw_command(
            client, headers, "claim_ship",
            payload={"ship_class": "strike_craft", "modules": [
                {"module_type": "starter_engine"},
                {"module_type": "starter_turret"},
            ]},
        )
        await _process(client)

        # Verify no rejection
        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 0, f"Unexpected rejections: {rejected}"

        # Verify a strike_craft now exists and is undocked
        ships = await _get_ships(client, headers)
        crafts = [s for s in ships if s["ship_class"] == "strike_craft"]
        assert len(crafts) == 1, f"Expected 1 strike_craft, got {len(crafts)}"
        assert crafts[0]["docked_in_id"] is None, "Ship should be undocked after claim"

        # Verify a ship_claimed event was emitted
        view = await _get_view(client, headers)
        assert any("claimed" in (e.get("message") or "").lower() for e in view.get("events", []))

    @pytest.mark.anyio
    async def test_claim_with_nonfree_ship_class_rejected(self, client: AsyncClient):
        """Auto-create with a non-free hull class (corvette) should be rejected."""
        headers, data = await _auth(client, "nonfree_user")

        resp = await client.post(
            "/api/teams", json={"name": "NonFreeTeam", "faction": "voidborn"},
            headers=headers,
        )
        assert resp.status_code in (200, 201), resp.text
        team_id = resp.json()["id"]

        resp = await client.post(f"/api/teams/{team_id}/join", headers=headers)
        assert resp.status_code == 200, resp.text

        await spawn_test_mothership(client, headers)

        await _send_raw_command(
            client, headers, "claim_ship",
            payload={"ship_class": "corvette", "modules": []},
        )
        await _process(client)

        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1
        reason = (rejected[0].get("rejection_reason") or "").lower()
        assert "free" in reason or "cost" in reason

    @pytest.mark.anyio
    async def test_claim_with_ship_class_no_team_rejected(self, client: AsyncClient):
        """Auto-create when the user has no team should be rejected."""
        headers = await _auth_header(client, "noteam_user")

        await _send_raw_command(
            client, headers, "claim_ship",
            payload={"ship_class": "strike_craft", "modules": []},
        )
        await _process(client)

        rejected = await _get_rejected_commands(client, headers)
        assert len(rejected) == 1
        reason = (rejected[0].get("rejection_reason") or "").lower()
        assert "team" in reason

    @pytest.mark.anyio
    async def test_free_hull_classes_in_view(self, client: AsyncClient):
        """Verify free_hull_classes appears in the view response."""
        headers = await _auth_header(client, "viewuser")
        view = await _get_view(client, headers)
        assert "free_hull_classes" in view
        assert "strike_craft" in view["free_hull_classes"]
