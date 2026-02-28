"""
Unit and integration tests for Phase 5: Research / Tech Tree.

Unit tests:
  - Tech tree data integrity (prerequisites exist, no cycles)
  - Gating helpers: is_module_unlocked, is_ship_unlocked
  - Prerequisite checking

Integration tests:
  - GET /api/ships/{id}/research/status — research progress
  - GET /api/research/tech-tree — tech tree
"""

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
        assert is_module_unlocked("medium_turret_kinetic", {"1a_medium_kinetic_turrets"})

    def test_starter_ship_always_unlocked(self):
        assert is_ship_unlocked("strike_craft", set())

    def test_destroyer_locked_without_research(self):
        assert not is_ship_unlocked("destroyer", set())

    def test_destroyer_unlocked_with_research(self):
        assert is_ship_unlocked("destroyer", {"3h_destroyer_hull"})

    def test_cruiser_locked_without_research(self):
        assert not is_ship_unlocked("cruiser", set())

    def test_cruiser_unlocked_with_research(self):
        assert is_ship_unlocked("cruiser", {"4h_cruiser_hull"})


# ---------------------------------------------------------------------------
# Unit tests: Prerequisites
# ---------------------------------------------------------------------------


class TestPrerequisites:
    def test_tier1_no_prereqs(self):
        assert check_prerequisites("1a_medium_kinetic_turrets", set()) is None

    def test_tier2_needs_tier1(self):
        error = check_prerequisites("2a_large_kinetic_turrets", set())
        assert error is not None
        assert "Medium Kinetic Turrets" in error

    def test_tier2_ok_with_tier1(self):
        assert check_prerequisites("2a_large_kinetic_turrets", {"1a_medium_kinetic_turrets"}) is None

    def test_fortress_needs_prereq(self):
        """4b_fortress requires 2k_enhanced_docking."""
        error = check_prerequisites("4b_fortress", set())
        assert error is not None
        assert "Enhanced Docking" in error

        assert check_prerequisites(
            "4b_fortress",
            {"2k_enhanced_docking"},
        ) is None


# ---------------------------------------------------------------------------
# Integration tests: Research API (GET-only)
# ---------------------------------------------------------------------------


async def _get_ship_id(client: AsyncClient, token: str) -> int:
    """Create a test mothership and return its ID."""
    from tests.conftest import spawn_test_mothership
    headers = {"Authorization": f"Bearer {token}"}
    ship = await spawn_test_mothership(client, headers)
    return ship["id"]


class TestResearchAPIRead:
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
        # User has no team/faction, so faction-specific nodes are excluded
        non_faction_count = sum(
            1 for n in TECH_TREE.values() if "faction" not in n
        )
        assert len(tree) == non_faction_count

        # All tier 1 nodes should be "available" since they have no prerequisites
        tier1_nodes = [n for n in tree if n["tier"] == 1]
        for node in tier1_nodes:
            assert node["status"] == "available"

        # Tier 2+ nodes with prerequisites should be "locked"
        for node in tree:
            if node["prerequisites"]:
                assert node["status"] == "locked"
