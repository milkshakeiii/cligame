"""
Unit and integration tests for Phase 5: Research / Tech Tree.

Unit tests:
  - Tech tree data integrity (prerequisites exist, no cycles)
  - Gating helpers: is_module_unlocked, is_ship_unlocked
  - Prerequisite checking

Integration tests:
  - POST /api/ships/{id}/research/start — start research
  - POST /api/ships/{id}/research/cancel — cancel research
  - GET /api/ships/{id}/research/status — research progress
  - GET /api/research/tech-tree — tech tree
  - Research gating on module install
  - Research gating on ship build
"""

import pytest
from httpx import AsyncClient

from server.models import (
    MODULE_REQUIRED_TECH,
    RESEARCH_COSTS,
    RESEARCH_GATED_MODULES,
    RESEARCH_GATED_SHIPS,
    SHIP_REQUIRED_TECH,
    TECH_TREE,
)
from server.research import (
    check_prerequisites,
    get_completed_tech_ids,
    is_module_unlocked,
    is_ship_unlocked,
)
from tests.conftest import register_user


# ---------------------------------------------------------------------------
# Unit tests: Tech tree data integrity
# ---------------------------------------------------------------------------


class TestTechTreeIntegrity:
    def test_all_prerequisites_exist(self):
        """Every prerequisite ID must reference a real tech node."""
        for tech_id, node in TECH_TREE.items():
            for prereq in node["prerequisites"]:
                assert prereq in TECH_TREE, (
                    f"Tech {tech_id} has unknown prerequisite: {prereq}"
                )

    def test_all_tiers_have_costs(self):
        """Every tier referenced in the tree must have cost data."""
        for tech_id, node in TECH_TREE.items():
            tier = node["tier"]
            assert tier in RESEARCH_COSTS, (
                f"Tech {tech_id} has tier {tier} with no cost data"
            )

    def test_no_self_prerequisites(self):
        for tech_id, node in TECH_TREE.items():
            assert tech_id not in node["prerequisites"], (
                f"Tech {tech_id} lists itself as a prerequisite"
            )

    def test_reverse_lookups_complete(self):
        """Every gated module/ship should map back to a tech ID."""
        for mod in RESEARCH_GATED_MODULES:
            assert mod in MODULE_REQUIRED_TECH, (
                f"Module {mod} is gated but has no reverse lookup"
            )
        for ship in RESEARCH_GATED_SHIPS:
            assert ship in SHIP_REQUIRED_TECH, (
                f"Ship {ship} is gated but has no reverse lookup"
            )


# ---------------------------------------------------------------------------
# Unit tests: Gating helpers
# ---------------------------------------------------------------------------


class TestGatingHelpers:
    def test_starter_module_always_unlocked(self):
        """Mining laser is never gated."""
        assert is_module_unlocked("mining_laser", set())

    def test_gated_module_locked_without_research(self):
        assert not is_module_unlocked("medium_turret_kinetic", set())

    def test_gated_module_unlocked_with_research(self):
        assert is_module_unlocked("medium_turret_kinetic", {"1a_medium_weapons"})

    def test_starter_ship_always_unlocked(self):
        assert is_ship_unlocked("frigate", set())
        assert is_ship_unlocked("strike_craft", set())

    def test_destroyer_locked_without_research(self):
        assert not is_ship_unlocked("destroyer", set())

    def test_destroyer_unlocked_with_research(self):
        assert is_ship_unlocked("destroyer", {"1c_destroyer_hull"})

    def test_cruiser_locked_without_research(self):
        assert not is_ship_unlocked("cruiser", set())

    def test_cruiser_unlocked_with_research(self):
        assert is_ship_unlocked("cruiser", {"2c_cruiser_hull"})


# ---------------------------------------------------------------------------
# Unit tests: Prerequisites
# ---------------------------------------------------------------------------


