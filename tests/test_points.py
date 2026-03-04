"""
Tests for Phase 9: Points Earning System.

Covers:
  1. Point constant validation — hull costs, module costs, build/kill/research points
  2. View includes points field (starts at 0)
  3. View includes available_hulls field
  4. EventType.points_earned exists
  5. MODULE_POINT_COSTS covers all expected modules
  6. HULL_POINT_COSTS covers all buildable ship classes
  7. Loadout costs API endpoint
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from server.models import (
    BUILD_COMPLETE_POINTS,
    EventType,
    HULL_POINT_COSTS,
    KILL_POINTS,
    MODULE_POINT_COSTS,
    ModuleType,
    RESEARCH_COMPLETE_POINTS,
    ShipClass,
)
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


# ---------------------------------------------------------------------------
# Point constant validation
# ---------------------------------------------------------------------------


class TestPointConstants:
    """Validate the point cost and reward tables defined in models.py."""

    def test_strike_craft_hull_is_free(self):
        assert HULL_POINT_COSTS["strike_craft"] == 0

    def test_hull_costs_scale_with_class(self):
        """Larger ship classes should cost more points than smaller ones."""
        assert HULL_POINT_COSTS["strike_craft"] < HULL_POINT_COSTS["corvette"]
        assert HULL_POINT_COSTS["corvette"] < HULL_POINT_COSTS["frigate"]
        assert HULL_POINT_COSTS["frigate"] < HULL_POINT_COSTS["destroyer"]
        assert HULL_POINT_COSTS["destroyer"] < HULL_POINT_COSTS["cruiser"]

    def test_hull_costs_cover_all_buildable_classes(self):
        """Every buildable ship class (not mothership) should have a hull cost."""
        buildable = {"strike_craft", "corvette", "frigate", "destroyer", "cruiser"}
        assert set(HULL_POINT_COSTS.keys()) == buildable

    def test_mothership_not_in_hull_costs(self):
        """Mothership is not buildable via the loadout system."""
        assert "mothership" not in HULL_POINT_COSTS

    def test_kill_points_scale_with_class(self):
        """Kill rewards should increase with ship class size."""
        assert KILL_POINTS["strike_craft"] < KILL_POINTS["corvette"]
        assert KILL_POINTS["corvette"] < KILL_POINTS["frigate"]
        assert KILL_POINTS["frigate"] < KILL_POINTS["destroyer"]
        assert KILL_POINTS["destroyer"] < KILL_POINTS["cruiser"]
        assert KILL_POINTS["cruiser"] < KILL_POINTS["mothership"]

    def test_kill_points_include_mothership(self):
        """Mothership kill should be the most valuable."""
        assert KILL_POINTS["mothership"] == 50_000

    def test_kill_points_cover_all_ship_classes(self):
        """Every ship class should have a kill reward."""
        for sc in ShipClass:
            assert sc.value in KILL_POINTS, f"Missing kill points for {sc.value}"

    def test_starter_modules_free(self):
        """All starter modules should cost zero points."""
        starter_modules = [
            "starter_turret",
            "starter_mining_laser",
            "starter_shield_extender",
            "starter_armor_plate",
            "starter_passive_detector",
        ]
        for mod in starter_modules:
            assert MODULE_POINT_COSTS[mod] == 0, f"{mod} should be free"

    def test_engines_always_free(self):
        assert MODULE_POINT_COSTS["starter_engine"] == 0

    def test_infrastructure_modules_free(self):
        """Core infrastructure modules should cost zero points."""
        free_modules = [
            "starter_engine", "starter_reactor", "tiny_cargo_bay",
            "tiny_docking_bay", "dropoff", "starter_factory",
        ]
        for mod in free_modules:
            assert MODULE_POINT_COSTS[mod] == 0, f"{mod} should be free"

    def test_mining_laser_free(self):
        assert MODULE_POINT_COSTS["mining_laser"] == 0

    def test_combat_modules_cost_points(self):
        """Weapon modules should cost non-zero points."""
        weapons = [
            "small_turret_kinetic", "small_turret_thermal",
            "medium_turret_kinetic", "medium_turret_thermal",
            "large_turret_kinetic", "large_turret_thermal",
            "light_missile_launcher", "heavy_missile_launcher",
            "torpedo_launcher",
        ]
        for mod in weapons:
            assert MODULE_POINT_COSTS[mod] > 0, f"{mod} should cost points"

    def test_large_modules_cost_more_than_small(self):
        """Large modules should be more expensive than their small counterparts."""
        assert MODULE_POINT_COSTS["large_turret_kinetic"] > MODULE_POINT_COSTS["medium_turret_kinetic"]
        assert MODULE_POINT_COSTS["medium_turret_kinetic"] > MODULE_POINT_COSTS["small_turret_kinetic"]
        assert MODULE_POINT_COSTS["large_shield_extender"] > MODULE_POINT_COSTS["medium_shield_extender"]
        assert MODULE_POINT_COSTS["medium_shield_extender"] > MODULE_POINT_COSTS["small_shield_extender"]
        assert MODULE_POINT_COSTS["large_armor_plate"] > MODULE_POINT_COSTS["medium_armor_plate"]
        assert MODULE_POINT_COSTS["medium_armor_plate"] > MODULE_POINT_COSTS["small_armor_plate"]

    def test_build_complete_points(self):
        """Verify specific build-complete point awards."""
        assert BUILD_COMPLETE_POINTS["strike_craft"] == 50
        assert BUILD_COMPLETE_POINTS["corvette"] == 200
        assert BUILD_COMPLETE_POINTS["frigate"] == 800
        assert BUILD_COMPLETE_POINTS["destroyer"] == 2_000
        assert BUILD_COMPLETE_POINTS["cruiser"] == 5_000

    def test_build_complete_points_scale_with_class(self):
        """Build rewards should increase with ship class size."""
        assert BUILD_COMPLETE_POINTS["strike_craft"] < BUILD_COMPLETE_POINTS["corvette"]
        assert BUILD_COMPLETE_POINTS["corvette"] < BUILD_COMPLETE_POINTS["frigate"]
        assert BUILD_COMPLETE_POINTS["frigate"] < BUILD_COMPLETE_POINTS["destroyer"]
        assert BUILD_COMPLETE_POINTS["destroyer"] < BUILD_COMPLETE_POINTS["cruiser"]

    def test_build_complete_points_cover_buildable_classes(self):
        """Every buildable ship class should have a build-complete reward."""
        buildable = {"strike_craft", "corvette", "frigate", "destroyer", "cruiser"}
        assert set(BUILD_COMPLETE_POINTS.keys()) == buildable

    def test_research_complete_points(self):
        """Verify specific research-complete point awards."""
        assert RESEARCH_COMPLETE_POINTS[1] == 200
        assert RESEARCH_COMPLETE_POINTS[2] == 500
        assert RESEARCH_COMPLETE_POINTS[3] == 1_000
        assert RESEARCH_COMPLETE_POINTS[4] == 2_000

    def test_research_complete_points_scale_with_tier(self):
        """Higher research tiers should award more points."""
        assert RESEARCH_COMPLETE_POINTS[1] < RESEARCH_COMPLETE_POINTS[2]
        assert RESEARCH_COMPLETE_POINTS[2] < RESEARCH_COMPLETE_POINTS[3]
        assert RESEARCH_COMPLETE_POINTS[3] < RESEARCH_COMPLETE_POINTS[4]

    def test_research_complete_points_cover_all_tiers(self):
        """All 4 research tiers should have defined points."""
        for tier in range(1, 5):
            assert tier in RESEARCH_COMPLETE_POINTS, f"Missing points for tier {tier}"

    def test_module_point_costs_cover_all_module_types(self):
        """Every ModuleType enum value should have an entry in MODULE_POINT_COSTS."""
        for mt in ModuleType:
            assert mt.value in MODULE_POINT_COSTS, f"Missing point cost for module type: {mt.value}"

    def test_faction_modules_cost_points(self):
        """Faction-specific combat modules should cost non-zero points."""
        faction_modules = [
            "focused_beam_medium", "focused_beam_large",
            "reactive_armor_membrane_medium", "reactive_armor_membrane_large",
            "light_leech_projector", "heavy_leech_projector",
            "phase_shield_amplifier_medium", "phase_shield_amplifier_large",
        ]
        for mod in faction_modules:
            assert MODULE_POINT_COSTS[mod] > 0, f"{mod} should cost points"

    def test_ultimate_modules_are_expensive(self):
        """Ultimate faction modules (solar_lance, bio_repair_swarm) should be very expensive."""
        assert MODULE_POINT_COSTS["solar_lance"] >= 5_000
        assert MODULE_POINT_COSTS["bio_repair_swarm"] >= 3_000


# ---------------------------------------------------------------------------
# EventType validation
# ---------------------------------------------------------------------------


class TestPointsEventType:
    """Verify the points_earned event type is defined."""

    def test_points_earned_event_type_exists(self):
        assert hasattr(EventType, "points_earned")
        assert EventType.points_earned.value == "points_earned"

    def test_ship_claimed_event_type_exists(self):
        assert hasattr(EventType, "ship_claimed")

    def test_reship_complete_event_type_exists(self):
        assert hasattr(EventType, "reship_complete")


# ---------------------------------------------------------------------------
# View endpoint: points field
# ---------------------------------------------------------------------------


class TestPointsInView:
    """Verify the /api/view response includes points-related fields."""

    @pytest.mark.anyio
    async def test_view_shows_zero_points_for_new_user(self, client: AsyncClient):
        """A freshly registered user should start with 0 points."""
        headers = await _auth_header(client)
        resp = await client.get("/api/view", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "points" in data
        assert data["points"] == 0.0

    @pytest.mark.anyio
    async def test_view_points_field_is_numeric(self, client: AsyncClient):
        """Points field should be a number (int or float)."""
        headers = await _auth_header(client)
        resp = await client.get("/api/view", headers=headers)
        data = resp.json()
        assert isinstance(data["points"], (int, float))

    @pytest.mark.anyio
    async def test_view_includes_available_hulls(self, client: AsyncClient):
        """View response should include the available_hulls list."""
        headers = await _auth_header(client)
        resp = await client.get("/api/view", headers=headers)
        data = resp.json()
        assert "available_hulls" in data
        # Without a team, available_hulls should be empty
        assert isinstance(data["available_hulls"], list)

    @pytest.mark.anyio
    async def test_view_structure_includes_points_alongside_ships(self, client: AsyncClient):
        """View should contain both points and ships in the same response."""
        headers = await _auth_header(client)
        resp = await client.get("/api/view", headers=headers)
        data = resp.json()
        assert "points" in data
        assert "ships" in data
        assert "available_hulls" in data
        assert "tick" in data


# ---------------------------------------------------------------------------
# Loadout costs API endpoint
# ---------------------------------------------------------------------------


class TestLoadoutCostsEndpoint:
    """Verify the /api/loadout/costs endpoint returns cost tables."""

    @pytest.mark.anyio
    async def test_loadout_costs_returns_hull_costs(self, client: AsyncClient):
        resp = await client.get("/api/loadout/costs")
        assert resp.status_code == 200
        data = resp.json()
        assert "hull_costs" in data
        assert data["hull_costs"]["strike_craft"] == 0
        assert data["hull_costs"]["cruiser"] == 10_000

    @pytest.mark.anyio
    async def test_loadout_costs_returns_module_costs(self, client: AsyncClient):
        resp = await client.get("/api/loadout/costs")
        assert resp.status_code == 200
        data = resp.json()
        assert "module_costs" in data
        assert data["module_costs"]["starter_engine"] == 0
        assert data["module_costs"]["small_turret_kinetic"] == 50

    @pytest.mark.anyio
    async def test_loadout_costs_no_auth_required(self, client: AsyncClient):
        """The loadout costs endpoint should work without authentication."""
        resp = await client.get("/api/loadout/costs")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Points events via API
# ---------------------------------------------------------------------------


class TestPointsEventsAPI:
    """Test that points-related events are queryable through the events API."""

    @pytest.mark.anyio
    async def test_events_accept_points_earned_filter(self, client: AsyncClient):
        """The events endpoint should accept 'points_earned' as a type filter without error."""
        headers = await _auth_header(client)
        resp = await client.get(
            "/api/events",
            params={"types": "points_earned"},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # New user has no events yet
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.anyio
    async def test_events_accept_multiple_type_filters(self, client: AsyncClient):
        """Events endpoint should handle comma-separated type filters including points_earned."""
        headers = await _auth_header(client)
        resp = await client.get(
            "/api/events",
            params={"types": "points_earned,transfer_complete"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