class TestPrerequisites:
    def test_tier1_no_prereqs(self):
        assert check_prerequisites("1a_medium_weapons", set()) is None

    def test_tier2_needs_tier1(self):
        error = check_prerequisites("2a_large_weapons", set())
        assert error is not None
        assert "Medium Weapons" in error

    def test_tier2_ok_with_tier1(self):
        assert check_prerequisites("2a_large_weapons", {"1a_medium_weapons"}) is None

    def test_fortress_needs_two_prereqs(self):
        """4b_fortress requires both 3b_advanced_defenses and 3c_capital_systems."""
        error = check_prerequisites("4b_fortress", {"3b_advanced_defenses"})
        assert error is not None
        assert "Capital Systems" in error

        assert check_prerequisites(
            "4b_fortress",
            {"3b_advanced_defenses", "3c_capital_systems"},
        ) is None


# ---------------------------------------------------------------------------
# Integration tests: Research API
# ---------------------------------------------------------------------------


async def _create_cruiser_with_research_module(client: AsyncClient, token: str) -> int:
    """Create a cruiser and install a research module. Return ship ID."""
    resp = await client.post(
        "/api/ships",
        json={"name": "Research Ship", "ship_class": "cruiser"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # Cruiser requires research - but for testing we need to work around this.
    # Actually, cruiser IS gated behind 2c_cruiser_hull research.
    # For integration tests, we'll use the starter frigate with a research module.
    # BUT research modules are 5000 m^3 and frigates have 20000 m^3 total, and
    # ~6000 m^3 is used by the starter engine. So it should fit.
    pass


async def _get_ship_id(client: AsyncClient, token: str) -> int:
    """Get the first ship ID for a user."""
    resp = await client.get(
        "/api/ships", headers={"Authorization": f"Bearer {token}"}
    )
    return resp.json()[0]["id"]


async def _install_research_module(client: AsyncClient, token: str, ship_id: int) -> int:
    """Install a research module on a ship, return module ID."""
    resp = await client.post(
        f"/api/ships/{ship_id}/modules",
        json={"module_type": "research_module", "volume": 0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _give_ship_ore(client: AsyncClient, token: str, ship_id: int, ore: float):
    """Give a ship ore by installing cargo bay and using direct DB isn't possible.
    Instead, we just need to ensure the ship has enough ore already.
    For tests, we can install a cargo bay first, but the real challenge is getting ore.
    Since we can't mine in tests without a running tick loop, we'll skip ore checks
    in the test by using a tech that requires minimal ore (Tier 1 = 500 ore).
    The starter frigate has 0 ore by default.
    """
    # We need to get ore onto the ship somehow. The simplest approach for tests
    # is to use the ship's ore field directly, but we can't easily do that through the API.
    # Instead, we'll test the error path when ore is insufficient.
    pass


class TestResearchAPI:
    async def test_start_research_insufficient_ore(self, client: AsyncClient):
        """Starting research without enough ore should fail."""
        auth = await register_user(client, "research_user1")
        ship_id = await _get_ship_id(client, auth["token"])
        mod_id = await _install_research_module(client, auth["token"], ship_id)

        resp = await client.post(
            f"/api/ships/{ship_id}/research/start",
            json={"tech_id": "1a_medium_weapons"},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 422
        assert "ore" in resp.json()["detail"].lower()

    async def test_start_research_unknown_tech(self, client: AsyncClient):
        auth = await register_user(client, "research_user2")
        ship_id = await _get_ship_id(client, auth["token"])
        await _install_research_module(client, auth["token"], ship_id)

        resp = await client.post(
            f"/api/ships/{ship_id}/research/start",
            json={"tech_id": "nonexistent_tech"},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 422

    async def test_start_research_no_research_module(self, client: AsyncClient):
        auth = await register_user(client, "research_user3")
        # Create a bare frigate (no research module) to test the error
        resp = await client.post(
            "/api/ships",
            json={"name": "Bare Frigate", "ship_class": "frigate"},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 201
        ship_id = resp.json()["id"]

        resp = await client.post(
            f"/api/ships/{ship_id}/research/start",
            json={"tech_id": "1a_medium_weapons"},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 422
        assert "research module" in resp.json()["detail"].lower()

    async def test_research_status_empty(self, client: AsyncClient):
        auth = await register_user(client, "research_user4")
        ship_id = await _get_ship_id(client, auth["token"])

        resp = await client.get(
            f"/api/ships/{ship_id}/research/status",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_tech_tree_returns_all_nodes(self, client: AsyncClient):
        auth = await register_user(client, "research_user5")

        resp = await client.get(
            "/api/research/tech-tree",
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 200
        tree = resp.json()
        assert len(tree) == len(TECH_TREE)

        # All tier 1 nodes should be "available" since they have no prerequisites
        tier1_nodes = [n for n in tree if n["tier"] == 1]
        for node in tier1_nodes:
            assert node["status"] == "available"

        # Tier 2+ nodes with prerequisites should be "locked"
        for node in tree:
            if node["prerequisites"]:
                assert node["status"] == "locked"

    async def test_cancel_no_active_research(self, client: AsyncClient):
        auth = await register_user(client, "research_user6")
        ship_id = await _get_ship_id(client, auth["token"])

        resp = await client.post(
            f"/api/ships/{ship_id}/research/cancel",
            json={},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Integration tests: Research gating
# ---------------------------------------------------------------------------


class TestResearchGating:
    async def test_cannot_install_medium_turret_without_research(self, client: AsyncClient):
        auth = await register_user(client, "gating_user1")
        ship_id = await _get_ship_id(client, auth["token"])

        resp = await client.post(
            f"/api/ships/{ship_id}/modules",
            json={"module_type": "medium_turret_kinetic", "volume": 0},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 422
        assert "research required" in resp.json()["detail"].lower()

    async def test_can_install_small_turret_without_research(self, client: AsyncClient):
        auth = await register_user(client, "gating_user2")
        ship_id = await _get_ship_id(client, auth["token"])

        resp = await client.post(
            f"/api/ships/{ship_id}/modules",
            json={"module_type": "small_turret_kinetic", "volume": 0},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 201

    async def test_cannot_create_destroyer_without_research(self, client: AsyncClient):
        auth = await register_user(client, "gating_user3")

        resp = await client.post(
            "/api/ships",
            json={"name": "My Destroyer", "ship_class": "destroyer"},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 422
        assert "research required" in resp.json()["detail"].lower()

    async def test_can_create_frigate_without_research(self, client: AsyncClient):
        auth = await register_user(client, "gating_user4")

        resp = await client.post(
            "/api/ships",
            json={"name": "My Frigate", "ship_class": "frigate"},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 201

    async def test_cannot_build_destroyer_without_research(self, client: AsyncClient):
        """Building a destroyer via factory should also be gated."""
        auth = await register_user(client, "gating_user5")
        ship_id = await _get_ship_id(client, auth["token"])

        # Install a factory large enough for destroyers (100,000 m^3)
        # Actually, frigate only has 20,000 total volume, so we can't fit a big factory.
        # But we can still test the gating error even if the factory is too small,
        # because the research check happens before the factory size check.
        # Let's install a small factory first.
        resp = await client.post(
            f"/api/ships/{ship_id}/modules",
            json={"module_type": "factory", "volume": 5000},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 201

        # Try to build a destroyer
        resp = await client.post(
            f"/api/ships/{ship_id}/build",
            json={"blueprint": "destroyer"},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 422
        assert "research required" in resp.json()["detail"].lower()

    async def test_cannot_install_strip_miner_without_research(self, client: AsyncClient):
        auth = await register_user(client, "gating_user6")
        ship_id = await _get_ship_id(client, auth["token"])

        resp = await client.post(
            f"/api/ships/{ship_id}/modules",
            json={"module_type": "strip_miner", "volume": 0},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 422
        assert "research required" in resp.json()["detail"].lower()

    async def test_can_install_research_module_without_research(self, client: AsyncClient):
        """Research module itself is not gated — it's available from the start."""
        auth = await register_user(client, "gating_user7")
        ship_id = await _get_ship_id(client, auth["token"])

        resp = await client.post(
            f"/api/ships/{ship_id}/modules",
            json={"module_type": "research_module", "volume": 0},
            headers={"Authorization": f"Bearer {auth['token']}"},
        )
        assert resp.status_code == 201
